#!/usr/bin/env python3
"""
Dzienny stan bazy — ŹRÓDŁO PRAWDY dla Indeksu podaży (`trend.html`).

Dlaczego ten plik w ogóle istnieje
----------------------------------
Indeks był wcześniej REKONSTRUOWANY wstecz z `offers.json`: dla dnia D liczba
ofert, których przedział `first_seen … last_seen` obejmował D. Ta metoda ma wadę
nie do naprawienia w samych danych ofert: oferta, która zniknęła 10.06 i wróciła
20.08, ma w bazie JEDEN ciągły przedział życia (dat deaktywacji do 09.2026 nikt
nie zapisywał), więc była liczona jako żywa przez cały czerwiec, lipiec i sierpień.

Skala błędu, zmierzona względem `stats.active` zapisanego w `scan_history.json`:
+27% dla końca maja, +20% dla lipca, +4% dla dnia dzisiejszego. Zawyżenie maleje
z wiekiem punktu (im starszy dzień, tym więcej reaktywacji zdążyło zasypać jego
dziury), więc prawy koniec wykresu ZAWSZE opadał — 29.07→02.09 rekonstrukcja
pokazywała −10%, a rynek w tym czasie urósł o +1,9%. Wykres mylił się co do
kierunku trendu, nie tylko co do poziomu.

Co robimy zamiast
-----------------
Każdy skan dopisuje tu swój wynik: `active` = ile ofert ma w bazie `active=true`
po zakończeniu skanu. To ta sama liczba, którą widać w monitoringu i na mapie —
mierzona, nie odtwarzana. Wykres rysuje ją wprost, więc stary punkt nigdy się już
nie zmienia (rekonstrukcja rosła wstecz z każdym nowym skanem).

Konwencja dnia: `active` = MAKSIMUM z odczytów danego dnia. Skan częściowy
(blokada OLX) zaniża stan, więc bierzemy najpełniejszy obraz dnia — inaczej
przerwany scrape rysowałby się jak załamanie rynku. `record()` nigdy nie obniża
już zapisanej wartości.

Dzień bez ani jednego skanu (awaria Actions) NIE MA tu wpisu i `daily_series()`
zwraca dla niego `None` — front rysuje lukę zamiast zmyślonego zera.

Historia sprzed wdrożenia (14.05–02.09.2026) jest odtworzona ze starszych rewizji
`data/scan_history.json` z historii gita — patrz `scripts/backfill_index_history.py`.
Te wpisy mają `backfilled: true`.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from shared_utils import DATA_DIR, write_json_atomic

INDEX_HISTORY_FILE = DATA_DIR / 'index_history.json'

NOTE = ("Dzienny stan bazy: ile ofert ma active=true po skanie. Zrodlo prawdy dla "
        "Indeksu podazy (trend.html). active = maksimum z odczytow danego dnia "
        "(skan czesciowy nie moze zanizyc historii). Nie edytowac recznie.")


def _path(base_dir=None) -> Path:
    return INDEX_HISTORY_FILE if base_dir is None else Path(base_dir) / 'data' / 'index_history.json'


def load(base_dir=None) -> dict:
    """Cała zawartość pliku. Brak pliku / uszkodzony JSON = pusty szkielet."""
    try:
        with open(_path(base_dir), 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {'note': NOTE, 'days': {}}
    if not isinstance(data, dict) or not isinstance(data.get('days'), dict):
        return {'note': NOTE, 'days': {}}
    return data


def save(data: dict, base_dir=None) -> None:
    data['note'] = NOTE
    data['generated_at'] = datetime.now().astimezone().isoformat()
    data['days'] = {d: data['days'][d] for d in sorted(data['days'])}
    write_json_atomic(_path(base_dir), data)


def record(active: int, timestamp: str = None, base_dir=None) -> dict:
    """Dopisuje wynik skanu do dnia, który wynika z `timestamp`.

    Wartość dnia to maksimum z odczytów — skan częściowy (blokada OLX) nigdy nie
    obniży już zapisanej liczby. `scans` liczy wszystkie odczyty dnia, także te
    niższe, żeby dało się poznać dzień z jednym skanem zamiast trzech.
    """
    if active is None:
        return {}
    ts = timestamp or datetime.now().astimezone().isoformat()
    try:
        day = datetime.fromisoformat(ts).date().isoformat()
    except (ValueError, TypeError):
        day = date.today().isoformat()

    data = load(base_dir)
    entry = data['days'].get(day) or {'active': 0, 'scans': 0}
    entry['scans'] = entry.get('scans', 0) + 1
    if active > entry.get('active', 0):
        entry['active'] = active
        entry['ts'] = ts
    # dzień dotknięty przez żywy skan przestaje być odtworzony z historii gita
    entry.pop('backfilled', None)
    data['days'][day] = entry
    save(data, base_dir)
    return entry


def daily_series(start: date = None, base_dir=None):
    """[(date, active|None), ...] — kolejne dni od `start` (lub od pierwszego
    zapisanego) do ostatniego zapisanego. `None` = dzień bez skanu."""
    days = load(base_dir)['days']
    parsed = {}
    for key, entry in days.items():
        try:
            parsed[date.fromisoformat(key)] = entry.get('active')
        except (ValueError, TypeError):
            continue
    if not parsed:
        return []
    first = max(start, min(parsed)) if start else min(parsed)
    last = max(parsed)
    out = []
    day = first
    while day <= last:
        out.append((day, parsed.get(day)))
        day += timedelta(days=1)
    return out
