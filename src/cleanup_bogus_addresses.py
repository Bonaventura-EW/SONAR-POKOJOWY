#!/usr/bin/env python3
"""
Cleanup script - naprawia bogus addresses w data/offers.json.

Dla każdej oferty z bogus address (np. 'Pokoje', 'Umcs', 'Lublin Studio'):
1. Re-paruje tekst (tytuł + opis) świeżym parserem
2. Jeśli znajdzie prawdziwy adres → geokoduje → aktualizuje rekord
3. Jeśli nie znajdzie → oznacza ofertę jako nieaktywną (znika z mapy)

Uruchom: cd src && python3 cleanup_bogus_addresses.py
        cd src && python3 cleanup_bogus_addresses.py --dry-run  # tylko podgląd
"""
import sys
import os
import json
import argparse
import time
from datetime import datetime
from pathlib import Path

# Dodaj src do path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from address_parser import AddressParser
from geocoder import Geocoder


def is_bogus_address(address_full: str, excluded_words: set) -> bool:
    """
    Sprawdza czy adres to "bogus" (taki sam algorytm jak SonarPokojowy._is_bogus_address).
    """
    if not address_full:
        return True
    
    BOGUS_PREFIXES = (
        'Lublin Studio', 'Lublin Witam', 'Lublin Oferuję',
        'Lublin Duży', 'Lublin Pokoje', 'Witam ', 'Oferuję ',
        'Kaucja', 'Depozyt'
    )
    if any(address_full.startswith(p) for p in BOGUS_PREFIXES):
        return True
    
    tokens = address_full.split()
    if not tokens:
        return True
    first_word = tokens[0].lower().rstrip('.,;:')
    if first_word in excluded_words:
        return True
    
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Pokaż co byłoby zmienione, ale nie zapisuj')
    parser.add_argument('--offers-file', default='../data/offers.json')
    parser.add_argument('--cache-file', default='../data/geocoding_cache.json')
    args = parser.parse_args()

    offers_path = Path(args.offers_file)
    if not offers_path.exists():
        # fallback dla uruchomienia z repo root
        offers_path = Path('data/offers.json')
    
    cache_path = Path(args.cache_file)
    if not cache_path.exists():
        cache_path = Path('data/geocoding_cache.json')
    
    print(f"📚 Wczytuję {offers_path}")
    with open(offers_path, 'r', encoding='utf-8') as f:
        db = json.load(f)
    
    ap = AddressParser(geocoding_cache_path=str(cache_path))
    geo = Geocoder(cache_file=str(cache_path))
    
    offers = db.get('offers', [])
    print(f"   Total ofert: {len(offers)}")
    
    # Znajdź bogus
    bogus_offers = []
    for o in offers:
        addr_full = o.get('address', {}).get('full', '')
        if is_bogus_address(addr_full, ap.EXCLUDED_WORDS):
            bogus_offers.append(o)
    
    print(f"   Bogus address: {len(bogus_offers)} ({len([o for o in bogus_offers if o.get('active')])} aktywnych)")
    print()
    
    fixed = 0
    deactivated = 0
    skipped = 0
    
    now_iso = datetime.now().isoformat()
    
    for i, offer in enumerate(bogus_offers, 1):
        addr_full = offer.get('address', {}).get('full', '')
        offer_id = offer.get('id', '')[:50]
        active = offer.get('active', False)
        
        title = offer.get('title', '') if 'title' in offer else ''
        description = offer.get('description', '') or ''
        full_text = (title + ' ' + description).strip()
        
        print(f"[{i}/{len(bogus_offers)}] id={offer_id} | bogus='{addr_full}' | active={active}")
        
        if not full_text:
            print(f"   ⚠️  Brak tekstu (title+desc) → nie da się re-parsować")
            skipped += 1
            continue
        
        # Re-parse
        new_addr = ap.extract_address(full_text)
        if not new_addr:
            new_addr = ap.extract_street_only(full_text)
        if not new_addr:
            new_addr = ap.extract_from_whitelist(full_text)
        
        if not new_addr or is_bogus_address(new_addr.get('full', ''), ap.EXCLUDED_WORDS):
            # Nie udało się znaleźć prawdziwego adresu → dezaktywuj ofertę
            if active:
                print(f"   ❌ Re-parse nieudany → DEZAKTYWUJĘ ofertę (znika z mapy)")
                if not args.dry_run:
                    offer['active'] = False
                    offer['deactivated_at'] = now_iso
                    offer['deactivation_reason'] = 'bogus_address_unfixable'
                deactivated += 1
            else:
                # Już nieaktywna - tylko czyść adres żeby ewentualna reaktywacja nie wzięła bogus
                print(f"   ℹ️  Już nieaktywna, czyść address.full → puste")
                if not args.dry_run:
                    offer['address']['previous_bogus'] = addr_full
                    offer['address']['full'] = ''
                    offer['address']['street'] = None
                skipped += 1
            continue
        
        new_full = new_addr['full']
        print(f"   ✅ Re-parse: '{addr_full}' → '{new_full}'")
        
        # Geokoduj
        coords = geo.geocode_address(new_full)
        if not coords:
            print(f"   ⚠️  Nie można zgeokodować '{new_full}' → DEZAKTYWUJĘ")
            if active:
                if not args.dry_run:
                    offer['active'] = False
                    offer['deactivated_at'] = now_iso
                    offer['deactivation_reason'] = 'bogus_address_no_geocode'
                deactivated += 1
            else:
                skipped += 1
            continue
        
        print(f"   📍 Coords: {coords['lat']:.4f}, {coords['lon']:.4f}")
        
        if not args.dry_run:
            offer['address']['previous_bogus'] = addr_full
            offer['address']['fixed_at'] = now_iso
            offer['address']['full'] = new_full
            offer['address']['street'] = new_addr.get('street')
            offer['address']['number'] = new_addr.get('number')
            offer['address']['coords'] = coords
            offer['address']['precision'] = 'exact' if new_addr.get('number') else 'street_only'
        fixed += 1
        
        # Małe opóźnienie żeby nie spamować geocoderem
        # (Nominatim limit: 1 req/s, ale większość trafień w cache)
        if i < len(bogus_offers):
            time.sleep(0.2)
    
    print()
    print("=" * 60)
    print("📊 PODSUMOWANIE")
    print("=" * 60)
    print(f"  Total bogus: {len(bogus_offers)}")
    print(f"  ✅ Naprawione: {fixed}")
    print(f"  ❌ Dezaktywowane (re-parse failed): {deactivated}")
    print(f"  ⏭️  Pominięte: {skipped}")
    
    if args.dry_run:
        print(f"\n  💧 DRY RUN - nic nie zapisano. Uruchom bez --dry-run żeby zapisać.")
    else:
        if fixed + deactivated > 0:
            with open(offers_path, 'w', encoding='utf-8') as f:
                json.dump(db, f, ensure_ascii=False, indent=2)
            print(f"\n  💾 Zapisano {offers_path}")
        else:
            print(f"\n  ℹ️  Brak zmian do zapisu")


if __name__ == "__main__":
    main()
