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
             if datetime.fromtimestamp(ms / 1000).date() < tg.REACT_RELIABLE_START]
    check('odcinek sprzed granicy to luka', early and all(v is None for v in early),
          f'{len(early)} dni')

    values = [v for _, v in series if v is not None]
    check('seria niepusta', bool(values), f'{len(values)} punktów')
    check('brak wartości ujemnych', all(v >= 0 for v in values))


if __name__ == '__main__':
    print("🧪 TEST INDEKSU PODAŻY\n" + "=" * 60)
    test_intervals()
    test_index_history_store()
    test_series_from_measurement()
    test_live_data()
    print("\n" + "=" * 60)
    if FAILED:
        print(f"❌ Niezaliczone ({len(FAILED)}): " + ', '.join(FAILED))
        sys.exit(1)
    print("✅ Wszystkie testy Indeksu przeszły.")
