#!/usr/bin/env python3
"""
Test integracyjny - sprawdza cały flow przetwarzania ofert
z nowymi cenami z JSON-LD
"""

import sys
sys.path.insert(0, 'src')

from main import SonarPokojowy

def test_integration():
    """Test pełnego flow dla problematycznych ogłoszeń"""
    
    print("🧪 TEST INTEGRACYJNY - CAŁY FLOW PRZETWARZANIA\n")
    print("=" * 70)
    
    # Symuluj dwie surowe oferty z problematycznymi cenami
    monitor = SonarPokojowy()
    
    # Test 1: Oferta która była wyświetlana jako 150 zł zamiast 700 zł
    test_offer_1 = {
        'url': 'https://www.olx.pl/d/oferta/wynajme-od-zaraz-pokoj-CID3-ID17pIVy.html',
        'title': 'Wynajmę od zaraz pokój!',
        'description': 'Wynajmę pokój od zaraz\n\nLublin ul. Rolna 2\nCZYNSZ plus dodatkowo płatne MEDIA',
        'price_raw': '700 zł',
        'official_price': 700,
        'official_price_raw': '700 zł (JSON-LD)',
        'price_source': 'json-ld'
    }
    
    print("\n📝 Test 1: Przetwarzanie oferty z JSON-LD (700 zł)")
    print(f"   URL: {test_offer_1['url']}")
    
    processed = monitor._process_offer(test_offer_1)
    
    assert processed is not None, "Oferta odrzucona przez system"
    
    actual_price = processed['price']['current']
    price_source = processed['price'].get('source', 'unknown')
    media_info = processed['price']['media_info']
    
    assert actual_price == 700, f"Otrzymano {actual_price} zł, oczekiwano 700 zł"
    
    print(f"   ✅ SUKCES: Cena {actual_price} zł")
    print(f"   Źródło: {price_source}")
    print(f"   Media: {media_info}")
    
    print("\n" + "=" * 70)
    print("\n✅ Test integracyjny zakończony pomyślnie!")
    print("\n💡 NASTĘPNE KROKI:")
    print("   1. GitHub Actions automatycznie uruchomi skanowanie za ~8h")
    print("   2. Lub możesz uruchomić ręcznie: python3 src/main.py")
    print("   3. Sprawdź zaktualizowane ceny na mapie: https://bonaventura-ew.github.io/SONAR-POKOJOWY/")

if __name__ == "__main__":
    test_integration()
