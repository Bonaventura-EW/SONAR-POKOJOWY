#!/usr/bin/env python3
"""One-off backfill: seed reactivation_dates z jedynej znanej daty (reactivated_at).

Baza historycznie trzymała tylko OSTATNIĄ datę reaktywacji (reactivated_at) +
licznik reactivation_count. Wcześniejszych dat wielokrotnych reaktywacji nie da
się odtworzyć (patrz CHANGELOG 2026-07-13). Ten skrypt inicjalizuje nowe pole
reactivation_dates listą z jedyną znaną datą; różnica count - len(dates) to
reaktywacje bez znanej daty (front pokazuje je jako "+N wcześniej").

Idempotentny: nie nadpisuje już wypełnionej listy.
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OFFERS = ROOT / 'data' / 'offers.json'


def main():
    db = json.loads(OFFERS.read_text(encoding='utf-8'))
    offers = db['offers'] if isinstance(db, dict) else db

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = ROOT / 'data' / 'backups' / f'offers.backup_reactivation_dates_{stamp}.json'
    shutil.copy2(OFFERS, backup)
    print(f'Backup: {backup}')

    seeded = seeded_empty = skipped = 0
    for o in offers:
        if o.get('reactivation_dates'):  # już wypełnione → idempotencja
            skipped += 1
            continue
        count = o.get('reactivation_count', 0) or 0
        if count <= 0:
            continue
        ra = o.get('reactivated_at')
        if ra:
            o['reactivation_dates'] = [ra]
            seeded += 1
        else:
            o['reactivation_dates'] = []  # count>0 bez znanej daty (8 ofert)
            seeded_empty += 1

    OFFERS.write_text(
        json.dumps(db, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    print(f'Zaseedowano 1 datą: {seeded}')
    print(f'count>0 bez daty (pusta lista): {seeded_empty}')
    print(f'Pominięto (już wypełnione): {skipped}')


if __name__ == '__main__':
    main()
