#!/usr/bin/env python3
"""
Generator trend_data.json dla SONAR POKOJOWY

Buduje DZIENNY szereg czasowy liczby aktywnych ofert pokoi — "indeks podaży" w
stylu betonometr.pl: ile żywych ofert wynajmu pokoi w Lublinie jest danego dnia
na rynku.

Indeks czytamy z data/index_history.json — MIERZONEGO stanu bazy po każdym
skanie (patrz src/index_history.py). Wcześniej był REKONSTRUOWANY wstecz z
offers.json (dla dnia D: ile ofert miało first_seen <= D <= last_seen) i zawyżał
przeszłość o +27% (koniec maja) do +4% (dziś), bo oferta z przerwą w życiu ma w
bazie jeden ciągły przedział. Zawyżenie malało z wiekiem punktu, więc prawy
koniec wykresu zawsze opadał i mylił kierunek trendu. Rekonstrukcja została jako
build_series_reconstructed() — awaryjne źródło, gdy nie ma zapisanej historii.

Dlaczego nie sam scan_history.json: trzyma tylko ostatnie ~100 skanów (≈33 dni).
index_history.json rośnie bezterminowo, a jego historia 14.05–02.09.2026 jest
odtworzona ze starszych rewizji scan_history.json z gita
(scripts/backfill_index_history.py).
"""

import json
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

import index_history
from shared_utils import write_json_atomic

TITLE = "Lublin – pokoje: wynajem"
UNIT = "ofert"
DAY_MS = 86_400_000

# Pierwszy wiarygodny dzień (po zakończeniu rozpędzania scrapera w maju 2026).
# Wszystko wcześniej to artefakt zbierania danych, nie obraz rynku.
RELIABLE_START = date(2026, 5, 16)

# Reaktywacje: pierwszy dzień, od którego seria jest RZETELNA. Pole
# `reactivation_dates` nie istniało do początku lipca 2026 (starsze rewizje
# main.py mają wyłącznie licznik `reactivation_count`), a przy wdrożeniu zrobiono
# backfill po JEDNEJ dacie na ofertę — wszystkie 224 oferty z datą sprzed 01.07
# mają dokładnie jedną, choć realnie było 3-20 reaktywacji dziennie. Wcześniejszy
# odcinek to zaślepka, nie historia: wykres pokazywał tam 104 zdarzenia zamiast
# 260. Dni sprzed tej granicy rysujemy jako lukę i nie wliczamy do statystyk.
REACT_RELIABLE_START = date(2026, 7, 1)

# Ta sama asekuracja po stronie odpływu. Dzień z taką liczbą deaktywacji to skutek
# częściowego scrape'u (guard w main.py łapie większość przypadków, ale nie wszystkie),
# nie ruch na rynku — realny odpływ to ~15 ofert dziennie. Taki dzień rysuje się jako
# luka i nie wchodzi do średniej ani statystyk. Dziś nic nie tnie (rekord to 42).
OUTFLOW_ARTIFACT_THRESHOLD = 100

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
    """Epoch (ms) dla południa UTC danego dnia — punkt ląduje w środku dnia na osi.

    Kotwica jest JAWNIE w UTC, bo naiwne `datetime(...).timestamp()` bierze strefę
    maszyny: przy generowaniu lokalnie w Polsce doba ze zmianą czasu ma 23 albo 25
    godzin, a `compute_deltas` odejmuje sztywne 24 h — delta „1D" po wiosennej
    zmianie wskazywała przedwczoraj zamiast wczoraj. GitHub Actions chodzi na UTC,
    więc w produkcji wartości się nie zmieniają.
    """
    return int(datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)


def _ms_day(ms: int) -> date:
    """Odwrotność _day_ms — ta sama kotwica UTC."""
    return datetime.fromtimestamp(ms / 1000, timezone.utc).date()


def _d(iso_string: str) -> date:
    return datetime.fromisoformat(iso_string).date()


def collect_dates(offer, field):
    """Wszystkie daty z pola `field` — także te schowane w `versions[]`.

    Zmiana adresu otwiera nową wersję oferty: `_update_existing_offer` resetuje
    `refresh_dates` / `reactivation_dates` / `deactivation_dates` i chowa stare
    do `versions[]`. Czytając tylko wierzch gubiliśmy tę historię (43 reaktywacje
    i 188 odświeżeń), a szeregi czasowe robiły się wstecz coraz rzadsze.
    """
    out = []
    for raw in (offer.get(field) or []):
        try:
            out.append(_d(str(raw)))
        except (ValueError, TypeError):
            continue
    for version in (offer.get('versions') or []):
        for raw in (version.get(field) or []):
            try:
                out.append(_d(str(raw)))
            except (ValueError, TypeError):
                continue
    return sorted(out)


def build_spans(offers):
    """[(offer, [(start, end), ...]), ...] — PRZEDZIAŁY życia każdej oferty.

    Oferta może żyć na raty: zniknęła z listingu (`deactivation_dates`) i wróciła
    (`reactivation_dates`). Każda taka przerwa zamyka jeden przedział i otwiera
    następny, więc dzień w środku przerwy nie liczy się jako żywy.

    UWAGA na dane historyczne: `deactivation_dates` zapisujemy dopiero od
    03.09.2026. Oferta bez ani jednej daty deaktywacji dostaje — jak dawniej —
    jeden ciągły przedział, czyli jej dawne przerwy nadal są niewidoczne. Dlatego
    Indeks NIE jest już z tego liczony (patrz build_series); przedziały służą
    podziałowi na pasma i będą dokładne dla dni od wdrożenia w górę.

    end ostatniego przedziału = dziś dla ofert wciąż aktywnych (last_seen bywa w
    tyle przez inteligentne pomijanie), inaczej last_seen.
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
            final_end = today if o.get('active') else _d(o['last_seen'])
        except (ValueError, TypeError):
            continue
        if final_end < start:
            final_end = start

        deactivations = [d for d in collect_dates(o, 'deactivation_dates') if start <= d <= final_end]
        reactivations = collect_dates(o, 'reactivation_dates')

        intervals = []
        cursor = start
        for gap_start in deactivations:
            if gap_start < cursor:
                continue
            intervals.append((cursor, gap_start))
            back = next((r for r in reactivations if r >= gap_start), None)
            if back is None or back > final_end:
                cursor = None
                break
            cursor = back
        if cursor is not None:
            intervals.append((cursor, final_end))
        elif o.get('active') and intervals:
            # Oferta jest AKTYWNA, ale po ostatniej deaktywacji nie ma daty powrotu
            # (niespójny rekord). Skoro żyje dziś, domykamy ostatni przedział do końca
            # zamiast chować ją z wykresu na dobre.
            last_start, last_end = intervals[-1]
            intervals[-1] = (last_start, final_end)
        spans.append((o, intervals))
    return spans, today


def _alive(intervals, day):
    """Czy oferta żyła danego dnia. Przedziały mogą się stykać (deaktywacja i
    powrót tego samego dnia) — liczy się raz, `any` nie sumuje."""
    return any(s <= day <= e for s, e in intervals)


def measured_series(base_dir=None):
    """Zmierzone dni Indeksu w zakresie, który faktycznie rysujemy.

    Jedno miejsce, w którym pytamy o pomiar — build_series i etykieta
    `index_source` MUSZĄ pytać tak samo. Wcześniej etykieta pytała o pełny plik,
    więc historia złożona wyłącznie z dni sprzed RELIABLE_START dawała wykres
    z rekonstrukcji podpisany jako „measured".
    """
    return index_history.daily_series(start=RELIABLE_START, base_dir=base_dir)


def build_series(offers, base_dir=None):
    """Dzienna seria [[ms, aktywne|None], ...] — MIERZONY stan bazy.

    Źródłem jest data/index_history.json: ile ofert miało `active=true` po skanie
    danego dnia. `None` = dzień, w którym nie odbył się ani jeden skan (awaria
    Actions) — front rysuje lukę zamiast zmyślonego zera.

    Gdy pliku nie ma (świeży klon, repo-brat bez historii), spadamy na starą
    rekonstrukcję — z jej znanym zawyżeniem przeszłości.
    """
    measured = measured_series(base_dir)
    if measured:
        return [[_day_ms(day), value] for day, value in measured]
    return build_series_reconstructed(offers)


def build_series_reconstructed(offers):
    """AWARYJNE źródło Indeksu: rekonstrukcja wsteczna z offers.json.

    Zawyża przeszłość (przerwy w życiu ofert sprzed 03.09.2026 są niewidoczne),
    a zawyżenie maleje z wiekiem punktu, więc prawy koniec sztucznie opada.
    Używane tylko, gdy nie ma data/index_history.json.
    """
    spans, today = build_spans(offers)
    if not spans:
        return []
    starts = [iv[0][0] for _, iv in spans if iv]
    if not starts:
        return []
    start = max(RELIABLE_START, min(starts))
    series = []
    day = start
    while day <= today:
        series.append([_day_ms(day), sum(1 for _, iv in spans if _alive(iv, day))])
        day += timedelta(days=1)
    return series


def _unscanned_days(days, series):
    """Dni, w których nie odbył się ANI JEDEN skan (Indeks ma tam None).

    Przepływy muszą je traktować jak lukę, nie jak zero: w dniu bez skanu nikt nie
    mógł zobaczyć ani zniknięcia oferty, ani nowej. Zero z takiego dnia wchodziło
    do średniej 7-dniowej i do mianownika `rate`, więc awaria Actions zaniżałaby
    odpływ i napływ jeszcze przez tydzień po sobie.
    """
    if not series:
        return set()
    return {day for day, (_, value) in zip(days, series) if value is None}


def _axis(offers, series=None):
    """Wspólna oś dni dla wszystkich szeregów: dokładnie te dni, które są na
    Indeksie. Dzięki temu odpływ, napływ i pasma stoją w tych samych słupkach."""
    if series:
        days = [_ms_day(ms) for ms, _ in series]
        return days, days[-1]
    spans, today = build_spans(offers)
    starts = [iv[0][0] for _, iv in spans if iv]
    if not starts:
        return [], today
    return _daily_range(max(RELIABLE_START, min(starts)), today), today


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


def build_outflow(offers, series=None):
    """Dzienny odpływ ofert (ile zniknęło danego dnia) + średnia krocząca 7 dni.

    Zniknięcie bierzemy z `deactivation_dates` — KAŻDE wypadnięcie z listingu,
    także to, po którym oferta wróciła. Oferta bez tych dat (wszystko sprzed
    03.09.2026) ma tylko jeden ślad: `last_seen`, czyli WYŁĄCZNIE ostatnią
    śmierć. Dlatego historyczny odpływ jest zaniżony — bilans się nie spinał:
    napływ 3174 − odpływ 1590 = +1584, a Indeks urósł w tym czasie o +480;
    różnica ≈ 1131 reaktywacji, których poprzedzające zgony nigdzie nie trafiły.
    Od wdrożenia `deactivation_dates` szereg domyka się sam.

    Druga seria to trailing average z 7 dni — wygładza dzienny szum.
    """
    days, _ = _axis(offers, series)
    if not days:
        return None
    start = days[0]

    dep = {}
    for o in offers:
        gone = collect_dates(o, 'deactivation_dates')
        if not gone and not o.get('active') and o.get('last_seen'):
            try:
                gone = [_d(o['last_seen'])]
            except (ValueError, TypeError):
                gone = []
        for d in gone:
            if d >= start:
                dep[d] = dep.get(d, 0) + 1

    artifacts = {d for d, v in dep.items() if v > OUTFLOW_ARTIFACT_THRESHOLD}
    return _flow_metric(dep, days, exclude=artifacts | _unscanned_days(days, series))


def build_inflow(offers, series=None):
    """Dzienny NAPŁYW ofert — trzy powiązane metryki (każda jak outflow):

    - `new`       : nowe oferty (pierwsze pojawienie się, `first_seen` = ten dzień),
                    BEZ reaktywacji. Czysty przyrost świeżych ogłoszeń.
    - `react`     : same reaktywacje (`reactivation_dates` = ten dzień) — oferty,
                    które wróciły na rynek po wcześniejszym zniknięciu.
    - `new_react` : suma powyższych = wszystkie „pojawienia się" na rynku danego
                    dnia (świeże + wskrzeszone).

    Ten sam zakres (od RELIABLE_START do dziś) i konwencja co Indeks/odpływ.
    Serie z reaktywacjami zaczynają się dopiero od REACT_RELIABLE_START — patrz
    komentarz przy tej stałej.
    """
    days, _ = _axis(offers, series)
    if not days:
        return None
    start = days[0]

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
        for d in collect_dates(o, 'reactivation_dates'):
            if d >= start:
                react[d] = react.get(d, 0) + 1

    combined = {}
    for d in set(new) | set(react):
        combined[d] = new.get(d, 0) + react.get(d, 0)

    # Dni-artefakty reaktywacji (patrz REACT_ARTIFACT_THRESHOLD) + odcinek sprzed
    # REACT_RELIABLE_START. Wykluczamy je z serii reaktywacji ORAZ z napływu
    # całkowitego (bo składnik reaktywacji tego dnia jest nierzetelny). Nowe
    # oferty (`new`) zostają nietknięte — ta seria trzyma się realiów (1879 wobec
    # 1894 zapisanych w historii skanów).
    unscanned = _unscanned_days(days, series)
    unreliable = {d for d in days if d < REACT_RELIABLE_START}
    unreliable |= {d for d, v in react.items() if v > REACT_ARTIFACT_THRESHOLD}
    unreliable |= unscanned

    react_metric = _flow_metric(react, days, exclude=unreliable)
    combined_metric = _flow_metric(combined, days, exclude=unreliable)
    for metric in (react_metric, combined_metric):
        metric['reliable_start'] = REACT_RELIABLE_START.isoformat()
        metric['reliable_start_ms'] = _day_ms(REACT_RELIABLE_START)

    return {
        'new': _flow_metric(new, days, exclude=unscanned),
        'react': react_metric,
        'new_react': combined_metric,
    }


def build_bands(offers, series=None):
    """Rozbicie dziennej liczby AKTYWNYCH ofert na dwa pasma (suma = Indeks):

    - `new`   : oferty świeże — do dnia D nie miały ani jednej reaktywacji,
    - `react` : „recykling" — oferty, które do dnia D już kiedyś wróciły z martwych
                (najwcześniejsza data w `reactivation_dates` <= D).

    Metoda: UDZIAŁ pasm liczymy z rekonstrukcji przedziałów życia (build_spans),
    a potem nakładamy go na MIERZONY Indeks, żeby suma pasm dalej równała się
    linii Indeksu. Same liczby z rekonstrukcji nie mogą tu wejść — zawyżają
    przeszłość o kilkanaście procent i stos wystawałby ponad linię.

    Czego ten podział jeszcze nie widzi: oferta, która w dniu D była martwa i
    wróciła później, jest w rekonstrukcji liczona jako żywa i trafia do pasma
    „świeże" (jej pierwsza reaktywacja jest PO D). Recykling jest więc zaniżony —
    dziś co najmniej o 65 aktywnych ofert, które mają `reactivation_count > 0`, a
    zerową albo skróconą listę dat. Domknie się to samo, gdy przybędzie
    `deactivation_dates` (od 03.09.2026) i przedziały przestaną kleić przerwy.
    """
    spans, _ = build_spans(offers)
    days, _ = _axis(offers, series)
    if not spans or not days:
        return {'new': [], 'react': []}

    first_reactivation = []
    for offer, intervals in spans:
        dates = collect_dates(offer, 'reactivation_dates')
        first_reactivation.append((intervals, dates[0] if dates else None))

    measured = {ms: value for ms, value in (series or [])}

    new_series, react_series = [], []
    for day in days:
        ms = _day_ms(day)
        total = recycled = 0
        for intervals, first in first_reactivation:
            if _alive(intervals, day):
                total += 1
                if first is not None and first <= day:
                    recycled += 1
        index_value = measured.get(ms, total if not measured else None)
        if index_value is None:
            new_series.append([ms, None])
            react_series.append([ms, None])
            continue
        scaled = round(index_value * recycled / total) if total else 0
        new_series.append([ms, index_value - scaled])
        react_series.append([ms, scaled])
    return {'new': new_series, 'react': react_series}


def load_scan_days(base_dir: Path) -> set:
    """Dni z ZAKOŃCZONYM skanem, wg data/scan_history.json (źródło prawdy o skanach).

    Historia trzyma ostatnie ~100 skanów (≈33 dni przy 3 skanach dziennie), więc
    starsze dni dobiera _scanned_days z `last_seen` ofert. Brak pliku = pusty zbiór.
    """
    path = base_dir / 'data' / 'scan_history.json'
    days = set()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            history = json.load(f)
    except (OSError, json.JSONDecodeError):
        return days
    if isinstance(history, dict):
        history = history.get('scans', [])
    for scan in history or []:
        if scan.get('status') not in ('completed', 'warning'):
            continue
        ts = scan.get('timestamp')
        if not ts:
            continue
        try:
            days.add(_d(ts))
        except (ValueError, TypeError):
            continue
    return days


def _scanned_days(offers):
    """Dni, w których scan REALNIE zebrał dane (jakakolwiek oferta ma tam last_seen).

    Dzień bez skanu (awaria Actions, blokada OLX) miałby zero promowanych i
    rysowałby się jak realne załamanie metryki. Takie dni oznaczamy jako lukę.
    Uzupełnienie dla dni starszych niż okno scan_history.json.
    """
    days = set()
    for o in offers:
        if not o.get('last_seen'):
            continue
        try:
            days.add(_d(o['last_seen']))
        except (ValueError, TypeError):
            continue
    return days


def build_promoted(offers, series, scan_days=None, base_dir=None):
    """Dzienna liczba ofert PROMOWANYCH (płatne wyróżnienie na listingu OLX).

    Źródło: `promoted_dates` w offers.json — dni, w których scraper zobaczył
    ofertę jako wyróżnioną (main._track_promoted, max 1 wpis/dzień). To metryka
    STANU (ile ofert jest promowanych danego dnia), nie przepływu, więc z bloku
    _flow_metric front używa `daily`/`avg`/`rate`/`max_day` — `total` (suma po
    dniach) nie ma tu sensu i nie jest pokazywane.

    Historia zaczyna się w dniu wdrożenia detekcji — wyróżnienia NIE DA SIĘ
    odtworzyć wstecz (to stan chwilowy na listingu, nie ślad w ofercie), więc
    seria startuje od pierwszego dnia z danymi, nie od RELIABLE_START.

    Druga seria to udział promowanych w rynku (% aktywnych ofert danego dnia),
    liczony na tym samym mianowniku co Indeks (`series`).
    """
    counts = {}
    for o in offers:
        for pd in (o.get('promoted_dates') or []):
            try:
                d = date.fromisoformat(str(pd)[:10])
            except (ValueError, TypeError):
                continue
            counts[d] = counts.get(d, 0) + 1

    if not counts:
        return None

    _, today = build_spans(offers)
    start = min(counts)
    days = _daily_range(start, max(today, max(counts)))

    # Dzień liczy się jako zeskanowany, gdy: zapisał się w index_history (najpewniejsze
    # źródło — wpis powstaje przy każdym skanie), jest w oknie scan_history, jakaś oferta
    # ma tam last_seen, albo widzieliśmy tego dnia promowaną ofertę. Reszta = luka
    # (brak skanu), żeby awaria Actions nie wyglądała jak zerowe promowanie.
    recorded = {day for day, value in index_history.daily_series(base_dir=base_dir) if value}
    scanned = recorded | set(scan_days or set()) | _scanned_days(offers) | set(counts)
    missing = {d for d in days if d not in scanned}

    metric = _flow_metric(counts, days, exclude=missing)

    active_by_ms = {ms: val for ms, val in (series or []) if val}
    share = []
    for d in days:
        ms = _day_ms(d)
        active = active_by_ms.get(ms)
        if d in missing or not active:
            share.append([ms, None])
        else:
            share.append([ms, round(100 * counts.get(d, 0) / active, 1)])

    last_day = next((d for d in reversed(days) if d not in missing), None)
    current = counts.get(last_day, 0) if last_day else None
    current_share = None
    if last_day:
        active = active_by_ms.get(_day_ms(last_day))
        if active:
            current_share = round(100 * counts.get(last_day, 0) / active, 1)

    metric.pop('total', None)
    metric.update({
        'share': share,
        'current': current,
        'current_share': current_share,
        'start': start.isoformat(),
        'start_label': start.strftime('%d.%m.%Y'),
        'days': len(days),
    })
    return metric


def _value_at_or_before(series, target_ms):
    """Ostatni ZMIERZONY odczyt nie później niż target_ms. Dni bez skanu (None)
    przeskakujemy — inaczej awaria Actions kasowałaby porównanie."""
    best = None
    for ms, val in series:
        if ms > target_ms:
            break
        if val is not None:
            best = val
    return best


def compute_deltas(series):
    """Zmiany 1D/1M/6M/1Y vs dziś. None gdy nie mamy tak starej historii."""
    measured = [(ms, val) for ms, val in (series or []) if val is not None]
    if not measured:
        return {}
    now_ms, current = measured[-1]
    first_ms = measured[0][0]
    out = {}
    for label, days in (('1D', 1), ('1M', 30), ('6M', 182), ('1Y', 365)):
        target = now_ms - days * DAY_MS
        if target < first_ms:
            out[label] = None  # brak tak starych danych → front pokaże "—"
            continue
        past = _value_at_or_before(measured, target)
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

    series = build_series(offers, base_dir)
    measured = [(ms, val) for ms, val in series if val is not None]
    if not measured:
        print("⚠️  Brak danych do Indeksu — pomijam trend_data.json")
        return False
    index_source = 'measured' if measured_series(base_dir) else 'reconstructed' 

    values = [val for _, val in measured]
    current = values[-1]
    mx, mn = max(values), min(values)
    # MAX: pierwsze wystąpienie, MIN: ostatnie (spójnie z mockupem)
    max_ts = next(ms for ms, val in measured if val == mx)
    min_ts = next(ms for ms, val in reversed(measured) if val == mn)
    last_day = _ms_day(measured[-1][0])

    out = {
        'generated_at': datetime.now().astimezone().isoformat(),
        'title': TITLE,
        'metric': 'active_daily',
        'unit': UNIT,
        'reliable_start': RELIABLE_START.isoformat(),
        # 'measured' = zapisany stan bazy (data/index_history.json),
        # 'reconstructed' = awaryjna rekonstrukcja z offers.json (zawyża przeszłość)
        'index_source': index_source,
        'current': current,
        'max': mx,
        'min': mn,
        'max_ts': max_ts,
        'min_ts': min_ts,
        'last_label': last_day.strftime('%d.%m.%Y'),
        'points': len(series),
        'measured_points': len(measured),
        'deltas': compute_deltas(series),
        'series': series,
        'outflow': build_outflow(offers, series),
        'inflow': build_inflow(offers, series),
        'bands': build_bands(offers, series),
        'promoted': build_promoted(offers, series, load_scan_days(base_dir), base_dir),
    }

    write_json_atomic(output_file, out)
    of = out['outflow'] or {}
    gaps = len(series) - len(measured)
    print(f"✅ trend_data.json: {len(series)} dni od {RELIABLE_START} "
          f"({index_source}, luk bez skanu: {gaps}), "
          f"teraz={current}, max={mx}, min={mn}; "
          f"odpływ: łącznie={of.get('total')}, śr={of.get('rate')}/dzień, "
          f"rekord={of.get('max_day')} ({of.get('max_label')})")
    pr = out['promoted']
    if pr:
        print(f"   ⭐ promowane: teraz={pr.get('current')} ({pr.get('current_share')}% rynku), "
              f"śr={pr.get('rate')}/dzień, rekord={pr.get('max_day')} ({pr.get('max_label')}), "
              f"historia od {pr.get('start_label')}")
    else:
        print("   ⭐ promowane: brak danych (metryka zbiera się od pierwszego skanu po wdrożeniu)")
    return True


if __name__ == '__main__':
    generate_trend_data()
