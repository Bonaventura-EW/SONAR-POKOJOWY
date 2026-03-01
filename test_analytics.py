#!/usr/bin/env python3
"""
Test diagnostyczny dla analytics.html
"""

import json
import os
from datetime import datetime

def check_analytics_issues():
    """Sprawdza potencjalne problemy w analytics.html"""
    
    print("🔍 DIAGNOSTYKA ANALYTICS.HTML\n")
    print("=" * 70)
    
    issues = []
    warnings = []
    
    # 1. Sprawdź czy pliki istnieją
    print("\n📁 SPRAWDZANIE PLIKÓW:")
    files_to_check = [
        'docs/analytics.html',
        'docs/data.json'
    ]
    
    for file in files_to_check:
        if os.path.exists(file):
            print(f"   ✅ {file} - istnieje")
        else:
            issues.append(f"Brak pliku: {file}")
            print(f"   ❌ {file} - BRAK")
    
    # 2. Sprawdź data.json
    print("\n📊 SPRAWDZANIE DANYCH:")
    try:
        with open('docs/data.json', 'r') as f:
            data = json.load(f)
        
        markers = data.get('markers', [])
        print(f"   ✅ Liczba markerów: {len(markers)}")
        
        if not markers:
            issues.append("Brak markerów w data.json")
            return 1
        
        # Zbierz oferty
        all_offers = []
        for marker in markers:
            for offer in marker.get('offers', []):
                if offer.get('active'):
                    all_offers.append(offer)
        
        print(f"   ✅ Aktywnych ofert: {len(all_offers)}")
        
        # 3. Sprawdź format dat
        print("\n📅 SPRAWDZANIE FORMATÓW DAT:")
        date_formats = set()
        invalid_dates = []
        
        for offer in all_offers[:20]:  # Sprawdź pierwsze 20
            first_seen = offer.get('first_seen', '')
            date_formats.add(first_seen)
            
            # Testuj parsowanie
            try:
                parts = first_seen.split('.')
                if len(parts) == 3:
                    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                    test_date = datetime(year, month, day)
                else:
                    invalid_dates.append((offer['id'], first_seen))
            except Exception as e:
                invalid_dates.append((offer['id'], first_seen, str(e)))
        
        if len(date_formats) <= 3:
            print(f"   ✅ Formaty dat: {list(date_formats)[:3]}")
        else:
            warnings.append(f"Wykryto {len(date_formats)} różnych formatów dat")
        
        if invalid_dates:
            warnings.append(f"Znaleziono {len(invalid_dates)} ofert z nieprawidłowymi datami")
            for invalid in invalid_dates[:3]:
                print(f"   ⚠️  Nieprawidłowa data: {invalid}")
        
        # 4. Sprawdź ceny
        print("\n💰 SPRAWDZANIE CEN:")
        prices = [o.get('price', 0) for o in all_offers if o.get('price')]
        
        if prices:
            min_price = min(prices)
            max_price = max(prices)
            avg_price = sum(prices) / len(prices)
            
            print(f"   ✅ Zakres cen: {min_price} - {max_price} zł")
            print(f"   ✅ Średnia cena: {avg_price:.0f} zł")
            
            # Sprawdź podejrzane ceny
            suspicious = [p for p in prices if p < 200 or p > 3000]
            if suspicious:
                warnings.append(f"Wykryto {len(suspicious)} podejrzanych cen: {suspicious[:5]}")
        
        # 5. Sprawdź HTML
        print("\n🌐 SPRAWDZANIE HTML:")
        try:
            with open('docs/analytics.html', 'r') as f:
                html_content = f.read()
            
            required_elements = [
                'id="priceChart"',
                'id="newOffersChart"',
                'id="priceDistribution"',
                'parseDate',
                'createPriceChart',
                'createNewOffersChart',
                'createPriceDistribution',
                'Chart.js'
            ]
            
            for element in required_elements:
                if element in html_content:
                    print(f"   ✅ Element '{element}' - obecny")
                else:
                    issues.append(f"HTML - brak elementu: {element}")
                    print(f"   ❌ Element '{element}' - BRAK")
        
        except FileNotFoundError:
            issues.append("Plik analytics.html nie istnieje")
    
    except json.JSONDecodeError as e:
        issues.append(f"Błąd parsowania data.json: {e}")
    except FileNotFoundError:
        issues.append("Plik data.json nie istnieje")
    
    # 6. Podsumowanie
    print("\n" + "=" * 70)
    print(f"\n📊 PODSUMOWANIE:")
    
    if not issues and not warnings:
        print("\n✅ Wszystko wygląda dobrze!")
        return 0
    
    if warnings:
        print(f"\n⚠️  OSTRZEŻENIA ({len(warnings)}):")
        for i, warning in enumerate(warnings, 1):
            print(f"   {i}. {warning}")
    
    if issues:
        print(f"\n❌ BŁĘDY ({len(issues)}):")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
        return 1
    
    return 0

if __name__ == "__main__":
    os.chdir('/tmp/SONAR-POKOJOWY')
    exit(check_analytics_issues())
