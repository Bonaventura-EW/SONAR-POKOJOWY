#!/usr/bin/env python3
"""
Jednorazowa naprawa markerów po audycie 2026-08-18 (klasy B, C, D, E, F).

Co robi:
  1. Czyści z geocoding_cache.json wpisy ZATRUTE — takie, pod którymi Nominatim
     zapisał punkt gorszego sortu niż etykieta obiecuje:
       - klucz z numerem domu, którego koordynaty są identyczne z koordynatami
         samej ulicy (fallback zapisany jako "dokładny adres"),
       - nazwy ulic, dla których Nominatim oddał osiedle/park/sklep zamiast ulicy,
       - śmieciowe klucze wyprodukowane przez stary parser.
  2. Przepuszcza WSZYSTKIE aktywne oferty przez aktualny parser + geokoder
     (dokładnie tak, jak zrobiłby to pełny scan bez inteligentnego pomijania)
     i zapisuje adres, gdy wynik jest inny niż w bazie.

Uruchomienie:
    python scripts/repair_markers_20260818.py --dry-run   # tylko raport
    python scripts/repair_markers_20260818.py --apply     # zapis do bazy
"""
import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'src'))

from address_parser import AddressParser          # noqa: E402
from geocoder import Geocoder, to_nominative      # noqa: E402
from shared_utils import write_json_atomic        # noqa: E402

OFFERS = REPO / 'data' / 'offers.json'
CACHE = REPO / 'data' / 'geocoding_cache.json'

# Klucze cache z audytu, pod którymi siedzi punkt NIE-ulicy (osiedle/park/sklep)
# albo śmieć po starym parserze. Po skasowaniu geokoder odpyta Nominatim ponownie,
# już z preferencją wyniku typu "ulica".
POISONED_KEYS = [
    'Chopina',                    # → osiedle Chopina (Czechów) zamiast ul. Fryderyka Chopina
    'Konopnickiej',               # → osiedle Konopnickiej (Rury) zamiast ul. Konopnickiej
    'Popiełuszki',                # → skwer Popiełuszki (Bronowice) zamiast ulicy na Wieniawie
    'Zana',                       # → "Centrum Zana Holding" (Konstantynów) zamiast ul. Zana
    'Zana, Lublin',
    'Skłodowskiej',               # → punkt przy Akademickiej zamiast ulicy
    'tylko 2',                    # śmieć parsera (ID1bFuLU)
    'Skierki w 3',                # śmieć parsera (ID1b3zK8)
    'Lipińskiego Lublin Lublin',  # śmieć parsera (ID16uG5V)
]


def house_number_keys_with_street_coords(cache):
    """Klucze z numerem domu, pod którymi NIE stoi budynek:
      - koordynaty identyczne z punktem samej ulicy (fallback zapisany jako
        "dokładny adres"),
      - numer z mieszkaniem ('29/4') — Nominatim takich nie zna i przed poprawką
        z 2026-08-18 zawsze oddawał punkt ulicy.
    """
    import re
    out = []
    num_re = re.compile(r'^(.*?)\s+\d+[a-zA-Z]?(?:/\d+[a-zA-Z]?)?$')
    for key, value in cache.items():
        if not value:
            continue
        m = num_re.match(key.strip())
        if not m:
            continue
        if '/' in key:
            out.append(key)
            continue
        street = m.group(1).strip()
        # Punkt ulicy bywa w cache pod formą z ogłoszenia ('Wileńskiej') albo pod
        # mianownikiem ('Wileńska') — sprawdzamy obie.
        for street_key in {street, to_nominative(street)}:
            street_coords = cache.get(street_key)
            if street_coords and street_coords == value:
                out.append(key)
                break
    return out


def parse_chain(parser, title, desc):
    """Kolejność ekstraktorów jak w main._process_offer (bez cache adresu)."""
    full_text = f"{title or ''} {desc or ''}"
    data = parser.extract_address(title or '')
    precision = 'exact'
    if not data:
        data = parser.extract_address(full_text)
    if not data and desc:
        data = parser.extract_address(desc)
    if not data:
        street_only = (parser.extract_street_only(title or '')
                       or parser.extract_street_only(full_text)
                       or (parser.extract_street_only(desc) if desc else None))
        if street_only:
            data, precision = street_only, 'street_only'
    if not data:
        wl = (parser.extract_from_whitelist(title or '')
              or parser.extract_from_whitelist(full_text)
              or (parser.extract_from_whitelist(desc) if desc else None))
        if wl:
            data, precision = wl, 'street_only'
    if not data:
        district = (parser.extract_district(full_text)
                    or (parser.extract_district(desc) if desc else None))
        if district:
            data, precision = district, 'district'
    return data, (precision if data else None)


def geocode_with_fallbacks(parser, geo, data, precision, title, desc):
    """Łańcuch fallbacków jak w main._geocode_with_fallbacks."""
    full_text = f"{title or ''} {desc or ''}"
    candidates = [(data, precision)]

    def add(result, prec):
        if result and result.get('full'):
            candidates.append((result, prec))

    add(parser.extract_street_only(full_text)
        or (parser.extract_street_only(desc) if desc else None), 'street_only')
    add(parser.extract_from_whitelist(full_text)
        or (parser.extract_from_whitelist(desc) if desc else None), 'street_only')
    add(parser.extract_district(full_text)
        or (parser.extract_district(desc) if desc else None), 'district')

    tried = set()
    for cand, prec in candidates:
        if not cand:
            continue
        full = cand['full']
        if full in tried:
            continue
        tried.add(full)
        coords, meta = geo.geocode_address(full, return_meta=True)
        if not meta.get('cache_hit'):
            time.sleep(1.1)  # Nominatim: max 1 req/s
        if not coords:
            continue
        if meta.get('number_fallback') and prec != 'district':
            prec = 'street_only'
        return coords, cand, prec
    return None, data, precision


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='zapisz zmiany do bazy')
    ap.add_argument('--dry-run', action='store_true', help='tylko raport (domyślne)')
    ap.add_argument('--limit', type=int, default=0, help='przetwórz tylko N ofert (debug)')
    args = ap.parse_args()
    apply_changes = args.apply and not args.dry_run

    cache = json.loads(CACHE.read_text(encoding='utf-8'))
    purge = [k for k in POISONED_KEYS if k in cache]
    purge += [k for k in house_number_keys_with_street_coords(cache) if k not in purge]
    print(f"🧹 Zatrute klucze cache do usunięcia: {len(purge)}")
    for k in sorted(purge):
        print(f"   - {k!r} = {cache[k]}")

    # W dry-run pracujemy na KOPII cache, żeby nie ruszać pliku produkcyjnego.
    cache_path = CACHE
    if not apply_changes:
        cache_path = REPO / 'data' / '.geocoding_cache.dryrun.json'
        write_json_atomic(cache_path, {k: v for k, v in cache.items() if k not in purge})
        print(f"   (dry-run: pracuję na kopii {cache_path.name})")
    else:
        for k in purge:
            cache.pop(k, None)
        write_json_atomic(CACHE, cache)
        print(f"   ✅ Wyczyszczono cache ({len(purge)} kluczy)")

    db = json.loads(OFFERS.read_text(encoding='utf-8'))
    parser = AddressParser(geocoding_cache_path=str(cache_path))
    geo = Geocoder(cache_file=str(cache_path))

    active = [o for o in db['offers'] if o.get('active')]
    if args.limit:
        active = active[:args.limit]
    print(f"\n🔁 Re-parsing {len(active)} aktywnych ofert…\n")

    changes, failures = [], []
    for i, offer in enumerate(active, 1):
        sid = offer['id'].split('-ID')[-1] if '-ID' in offer['id'] else offer['id']
        old = offer.get('address', {}) or {}
        data, precision = parse_chain(parser, offer.get('title'), offer.get('description'))
        if not data:
            continue
        coords, chosen, precision = geocode_with_fallbacks(
            parser, geo, data, precision, offer.get('title'), offer.get('description'))
        if not coords:
            failures.append((sid, chosen.get('full') if chosen else None))
            continue

        new_full = chosen['full']
        same_label = (old.get('full') or '').strip().lower() == new_full.strip().lower()
        same_coords = (old.get('coords') or {}) == coords
        same_precision = old.get('precision') == precision
        if same_label and same_coords and same_precision:
            continue

        changes.append({
            'id': sid,
            'old': f"{old.get('full')!r} ({old.get('precision')})",
            'new': f"{new_full!r} ({precision})",
            'old_coords': old.get('coords'),
            'new_coords': coords,
            'moved_m': _dist(old.get('coords'), coords),
        })
        if apply_changes:
            address = dict(old)
            address.update({
                'full': new_full,
                'street': chosen.get('street'),
                'number': chosen.get('number'),
                'coords': coords,
                'precision': precision,
            })
            offer['address'] = address
        if i % 50 == 0:
            print(f"   … {i}/{len(active)}", flush=True)

    print(f"\n📋 Zmian: {len(changes)}, bez koordynatów: {len(failures)}\n")
    changes.sort(key=lambda c: -(c['moved_m'] or 0))
    for c in changes:
        moved = f"{c['moved_m']:.0f} m" if c['moved_m'] is not None else '—'
        print(f"  {c['id']:9s} {c['old']:44s} → {c['new']:44s} ({moved})")
    if failures:
        print("\n⚠️  Bez koordynatów (adres zostaje bez zmian):")
        for sid, full in failures:
            print(f"  {sid:9s} {full!r}")

    if apply_changes:
        write_json_atomic(OFFERS, db)
        print(f"\n💾 Zapisano {OFFERS}")
    else:
        print("\n(dry-run — nic nie zapisano; użyj --apply)")


def _dist(a, b):
    if not a or not b:
        return None
    import math
    lat1, lon1, lat2, lon2 = a['lat'], a['lon'], b['lat'], b['lon']
    p = math.pi / 180
    return 2 * 6371000 * math.asin(math.sqrt(
        math.sin((lat2 - lat1) * p / 2) ** 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2))


if __name__ == '__main__':
    main()
