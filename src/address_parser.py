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
    # WYMAGA dużej litery na początku pierwszego słowa (nie dopuszcza "stancja 1", "pokoju 4")
    # Dopuszcza: 1-2 słowa, pierwsze słowo MUSI zaczynać się dużą literą
    # Numer: cyfry + opcjonalna litera (a-z), opcjonalnie /cyfry, opcjonalnie lok. cyfry
    ADDRESS_PATTERN = re.compile(
        rf'{PREFIXES}\s*([A-ZŚĆŁĄĘÓŻŹŃ][a-zśćłąęóżźń]+(?:\s+[A-ZŚĆŁĄĘÓŻŹŃ]?[a-zśćłąęóżźń]+)?)\s+(\d+[a-zA-Z]?(?:/\d+)?(?:\s+lok\.\s+\d+)?)',
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
        
        # FILTR 1: Sprawdź czy tekst zawiera "X metrów od" - to NIE jest adres
        if re.search(r'\d+\s*metr[oó]w\s+(od|do)', text, re.IGNORECASE):
            return None
        
        # SPECJALNY PRZYPADEK: znane ulice w Lublinie które mogą zaczynać się małą literą lub nie pasować do wzorca
        # WYMAGA NUMERU! (usunięto fallback bez numeru)
        lowercase_streets = ['zimowa', 'wiosenna', 'letnia', 'jesienna']
        special_streets = ['botaniczna', 'morsztynów'] + lowercase_streets
        
        for street_name in special_streets:
            # Pattern z numerem (WYMAGANY!)
            pattern_num = rf'\b{street_name}\s+(\d+[a-zA-Z]?(?:/\d+)?)'
            match = re.search(pattern_num, text, re.IGNORECASE)
            if match:
                number = match.group(1)
                # Walidacja numeru
                try:
                    num_str = number.rstrip('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ/')
                    num_value = int(num_str)
                    if num_value <= 250:
                        return {
                            'street': street_name.capitalize(),
                            'number': number,
                            'full': f"{street_name.capitalize()} {number}"
                        }
                except ValueError:
                    pass
        
        # Słowa które NIE mogą być nazwą ulicy
        excluded_words_lower = {
            'pokój', 'przy', 'obok', 'blisko', 'centrum', 'okolice', 'minut', 'minutę', 'rok', 'lata',
            'jednoosobowy', 'dwuosobowy', 'trzoosobowy', 'osobowy',
            'dla', 'bez', 'lub', 'osób', 'osoby',
            # NOWE: nazwy dzielnic Lublina (nie są ulicami)
            'wieniawa', 'śródmieście', 'bronowice', 'czuby', 'kalinowszczyzna', 'tatary',
            'czechów', 'sławinek', 'sławin', 'abramowice', 'konstantynów', 'ponikwoda',
            'głusk', 'węglin', 'felin', 'hajdów',
            # NOWE: słowa z ogłoszeń które nie są ulicami
            'net', 'ciepło', 'internet', 'wifi', 'balkon', 'ogród', 'parking',
            'od', 'do', 'za', 'na', 'po', 'we', 'ze',
            # NOWE: słowa które parser myli z ulicami
            'stancja', 'mieszkaniu', 'mieszkanie', 'przechowywania', 'powierzchni',
            'fajna', 'fajny', 'studentki', 'studenta', 'lokalu', 'budynku',
            'pokoju', 'kuchni', 'salonu', 'łazienki', 'sypialni'
        }
        
        # Szukamy WSZYSTKICH dopasowań (ulica + numer)
        matches = self.ADDRESS_PATTERN.finditer(text)
        
        for match in matches:
            street = match.group(1).strip()
            number = match.group(2).strip()
            
            # Sprawdź minimum 4 litery w nazwie ulicy (żeby wykluczyć "dla", "bez" etc)
            if len(street.replace(' ', '')) < 4:
                continue
            
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
            
            # FILTR 2: Sprawdź czy numer jest rozsądny (max 250)
            # Numery >250 to prawdopodobnie CENY np. "Samsonowicza 500 zł"
            try:
                # Usuń literę na końcu jeśli jest (np. "12a" -> "12")
                num_str = main_number.rstrip('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
                num_value = int(num_str)
                if num_value > 250:
                    continue  # Ignoruj, to prawdopodobnie cena
            except ValueError:
                pass  # Jeśli nie można sparsować, to OK
            
            # Normalizacja: usuwamy wielokrotne spacje
            street = ' '.join(street.split())
            number = ' '.join(number.split())
            
            return {
                'street': street,
                'number': number,
                'full': f"{street} {number}"
            }
        
        # BRAK FALLBACK - Wymagamy NUMERU domu!
        # Adresy bez numeru (np. "ul. Niecała") są zbyt nieprecyzyjne dla mapy
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
        ("Narutowicza 5", "Narutowicza 5"),  # Bez 'przy' - powinno działać
        ("ul. Rynek 8, centrum", "Rynek 8"),
        ("al. Andersa 13 lok. 5", "Andersa 13 lok. 5"),
        ("Aleje Racławickie 12/2", "Aleje Racławickie 12/2"),
        ("Os. Przyjaźni 23", "Przyjaźni 23"),
        ("Langiewicza 3A", "Langiewicza 3A"),  # Z literą
        ("zimowa 10", "zimowa 10"),  # Mała litera
        ("Czechów okolice", None),  # brak numeru
        ("Przy rondzie Chatki Żaka", None),  # brak numeru
        ("5 minut od centrum", None),  # nie adres
        ("100 metrów od UMCS", None),  # metrów od
    ]
    
    print("🧪 Testy Address Parser:\n")
    for text, expected in test_cases:
        result = parser.extract_address(text)
        extracted = result['full'] if result else None
        status = "✅" if extracted == expected else "❌"
        print(f"{status} '{text}' → {extracted}")
        if extracted != expected:
            print(f"   Oczekiwano: {expected}")
