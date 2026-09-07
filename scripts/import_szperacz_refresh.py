#!/usr/bin/env python3
"""
Import historii odświeżeń z repo-brata SZPERACZ → data/szperacz_refresh_backfill.json.

PO CO: nasz szereg „odświeżenia — cała baza" zaczyna się 07.09.2026, w dniu
wdrożenia parsera karty listingu. SZPERACZ skanuje tę samą kategorię OLX-a
(stancje-pokoje/lublin) i zapisuje daty podbić od kwietnia — czyli cztery
miesiące, których u nas nie ma i których nie da się odtworzyć wstecz.

DLACZEGO OSOBNA SERIA, NIE PRZEDŁUŻENIE NASZEJ: SZPERACZ skanuje 1×/dobę,
my 3×/dobę. Na wspólnych dniach (te same 10 profili firmowych, 49 dni bez
ich awarii) mediana stosunku SONAR/SZPERACZ to 1,05 — czyli mierzymy to samo
z dokładnością do 5%, ale to nadal DWA pomiary, nie jeden. Front rysuje je
jako dwie linie i tak je podpisuje.

DWA ODCINKI ICH DANYCH, różnej jakości:
  · do 09.06 — odtworzone z `refresh_history` ofert, które SZPERACZ nadal ma
    w bazie. Oferty skasowane z jego bazy nie wnoszą swoich podbić, więc ten
    odcinek jest ZANIŻONY (survivorship) i front go zakreskowuje.
  · od 10.06 — ich własny dzienny agregat `daily_counts.refreshed_count`,
    zapisywany przy każdym skanie. Zgadza się z historią ofert na 79 z 90 dni,
    a rozbieżności są wyłącznie w czerwcu i zawsze w stronę „agregat wyższy",
    co potwierdza survivorship w odcinku wcześniejszym.

REAKTYWACJI NIE IMPORTUJEMY: tam stosunek to 2,55×, nie 1,05×. Reaktywacja to
zdarzenie chwilowe (oferta znika i wraca) — przy 1 skanie na dobę powrót w tej
samej dobie jest niewidoczny. To nie ta sama wielkość zmierzona dwiema
metodami, tylko dwie różne wielkości.

UŻYCIE (skrypt jest odpalany ręcznie, nie w skanie):
    git clone --depth 1 https://github.com/Bonaventura-EW/SZPERACZ /tmp/szperacz
    python scripts/import_szperacz_refresh.py /tmp/szperacz
"""

import json
import statistics
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))

from trend_generator import collect_dates  # noqa: E402

# Pierwszy dzień, od którego bierzemy ich historię. Wcześniejsze dni (06–21.04)
# to pojedyncze zdarzenia i jeden odosobniony pik — za rzadkie, żeby coś mówiły.
BACKFILL_START = date(2026, 4, 22)
# Od tego dnia mają własny dzienny agregat; wcześniej odtwarzamy z historii ofert.
AGGREGATE_FROM = date(2026, 6, 10)
CATEGORY_KEY = 'wszystkie_pokoje'
# Ich awaria skanu profili — te dni wypadają z walidacji (ich seria kategorii
# chodziła wtedy normalnie, więc backfillu to nie dotyczy).
OUTAGE = (date(2026, 8, 11), date(2026, 8, 24))


def _iter_offers(profile):
    return (profile.get('current_listings') or []) + (profile.get('archived_listings') or [])


def _refresh_days(profile):
    """{data: liczba podbić} z `refresh_history` ofert profilu."""
    counts = {}
    for offer in _iter_offers(profile):
        for entry in offer.get('refresh_history') or []:
            day = (entry.get('refreshed_at') or '')[:10]
            if day:
                counts[day] = counts.get(day, 0) + 1
    return counts


def _validation(szperacz, base_dir):
    """Zgodność obu pipeline'ów na tych samych 10 profilach firmowych.

    Liczona przy imporcie i zapisywana w snapshocie — żeby przy następnym
    imporcie było widać, czy zgodność nie odjechała.
    """
    ours = {}
    offers = json.loads((base_dir / 'data' / 'offers.json').read_text(encoding='utf-8'))['offers']
    for offer in offers:
        if not offer.get('profile_name'):
            continue
        for day in set(collect_dates(offer, 'refresh_dates')):
            ours[day.isoformat()] = ours.get(day.isoformat(), 0) + 1

    theirs = {}
    for key, profile in szperacz['profiles'].items():
        if profile.get('is_category'):
            continue
        for day, value in _refresh_days(profile).items():
            theirs[day] = theirs.get(day, 0) + value

    common = sorted(set(ours) & set(theirs))
    clean = [d for d in common
             if d >= '2026-07-08' and not (OUTAGE[0].isoformat() <= d < OUTAGE[1].isoformat())]
    ratios = [ours[d] / theirs[d] for d in clean if theirs[d]]
    if not ratios:
        return None
    return {
        'days': len(clean),
        'ratio_median': round(statistics.median(ratios), 2),
        'sum_sonar': sum(ours[d] for d in clean),
        'sum_szperacz': sum(theirs[d] for d in clean),
        'excluded_outage': [OUTAGE[0].isoformat(), OUTAGE[1].isoformat()],
        'note': 'te same 10 profili firmowych; wykluczona awaria skanu profili po ich stronie',
    }


def main(szperacz_root, base_dir=None):
    base_dir = base_dir or ROOT
    szperacz_root = Path(szperacz_root)
    source_file = szperacz_root / 'data' / 'dashboard_data.json'
    data = json.loads(source_file.read_text(encoding='utf-8'))

    category = data['profiles'][CATEGORY_KEY]
    from_history = _refresh_days(category)
    aggregate = {row['date']: row.get('refreshed_count')
                 for row in (category.get('daily_counts') or [])
                 if row.get('refreshed_count') is not None}

    last = max(list(from_history) + list(aggregate))
    daily, day = {}, BACKFILL_START
    while day.isoformat() <= last:
        key = day.isoformat()
        # Od AGGREGATE_FROM ich własny agregat jest źródłem prawdy — historia
        # ofert bywa tam niższa o oferty skasowane z ich bazy.
        value = aggregate.get(key) if day >= AGGREGATE_FROM else from_history.get(key)
        if value is None and day >= AGGREGATE_FROM:
            value = from_history.get(key)
        if value is not None:
            daily[key] = value
        day += timedelta(days=1)

    try:
        commit = subprocess.run(['git', '-C', str(szperacz_root), 'rev-parse', 'HEAD'],
                                capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit = ''

    snapshot = {
        'source': {
            'repo': 'Bonaventura-EW/SZPERACZ',
            'commit': commit,
            'file': 'data/dashboard_data.json',
            'profile': CATEGORY_KEY,
            'listing': category.get('url', ''),
            'scan_cadence': '1/dobę (my: 3/dobę)',
            'last_scan': data.get('last_scan', ''),
            'imported_at': datetime.now().astimezone().isoformat(),
        },
        'method': {
            'do': AGGREGATE_FROM.isoformat(),
            'before': 'refresh_history ofert (survivorship — zaniżone)',
            'after': 'daily_counts.refreshed_count (ich dzienny agregat)',
        },
        'survivorship_until': (AGGREGATE_FROM - timedelta(days=1)).isoformat(),
        'validation': _validation(data, base_dir),
        'daily': daily,
    }

    out = base_dir / 'data' / 'szperacz_refresh_backfill.json'
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    val = snapshot['validation'] or {}
    print(f"✅ {out.relative_to(base_dir)}: {len(daily)} dni "
          f"({min(daily)} → {max(daily)}), {sum(daily.values())} podbić")
    print(f"   walidacja: {val.get('days')} wspólnych dni, mediana stosunku "
          f"SONAR/SZPERACZ = {val.get('ratio_median')}")
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
