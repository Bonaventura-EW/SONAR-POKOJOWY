#!/usr/bin/env python3
"""
Retry geokodowania dla wszystkich None entries w cache.
Używa Fix #3 (transformacja do mianownika).

Uruchom: cd src && python3 retry_none_cache.py
"""
import sys
import os
import json
import time
from pathlib import Path

# Dodaj src do path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from geocoder import Geocoder, to_nominative

# Filtr noise - słowa które na pewno nie są ulicami (z analizy skipped_offers_sample.json
# + ręcznej inspekcji cache geokodera)
NOISE_WORDS_LOWER = {
    # Z analizy no_coords w skipped_offers_sample.json
    'oddzielnej', 'oddzielną', 'oddzielne', 'oddzielny',
    'telefonu', 'telefon', 'telefoniczny', 'telefoniczne', 'telefonicznego',
    'kondygnacji', 'kondygnacja',
    'dnia', 'dni',
    'pozostałych', 'pozostałe', 'pozostały', 'pozostałymi', 'zostały',
    'zajmie', 'zajmuje',
    'zł', 'złpokój', 'opisduży', 'opisdwuosobowy',
    'preferably', 'attractive', 'uniwercity', 'gyms', 'rent', 'monthly',
    'montly', 'within', 'choose', 'from', 'march',
    'wg', 'oraz', 'tel',
    'miesięcznego', 'średnio', 'miesięcznie',
    'oznaczony', 'nr',
    'samodzielnym', 'samodzielne',
    'nowoczesnym', 'nowoczesne',
    'użytku',
    'linii',
    'tylko',
    'częścią', 'częściej',
    'ochronę',
    'numerze', 'numerem', 'numer',
    # Z ręcznej inspekcji cache:
    'wynajęcia', 'wynajmę', 'wynajme', 'wynajem',
    'cenie', 'cena',
    'oferuję', 'oferta',
    'pokoj', 'pokoje', 'pokój',
    'kaucja', 'depozyt',
    'wolne', 'wolny',
    'około', 'okolica',
    'media',
    'odjeżdżają', 'autobusy', 'autobusowy',
    'się', 'jest', 'są',
    'lokal', 'lokalu',
    'lubelski', 'lubelska', 'lubelskiej',
    'opłaty', 'opłat',
    'politechnika', 'politechniki',  # nazwa uczelni, nie ulicy
    'kontaktu', 'kontakt',
    'małgorzata',  # imię, nie ulica
    'duży', 'duża',
    'tu', 'również',
    'materacem',
    'vpustreet',  # śmieć z OCR
    'spacer',
}

# Prefiksy które wskazują że to NIE jest ulica (cały adres to bzdura)
NOISE_PREFIXES = (
    'wynajm', 'oferuj', 'cena', 'cenie', 'kaucja', 'depozyt',
    'pokoj', 'pokój', 'pokoje', 'opis', 'media', 'wolne',
    'około', 'mont', 'rent ', 'gyms', 'choose', 'numer',
    'lubelsk', 'lokal', 'autobus', 'odjeżdż',
)

def is_noise_address(address: str) -> bool:
    """
    Czy adres to noise (rzeczownik + liczba) który NIE powinien być geokodowany.
    
    Reguły:
    1. Pierwsze słowo w NOISE_WORDS_LOWER → noise
    2. Pierwsze słowo zaczyna się od NOISE_PREFIXES → noise
    3. Adres jest pojedynczą liczbą lub krótszym niż 4 znaki → noise
    4. Adres zaczyna się od "się ", "z ", "w " (spójniki) → noise
    """
    if not address:
        return True
    
    addr_stripped = address.strip()
    if len(addr_stripped) < 4:
        return True
    
    tokens = addr_stripped.split()
    if not tokens:
        return True
    
    first = tokens[0].lower().rstrip(',.;:')
    
    # Reguła 1: exact match w noise words
    if first in NOISE_WORDS_LOWER:
        return True
    
    # Reguła 2: prefix match (np. "wynajęcia", "wynajmę" → 'wynajm')
    if any(first.startswith(p) for p in NOISE_PREFIXES):
        return True
    
    # Reguła 3: spójniki na początku
    if first in {'się', 'z', 'w', 'na', 'po', 'do', 'od'}:
        return True
    
    # Reguła 4: pierwszy token zaczyna się od małej litery (prawdziwe ulice
    # ZAWSZE zaczynają się od wielkiej litery, ewentualnie po prefiksie "ul./al./ulica")
    # Wyjątek: "ulica Foo", "ul. Foo", "Aleja Foo" - dopuszczamy, jeśli pierwszy token to prefiks
    PREFIX_TOKENS = {'ul.', 'ul', 'ulica', 'al.', 'al', 'aleja', 'aleje',
                     'pl.', 'pl', 'plac', 'os.', 'os', 'osiedle'}
    if first not in PREFIX_TOKENS and tokens[0][0].islower():
        return True
    
    return False



def main():
    cache_path = Path("../data/geocoding_cache.json")
    if not cache_path.exists():
        cache_path = Path("data/geocoding_cache.json")
    
    print(f"Wczytuję cache z {cache_path}")
    with open(cache_path) as f:
        cache = json.load(f)
    
    total = len(cache)
    none_keys = [k for k, v in cache.items() if v is None]
    print(f"Total: {total}, None: {len(none_keys)} ({len(none_keys)/total*100:.0f}%)")
    
    # Odfiltruj noise (nie próbuj geokodować "telefonu 60")
    noise_keys = [k for k in none_keys if is_noise_address(k)]
    real_keys = [k for k in none_keys if not is_noise_address(k)]
    print(f"Noise (pominięte): {len(noise_keys)}")
    print(f"Realne adresy do retry: {len(real_keys)}")
    
    # Pokaż próbki
    print("\n--- Próbka noise (zostają None) ---")
    for k in noise_keys[:10]:
        print(f"  {k}")
    print("\n--- Próbka realnych (retry) ---")
    for k in real_keys[:15]:
        nom = to_nominative(k)
        print(f"  {k}" + (f"  →  {nom}" if nom != k else ""))
    
    # Geocoder w sąsiednim katalogu
    geocoder = Geocoder(cache_file=str(cache_path))
    
    print(f"\n🚀 Rozpoczynam retry {len(real_keys)} adresów (delay 1.1s/req)...")
    print(f"   Szacowany czas: {len(real_keys) * 1.1 / 60:.1f} min")
    
    fixed = 0
    still_none = 0
    
    for i, key in enumerate(real_keys, 1):
        # Wymuszamy retry - usuwamy z cache i geokodujemy od zera
        if key in geocoder.cache:
            del geocoder.cache[key]
        
        coords = geocoder.geocode_address(key)
        
        if coords:
            fixed += 1
            status = f"✅ {coords['lat']:.4f},{coords['lon']:.4f}"
        else:
            still_none += 1
            status = "❌"
        
        if i % 20 == 0 or i == len(real_keys):
            print(f"  [{i}/{len(real_keys)}] {key[:40]:40s} → {status}  | fixed={fixed}, none={still_none}")
        
        # Nominatim: max 1 req/s
        time.sleep(1.1)
    
    # Final save
    geocoder._save_cache()
    
    print(f"\n{'='*60}")
    print(f"📊 PODSUMOWANIE")
    print(f"{'='*60}")
    print(f"Cache total: {total}")
    print(f"None przed: {len(none_keys)}")
    print(f"  - Noise pominięte: {len(noise_keys)}")
    print(f"  - Realnych retry: {len(real_keys)}")
    print(f"    - Fixed (znaleziono): {fixed}")
    print(f"    - Still None: {still_none}")
    print(f"\n✨ Cache zaktualizowany: {fixed} nowych zgeokodowanych adresów")


if __name__ == "__main__":
    main()
