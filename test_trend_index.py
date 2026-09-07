#!/usr/bin/env python3
"""
Test Indeksu podaży (trend.html, pierwszy wykres) i szeregów pochodnych.

Pilnuje trzech rzeczy, które w 09.2026 były zepsute:
1. Indeks bierze się z ZAPISANEGO stanu bazy (data/index_history.json), a nie
   z rekonstrukcji wstecznej — ta zawyżała przeszłość o +27% i odwracała trend.
2. Przedziały życia oferty rozpoznają przerwę (deaktywacja → reaktywacja), więc
   dzień w środku przerwy nie liczy się jako żywy.
3. Pasma „nowe / recykling" sumują się DOKŁADNIE do linii Indeksu.
"""

import json
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

import index_history
import trend_generator as tg

FAILED = []


def check(label, condition, detail=''):
    print(f"   {'✅' if condition else '❌'} {label}" + (f" — {detail}" if detail else ''))
    if not condition:
        FAILED.append(label)


def iso(d, hour=12):
    return datetime(d.year, d.month, d.day, hour).isoformat()


def test_intervals():
    print("\n📆 Test 1: przedziały życia rozpoznają przerwę")
    offers = [{
        'id': 'z-przerwa', 'first_seen': iso(date(2026, 6, 1)), 'last_seen': iso(date(2026, 6, 30)),
        'active': True,
        'deactivation_dates': [iso(date(2026, 6, 10))],
        'reactivation_dates': [iso(date(2026, 6, 20))],
    }, {
        'id': 'ciagla', 'first_seen': iso(date(2026, 6, 1)), 'last_seen': iso(date(2026, 6, 30)),
        'active': True,
    }]
    spans, _ = tg.build_spans(offers)
    intervals = dict((o['id'], iv) for o, iv in spans)
    check('oferta z przerwą ma dwa przedziały', len(intervals['z-przerwa']) == 2,
          str(intervals['z-przerwa']))
    check('żyje 5.06 (przed przerwą)', tg._alive(intervals['z-przerwa'], date(2026, 6, 5)))
    check('NIE żyje 15.06 (w przerwie)', not tg._alive(intervals['z-przerwa'], date(2026, 6, 15)))
    check('żyje 25.06 (po powrocie)', tg._alive(intervals['z-przerwa'], date(2026, 6, 25)))
    check('oferta bez przerw ma jeden przedział', len(intervals['ciagla']) == 1)
    check('oferta bez przerw żyje 15.06', tg._alive(intervals['ciagla'], date(2026, 6, 15)))

    # deaktywacja i powrót tego samego dnia = oferta żyła tego dnia, liczona RAZ
    same_day = [{
        'id': 'tam-i-z-powrotem', 'first_seen': iso(date(2026, 6, 1)), 'last_seen': iso(date(2026, 6, 30)),
        'active': True,
        'deactivation_dates': [iso(date(2026, 6, 10), 9)],
        'reactivation_dates': [iso(date(2026, 6, 10), 15)],
    }]
    (_, iv), = tg.build_spans(same_day)[0]
    check('powrót tego samego dnia — dzień liczy się jako żywy', tg._alive(iv, date(2026, 6, 10)))


def test_index_history_store():
    print("\n💾 Test 2: magazyn dziennego stanu bazy")
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / 'data').mkdir()
        index_history.record(500, iso(date(2026, 8, 1), 9), base_dir=base)
        index_history.record(300, iso(date(2026, 8, 1), 15), base_dir=base)   # skan częściowy
        index_history.record(520, iso(date(2026, 8, 3), 9), base_dir=base)    # 02.08 bez skanu

        days = dict(index_history.daily_series(base_dir=base))
        check('skan częściowy nie obniża dnia', days[date(2026, 8, 1)] == 500, str(days))
        check('dzień bez skanu = None', days[date(2026, 8, 2)] is None)
        check('trzy kolejne dni na osi', len(days) == 3)
        entry = index_history.load(base_dir=base)['days']['2026-08-01']
        check('liczy wszystkie odczyty dnia', entry['scans'] == 2, str(entry))


def test_series_from_measurement():
    print("\n📈 Test 3: Indeks czyta pomiar, nie rekonstrukcję")
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / 'data').mkdir()
        # rekonstrukcja z tych ofert dałaby 2 aktywne w każdym dniu
        offers = [{'id': f'o{i}', 'first_seen': iso(date(2026, 5, 16)),
                   'last_seen': iso(date(2026, 5, 18)), 'active': True} for i in range(2)]
        for day, active in ((date(2026, 5, 16), 111), (date(2026, 5, 17), 222)):
            index_history.record(active, iso(day), base_dir=base)

        series = tg.build_series(offers, base_dir=base)
        check('bierze zapisane wartości', [v for _, v in series] == [111, 222], str(series))

        empty = Path(tmp) / 'puste'
        (empty / 'data').mkdir(parents=True)
        fallback = tg.build_series(offers, base_dir=empty)
        check('bez pliku spada na rekonstrukcję', [v for _, v in fallback] == [2, 2, 2], str(fallback))


def test_live_data():
    print("\n🗂️  Test 4: wygenerowany docs/trend_data.json")
    path = Path(__file__).parent / 'docs' / 'trend_data.json'
    if not path.exists():
        check('trend_data.json istnieje', False, 'uruchom src/trend_generator.py')
        return
    d = json.loads(path.read_text(encoding='utf-8'))
    series = d['series']
    check('Indeks z pomiaru', d.get('index_source') == 'measured', str(d.get('index_source')))

    bands = d.get('bands') or {}
    mismatch = [i for i, (n, r, s) in enumerate(zip(bands.get('new', []), bands.get('react', []), series))
                if (s[1] is None) != (n[1] is None) or (s[1] is not None and n[1] + r[1] != s[1])]
    check('pasma sumują się do Indeksu', not mismatch, f'{len(mismatch)} dni się nie zgadza')

    react = (d.get('inflow') or {}).get('react') or {}
    start = react.get('reliable_start')
    check('reaktywacje mają granicę rzetelności', start == tg.REACT_RELIABLE_START.isoformat(), str(start))
    early = [v for ms, v in react.get('daily', [])
             if tg._ms_day(ms) < tg.REACT_RELIABLE_START]
    check('odcinek sprzed granicy to luka', early and all(v is None for v in early),
          f'{len(early)} dni')

    values = [v for _, v in series if v is not None]
    check('seria niepusta', bool(values), f'{len(values)} punktów')
    check('brak wartości ujemnych', all(v >= 0 for v in values))


def test_corrupted_history():
    print("\n🛡️  Test 5: uszkodzony index_history.json nie kasuje historii")
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / 'data').mkdir()
        for day, active in ((date(2026, 8, 1), 500), (date(2026, 8, 2), 510)):
            index_history.record(active, iso(day), base_dir=base)
        path = base / 'data' / 'index_history.json'
        path.write_text('{"days": {"2026-08-01": {"acti', encoding='utf-8')

        index_history.record(520, iso(date(2026, 8, 3)), base_dir=base)
        check('record() nie nadpisał uszkodzonego pliku',
              path.read_text(encoding='utf-8').startswith('{"days": {"2026-08-01": {"acti'))

        try:
            index_history.save({'days': {}}, base_dir=base)
            refused = False
        except index_history.IndexHistoryError:
            refused = True
        check('save() odmawia zastąpienia historii pustką', refused)


def test_unscanned_day_is_a_gap():
    print("\n🕳️  Test 6: dzień bez skanu to luka także w przepływach")
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / 'data').mkdir()
        for day, active in ((16, 700), (17, 705), (19, 712), (20, 715)):   # 18.05 bez skanu
            index_history.record(active, iso(date(2026, 5, day)), base_dir=base)
        offers = [{'id': f'o{i}', 'first_seen': iso(date(2026, 5, 16)),
                   'last_seen': iso(date(2026, 5, 17)), 'active': False,
                   'deactivation_dates': [iso(date(2026, 5, 17))]} for i in range(4)]

        series = tg.build_series(offers, base_dir=base)
        check('Indeks ma lukę 18.05', series[2][1] is None)
        out = tg.build_outflow(offers, series)
        inflow = tg.build_inflow(offers, series)
        check('odpływ ma tam lukę, nie zero', out['daily'][2][1] is None, str(out['daily']))
        check('napływ ma tam lukę, nie zero', inflow['new']['daily'][2][1] is None)
        check('dzień bez skanu poza mianownikiem rate', out['rate'] == 1.0,
              f"rate={out['rate']} (4 zniknięcia / 4 zmierzone dni)")


def test_index_source_label():
    print("\n🏷️  Test 7: etykieta index_source zgodna z tym, co narysowano")
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / 'data').mkdir()
        index_history.record(100, iso(date(2026, 4, 1)), base_dir=base)   # przed RELIABLE_START
        offers = [{'id': 'a', 'first_seen': iso(date(2026, 5, 16)),
                   'last_seen': iso(date(2026, 5, 18)), 'active': True}]
        series = tg.build_series(offers, base_dir=base)
        check('seria z rekonstrukcji (pomiar poza zakresem)', [v for _, v in series] == [1, 1, 1])
        check('etykieta mówi reconstructed', not tg.measured_series(base))


def test_promoted_survives_address_change():
    print("\n⭐ Test 9: wyróżnienia przeżywają zmianę adresu")
    offer = {
        'id': 'po-przeprowadzce', 'first_seen': iso(date(2026, 8, 20)),
        'last_seen': iso(date(2026, 9, 3)), 'active': True,
        # stan po resecie, który robi _update_existing_offer przy zmianie adresu
        'promoted_dates': ['2026-09-01'],
        'versions': [{'promoted_dates': ['2026-08-28', '2026-08-29', '2026-09-01']}],
    }
    days = sorted(str(d) for d in set(tg.collect_dates(offer, 'promoted_dates')))
    check('dni sprzed przeprowadzki odzyskane',
          days == ['2026-08-28', '2026-08-29', '2026-09-01'], str(days))
    check('dzień obecny w obu miejscach liczy się raz', days.count('2026-09-01') == 1)

    series = [[tg._day_ms(date(2026, 8, 28) + timedelta(days=i)), 800] for i in range(7)]
    promoted = tg.build_promoted([offer], series, scan_days={date(2026, 8, 28) + timedelta(days=i)
                                                            for i in range(7)})
    counted = {tg._ms_day(ms): v for ms, v in promoted['daily']}
    check('wykres liczy ofertę raz dziennie',
          [counted.get(date(2026, 8, d)) for d in (28, 29, 30)] == [1, 1, 0], str(counted))


def test_refreshes_two_series():
    print("\n🔄 Test 10: odświeżenia — dwa szeregi o różnych początkach")
    # Szereg firmowy sięga sprzed granicy rozruchu trackera, żeby sprawdzić
    # zakreskowanie; prywatna oferta ma datę sprzed wdrożenia parsera karty
    # (backfill) i po nim (realny pomiar).
    offers = [
        {'id': 'firmowa', 'profile_name': 'Poqui', 'active': True,
         'first_seen': iso(date(2026, 6, 25)), 'last_seen': iso(date(2026, 9, 7)),
         'refresh_dates': ['2026-06-25', '2026-09-05', '2026-09-07']},
        {'id': 'prywatna', 'active': True,
         'first_seen': iso(date(2026, 8, 1)), 'last_seen': iso(date(2026, 9, 7)),
         'refresh_dates': ['2026-09-05', '2026-09-07']},
        # oferta po zmianie adresu: świeże daty na wierzchu, starsze w versions[]
        {'id': 'po-przeprowadzce', 'profile_name': 'Artymiuk', 'active': True,
         'first_seen': iso(date(2026, 8, 1)), 'last_seen': iso(date(2026, 9, 7)),
         'refresh_dates': ['2026-09-07'],
         'versions': [{'refresh_dates': ['2026-06-25']}]},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / 'data').mkdir()
        rf = tg.build_refreshes(offers, scan_days=set(), base_dir=base)

    firm, whole = rf['firm'], rf['all']
    check('szereg firmowy startuje od pierwszego zapisu',
          firm['start'] == '2026-06-25', firm['start'])
    check('szereg całej bazy startuje od wdrożenia parsera karty',
          whole['start'] == tg.REFRESH_ALL_RELIABLE_START.isoformat(), whole['start'])
    # REGRESJA: backfill ofert prywatnych nie może wejść na wykres całej bazy
    before = [v for ms, v in whole['daily'] if tg._ms_day(ms) < tg.REFRESH_ALL_RELIABLE_START]
    check('dni sprzed granicy w ogóle nie ma w szeregu całej bazy', before == [], str(before))

    firm_by_day = {tg._ms_day(ms): v for ms, v in firm['daily']}
    check('data z versions[] policzona (zmiana adresu nie gubi historii)',
          firm_by_day[date(2026, 6, 25)] == 2, str(firm_by_day[date(2026, 6, 25)]))
    check('oferta prywatna nie wchodzi do szeregu firmowego',
          firm_by_day[date(2026, 9, 5)] == 1, str(firm_by_day[date(2026, 9, 5)]))

    whole_by_day = {tg._ms_day(ms): v for ms, v in whole['daily']}
    check('07.09 liczy wszystkie trzy oferty', whole_by_day[date(2026, 9, 7)] == 3,
          str(whole_by_day[date(2026, 9, 7)]))
    check('szereg firmowy niesie granicę rozruchu do zakreskowania',
          firm.get('reliable_start_ms') == tg._day_ms(tg.REFRESH_FIRM_RELIABLE_START),
          str(firm.get('reliable_start_ms')))
    check('szereg całej bazy nie ma czego zakreskowywać',
          'reliable_start_ms' not in whole)


def test_refresh_unscanned_day_is_a_gap():
    print("\n🕳️  Test 11: doba bez skanu nie jest zerem podbić")
    offers = [{'id': 'firmowa', 'profile_name': 'Poqui', 'active': True,
               'first_seen': iso(date(2026, 8, 20)), 'last_seen': iso(date(2026, 8, 21)),
               'refresh_dates': ['2026-08-20', '2026-08-24']}]
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / 'data').mkdir()
        for day in (20, 21, 23):                       # 22.08 = awaria Actions, brak skanu
            index_history.record(700, iso(date(2026, 8, day)), base_dir=base)
        firm = tg.build_refreshes(offers, scan_days=set(), base_dir=base)['firm']

    by_day = {tg._ms_day(ms): v for ms, v in firm['daily']}
    check('dzień bez skanu to luka (None)', by_day[date(2026, 8, 22)] is None, str(by_day))
    check('dzień zeskanowany bez podbić to zero', by_day[date(2026, 8, 21)] == 0, str(by_day))
    check('luka nie wchodzi do mianownika rate', firm['rate'] == round(2 / 4, 1),
          f"rate={firm['rate']} (2 podbicia / 4 zmierzone dni)")


def test_szperacz_backfill():
    print("\n🔗 Test 12: backfill ze SZPERACZA jest OSOBNĄ serią")
    offers = [{'id': 'a', 'active': True,
               'first_seen': iso(date(2026, 9, 7)), 'last_seen': iso(date(2026, 9, 7)),
               'refresh_dates': ['2026-09-07']}]
    snapshot = {
        'source': {'repo': 'Bonaventura-EW/SZPERACZ', 'listing': 'https://www.olx.pl/x/'},
        'survivorship_until': '2026-06-09',
        'validation': {'days': 49, 'ratio_median': 1.05},
        'daily': {'2026-04-22': 12, '2026-06-09': 30, '2026-06-10': 44, '2026-09-06': 50},
    }
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / 'data').mkdir()
        (base / 'data' / 'szperacz_refresh_backfill.json').write_text(
            json.dumps(snapshot), encoding='utf-8')
        rf = tg.build_refreshes(offers, scan_days=set(), base_dir=base)
        whole = rf['all']

        check('seria brata dołączona osobno', len(whole.get('backfill') or []) == 4,
              str(len(whole.get('backfill') or [])))
        # REGRESJA: ich pomiar nie może wsiąknąć w nasz szereg ani w nasze statystyki
        ours = {tg._ms_day(ms): v for ms, v in whole['daily']}
        check('nasz szereg nadal zaczyna się od granicy', min(ours) == tg.REFRESH_ALL_RELIABLE_START,
              str(min(ours)))
        check('nasz szereg liczy tylko nasze zdarzenia', ours[date(2026, 9, 7)] == 1)
        check('ich dane nie wchodzą do naszej sumy', whole['total'] == 1, str(whole['total']))

        meta = whole['backfill_meta']
        check('meta niesie źródło i etykietę',
              meta['source'] == 'Bonaventura-EW/SZPERACZ' and 'SZPERACZ' in meta['label'], str(meta['label']))
        check('meta niesie granicę survivorship do zakreskowania',
              meta.get('survivorship_end_ms') == tg._day_ms(date(2026, 6, 10)),
              str(meta.get('survivorship_end_ms')))
        check('meta niesie wynik walidacji', (meta.get('validation') or {}).get('ratio_median') == 1.05)

    # Bez snapshotu wykres ma po prostu naszą serię — nie wywala generatora
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / 'data').mkdir()
        whole = tg.build_refreshes(offers, scan_days=set(), base_dir=base)['all']
        check('brak snapshotu = brak serii brata, bez błędu', 'backfill' not in whole)


def test_day_anchor_is_utc():
    print("\n🌍 Test 8: kotwica dnia niezależna od strefy czasowej")
    days = [date(2027, 3, 24) + timedelta(days=i) for i in range(5)]      # 28.03 = zmiana czasu
    series = [[tg._day_ms(d), 800 + i] for i, d in enumerate(days)]
    spacing = {series[i + 1][0] - series[i][0] for i in range(len(series) - 1)}
    check('wszystkie punkty co równo 24 h', spacing == {tg.DAY_MS}, str(spacing))
    check('delta 1D przez zmianę czasu = 1', tg.compute_deltas(series)['1D'] == 1)
    check('_ms_day odwraca _day_ms', all(tg._ms_day(ms) == d for (ms, _), d in zip(series, days)))


if __name__ == '__main__':
    print("🧪 TEST INDEKSU PODAŻY\n" + "=" * 60)
    test_intervals()
    test_index_history_store()
    test_series_from_measurement()
    test_live_data()
    test_corrupted_history()
    test_unscanned_day_is_a_gap()
    test_index_source_label()
    test_promoted_survives_address_change()
    test_refreshes_two_series()
    test_refresh_unscanned_day_is_a_gap()
    test_szperacz_backfill()
    test_day_anchor_is_utc()
    print("\n" + "=" * 60)
    if FAILED:
        print(f"❌ Niezaliczone ({len(FAILED)}): " + ', '.join(FAILED))
        sys.exit(1)
    print("✅ Wszystkie testy Indeksu przeszły.")
