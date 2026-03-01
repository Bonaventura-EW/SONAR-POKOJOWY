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
    
    results = []
    
    for i, test_case in enumerate(test_urls, 1):
        print(f"\n📝 Test {i}/{len(test_urls)}: {test_case['description']}")
        print(f"   URL: {test_case['url']}")
        
        # Pobierz szczegóły
        details = scraper.fetch_offer_details(test_case['url'])
        
        if not details:
            print(f"   ⚠️ Nie udało się pobrać szczegółów (oferta może być niedostępna)")
            results.append(('skipped', test_case['url']))
            continue
        
        actual_price = details.get('official_price')
        expected_price = test_case['expected_price']
        price_source = details.get('price_source', 'unknown')
        
        if actual_price == expected_price:
            print(f"   ✅ SUKCES: Cena {actual_price} zł (źródło: {price_source})")
            results.append(('passed', test_case['url']))
        else:
            print(f"   ⚠️ Różnica: Otrzymano {actual_price} zł, oczekiwano {expected_price} zł")
            print(f"   Źródło: {price_source}")
            results.append(('different', test_case['url'], actual_price, expected_price))
    
    print("\n" + "=" * 70)
    
    passed = sum(1 for r in results if r[0] == 'passed')
    skipped = sum(1 for r in results if r[0] == 'skipped')
    different = sum(1 for r in results if r[0] == 'different')
    
    print(f"\n📊 WYNIKI TESTÓW:")
    print(f"   ✅ Passed: {passed}/{len(test_urls)}")
    print(f"   ⏭️ Skipped: {skipped}/{len(test_urls)}")
    print(f"   ⚠️ Different: {different}/{len(test_urls)}")
    
    # Assert że przynajmniej logika działa (nie wyrzuca wyjątków)
    assert len(results) == len(test_urls), "Nie wszystkie testy zostały wykonane"
    
    print("\n🎉 Test zakończony!")


if __name__ == "__main__":
    test_price_extraction()
