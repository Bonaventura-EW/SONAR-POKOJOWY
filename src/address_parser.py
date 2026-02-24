"""
Address Parser - ekstrakcja adresów z opisów ogłoszeń
Akceptuje formaty:
- "Narutowicza 5" (bez "ul.")
- "Rynek 8" (bez określenia typu)
- "al. Andersa 13 lok. 5"
- "ul. Racławickie 12/2"
"""

import re
from typing import Optional, Dict

class AddressParser:
    # Prefiksy ulic (opcjonalne)
    PREFIXES = r'(?:ul\.|ulica|al\.|aleja|aleje|pl\.|plac|os\.|osiedle)?'
    
    # Główny pattern adresu
    # Dopuszcza: 1-2 słowa z wielkimi literami (np. "Narutowicza", "Aleje Racławickie")
    # Numer: cyfry, opcjonalnie /cyfry, opcjonalnie lok. cyfry
    ADDRESS_PATTERN = re.compile(
        rf'{PREFIXES}\s*([A-ZŚĆŁĄĘÓŻŹŃ][a-zśćłąęóżźń]+(?:\s+[A-ZŚĆŁĄĘÓŻŹŃ][a-zśćłąęóżźń]+)?)\s+(\d+(?:/\d+)?(?:\s+lok\.\s+\d+)?)',
        re.UNICODE
    )
    
    def __init__(self):
        pass
    
    def extract_address(self, text: str) -> Optional[Dict[str, str]]:
        """
        Wyciąga adres z tekstu.
        
        Args:
            text: Tekst do przeszukania (tytuł + opis)
            
        Returns:
            Dict z kluczami: street, number, full lub None jeśli nie znaleziono
        """
        if not text:
            return None
        
        # Sprawdź czy tekst zawiera "X metrów od" - to NIE jest adres
        if re.search(r'\d+\s*metr[oó]w\s+od', text, re.IGNORECASE):
            return None
        
        # Słowa które NIE mogą być nazwą ulicy
        excluded_words_lower = {'pokój', 'przy', 'obok', 'blisko', 'centrum', 'okolice', 'minut', 'minutę', 'rok', 'lata'}
        
        # Szukamy WSZYSTKICH dopasowań
        matches = self.ADDRESS_PATTERN.finditer(text)
        
        for match in matches:
            street = match.group(1).strip()
            number = match.group(2).strip()
            
            # Sprawdź czy którekolwiek słowo w nazwie ulicy NIE jest słowem wykluczonym
            street_words = street.split()
            is_valid = True
            
            for word in street_words:
                if word.lower() in excluded_words_lower:
                    is_valid = False
                    break
            
            if not is_valid:
                continue
            
            # Wyciągnij główny numer (przed / lub lok.)
            main_number = number.split('/')[0].split()[0]
            
            # Sprawdź czy numer jest rozsądny (max 250)
            try:
                num_value = int(main_number)
                if num_value > 250:
                    continue  # Ignoruj, to prawdopodobnie cena
            except ValueError:
                pass  # Jeśli nie można sparsować, to OK (może być "12a")
            
            # Normalizacja: usuwamy wielokrotne spacje
            street = ' '.join(street.split())
            number = ' '.join(number.split())
            
            return {
                'street': street,
                'number': number,
                'full': f"{street} {number}"
            }
        
        return None
    
    def validate_lublin_address(self, address: str) -> bool:
        """
        Sprawdza czy adres wygląda na prawdziwy adres w Lublinie.
        Filtruje oczywiste błędy typu "123 abc" itp.
        
        Args:
            address: Pełny adres do walidacji
            
        Returns:
            True jeśli adres wygląda poprawnie
        """
        if not address:
            return False
        
        # Musi zawierać przynajmniej jedną literę i jedną cyfrę
        has_letter = any(c.isalpha() for c in address)
        has_digit = any(c.isdigit() for c in address)
        
        if not (has_letter and has_digit):
            return False
        
        # Nie może być zbyt krótki (min. "A 1")
        if len(address) < 3:
            return False
        
        return True


# Testy jednostkowe
if __name__ == "__main__":
    parser = AddressParser()
    
    test_cases = [
        ("Pokój przy Narutowicza 5, umeblowany", "Narutowicza 5"),
        ("ul. Rynek 8, centrum", "Rynek 8"),
        ("al. Andersa 13 lok. 5", "Andersa 13 lok. 5"),
        ("Aleje Racławickie 12/2", "Aleje Racławickie 12/2"),  # Poprawna 2-składnikowa nazwa
        ("Os. Przyjaźni 23", "Przyjaźni 23"),
        ("Czechów okolice", None),  # brak numeru
        ("Przy rondzie Chatki Żaka", None),  # brak numeru
        ("5 minut od centrum", None),  # nie adres
    ]
    
    print("🧪 Testy Address Parser:\n")
    for text, expected in test_cases:
        result = parser.extract_address(text)
        extracted = result['full'] if result else None
        status = "✅" if extracted == expected else "❌"
        print(f"{status} '{text}' → {extracted}")
        if extracted != expected:
            print(f"   Oczekiwano: {expected}")
