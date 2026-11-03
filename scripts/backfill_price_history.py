#!/usr/bin/env python3
"""
Backfill `data/price_history.json` z historii gita.

Skąd bierzemy przeszłość
------------------------
`data/offers.json` jest commitowany po każdym skanie, więc każda jego rewizja
to dokładny stan bazy po tamtym skanie: które oferty były aktywne i jaką miały
cenę. Dla każdej rewizji liczymy `price_history.snapshot()` i przypisujemy ją
do dnia skanu (`last_scan` z samego pliku, a gdy go brak — data commita).
Z kilku skanów dnia zostaje ten z największą liczbą aktywnych ofert, czyli ta
sama konwencja co w `index_history` i w żywym `price_history.record()`.

Rekonstrukcji z `first_seen`/`last_seen` celowo NIE używamy — zawyża przeszłość
(patrz docstring `index_history`).

Wpisy z żywych skanów (bez `backfilled`) zostają nietknięte, więc skrypt można
puścić ponownie, żeby uzupełnić dni, które przepadły między backfillem a
wdrożeniem zapisu w skanie.

Wymaga historii gita od startu zakresu. W płytkim klonie najpierw:
    git fetch --shallow-since=2026-05-14 origin main

Użycie:
    python scripts/backfill_price_history.py            # raport (dry-run)
    python scripts/backfill_price_history.py --apply    # zapis do data/price_history.json
"""

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))

from price_history import load, merge_snapshot, save, snapshot  # noqa: E402
from trend_generator import RELIABLE_START  # noqa: E402

WARSAW = ZoneInfo('Europe/Warsaw')


def _git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True)


def revisions(ref: str):
    """[(sha, commit_iso), ...] rewizji offers.json, od najstarszej."""
    out = _git('log', ref, '--format=%H %aI', '--', 'data/offers.json')
    if out.returncode:
        sys.exit(f"git log nie powiódł się: {out.stderr.decode().strip()}")
    revs = [line.split() for line in out.stdout.decode().splitlines() if line.strip()]
    return list(reversed(revs))


def scan_day(data, commit_iso: str):
    """(dzień, znacznik) skanu, który zapisał tę rewizję."""
    stamp = data.get('last_scan') if isinstance(data, dict) else None
    for candidate in (stamp, commit_iso):
        if not candidate:
            continue
        try:
            dt = datetime.fromisoformat(candidate)
        except (ValueError, TypeError):
            continue
        if dt.tzinfo is not None:
            dt = dt.astimezone(WARSAW)
        return dt.date(), candidate
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--apply', action='store_true', help='zapisz wynik do data/price_history.json')
    ap.add_argument('--ref', default='origin/main', help='gałąź, z której czytamy historię (domyślnie origin/main)')
    ap.add_argument('--start', default=RELIABLE_START.isoformat(), help='pierwszy dzień (domyślnie RELIABLE_START)')
    args = ap.parse_args()
    start = date.fromisoformat(args.start)

    history = load(strict=True)
    days = history['days']
    live = {d for d, e in days.items() if not e.get('backfilled')}

    revs = revisions(args.ref)
    print(f"📜 {len(revs)} rewizji data/offers.json w {args.ref}")
    touched, unreadable = set(), 0
    for sha, commit_iso in revs:
        raw = _git('show', f'{sha}:data/offers.json')
        if raw.returncode:
            unreadable += 1
            continue
        try:
            data = json.loads(raw.stdout)
        except json.JSONDecodeError:
            unreadable += 1
            continue
        day, stamp = scan_day(data, commit_iso)
        if day is None or day < start:
            continue
        key = day.isoformat()
        if key in live:
            continue
        offers = data.get('offers', []) if isinstance(data, dict) else data
        if isinstance(offers, dict):
            offers = list(offers.values())
        if merge_snapshot(days, key, snapshot(offers), stamp, backfilled=True):
            touched.add(key)

    span = sorted(days)
    print(f"✅ dni zmienione: {len(touched)}, z żywych skanów (nietknięte): {len(live)}, "
          f"nieczytelnych rewizji: {unreadable}")
    if span:
        first, last = date.fromisoformat(span[0]), date.fromisoformat(span[-1])
        missing = (last - first).days + 1 - len(span)
        print(f"   zakres {span[0]} … {span[-1]}: {len(span)} dni, luk: {missing}")
    if args.apply:
        save(history)
        print("💾 zapisano data/price_history.json")
    else:
        print("ℹ️  dry-run — dodaj --apply, żeby zapisać")


if __name__ == '__main__':
    main()
