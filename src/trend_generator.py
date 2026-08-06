#!/usr/bin/env python3
"""
Generator trend_data.json dla SONAR POKOJOWY

Buduje DZIENNY szereg czasowy liczby aktywnych ofert pokoi przez rekonstrukcję
z data/offers.json: dla każdego dnia D liczy ile ofert "żyło" tego dnia
(first_seen <= D <= last_seen; dla wciąż aktywnych granicą jest dziś).

To "indeks podaży" w stylu betonometr.pl: ile żywych ofert wynajmu pokoi w
Lublinie jest danego dnia na rynku.

Dlaczego nie scan_history.json: tam dane sięgają tylko 24.05 (od kiedy w ogóle
zapisujemy historię skanów). offers.json sięga lutego, ale rekonstrukcja sprzed
~16.05 jest niewiarygodna — to moment, w którym scraper ruszył na pełnych
obrotach (skok ~119 -> 330 w tygodniu 10-16.05). Wcześniejszy okres jest
zaniżony (survivorship: w bazie zostały tylko długo żyjące oferty z tamtych dni),
więc odcinamy go i rysujemy tylko wiarygodny zakres.
"""

import json
from datetime import datetime, date, timedelta
from pathlib import Path

from shared_utils import write_json_atomic

TITLE = "Lublin – pokoje: wynajem"
UNIT = "ofert"
DAY_MS = 86_400_000

# Pierwszy wiarygodny dzień (po zakończeniu rozpędzania scrapera w maju 2026).
# Wszystko wcześniej to artefakt zbierania danych, nie obraz rynku.
RELIABLE_START = date(2026, 5, 16)

# Dzień z liczbą reaktywacji powyżej tego progu traktujemy jako artefakt
# pipeline'u, nie realny sygnał rynkowy. Piki 432 (21.07) i 182 (12.06) to skutek
# CZĘŚCIOWEGO SCRAPE'U (blokada OLX): poprzedni skan złapał ~299 zamiast ~840 ofert
# (guard nie zablokował — 40% > próg 30%), przez co ~560 ofert błędnie oznaczono
# jako nieaktywne; następny pełny skan zobaczył je z powrotem i „zreaktywował"
# hurtem (429 ofert z identycznym znacznikiem 11:23:30 = jeden skan). Realny odpływ
# rynkowy to ~9/dzień. Naprawione u źródła auto-retry po częściowym scrape (22.07);
# same artefakty USUNIĘTE z offers.json 2026-08-06 (608 wpisów batcha, backup w
# data/backups/). Dziś ten próg NIC nie tnie (dane czyste) — zostaje jako tania
# asekuracja: taki dzień rysowałby się jako luka i nie wchodził do średniej/statystyk.
REACT_ARTIFACT_THRESHOLD = 100


def _day_ms(d: date) -> int:
    """Epoch (ms) dla południa danego dnia — punkt ląduje w środku dnia na osi."""
    return int(datetime(d.year, d.month, d.day, 12, 0).timestamp() * 1000)


def _d(iso_string: str) -> date:
    return datetime.fromisoformat(iso_string).date()


def build_spans(offers):
    """[(start_date, end_date), ...] — okres życia każdej oferty.

    end = dziś dla ofert wciąż aktywnych (last_seen może być nieco w tyle przez
    inteligentne pomijanie), inaczej last_seen.
    """
    today = max(
        (_d(o['last_seen']) for o in offers if o.get('last_seen')),
        default=date.today(),
    )
    spans = []
    for o in offers:
        if not o.get('first_seen') or not o.get('last_seen'):
            continue
        try:
            start = _d(o['first_seen'])
            end = today if o.get('active') else _d(o['last_seen'])
        except (ValueError, TypeError):
            continue
        if end < start:
            end = start
        spans.append((start, end))
    return spans, today


def build_series(offers):
    """Dzienna seria [[ms, liczba_aktywnych], ...] od RELIABLE_START do dziś."""
    spans, today = build_spans(offers)
    if not spans:
        return []
    start = max(RELIABLE_START, min(s for s, _ in spans))
    series = []
    day = start
    while day <= today:
        count = sum(1 for s, e in spans if s <= day <= e)
        series.append([_day_ms(day), count])
        day += timedelta(days=1)
    return series


def _daily_range(start, today):
    """Lista kolejnych dni [start .. today] (włącznie)."""
    days = []
    day = start
    while day <= today:
        days.append(day)
        day += timedelta(days=1)
    return days


def _flow_metric(counts, days, exclude=None):
    """Standardowy blok szeregu dziennego + średnia krocząca 7 dni.

    counts:  dict {date: liczba zdarzeń tego dnia}
    days:    uporządkowana lista kolejnych dni (oś czasu)
    exclude: zbiór dni-artefaktów (np. piki buga pętli reaktywacji). Taki dzień
             rysuje się jako LUKA (daily=None), nie wchodzi do średniej kroczącej
             ani do statystyk (total/rate/rekord) — żeby nierynkowy pik nie
             zniekształcał czytelności i trendu.

    Zwraca dict zgodny z tym, czego oczekuje front (jak w outflow):
    daily / avg / total / rate / max_day / max_ts / max_label.
    """
    exclude = exclude or set()

    daily = []
    for d in days:
        if d in exclude:
            daily.append([_day_ms(d), None])
        else:
            daily.append([_day_ms(d), counts.get(d, 0)])

    # średnia krocząca 7 dni licząca tylko dni „zdrowe" w oknie
    avg = []
    for i, d in enumerate(days):
        window = [counts.get(days[j], 0)
                  for j in range(max(0, i - 6), i + 1)
                  if days[j] not in exclude]
        if window:
            avg.append([_day_ms(d), round(sum(window) / len(window), 1)])
        else:
            avg.append([_day_ms(d), None])

    clean = [(d, counts.get(d, 0)) for d in days if d not in exclude]
    total = sum(v for _, v in clean)
    ndays = len(clean)
    mx = max((v for _, v in clean), default=0)
    # dzień rekordu: ostatnie (najświeższe) wystąpienie maksimum
    max_day_date = next((d for d, v in reversed(clean) if v == mx), None)

    return {
        'daily': daily,
        'avg': avg,
        'total': total,
        'rate': round(total / ndays, 1) if ndays else 0,
        'max_day': mx,
        'max_ts': _day_ms(max_day_date) if max_day_date else None,
        'max_label': max_day_date.strftime('%d.%m') if max_day_date else '',
    }


def build_outflow(offers):
    """Dzienny odpływ ofert (ile zniknęło danego dnia) + średnia krocząca 7 dni.

    „Zniknięcie" = oferta nieaktywna, której `last_seen` przypada danego dnia —
    to ostatni dzień, w którym żyła. Liczymy narastająco tak samo jak Indeks:
    od RELIABLE_START do dziś, dzień po dniu. Druga seria to trailing average
    z 7 dni — wygładza dzienny szum i pokazuje trend nasilenia znikania.
    """
    spans, today = build_spans(offers)
    if not spans:
        return None
    start = max(RELIABLE_START, min(s for s, _ in spans))

    dep = {}
    for o in offers:
        if o.get('active') or not o.get('last_seen'):
            continue
        try:
            d = _d(o['last_seen'])
        except (ValueError, TypeError):
            continue
        if d >= start:
            dep[d] = dep.get(d, 0) + 1

    return _flow_metric(dep, _daily_range(start, today))


def build_inflow(offers):
    """Dzienny NAPŁYW ofert — trzy powiązane metryki (każda jak outflow):

    - `new`       : nowe oferty (pierwsze pojawienie się, `first_seen` = ten dzień),
                    BEZ reaktywacji. Czysty przyrost świeżych ogłoszeń.
    - `react`     : same reaktywacje (`reactivation_dates` = ten dzień) — oferty,
                    które wróciły na rynek po wcześniejszym zniknięciu.
    - `new_react` : suma powyższych = wszystkie „pojawienia się" na rynku danego
                    dnia (świeże + wskrzeszone).

    Ten sam zakres (od RELIABLE_START do dziś) i konwencja co Indeks/odpływ.
    """
    spans, today = build_spans(offers)
    if not spans:
        return None
    start = max(RELIABLE_START, min(s for s, _ in spans))
    days = _daily_range(start, today)

    new = {}
    react = {}
    for o in offers:
        fs = o.get('first_seen')
        if fs:
            try:
                d = _d(fs)
                if d >= start:
                    new[d] = new.get(d, 0) + 1
            except (ValueError, TypeError):
                pass
        for rr in (o.get('reactivation_dates') or []):
            try:
                d = _d(rr)
                if d >= start:
                    react[d] = react.get(d, 0) + 1
            except (ValueError, TypeError):
                pass

    combined = {}
    for d in set(new) | set(react):
        combined[d] = new.get(d, 0) + react.get(d, 0)

    # Dni-artefakty reaktywacji (patrz REACT_ARTIFACT_THRESHOLD). Wykluczamy je z
    # serii reaktywacji ORAZ z napływu całkowitego (bo składnik reaktywacji tego
    # dnia jest nierynkowy). Nowe oferty (`new`) zostają nietknięte.
    react_artifacts = {d for d, v in react.items() if v > REACT_ARTIFACT_THRESHOLD}

    return {
        'new': _flow_metric(new, days),
        'react': _flow_metric(react, days, exclude=react_artifacts),
        'new_react': _flow_metric(combined, days, exclude=react_artifacts),
    }


def build_bands(offers):
    """Rozbicie dziennej liczby AKTYWNYCH ofert na dwa pasma (suma = Indeks):

    - `new`   : oferty świeże — do dnia D nie miały ani jednej reaktywacji,
    - `react` : „recykling" — oferty, które do dnia D już kiedyś wróciły z martwych
                (najwcześniejsza data w `reactivation_dates` <= D).

    Ten sam zakres i konwencja co Indeks (`build_series`): oferta żyje w [first_seen,
    end], end = dziś dla aktywnych, inaczej last_seen. Zwraca serie [[ms, v], ...]
    wyrównane dzień-w-dzień do `series`, żeby front mógł je ustawić w stack.
    """
    spans, today = build_spans(offers)
    if not spans:
        return {'new': [], 'react': []}

    # najwcześniejsza data reaktywacji per oferta (None = nigdy nie reaktywowana).
    # Bazujemy na tej samej kolejności co build_spans (pomija oferty bez dat).
    firsts = []
    for o in offers:
        if not o.get('first_seen') or not o.get('last_seen'):
            continue
        try:
            _d(o['first_seen']); _d(o['last_seen'])
        except (ValueError, TypeError):
            continue
        fr = None
        for rr in (o.get('reactivation_dates') or []):
            try:
                rd = _d(rr)
            except (ValueError, TypeError):
                continue
            if fr is None or rd < fr:
                fr = rd
        firsts.append(fr)

    start = max(RELIABLE_START, min(s for s, _ in spans))
    new_series, react_series = [], []
    day = start
    while day <= today:
        ms = _day_ms(day)
        r = 0
        t = 0
        for (s, e), fr in zip(spans, firsts):
            if s <= day <= e:
                t += 1
                if fr is not None and fr <= day:
                    r += 1
        new_series.append([ms, t - r])
        react_series.append([ms, r])
        day += timedelta(days=1)
    return {'new': new_series, 'react': react_series}


def _value_at_or_before(series, target_ms):
    best = None
    for ms, val in series:
        if ms <= target_ms:
            best = val
        else:
            break
    return best


def compute_deltas(series):
    """Zmiany 1D/1M/6M/1Y vs dziś. None gdy nie mamy tak starej historii."""
    if not series:
        return {}
    now_ms = series[-1][0]
    current = series[-1][1]
    first_ms = series[0][0]
    out = {}
    for label, days in (('1D', 1), ('1M', 30), ('6M', 182), ('1Y', 365)):
        target = now_ms - days * DAY_MS
        if target < first_ms:
            out[label] = None  # brak tak starych danych → front pokaże "—"
            continue
        past = _value_at_or_before(series, target)
        out[label] = (current - past) if past is not None else None
    return out


def generate_trend_data(base_dir: Path = None) -> bool:
    """data/offers.json → docs/trend_data.json (dzienna rekonstrukcja)."""
    if base_dir is None:
        base_dir = Path(__file__).parent.parent
    input_file = base_dir / 'data' / 'offers.json'
    output_file = base_dir / 'docs' / 'trend_data.json'

    print("🔄 Generowanie trend_data.json...")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    offers = data.get('offers', [])

    series = build_series(offers)
    if not series:
        print("⚠️  Brak danych do rekonstrukcji — pomijam trend_data.json")
        return False

    values = [val for _, val in series]
    current = values[-1]
    mx, mn = max(values), min(values)
    # MAX: pierwsze wystąpienie, MIN: ostatnie (spójnie z mockupem)
    max_ts = next(ms for ms, val in series if val == mx)
    min_ts = next(ms for ms, val in reversed(series) if val == mn)
    last_day = datetime.fromtimestamp(series[-1][0] / 1000).date()

    out = {
        'generated_at': datetime.now().astimezone().isoformat(),
        'title': TITLE,
        'metric': 'active_daily',
        'unit': UNIT,
        'reliable_start': RELIABLE_START.isoformat(),
        'current': current,
        'max': mx,
        'min': mn,
        'max_ts': max_ts,
        'min_ts': min_ts,
        'last_label': last_day.strftime('%d.%m.%Y'),
        'points': len(series),
        'deltas': compute_deltas(series),
        'series': series,
        'outflow': build_outflow(offers),
        'inflow': build_inflow(offers),
        'bands': build_bands(offers),
    }

    write_json_atomic(output_file, out)
    of = out['outflow'] or {}
    print(f"✅ trend_data.json: {len(series)} dni od {RELIABLE_START}, "
          f"teraz={current}, max={mx}, min={mn}; "
          f"odpływ: łącznie={of.get('total')}, śr={of.get('rate')}/dzień, "
          f"rekord={of.get('max_day')} ({of.get('max_label')})")
    return True


if __name__ == '__main__':
    generate_trend_data()
