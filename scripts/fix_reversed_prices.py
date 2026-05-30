#!/usr/bin/env python3
"""
Skrypt naprawczy: Naprawia odwrócone ceny i trendy
================================

PROBLEM:
- Niektóre oferty mają odwróconą kolejność current/previous_price
- Trendy są odwrócone (up zamiast down i vice versa)
- Historia cen jest poprawna, ale current wskazuje na błędną wartość

ROZWIĄZANIE:
1. Pobierz aktualną cenę z OLX (JSON-LD)
2. Porównaj z ceną w bazie
3. Jeśli różne - napraw:
   - Zamień current i previous_price
   - Odwróć trend
   - Dodaj source='JSON-LD (OLX)'
4. Usuń błędne wpisy z price_history
"""

import json
import sys
from pathlib import Path
from datetime import datetime
import pytz
import requests
from bs4 import BeautifulSoup
import time

# Import scrapera
sys.path.insert(0, str(Path(__file__).parent / 'src'))
from scraper import OLXScraper

def fetch_current_price_from_olx(url: str, scraper: OLXScraper) -> dict:
    """
    Pobiera aktualną cenę z OLX używając JSON-LD.
    
    Returns:
        {'price': int, 'source': str} lub None
    """
    try:
        details = scraper.fetch_offer_details(url)
        if details and details.get('official_price'):
            return {
                'price': details['official_price'],
                'source': details.get('price_source', 'json-ld')
            }
    except Exception as e:
        print(f"      ❌ Błąd pobierania z OLX: {e}")
    
    return None


def fix_reversed_prices(db_path='data/offers.json', dry_run=False):
    """
    Naprawia odwrócone ceny w bazie danych.
    
    Args:
        db_path: Ścieżka do bazy danych
        dry_run: Jeśli True, tylko pokazuje co by się zmieniło (bez zapisu)
    """
    print("\n" + "="*80)
    print("🔧 NAPRAWA ODWRÓCONYCH CEN I TRENDÓW")
    print("="*80 + "\n")
    
    # Wczytaj bazę
    print("📥 Ładowanie bazy danych...")
    with open(db_path, 'r', encoding='utf-8') as f:
        db = json.load(f)
    
    offers = db.get('offers', [])
    print(f"📊 Znaleziono {len(offers)} ofert w bazie\n")
    
    # Inicjalizuj scraper
    scraper = OLXScraper(delay_range=(1, 2), max_workers=1)
    
    # Statystyki
    stats = {
        'checked': 0,
        'fixed': 0,
        'skipped_inactive': 0,
        'skipped_no_history': 0,
        'errors': 0
    }
    
    fixed_offers = []
    
    for offer in offers:
        stats['checked'] += 1
        offer_id = offer['id']
        
        # Pomiń nieaktywne
        if not offer.get('active', False):
            stats['skipped_inactive'] += 1
            continue
        
        # Pomiń oferty bez historii zmian cen
        price_data = offer.get('price', {})
        if not price_data.get('previous_price') or not price_data.get('price_trend'):
            stats['skipped_no_history'] += 1
            continue
        
        url = offer.get('url')
        current_price = price_data.get('current')
        previous_price = price_data.get('previous_price')
        trend = price_data.get('price_trend')
        source = price_data.get('source', 'unknown')
        
        print(f"\n{'='*80}")
        print(f"🔍 Sprawdzam: {offer_id}")
        print(f"   Adres: {offer['address']['full']}")
        print(f"   URL: {url}")
        print(f"   W bazie: current={current_price} zł, previous={previous_price} zł, trend={trend}")
        print(f"   Źródło w bazie: {source}")
        
        # Pobierz aktualną cenę z OLX
        print(f"   📡 Pobieram aktualną cenę z OLX...")
        olx_data = fetch_current_price_from_olx(url, scraper)
        
        if not olx_data:
            print(f"   ⚠️ Nie udało się pobrać ceny z OLX - pomijam")
            stats['errors'] += 1
            continue
        
        olx_price = olx_data['price']
        print(f"   ✅ OLX zwraca: {olx_price} zł (źródło: {olx_data['source']})")
        
        # Porównaj ceny
        if olx_price == current_price:
            print(f"   ✓ Cena poprawna - brak zmian")
            continue
        
        if olx_price == previous_price:
            # ODWRÓCONA CENA!
            print(f"   🔄 WYKRYTO ODWRÓCONĄ CENĘ!")
            print(f"      OLX ma {olx_price} zł (previous_price)")
            print(f"      Baza ma {current_price} zł (current)")
            print(f"      Trend w bazie: {trend}")
            
            # Oblicz prawidłowy trend
            correct_trend = 'down' if olx_price < current_price else 'up'
            
            print(f"\n   🔧 NAPRAWA:")
            print(f"      current: {current_price} → {olx_price} zł")
            print(f"      previous: {previous_price} → {current_price} zł")
            print(f"      trend: {trend} → {correct_trend}")
            print(f"      source: {source} → JSON-LD (OLX)")
            
            if not dry_run:
                # Zamień ceny
                offer['price']['current'] = olx_price
                offer['price']['previous_price'] = current_price
                offer['price']['price_trend'] = correct_trend
                offer['price']['source'] = 'JSON-LD (OLX)'
                
                # Napraw historię - usuń błędny wpis i dodaj prawidłowy
                history = offer['price'].get('history', [])
                if len(history) >= 2:
                    # Usuń ostatni błędny wpis
                    if history[-1] == current_price:
                        history.pop()
                    # Upewnij się że pierwsza cena to previous, druga to current
                    if history[0] != current_price:
                        history.insert(0, current_price)
                    if olx_price not in history:
                        history.append(olx_price)
                    offer['price']['history'] = history
                    print(f"      Historia naprawiona: {history}")
            
            stats['fixed'] += 1
            fixed_offers.append({
                'id': offer_id,
                'address': offer['address']['full'],
                'old_current': current_price,
                'new_current': olx_price,
                'old_trend': trend,
                'new_trend': correct_trend
            })
        
        else:
            # Cena w OLX inna niż w bazie - ale nie jest odwrócona
            print(f"   ⚠️ OLX ma inną cenę ({olx_price} zł), ale to nie jest odwrócenie")
            print(f"      Może to być prawdziwa zmiana ceny - pomijam")
    
    # Podsumowanie
    print("\n" + "="*80)
    print("📊 PODSUMOWANIE NAPRAWY")
    print("="*80)
    print(f"✅ Sprawdzone oferty: {stats['checked']}")
    print(f"🔧 Naprawione odwrócenia: {stats['fixed']}")
    print(f"⏭️  Pominięte (nieaktywne): {stats['skipped_inactive']}")
    print(f"⏭️  Pominięte (brak zmian): {stats['skipped_no_history']}")
    print(f"❌ Błędy pobierania: {stats['errors']}")
    
    if fixed_offers:
        print(f"\n📋 NAPRAWIONE OFERTY:")
        for item in fixed_offers:
            print(f"   • {item['address']}")
            print(f"     Cena: {item['old_current']} → {item['new_current']} zł")
            print(f"     Trend: {item['old_trend']} → {item['new_trend']}")
    
    # Zapis
    if not dry_run and stats['fixed'] > 0:
        # Backup
        tz = pytz.timezone('Europe/Warsaw')
        timestamp = datetime.now(tz).strftime('%Y%m%d_%H%M%S')
        backup_path = f'{db_path}.backup_{timestamp}'
        
        print(f"\n💾 Tworzę backup: {backup_path}")
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        
        # Zapisz naprawioną bazę
        print(f"💾 Zapisuję naprawioną bazę...")
        with open(db_path, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Zapisano {backup_path}")
        print(f"✅ Zaktualizowano {db_path}")
    
    elif dry_run and stats['fixed'] > 0:
        print(f"\n⚠️ DRY RUN - zmiany NIE zostały zapisane")
        print(f"   Uruchom ponownie bez --dry-run aby zapisać zmiany")
    
    print("="*80 + "\n")
    
    return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Napraw odwrócone ceny w bazie danych')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Tylko pokaż zmiany bez zapisu')
    parser.add_argument('--db', default='data/offers.json',
                       help='Ścieżka do bazy danych')
    
    args = parser.parse_args()
    
    fix_reversed_prices(db_path=args.db, dry_run=args.dry_run)
