#!/usr/bin/env python3
"""
Test naprawy ekstrakcji cen z JSON-LD
Sprawdza dwa problematyczne ogłoszenia
"""

import sys
sys.path.insert(0, 'src')

from scraper import OLXScraper

def test_price_extraction():
    """Test dwóch problematycznych ogłoszeń"""
    
    test_urls = [
        {
            'url': 'https://www.olx.pl/d/oferta/wynajme-od-zaraz-pokoj-CID3-ID17pIVy.html',
            'expected_price': 700,
            'description': 'Pokój 700 zł (był błędnie wyświetlany jako 150 zł)'
        },
        {
            'url': 'https://www.olx.pl/d/oferta/nowe-mieszkanie-25m2-super-wyposazone-blisko-centrum-i-uczelni-CID3-IDUXwYh.html',
            'expected_price': 2400,
            'description': 'Mieszkanie 2400 zł (był błędnie wyświetlany jako 144 zł)'
        }
    ]
    
    print("🧪 TEST NAPRAWY EKSTRAKCJI CEN Z JSON-LD\n")
    print("=" * 70)
    
    scraper = OLXScraper(delay_range=(1, 2))
    
    passed = 0
    failed = 0
    
    for i, test_case in enumerate(test_urls, 1):
        print(f"\n📝 Test {i}/{len(test_urls)}: {test_case['description']}")
        print(f"   URL: {test_case['url']}")
        
        # Pobierz szczegóły
        details = scraper.fetch_offer_details(test_case['url'])
        
        if not details:
            print(f"   ❌ BŁĄD: Nie udało się pobrać szczegółów")
            failed += 1
            continue
        
        actual_price = details.get('official_price')
        expected_price = test_case['expected_price']
        price_source = details.get('price_source', 'unknown')
        
        if actual_price == expected_price:
            print(f"   ✅ SUKCES: Cena {actual_price} zł (źródło: {price_source})")
            passed += 1
        else:
            print(f"   ❌ BŁĄD: Otrzymano {actual_price} zł, oczekiwano {expected_price} zł")
            print(f"   Źródło: {price_source}")
            print(f"   Raw: {details.get('official_price_raw')}")
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"\n📊 WYNIKI TESTÓW:")
    print(f"   ✅ Passed: {passed}/{len(test_urls)}")
    print(f"   ❌ Failed: {failed}/{len(test_urls)}")
    
    if failed == 0:
        print("\n🎉 Wszystkie testy przeszły pomyślnie!")
        return 0
    else:
        print("\n⚠️ Niektóre testy nie przeszły")
        return 1

if __name__ == "__main__":
    exit(test_price_extraction())
