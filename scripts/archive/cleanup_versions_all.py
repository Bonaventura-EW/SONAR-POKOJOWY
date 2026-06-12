#!/usr/bin/env python3
"""
Migracja idempotentna (Faza 2 — Część B + próg fleksji):
1. Scala WSZYSTKIE grupy duplikatów po ID OLX (także martwe — bez aktywnego rekordu).
2. Re-ewaluuje istniejące versions[] pod nowym progiem podobieństwa (0.75):
   fałszywe „zmiany" z samej fleksji (np. Bajkowa/Bajkowej) zwija z powrotem
   do bieżącej wersji (scalając ich historię cen / odświeżenia / reaktywacje).

Można puszczać wielokrotnie — wynik jest stabilny.
NIE rusza geocoding_cache.json (adresy pozostają realne i poprawne).

Uruchom z katalogu repo:  python scripts/cleanup_versions_all.py
"""
import json
import shutil
import difflib
from collections import defaultdict
from datetime import datetime
from pathlib import Path

OFFERS = Path('data/offers.json')
THRESH = 0.75


def addr_changed(old_addr, new_addr):
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
    o_tok, n_tok = set(o_st.split()), set(n_st.split())
    if o_tok and n_tok and (o_tok <= n_tok or n_tok <= o_tok):
        return False  # ten sam rdzeń ulicy, zgubione imię/prefiks
    return difflib.SequenceMatcher(None, o_st, n_st).ratio() < THRESH


def price_history(rec):
    ph = rec.get('price', {}).get('history_full', [])
    if ph:
        return list(ph)
    hist = rec.get('price', {}).get('history', [])
    return [{'price': p, 'date': rec.get('first_seen', ''), 'approximated': False} for p in hist]


def merge_price_into(canonical, ph_list):
    cph = price_history(canonical)
    seen = {(h.get('price'), h.get('date')) for h in cph}
    for h in ph_list:
        k = (h.get('price'), h.get('date'))
        if k not in seen:
            cph.append(h)
            seen.add(k)
    cph.sort(key=lambda h: h.get('date', ''))
    canonical.setdefault('price', {})['history_full'] = cph
    canonical['price']['history'] = [h.get('price') for h in cph]


def fold_counters(canonical, refresh_dates, reactivation_count, first_seen):
    rd = set(canonical.get('refresh_dates', [])) | set(refresh_dates or [])
    canonical['refresh_dates'] = sorted(rd)
    canonical['refresh_count'] = len(rd)
    canonical['reactivation_count'] = canonical.get('reactivation_count', 0) + (reactivation_count or 0)
    if first_seen:
        cur = canonical.get('first_seen') or first_seen
        canonical['first_seen'] = min(cur, first_seen)


def build_version(rec):
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
    backup = Path('data/backups') / f'offers.backup_cleanup_all_{ts}.json'
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(OFFERS, backup)
    print(f'💾 Backup: {backup}')

    groups = defaultdict(list)
    for o in offers:
        oid = o.get('id', '')
        if '-ID' in oid:
            groups[oid.split('-ID')[-1]].append(o)

    to_remove = set()
    merged_dead = 0
    versions_folded = 0
    same_addr_merged = 0
    versions_built = 0

    for sid, recs in groups.items():
        canonical = sorted(
            recs, key=lambda r: (r.get('active', False), r.get('last_seen', '')), reverse=True
        )[0]
        had_active = any(r.get('active') for r in recs)

        # 1) Re-ewaluacja istniejących wersji pod nowym progiem
        kept = []
        for v in canonical.get('versions', []):
            if addr_changed(canonical.get('address', {}), v.get('address', {})):
                kept.append(v)
            else:
                merge_price_into(canonical, v.get('price_history', []))
                fold_counters(canonical, v.get('refresh_dates', []),
                              v.get('reactivation_count', 0), v.get('first_seen', ''))
                versions_folded += 1
        canonical['versions'] = kept

        # 2) Scalenie pozostałych rekordów grupy (także martwe)
        others = [r for r in recs if r is not canonical]
        if others and not had_active:
            merged_dead += 1
        for r in others:
            if addr_changed(canonical.get('address', {}), r.get('address', {})):
                canonical.setdefault('versions', []).append(build_version(r))
                versions_built += 1
            else:
                merge_price_into(canonical, price_history(r))
                fold_counters(canonical, r.get('refresh_dates', []),
                              r.get('reactivation_count', 0), r.get('first_seen', ''))
                same_addr_merged += 1
            to_remove.add(id(r))

        # 3) Finalizacja pól wersji
        all_first = [r.get('first_seen', '') for r in recs if r.get('first_seen')]
        if all_first:
            canonical['first_seen'] = min([canonical.get('first_seen', '')] + all_first
                                          if canonical.get('first_seen') else all_first)
        canonical['version_first_seen'] = canonical.get('version_first_seen') or canonical.get('first_seen', '')
        vers = canonical.get('versions', [])
        if vers:
            vers.sort(key=lambda v: v.get('first_seen', ''))
            canonical['versions'] = vers
            canonical['address_change_count'] = len(vers)
            canonical['address_changed_at'] = canonical.get('version_first_seen') or canonical.get('first_seen', '')
        else:
            canonical.pop('versions', None)
            canonical.pop('address_change_count', None)
            canonical.pop('address_changed_at', None)

    data['offers'] = [o for o in offers if id(o) not in to_remove]
    OFFERS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'✅ Martwych grup scalonych: {merged_dead}')
    print(f'   Fałszywych wersji (fleksja) zwiniętych: {versions_folded}')
    print(f'   Duplikatów o tym samym adresie wchłoniętych: {same_addr_merged}')
    print(f'   Nowych wersji adresu z martwych grup: {versions_built}')
    print(f'   Rekordów usuniętych: {len(to_remove)}')
    print(f'   Ofert przed: {len(offers)} → po: {len(data["offers"])}')


if __name__ == '__main__':
    main()
