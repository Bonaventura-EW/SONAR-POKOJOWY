#!/usr/bin/env python3
"""
Migracja jednorazowa (Faza 1, opcja ii):
Scala duplikaty ofert dla ŻYWYCH grup (≥1 aktywny rekord o tej samej końcówce ID OLX)
w jeden kanoniczny rekord per ID OLX, odtwarzając model wersji z tego co jest w bazie.

Reguły:
- kanoniczny = aktywny rekord o najświeższym last_seen,
- duplikat o TYM SAMYM adresie → scal historię cen / odświeżeń / reaktywacji,
- duplikat o INNYM adresie → osobna WERSJA (versions[]) z własną historią,
- martwe grupy (bez aktywnego rekordu) NIE są ruszane.

NIE czyści geocoding_cache.json — wszystkie adresy pozostają realne i poprawnie
zgeokodowane (scalamy/zapisujemy je, nie kasujemy błędnych danych).

Uruchom z katalogu repo:  python scripts/migrate_versions_live_groups.py
"""
import json
import shutil
import difflib
from collections import defaultdict
from datetime import datetime
from pathlib import Path

OFFERS = Path('data/offers.json')


def addr_changed(old_addr, new_addr):
    """Identyczna logika jak main._addr_changed."""
    if not isinstance(old_addr, dict) or not isinstance(new_addr, dict):
        return False
    o_full = (old_addr.get('full') or '').strip().lower()
    n_full = (new_addr.get('full') or '').strip().lower()
    if not o_full or not n_full or o_full == n_full:
        return False
    o_num = str(old_addr.get('number') or '').strip().lower()
    n_num = str(new_addr.get('number') or '').strip().lower()
    if o_num and n_num and o_num != n_num:
        return True
    o_st = (old_addr.get('street') or '').strip().lower() or o_full
    n_st = (new_addr.get('street') or '').strip().lower() or n_full
    return difflib.SequenceMatcher(None, o_st, n_st).ratio() < 0.82


def price_history(rec):
    ph = rec.get('price', {}).get('history_full', [])
    if ph:
        return list(ph)
    # backfill z prostej historii
    hist = rec.get('price', {}).get('history', [])
    return [{'price': p, 'date': rec.get('first_seen', ''), 'approximated': False} for p in hist]


def merge_same_address(canonical, dup):
    """Scal duplikat o tym samym adresie do kanonicznego."""
    # historia cen: unia po (price, date) zachowując porządek czasowy
    cph = price_history(canonical)
    seen = {(h.get('price'), h.get('date')) for h in cph}
    for h in price_history(dup):
        key = (h.get('price'), h.get('date'))
        if key not in seen:
            cph.append(h)
            seen.add(key)
    cph.sort(key=lambda h: h.get('date', ''))
    canonical['price']['history_full'] = cph
    canonical['price']['history'] = [h.get('price') for h in cph]
    # odświeżenia: unia dat
    rd = set(canonical.get('refresh_dates', [])) | set(dup.get('refresh_dates', []))
    canonical['refresh_dates'] = sorted(rd)
    canonical['refresh_count'] = len(rd)
    # reaktywacje: suma
    canonical['reactivation_count'] = (canonical.get('reactivation_count', 0)
                                       + dup.get('reactivation_count', 0))


def build_version(rec):
    """Zrzut rekordu jako zamknięta wersja adresu."""
    ph = price_history(rec)
    return {
        'address': dict(rec.get('address', {})),
        'price_history': ph,
        'first_seen': rec.get('first_seen', ''),
        'last_seen': rec.get('last_seen', ''),
        'refresh_count': rec.get('refresh_count', 0),
        'refresh_dates': list(rec.get('refresh_dates', [])),
        'reactivation_count': rec.get('reactivation_count', 0),
        'last_price': ph[-1]['price'] if ph else rec.get('price', {}).get('current'),
    }


def main():
    data = json.loads(OFFERS.read_text(encoding='utf-8'))
    offers = data.get('offers', [])

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = OFFERS.with_name(f'offers.backup_versions_migration_{ts}.json')
    shutil.copy(OFFERS, backup)
    print(f'💾 Backup: {backup}')

    groups = defaultdict(list)
    for o in offers:
        oid = o.get('id', '')
        if '-ID' in oid:
            groups[oid.split('-ID')[-1]].append(o)

    to_remove = []          # rekordy (id) do usunięcia po scaleniu
    merged_groups = 0
    versions_built = 0
    same_addr_merged = 0

    for sid, recs in groups.items():
        if len(recs) < 2:
            continue
        if not any(r.get('active') for r in recs):
            continue  # martwa grupa — nie ruszamy

        # kanoniczny = aktywny, najświeższy last_seen
        canonical = sorted(
            recs, key=lambda r: (r.get('active', False), r.get('last_seen', '')), reverse=True
        )[0]
        others = [r for r in recs if r is not canonical]

        # podziel na te o innym adresie (→ wersje) i tym samym (→ scalenie)
        version_recs = [r for r in others if addr_changed(canonical.get('address', {}), r.get('address', {}))]
        same_recs = [r for r in others if r not in version_recs]

        for r in same_recs:
            merge_same_address(canonical, r)
            same_addr_merged += 1

        versions = canonical.get('versions', [])
        for r in sorted(version_recs, key=lambda x: x.get('first_seen', '')):
            versions.append(build_version(r))
            versions_built += 1
        if versions:
            versions.sort(key=lambda v: v.get('first_seen', ''))
            canonical['versions'] = versions
            canonical['address_change_count'] = len(versions)
            canonical['address_changed_at'] = canonical.get('first_seen', '')

        # daty całościowe + start bieżącej wersji
        all_first = [r.get('first_seen', '') for r in recs if r.get('first_seen')]
        canonical['version_first_seen'] = canonical.get('first_seen', '')
        if all_first:
            canonical['first_seen'] = min(all_first)

        for r in others:
            to_remove.append(id(r))
        merged_groups += 1

    data['offers'] = [o for o in offers if id(o) not in to_remove]
    OFFERS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'✅ Scalono grup: {merged_groups}')
    print(f'   wersji adresu odtworzonych: {versions_built}')
    print(f'   duplikatów o tym samym adresie wchłoniętych: {same_addr_merged}')
    print(f'   rekordów usuniętych: {len(to_remove)}')
    print(f'   ofert przed: {len(offers)} → po: {len(data["offers"])}')


if __name__ == '__main__':
    main()
