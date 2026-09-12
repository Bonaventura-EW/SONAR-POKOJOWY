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

# Klucze cache z audytu, pod którymi siedzi punkt NIE-ulicy (osiedle/park/sklep/
# biblioteka o tej samej nazwie) albo śmieć po starym parserze. Wartość to ZŁY punkt,
# który tam zastaliśmy — czyścimy klucz tylko wtedy, gdy nadal wskazuje właśnie ten
# punkt. Dzięki temu skrypt jest idempotentny: po naprawie kolejne uruchomienie nie
# kasuje już dobrego wpisu (a każde skasowanie to nowe zapytanie do Nominatim, które
# na długiej ulicy potrafi zwrócić inny jej odcinek — marker skakałby bez powodu).
POISONED_KEYS = {
    # Tura 1 (2026-08-18) — z audytu markerów.
    'Chopina': (51.2694257, 22.5474285),       # osiedle Chopina zamiast ul. Fryderyka Chopina
    'Konopnickiej': (51.2365964, 22.5254332),  # osiedle Konopnickiej zamiast ul. Konopnickiej
    'Popiełuszki': (51.2343329, 22.5975718),   # skwer na Bronowicach zamiast ulicy na Wieniawie
    'Zana': (51.2481738, 22.5177575),          # "Centrum Zana Holding" zamiast ul. Tomasza Zana
    'Zana, Lublin': (51.2481738, 22.5177575),
    'Skłodowskiej': (51.242925, 22.5419752),   # punkt przy Akademickiej zamiast ulicy
    'tylko 2': (51.2046604, 22.5870081),       # śmieć parsera (ID1bFuLU)
    'Skierki w 3': (51.2436962, 22.517454),    # śmieć parsera (ID1b3zK8)
    'Lipińskiego Lublin Lublin': (51.2579395, 22.5493814),  # śmieć parsera (ID16uG5V)
    # Tura 2 (2026-08-19) — przegląd CAŁEGO cache: każdy klucz bez numeru porównany
    # z geometrią ulic OSM (Overpass). Te trzy punkty leżały 1,4–2,7 km od ulicy,
    # której nazwę noszą. Wzorzec ten sam co wyżej: pierwszym wynikiem Nominatim jest
    # obiekt nazwany od tej samej postaci, ulica dopiero drugim.
    'Prusa': (51.2346058, 22.5348422),          # osiedle Prusa (LSM) zamiast ul. Bolesława Prusa
    'Wyszyńskiego': (51.2328464, 22.5876506),   # skwer Wyszyńskiego zamiast ul. Prymasa S. Wyszyńskiego
    'Łopacińskiego': (51.2465117, 22.5632522),  # biblioteka im. Łopacińskiego zamiast ul. H. Łopacińskiego
}


def still_poisoned(cache, key, bad_point, tolerance_m=30):
    """Czy pod kluczem nadal stoi TEN zły punkt? (a nie już poprawiony)"""
    v = cache.get(key)
    if not v:
        return False
    import math
    p = math.pi / 180
    d = 2 * 6371000 * math.asin(math.sqrt(
        math.sin((bad_point[0] - v['lat']) * p / 2) ** 2
        + math.cos(v['lat'] * p) * math.cos(bad_point[0] * p)
        * math.sin((bad_point[1] - v['lon']) * p / 2) ** 2))
    return d <= tolerance_m


def house_number_keys_with_street_coords(cache, apartment_keys=False):
    """Klucze z numerem domu, pod którymi NIE stoi budynek:
      - koordynaty identyczne z punktem samej ulicy (fallback zapisany jako
        "dokładny adres"),
      - numer z mieszkaniem ('29/4') — Nominatim takich nie znał i przed poprawką
        z 2026-08-18 zawsze oddawał punkt ulicy; TYLKO przy apartment_keys=True
        (tura 1). Po poprawce geokoder ucina część po '/' i trafia w budynek, więc
        domyślnie tych kluczy nie ruszamy — kolejne czyszczenie byłoby pustą pracą.
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
        if '/' in key and apartment_keys:
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
    ap.add_argument('--purge-apartment-keys', action='store_true',
                    help='czyść też klucze z numerem mieszkania ("29/4") — użyte w turze 1, '
                         'przed poprawką geokodera; dziś zbędne')
    args = ap.parse_args()
    apply_changes = args.apply and not args.dry_run

    cache = json.loads(CACHE.read_text(encoding='utf-8'))
    purge = [k for k, bad in POISONED_KEYS.items() if still_poisoned(cache, k, bad)]
    purge += [k for k in house_number_keys_with_street_coords(cache, args.purge_apartment_keys)
              if k not in purge]
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
