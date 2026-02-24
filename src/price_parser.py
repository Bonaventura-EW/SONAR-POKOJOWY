"""
Price Parser - inteligentne parsowanie cen bez mediów
Wykrywa: "700 zł + media", "850 wszystko wliczone", "600 bez mediów"
"""

import re
from typing import Optional, Dict

class PriceParser:
    # Pattern do wyciągania kwot (np. 700, 1200, 850 zł)
    PRICE_PATTERN = re.compile(r'(\d{3,4})\s*(?:zł|PLN|złotych)?', re.IGNORECASE)
    
    # Frazy wskazujące na media wliczone
    MEDIA_INCLUDED = [
        'wliczone', 'w cenie', 'wszystko wliczone', 'razem z mediami',
        'wraz z mediami', 'łącznie z mediami', 'z mediami'
    ]
    
    # Frazy wskazujące na media osobno
    MEDIA_SEPARATE = [
        '+ media', 'plus media', 'bez mediów', 'opłaty dodatkowe',
        'media dodatkowo', 'media osobno', 'do tego media'
    ]
    
    def __init__(self):
        pass
    
    def extract_price(self, text: str) -> Optional[Dict[str, any]]:
        """
        Wyciąga cenę pokoju (bez mediów) z tekstu.
        
        Args:
            text: Tekst ogłoszenia (tytuł + opis)
            
        Returns:
            Dict z kluczami:
            - price: int - cena pokoju
            - media_info: str - informacja o mediach
            - raw_text: str - oryginalny fragment tekstu
        """
        if not text:
            return None
        
        text_lower = text.lower()
        
        # Znajdujemy wszystkie kwoty w tekście
        prices = self.PRICE_PATTERN.findall(text)
        if not prices:
            return None
        
        # Konwertujemy na int
        prices = [int(p) for p in prices]
        
        # Filtrujemy kwoty poniżej 100 zł (prawdopodobnie nie cena pokoju/mediów)
        # i powyżej 3000 zł (prawdopodobnie błąd lub cała kawalerka)
        prices = [p for p in prices if 100 <= p <= 3000]
        
        if not prices:
            return None
        
        # Główna cena to zazwyczaj pierwsza lub najwyższa
        main_price = prices[0]
        
        # Wykrywamy informację o mediach
        media_info = self._detect_media_info(text_lower, prices)
        
        return {
            'price': main_price,
            'media_info': media_info,
            'raw_text': self._extract_price_context(text, main_price)
        }
    
    def _detect_media_info(self, text_lower: str, prices: list) -> str:
        """
        Wykrywa informację o mediach na podstawie fraz w tekście.
        """
        # Sprawdzamy czy media są wliczone
        for phrase in self.MEDIA_INCLUDED:
            if phrase in text_lower:
                return "wliczone"
        
        # Sprawdzamy czy media są osobno
        for phrase in self.MEDIA_SEPARATE:
            if phrase in text_lower:
                # Próbujemy znaleźć kwotę mediów
                # Jeśli są 2+ kwoty I jest fraza "+ media" lub "bez mediów"
                if len(prices) >= 2:
                    # Druga kwota to prawdopodobnie media
                    media_cost = prices[1]
                    # Sprawdź czy druga kwota jest mniejsza (typowo media < czynsz)
                    if media_cost < prices[0]:
                        return f"+ media (~{media_cost} zł)"
                
                # Jeśli nie znaleziono drugiej kwoty, ogólna informacja
                return "+ media"
        
        # Jeśli nie ma informacji, zakładamy że nie wiadomo
        return "brak informacji"
    
    def _extract_price_context(self, text: str, price: int) -> str:
        """
        Wyciąga fragment tekstu wokół ceny (kontekst).
        """
        price_str = str(price)
        idx = text.find(price_str)
        
        if idx == -1:
            return text[:100]  # Pierwsze 100 znaków
        
        # Wyciągamy +/- 50 znaków wokół ceny
        start = max(0, idx - 50)
        end = min(len(text), idx + len(price_str) + 50)
        
        context = text[start:end].strip()
        
        if start > 0:
            context = "..." + context
        if end < len(text):
            context = context + "..."
        
        return context


# Testy jednostkowe
if __name__ == "__main__":
    parser = PriceParser()
    
    test_cases = [
        ("Pokój 700 zł + media ok. 150 zł", 700, "+ media (~150 zł)"),
        ("Wynajem 850 zł wszystko wliczone", 850, "wliczone"),
        ("Cena 600 bez mediów", 600, "+ media"),
        ("Pokój za 1200 złotych, opłaty dodatkowe", 1200, "+ media"),
        ("750 zł razem z mediami", 750, "wliczone"),
        ("Czynsz 900 PLN", 900, "brak informacji"),
    ]
    
    print("🧪 Testy Price Parser:\n")
    for text, expected_price, expected_media in test_cases:
        result = parser.extract_price(text)
        
        if result:
            price_ok = result['price'] == expected_price
            media_ok = result['media_info'] == expected_media
            status = "✅" if (price_ok and media_ok) else "❌"
            
            print(f"{status} '{text}'")
            print(f"   Cena: {result['price']} zł (oczekiwano: {expected_price})")
            print(f"   Media: {result['media_info']} (oczekiwano: {expected_media})")
        else:
            print(f"❌ '{text}' → Nie wykryto ceny")
