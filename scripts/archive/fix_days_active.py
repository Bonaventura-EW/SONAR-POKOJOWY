#!/usr/bin/env python3
"""
Skrypt naprawczy - przelicza days_active dla wszystkich ofert w bazie danych.
Uruchom jednorazowo po wdrożeniu nowej logiki.
"""

import json
from datetime import datetime
from pathlib import Path


def fix_days_active(data_file: Path):
    """
    Przelicza days_active dla wszystkich ofert w bazie.
    """
    print("🔧 Naprawa days_active w bazie danych...")
    print(f"📁 Plik: {data_file}\n")
    
    # Wczytaj bazę
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    offers = data.get('offers', [])
    print(f"📊 Znaleziono {len(offers)} ofert\n")
    
    # Statystyki
    fixed_count = 0
    error_count = 0
    stats = {
        'days_0': 0,
        'days_1_3': 0,
        'days_4_7': 0,
        'days_8_plus': 0
    }
    
    # Przelicz days_active dla każdej oferty
    for offer in offers:
        try:
            first_seen = datetime.fromisoformat(offer['first_seen'].split('+')[0] if '+' in offer['first_seen'] else offer['first_seen'])
            last_seen = datetime.fromisoformat(offer['last_seen'].split('+')[0] if '+' in offer['last_seen'] else offer['last_seen'])
            
            old_days = offer.get('days_active', 0)
            new_days = (last_seen - first_seen).days
            
            offer['days_active'] = new_days
            
            # Zlicz statystyki
            if new_days == 0:
                stats['days_0'] += 1
            elif 1 <= new_days <= 3:
                stats['days_1_3'] += 1
            elif 4 <= new_days <= 7:
                stats['days_4_7'] += 1
            else:
                stats['days_8_plus'] += 1
            
            if old_days != new_days:
                fixed_count += 1
                if fixed_count <= 5:  # Pokaż pierwsze 5 przykładów
                    print(f"   ✓ {offer['id'][:20]}: {old_days} → {new_days} dni")
        
        except (ValueError, KeyError) as e:
            error_count += 1
            print(f"   ⚠️ Błąd dla {offer.get('id', 'unknown')}: {e}")
    
    # Zapisz naprawioną bazę
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print("📊 PODSUMOWANIE NAPRAWY")
    print(f"{'='*60}")
    print(f"✅ Naprawiono: {fixed_count} ofert")
    print(f"❌ Błędy: {error_count}")
    print(f"\n📈 Rozkład dni aktywności:")
    print(f"   0 dni (nowe): {stats['days_0']}")
    print(f"   1-3 dni: {stats['days_1_3']}")
    print(f"   4-7 dni: {stats['days_4_7']}")
    print(f"   8+ dni: {stats['days_8_plus']}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    data_file = Path(__file__).parent / 'data' / 'offers.json'
    
    if not data_file.exists():
        print(f"❌ Plik {data_file} nie istnieje!")
        exit(1)
    
    fix_days_active(data_file)
    print("✅ Gotowe! Możesz teraz wygenerować nową mapę.")
