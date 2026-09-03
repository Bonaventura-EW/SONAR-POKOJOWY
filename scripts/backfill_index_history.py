#!/usr/bin/env python3
"""
Jednorazowy backfill `data/index_history.json` z historii gita.

Skąd bierzemy przeszłość
------------------------
`data/scan_history.json` trzyma tylko OSTATNIE ~100 skanów (≈33 dni przy trzech
skanach dziennie), ale jest commitowany po każdym skanie — więc pełna historia
`stats.active` leży w starszych rewizjach tego pliku. Wystarczy kilka rewizji
rozstawionych co ~30 dni, żeby okna się zazębiły i pokryły cały okres.

Użycie:
    python scripts/backfill_index_history.py <plik|URL> [<plik|URL> ...]

Argumenty to rewizje `scan_history.json` (ścieżki lokalne albo URL-e do
raw.githubusercontent.com). Bieżący `data/scan_history.json` doliczany jest
zawsze. Skrypt NIE nadpisuje wpisów pochodzących z żywych skanów — bierze
maksimum, tak samo jak `index_history.record()`.

Rewizje użyte przy pierwszym backfillu (14.05–02.09.2026, 112 dni bez luk):
    a6d03ef  (do 08.06)   46b191f  (do 25.06)   8bafa41  (do 05.07)
    8efffc4  (do 25.07)   ead58e0  (do 08.08)
URL: https://raw.githubusercontent.com/Bonaventura-EW/SONAR-POKOJOWY/<sha>/data/scan_history.json
"""

import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from index_history import load, save  # noqa: E402
from shared_utils import SCAN_HISTORY_FILE  # noqa: E402


def read_source(src: str):
    if src.startswith('http://') or src.startswith('https://'):
        with urllib.request.urlopen(src, timeout=60) as resp:
            data = json.load(resp)
    else:
        with open(src, 'r', encoding='utf-8') as f:
            data = json.load(f)
    return data.get('scans', []) if isinstance(data, dict) else data


def main(sources):
    history = load()
    days = history['days']
    seen_scans = set()
    added = 0

    for src in list(sources) + [str(SCAN_HISTORY_FILE)]:
        try:
            scans = read_source(src)
        except Exception as exc:                      # noqa: BLE001
            print(f"⚠️  pomijam {src}: {exc}")
            continue
        used = 0
        for scan in scans or []:
            ts = scan.get('timestamp')
            active = (scan.get('stats') or {}).get('active')
            if not ts or ts in seen_scans or active is None:
                continue
            if scan.get('status') not in ('completed', 'warning'):
                continue
            seen_scans.add(ts)
            used += 1
            try:
                day = datetime.fromisoformat(ts).date().isoformat()
            except (ValueError, TypeError):
                continue
            entry = days.get(day) or {'active': 0, 'scans': 0, 'backfilled': True}
            entry['scans'] = entry.get('scans', 0) + 1
            if active > entry.get('active', 0):
                entry['active'] = active
                entry['ts'] = ts
            days[day] = entry
            added += 1
        print(f"   {Path(src).name if not src.startswith('http') else src[-60:]}: {used} skanów")

    save(history)
    keys = sorted(days)
    print(f"\n✅ index_history.json: {len(keys)} dni ({keys[0]} → {keys[-1]}), "
          f"{added} odczytów, {len(seen_scans)} unikalnych skanów")
    gaps = []
    cur = datetime.fromisoformat(keys[0]).date()
    end = datetime.fromisoformat(keys[-1]).date()
    from datetime import timedelta
    while cur <= end:
        if cur.isoformat() not in days:
            gaps.append(cur.isoformat())
        cur += timedelta(days=1)
    print(f"   dni bez ani jednego skanu: {len(gaps)}{' → ' + ', '.join(gaps) if gaps else ''}")


if __name__ == '__main__':
    main(sys.argv[1:])
