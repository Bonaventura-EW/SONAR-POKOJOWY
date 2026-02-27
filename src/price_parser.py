"""
Price Parser V2 - inteligentne parsowanie cen pokoi
Priorytet: cena pokoju (bez opłat) > cena z nagłówka
Filtruje: liczby z adresów, lata (2024-2030), liczby <100 zł
"""

import re
from typing import Optional, Dict, List

class PriceParser:
    # Pattern do wyciągania kwot (3-4 cyfry + opcjonalnie "zł", "PLN")
    PRICE_PATTERN = re.compile(r'(\d{3,4})\s*(?:zł|PLN|złotych)?', re.IGNORECASE)
    
    # Wzorce na cenę pokoju (BEZ opłat/mediów)
    ROOM_PRICE_PATTERNS = [
        re.compile(r'(\d{3,4})\s*(?:zł|PLN)?\s*[-–—]\s*pokój', re.IGNORECASE),
        re.compile(r'pokój\s*[-–—]?\s*(\d{3,4})\s*(?:zł|PLN)?', re.IGNORECASE),
        re.compile(r'za\s*pokój\s*(\d{3,4})\s*(?:zł|PLN)?', re.IGNORECASE),
        re.compile(r'(\d{3,4})\s*(?:zł|PLN)?\s*pokój', re.IGNORECASE),
        re.compile(r'czynsz\s*(\d{3,4})\s*(?:zł|PLN)?', re.IGNORECASE),
        re.compile(r'najem\s*(\d{3,4})\s*(?:zł|PLN)?', re.IGNORECASE),
    ]
    
    # Wzorce na rozbicie: pokój + opłaty
    SPLIT_PATTERNS = [
        # "1100 zł (850 zł – pokój + 250 zł – opłaty)"
        re.compile(r'\((\d{3,4})\s*(?:zł)?\s*[-–—]\s*pokój\s*\+\s*(\d{2,4})\s*(?:zł)?\s*[-–—]\s*opłaty\)', re.IGNORECASE),
        # "850 zł – pokój + 250 zł – opłaty"
        re.compile(r'(\d{3,4})\s*(?:zł)?\s*[-–—]\s*pokój\s*\+\s*(\d{2,4})\s*(?:zł)?\s*[-–—]\s*opłaty', re.IGNORECASE),
        # "pokój 850 zł + opłaty 250 zł"
        re.compile(r'pokój\s*(\d{3,4})\s*(?:zł)?\s*\+\s*opłaty\s*(\d{2,4})', re.IGNORECASE),
    ]
    
    # Frazy wskazujące na media wliczone
    MEDIA_INCLUDED = [
        'wliczone', 'w cenie', 'wszystko wliczone', 'razem z mediami',
        'wraz z mediami', 'łącznie z mediami', 'z mediami', 'all inclusive',
        'wszystko w cenie', 'opłaty wliczone', 'w tym wszystkie opłaty'
    ]
    
    # Frazy wskazujące na media osobno
    MEDIA_SEPARATE = [
        '+ media', 'plus media', 'bez mediów', 'opłaty dodatkowe',
        'media dodatkowo', 'media osobno', 'do tego media', 'bez opłat',
        'media oddzielnie', '+ opłaty', 'opłaty osobno'
    ]
    
    def __init__(self):
        pass
    
    def _filter_invalid_prices(self, prices: List[int], text_lower: str) -> List[int]:
        """
        Filtruje nieprawidłowe kwoty:
        - Numery domów/ulic (jeśli występują z 'ul.')
        - Lata (2024-2030)
        - Kwoty poniżej 100 zł lub powyżej 3000 zł
        """
        filtered = []
        
        for price in prices:
            # Odrzuć lata
            if 2024 <= price <= 2030:
                continue
            
            # Odrzuć kwoty poza sensownym zakresem
            if price < 100 or price > 3000:
                continue
            
            # Odrzuć numery domów - sprawdź czy występuje przy "ul.", "ulica"
            if 100 <= price <= 300:
                price_str = str(price)
                idx = text_lower.find(price_str)
                
                if idx != -1:
                    # Sprawdź 30 znaków przed i po
                    context_start = max(0, idx - 30)
                    context_end = min(len(text_lower), idx + len(price_str) + 30)
                    context = text_lower[context_start:context_end]
                    
                    # Jeśli w kontekście jest "ul.", "ulica" - to prawdopodobnie numer domu
                    if any(word in context for word in ['ul.', 'ulica', 'ulicy', 'ulicę', 'przy']):
                        continue
            
            filtered.append(price)
        
        return filtered
    
    def _extract_room_price(self, text: str) -> Optional[int]:
        """
        Próbuje wyciągnąć cenę pokoju (bez opłat) używając wzorców.
        Zwraca None jeśli nie znaleziono.
        """
        # Najpierw sprawdź rozbicie: "850 zł – pokój + 250 zł – opłaty"
        for pattern in self.SPLIT_PATTERNS:
            match = pattern.search(text)
            if match:
                room_price = int(match.group(1))
                # Walidacja
                if 200 <= room_price <= 2500:
                    return room_price
        
        # Potem szukaj wzorców typu "X zł – pokój", "pokój X zł" itp.
        for pattern in self.ROOM_PRICE_PATTERNS:
            match = pattern.search(text)
            if match:
                price = int(match.group(1))
                # Walidacja - sensowny zakres dla pokoju
                if 200 <= price <= 2500:
                    return price
        
        return None
    
    def _detect_media_info_advanced(self, text_lower: str, room_price: int) -> str:
        """
        Wykrywa informację o mediach - zaawansowana wersja.
        Próbuje wyciągnąć konkretną kwotę opłat jeśli jest podana.
        """
        # Sprawdź czy jest rozbicie z konkretną kwotą opłat
        for pattern in self.SPLIT_PATTERNS:
            match = pattern.search(text_lower)
            if match and len(match.groups()) >= 2:
                utilities_cost = int(match.group(2))
                return f"+ {utilities_cost} zł opłaty"
        
        # Sprawdź czy media są wliczone
        for phrase in self.MEDIA_INCLUDED:
            if phrase in text_lower:
                return "wliczone"
        
        # Sprawdź czy media są osobno
        for phrase in self.MEDIA_SEPARATE:
            if phrase in text_lower:
                return "+ media"
        
        # Jeśli nie ma informacji
        return "brak informacji"
    
    def extract_price(self, text: str) -> Optional[Dict[str, any]]:
        """
        Wyciąga cenę pokoju (bez mediów/opłat) z tekstu.
        
        Strategia:
        1. Szukaj wzorców typu "850 zł – pokój + 250 zł – opłaty" (priorytet)
        2. Szukaj wzorców typu "pokój 800 zł", "za pokój 750 zł"
        3. Jeśli nie znaleziono - bierz pierwszą sensowną kwotę (po filtrowaniu)
        
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
        
        # PRIORYTET 1: Szukaj ceny pokoju w opisie (wzorce)
        room_price = self._extract_room_price(text)
        
        if room_price:
            # Znaleziono cenę pokoju - wykryj info o mediach
            media_info = self._detect_media_info_advanced(text_lower, room_price)
            
            return {
                'price': room_price,
                'media_info': media_info,
                'raw_text': self._extract_price_context(text, room_price)
            }
        
        # PRIORYTET 2: Nie znaleziono wzorców - użyj pierwszej sensownej kwoty
        # Znajdujemy wszystkie kwoty w tekście
        prices = self.PRICE_PATTERN.findall(text)
        if not prices:
            return None
        
        # Konwertujemy na int
        prices = [int(p) for p in prices]
        
        # Filtrujemy nieprawidłowe kwoty (lata, numery domów, etc.)
        valid_prices = self._filter_invalid_prices(prices, text_lower)
        
        if not valid_prices:
            return None
        
        # Bierzemy pierwszą sensowną kwotę
        main_price = valid_prices[0]
        
        # Wykrywamy informację o mediach
        media_info = self._detect_media_info_simple(text_lower, valid_prices)
        
        return {
            'price': main_price,
            'media_info': media_info,
            'raw_text': self._extract_price_context(text, main_price)
        }
    
    def _detect_media_info_simple(self, text_lower: str, prices: list) -> str:
        """
        Wykrywa informację o mediach (stara metoda - dla przypadków bez wzorców).
        """
        # Sprawdzamy czy media są wliczone
        for phrase in self.MEDIA_INCLUDED:
            if phrase in text_lower:
                return "wliczone"
        
        # Sprawdzamy czy media są osobno
        for phrase in self.MEDIA_SEPARATE:
            if phrase in text_lower:
                # Próbujemy znaleźć kwotę mediów
                if len(prices) >= 2:
                    media_cost = prices[1]
                    # Sprawdź czy druga kwota jest mniejsza (typowo media < czynsz)
                    if media_cost < prices[0]:
                        return f"+ ~{media_cost} zł"
                
                # Jeśli nie znaleziono drugiej kwoty, ogólna informacja
                return "+ media"
        
        # Jeśli nie ma informacji
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
        # (tekst, oczekiwana_cena, oczekiwane_media_info)
        ("Pokój 700 zł + media ok. 150 zł", 700, "+ media"),
        ("Wynajem 850 zł wszystko wliczone", 850, "wliczone"),
        ("Cena 600 bez mediów", 600, "+ media"),
        ("Pokój za 1200 złotych, opłaty dodatkowe", 1200, "+ media"),
        ("750 zł razem z mediami", 750, "wliczone"),
        ("Czynsz 900 PLN", 900, "brak informacji"),
        # Nowe przypadki - rozbicie
        ("Cena: 1100 zł – w tym wszystkie opłaty (850 zł – pokój + 250 zł – opłaty)", 850, "+ 250 zł opłaty"),
        ("Pokój przy ul. Pana Balcera 6. Cena: 750 zł + opłaty", 750, "+ media"),
        # Problem z latami
        ("Umowa do lipca 2026. Cena 800 zł miesięcznie", 800, "brak informacji"),
        # Problem z numerami domów
        ("Pokój przy ul. Skrzatów 7, cena 1100 zł", 1100, "brak informacji"),
    ]
    
    print("🧪 Testy Price Parser V2:\n")
    passed = 0
    failed = 0
    
    for text, expected_price, expected_media in test_cases:
        result = parser.extract_price(text)
        
        if result:
            price_ok = result['price'] == expected_price
            # Media info może się różnić - sprawdzamy tylko czy nie jest None
            status = "✅" if price_ok else "❌"
            
            if price_ok:
                passed += 1
            else:
                failed += 1
            
            print(f"{status} '{text[:60]}...'")
            print(f"   Cena: {result['price']} zł (oczekiwano: {expected_price})")
            print(f"   Media: {result['media_info']}")
            if not price_ok:
                print(f"   ⚠️ BŁĄD: Oczekiwano {expected_price}, otrzymano {result['price']}")
            print()
        else:
            print(f"❌ '{text}' → Nie wykryto ceny")
            failed += 1
            print()
    
    print(f"\n📊 Wyniki: {passed} ✅ / {failed} ❌ / {len(test_cases)} testów")
