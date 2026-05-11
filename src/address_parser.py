"""
Address Parser - ekstrakcja adresów z opisów ogłoszeń
Akceptuje formaty:
- "Narutowicza 5" (bez "ul.")
- "Rynek 8" (bez określenia typu)
- "al. Andersa 13 lok. 5"
- "ul. Racławickie 12/2"
- "Aleja Kraśnicka 73a" - zachowuje prefiks Aleja!
"""

import re
from typing import Optional, Dict

class AddressParser:
    # Prefiksy ulic - teraz jako GRUPY do wyciągnięcia
    # Grupa 1: prefiks (opcjonalny)
    # Grupa 2: nazwa ulicy
    # Grupa 3: numer
    # UWAGA: Dłuższe prefiksy MUSZĄ być przed krótszymi
    PREFIX_PATTERN = r'(ulica|ul\.|ul|aleja|aleje|al\.|al|plac|pl\.|pl|osiedle|os\.|os)?\s*'
    
    # Główny pattern adresu - z prefixem jako opcjonalną grupą
    # UWAGA: Dłuższe prefiksy MUSZĄ być przed krótszymi (ulica przed ul, aleja przed al, itd.)
    ADDRESS_PATTERN = re.compile(
        rf'(ulica|ul\.|ul|aleja|aleje|al\.|al|plac|pl\.|pl|osiedle|os\.|os)?\s*([A-ZŚĆŁĄĘÓŻŹŃ][a-zśćłąęóżźń]+(?:\s+[A-ZŚĆŁĄĘÓŻŹŃ]?[a-zśćłąęóżźń]+)?)\s+(\d+[a-zA-Z]?(?:/\d+)?(?:\s+lok\.\s+\d+)?)',
        re.UNICODE | re.IGNORECASE
    )
    
    # NOWY: Wzorzec dla polskich nazwisk w dopełniaczu (Langiewicza, Słowackiego, Czuby itd.)
    # Łapie: "[Nazwisko kończące się na -a/-cza/-sza/-ego/-iego/-owej/-skiej] + numer"
    POLISH_SURNAME_PATTERN = re.compile(
        r'\b([A-ZŚĆŁĄĘÓŻŹŃ][a-zśćłąęóżźń]*(?:cza|sza|ego|iego|owej|skiej|skiego|ckiego|nej|nego|wej|wego|ej|a))\s+(\d+[a-zA-Z]?(?:/\d+)?)\b',
        re.UNICODE
    )
    
    # Mapowanie prefiksów do pełnych nazw (dla geokodowania)
    PREFIX_MAP = {
        'ul.': '',  # ul. usuwamy
        'ulica': '',
        'al.': 'Aleja',  # al. zamieniamy na Aleja
        'aleja': 'Aleja',
        'aleje': 'Aleje',
        'pl.': 'Plac',
        'plac': 'Plac',
        'os.': 'Osiedle',
        'osiedle': 'Osiedle'
    }

    # Słowa które NIE mogą być nazwą ulicy (class-level, używane przez extract_address i extract_street_only)
    # KRYTYCZNE: używaj lower()! Wszystkie wpisy muszą być małymi literami.
    EXCLUDED_WORDS = {
        'pokój', 'przy', 'obok', 'blisko', 'centrum', 'okolice', 'minut', 'minutę', 'rok', 'lata',
        'jednoosobowy', 'dwuosobowy', 'trzoosobowy', 'osobowy',
        'dla', 'bez', 'lub', 'osób', 'osoby',
        # Dzielnice Lublina (nie są ulicami)
        'wieniawa', 'śródmieście', 'bronowice', 'czuby', 'kalinowszczyzna', 'tatary',
        'czechów', 'sławinek', 'sławin', 'abramowice', 'konstantynów', 'ponikwoda',
        'głusk', 'węglin', 'felin', 'hajdów',
        # Słowa z ogłoszeń które nie są ulicami
        'net', 'ciepło', 'internet', 'wifi', 'balkon', 'ogród', 'parking',
        'od', 'do', 'za', 'na', 'po', 'we', 'ze',
        # Słowa które parser myli z ulicami
        'stancja', 'mieszkaniu', 'mieszkanie', 'przechowywania', 'powierzchni',
        'fajna', 'fajny', 'studentki', 'studenta', 'lokalu', 'budynku', 'budynek',
        'pokoju', 'kuchni', 'salonu', 'łazienki', 'sypialni',
        # Pseudo-adresy
        'blok', 'bloku', 'bloków', 'wieżowiec', 'wieżowca', 'kamienica', 'kamienicy',
        # Pseudo-ulice wyciągnięte z opisów
        'rachunki', 'pokoje', 'około', 'dostępny', 'dostępna', 'dostępne',
        'wynajmę', 'wynajem', 'located', 'gyms', 'available', 'meters',
        'numer', 'kontaktowy', 'telefon', 'kontakt', 'number',
        # Instytucje, sklepy, uczelnie - NIE są ulicami
        'umcs', 'kul', 'politechnika', 'up', 'uniwersytet', 'szkoła', 'szpital',
        'galeria', 'rondo', 'przystanek', 'dworzec', 'stacja',
        'sklep', 'biedronka', 'lidl', 'żabka', 'rossmann', 'leclerc', 'auchan', 'kaufland',
        'park', 'las', 'jezioro', 'rzeka', 'plaża', 'stadion', 'hala', 'basen', 'lsm',
        'carrefour', 'tesco', 'empik', 'media', 'saturn', 'decathlon',
        'poczta', 'urząd', 'sąd', 'kościół', 'cerkiew', 'meczet', 'synagoga',
        'apteka', 'bank', 'hotel', 'restauracja', 'kawiarnia', 'pub', 'klub',
        'kino', 'teatr', 'muzeum', 'biblioteka', 'klinika', 'przychodnia',
        # Słowa z opisów metrażu/powierzchni
        'ma', 'ok', 'około', 'posiada', 'powierzchnia', 'powierzchni', 'metraż', 'metrażu',
        # === FIX #1 (2026-05-11): blokada wzorca "[Ulica] Lublin Witam/Oferuję" ===
        'lublin', 'witam', 'oferuję',
        # === FIX #2 (2026-05-11): słowa z analizy 105 false-positives w logach ===
        # Płatności/koszty
        'kaucja', 'depozyt', 'zaliczka', 'kwocie', 'opłaty', 'opłat', 'cenie', 'obowiązuje',
        'płatne', 'płatność', 'czynszu',
        # Opisowe rzeczowniki
        'piętro', 'piętrze', 'kawalerka', 'apartamencie', 'telewizor', 'łóżko', 'przedpokój',
        # Transport publiczny
        'whatsapp', 'mpk', 'linia', 'linie', 'autobus', 'autobusowe', 'autobusowego', 'tramwaj',
        # Ludzie / status
        'obecnie', 'aktualnie', 'mieszka', 'mieszkają', 'mieszkaja', 'zamieszkują',
        'dziewczyna', 'student',
        # Czasowniki/spójniki
        'są', 'jest', 'się', 'znajdują', 'dyspozycji',
        # Przymiotniki opisowe (sprawdzone: nie istnieją jako nazwy ulic w Lublinie)
        'duży', 'mały', 'jasny', 'nowoczesny', 'samodzielny', 'pozostałe',
        # Angielskie słowa z opisów
        'contact', 'rent', 'detached',
        # Inne wzorce z logów
        'wieku', 'wymiarach', 'wysokości', 'zasięgu', 'odległości',
        'czas', 'umowa', 'najmu',
        # Liczebniki słownie
        'dwieście', 'pięć',
    }

    # Pattern dla ekstrakcji ulicy BEZ numeru (decyzja 1a — tylko z jawnym prefiksem)
    # Wymaga: prefiks + nazwa ulicy (1-3 słowa)
    # Prefiks: case-insensitive (przez inline flag (?i:...))
    # Pierwsze słowo nazwy: musi zaczynać się WIELKĄ literą (lub być znaną small-case ulicą — zimowa, etc.)
    # Słowa dodatkowe: MUSZĄ zaczynać się WIELKĄ literą (chroni przed "Racławickie centrum")
    STREET_ONLY_PATTERN = re.compile(
        r'\b(?i:(ulica|ul\.|ul|aleja|aleje|al\.|al|plac|pl\.|pl|osiedle|os\.|os))\s+'
        r'([A-ZŚĆŁĄĘÓŻŹŃ][a-zśćłąęóżźń]{2,}'
        r'(?:\s+[A-ZŚĆŁĄĘÓŻŹŃ][a-zśćłąęóżźń]{2,}){0,2})',
        re.UNICODE
    )

    def __init__(self, geocoding_cache_path: str = "../data/geocoding_cache.json"):
        """
        Args:
            geocoding_cache_path: ścieżka do JSON z geocoding cache (do whitelist Fix #4).
                Jeśli plik nie istnieje, whitelist pozostaje pusty (parser działa bez fallbacku #4).
        """
        # === FIX #4 (2026-05-11): whitelist znanych ulic Lublina z geocoding_cache ===
        # Wczytuje 148+ znanych nazw ulic które już raz geokodowaliśmy.
        # Używane jako TRZECI fallback po extract_address i extract_street_only.
        self._known_streets = self._load_known_streets(geocoding_cache_path)
    
    @staticmethod
    def _load_known_streets(cache_path: str) -> set:
        """
        Ekstraktuje unikalne nazwy ulic z geocoding_cache.json.
        Zwraca set z nazwami w lowercase dla szybkiego matching case-insensitive.
        """
        try:
            import json as _json
            from pathlib import Path as _Path
            p = _Path(cache_path)
            if not p.exists():
                return set()
            with open(p, 'r', encoding='utf-8') as f:
                cache = _json.load(f)
            streets = set()
            # Wzorzec: "Nazwa Ulicy 5" lub "Nazwa Ulicy" - wyciągamy część PRZED numerem
            addr_pattern = re.compile(r'^([\w\sśćłąęóżźńŚĆŁĄĘÓŻŹŃ\.]+?)(?:\s+\d+[a-zA-Z]?(?:/\d+)?)?$')
            prefix_pattern = re.compile(r'^(Aleja|Aleje|Plac|Osiedle)\s+', re.UNICODE)
            
            for addr, coords in cache.items():
                # Bierzemy tylko wpisy z poprawnymi współrzędnymi
                if coords is None:
                    continue
                m = addr_pattern.match(addr.strip())
                if not m:
                    continue
                street_name = m.group(1).strip()
                # Usuń prefiks ("Aleja Racławickie" → "Racławickie")
                street_name = prefix_pattern.sub('', street_name)
                # Filtruj: min 3 znaki, pierwsza wielka, brak whitespace artefaktów
                if len(street_name) < 3 or not street_name[0].isalpha():
                    continue
                if not street_name[0].isupper():
                    continue
                # Filtr dodatkowy: nazwa nie może zawierać dziwnych słów typu "Mieszkanie", "OpisPokój"
                # (artefakty z parsera) - jeśli zawiera "Mieszkanie"/"Pokój"/"Opis" w środku, skip
                if any(noise in street_name for noise in ['Mieszkanie', 'OpisPokój', 'Lublin', 'Witam', 'Oferuję']):
                    continue
                streets.add(street_name.lower())
            return streets
        except Exception as e:
            print(f"⚠️ Nie udało się załadować whitelist z {cache_path}: {e}")
            return set()
    
    def extract_from_whitelist(self, text: str) -> Optional[Dict[str, Optional[str]]]:
        """
        Fix #4 (2026-05-11): trzeci fallback parsera.
        Wyszukuje w tekście jakiekolwiek znane nazwy ulic Lublina (z geocoding_cache).
        Używany TYLKO gdy extract_address i extract_street_only zwróciły None.
        
        Kluczowa transformacja: każde słowo w tekście przekształca się do mianownika
        przed porównaniem z whitelistą - inaczej "Lipowej" nie matchowałoby "Lipowa".
        
        Wymaga dopasowania całych słów (case-insensitive) żeby uniknąć false-positives
        typu "Glinianej" matchującego "Glina" wewnątrz innego słowa.
        
        Returns:
            Dict z 'street', 'number'=None, 'full' lub None jeśli nie znaleziono.
            Adres jest precyzji street_only (brak numeru).
        """
        if not self._known_streets or not text:
            return None
        
        # Lazy import to_nominative z geocodera (uniknięcie circular import na poziomie modułu)
        try:
            from geocoder import to_nominative
        except ImportError:
            to_nominative = lambda x: x  # fallback - brak transformacji
        
        # Normalizacja tekstu: zamień znaki interpunkcyjne na spacje
        normalized = re.sub(r'[^\w\sśćłąęóżźńŚĆŁĄĘÓŻŹŃ]', ' ', text)
        
        # KLUCZ: każde słowo z tekstu zamieniamy do mianownika (Lipowej → Lipowa)
        # Pomijamy słowa krótsze niż 4 znaki (nie mogą być nazwami ulic)
        words = normalized.split()
        nominative_words = []
        for w in words:
            if len(w) >= 4 and w[0].isalpha():
                nm = to_nominative(w).lower()
                nominative_words.append(nm)
            else:
                nominative_words.append(w.lower())
        
        # Zrekonstruuj tekst z mianownikami dla matchingu wieloczłonowych nazw
        text_nominative = ' '.join(nominative_words)
        words_set = set(nominative_words)
        
        candidates = []
        for street_lower in self._known_streets:
            street_words = street_lower.split()
            if len(street_words) == 1:
                # Pojedyncze słowo - sprawdź obecność w secie słów
                if street_lower in words_set:
                    candidates.append((street_lower, len(street_lower)))
            else:
                # Wieloczłonowa nazwa - sprawdź dopasowanie do granic słów
                pattern = r'\b' + re.escape(street_lower) + r'\b'
                if re.search(pattern, text_nominative):
                    candidates.append((street_lower, len(street_lower)))
        
        if not candidates:
            return None
        
        # Wybierz najdłuższego kandydata (najbardziej specyficzny)
        best_street_lower, _ = max(candidates, key=lambda x: x[1])
        # Kapitalizacja zgodnie z polską normą (każde słowo z dużej litery)
        best_street = ' '.join(w.capitalize() for w in best_street_lower.split())
        
        return {
            'street': best_street,
            'number': None,
            'full': best_street
        }
    
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
        
        # FILTR 2: Wykryj fałszywe adresy typu "NAZWA 10 minut" / "NAZWA 5 min"
        # Przykład: "UMCS 10 minut pieszo" - to NIE jest adres "UMCS 10"
        false_address_pattern = re.compile(
            r'\b([A-ZŚĆŁĄĘÓŻŹŃ][A-Za-zśćłąęóżźń]*)\s+(\d+)\s*(minut|min\.?|minuty?|sekund|sek\.?|godzin|godz\.?|metr[oó]w|km|m\b)',
            re.IGNORECASE | re.UNICODE
        )
        # Zapamiętaj fałszywe "adresy" do późniejszego odrzucenia
        false_addresses = set()
        for match in false_address_pattern.finditer(text):
            false_addr = f"{match.group(1)} {match.group(2)}"
            false_addresses.add(false_addr.lower())
        
        # FILTR 3: Wykryj metraż/powierzchnię typu "ma ok 9m", "około 15m2", "powierzchnia 20m"
        # Przykład: "Pokój ma ok 9m2" - to NIE jest adres "ma ok 9m"
        area_pattern = re.compile(
            r'\b(ma|około|ok\.?|posiada|powierzchni[aę]?|metraż[u]?)\s+(ok\.?\s+)?(\d+)\s*m[²2]?\b',
            re.IGNORECASE | re.UNICODE
        )
        for match in area_pattern.finditer(text):
            # Dodaj różne warianty tego samego metrażu
            false_addr_variants = [
                f"{match.group(1)} {match.group(3)}",  # "ma 9"
                f"{match.group(1)} ok {match.group(3)}",  # "ma ok 9"
            ]
            if match.group(2):  # jeśli było "ok" w środku
                false_addr_variants.append(f"{match.group(1)} {match.group(2).strip()} {match.group(3)}")
            
            for variant in false_addr_variants:
                false_addresses.add(variant.lower().replace('.', '').strip())
        
        # Słowa które NIGDY nie mogą być nazwą ulicy (instytucje, uczelnie, itp.)
        # Te słowa + numer to prawie zawsze "X minut od", "X metrów od"
        non_street_names = {
            'umcs', 'kul', 'politechnika', 'up', 'uniwersytet', 'szkoła', 'szpital',
            'galeria', 'centrum', 'rondo', 'przystanek', 'dworzec', 'stacja',
            'sklep', 'biedronka', 'lidl', 'żabka', 'rossmann', 'leclerc', 'auchan', 'kaufland',
            'park', 'las', 'jezioro', 'rzeka', 'plaża', 'stadion', 'hala', 'basen',
            'lsm', 'czuby', 'kalinowszczyzna', 'tatary', 'bronowice', 'wieniawa',
            # Dodatkowe
            'carrefour', 'tesco', 'empik', 'media', 'saturn', 'decathlon',
            'poczta', 'urząd', 'sąd', 'kościół', 'cerkiew', 'meczet', 'synagoga',
            'apteka', 'bank', 'hotel', 'restauracja', 'kawiarnia', 'pub', 'klub',
            'kino', 'teatr', 'muzeum', 'biblioteka', 'szpital', 'klinika', 'przychodnia'
        }
        
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
        
        # Słowa które NIE mogą być nazwą ulicy (definicja na poziomie klasy - patrz EXCLUDED_WORDS)
        excluded_words_lower = self.EXCLUDED_WORDS
        
        # Szukamy WSZYSTKICH dopasowań (prefiks + ulica + numer)
        matches = self.ADDRESS_PATTERN.finditer(text)
        
        # Zbierz wszystkie kandydaty
        candidates = []
        
        for match in matches:
            prefix = match.group(1)  # może być None
            street = match.group(2).strip()
            number = match.group(3).strip()
            
            # Sprawdź minimum 4 litery w nazwie ulicy (żeby wykluczyć "dla", "bez" etc)
            if len(street.replace(' ', '')) < 4:
                continue
            
            # NOWY FILTR: Sprawdź czy to nie jest fałszywy adres (np. "UMCS 10" z "UMCS 10 minut")
            potential_addr = f"{street} {number.split('/')[0].split()[0]}"
            if potential_addr.lower() in false_addresses:
                print(f"      ⚠️ Odrzucono fałszywy adres: {potential_addr} (wykryto 'X minut/metrów')")
                continue
            
            # NOWY FILTR: Sprawdź czy nazwa ulicy to nie instytucja/miejsce (nie ulica)
            if street.lower() in non_street_names:
                print(f"      ⚠️ Odrzucono: '{street}' to nie jest nazwa ulicy")
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
            
            # FILTR BEZPIECZEŃSTWA: Odrzuć numery z literą O/o zaraz po cyfrze (błąd OCR)
            # Przykład: "1O", "10O", "2o" - prawdopodobnie błąd, powinno być "10", "100", "20"
            if re.search(r'\d[Oo](?:[^a-zA-Z]|$)', main_number):
                print(f"      ⚠️ Odrzucono podejrzany numer: {number} (prawdopodobnie błąd OCR: 'O' zamiast '0')")
                continue
            
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
            
            # NOWE: Buduj pełny adres z prefixem (jeśli jest)
            full_address = street
            has_prefix = False
            if prefix:
                has_prefix = True
                prefix_lower = prefix.lower().rstrip('.')
                # Mapuj prefiks na pełną nazwę
                if prefix_lower in ['al', 'aleja']:
                    full_address = f"Aleja {street}"
                elif prefix_lower in ['aleje']:
                    full_address = f"Aleje {street}"
                elif prefix_lower in ['pl', 'plac']:
                    full_address = f"Plac {street}"
                elif prefix_lower in ['os', 'osiedle']:
                    full_address = f"Osiedle {street}"
                # ul./ulica - pomijamy, zostawiamy samą nazwę ulicy
            
            # Dodaj do listy kandydatów z priorytetem
            # Priorytet: 
            # 1. Ma prefiks ul./al./pl. (najbardziej pewne)
            # 2. Długość nazwy ulicy (dłuższa nazwa = bardziej specyficzna)
            priority = 0
            if has_prefix:
                priority += 100  # Prefiks daje wysoką pewność
            priority += len(street)  # Dłuższa nazwa = wyższy priorytet
            
            candidates.append({
                'street': street,
                'number': number,
                'full': f"{full_address} {number}",
                'priority': priority,
                'has_prefix': has_prefix
            })
        
        # Jeśli znaleziono kandydatów, wybierz najlepszego (najwyższy priorytet)
        if candidates:
            best = max(candidates, key=lambda x: x['priority'])
            return {
                'street': best['street'],
                'number': best['number'],
                'full': best['full']
            }
        
        # NOWY FALLBACK: Wzorzec dla polskich nazwisk w dopełniaczu
        # Łapie przypadki jak "Langiewicza 3A", "Słowackiego 12" bez prefiksu
        surname_matches = self.POLISH_SURNAME_PATTERN.finditer(text)
        
        for match in surname_matches:
            street = match.group(1).strip()
            number = match.group(2).strip()
            
            # Sprawdź minimum 5 liter (żeby wykluczyć "Pokoja 5" itp.)
            if len(street) < 5:
                continue
            
            # Sprawdź czy nie jest wykluczonym słowem
            if street.lower() in excluded_words_lower:
                continue
            
            # Walidacja numeru (max 250)
            try:
                main_num = number.rstrip('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ/').split('/')[0]
                if int(main_num) > 250:
                    continue
            except ValueError:
                continue
            
            return {
                'street': street,
                'number': number,
                'full': f"{street} {number}"
            }
        
        # BRAK FALLBACK - Wymagamy NUMERU domu!
        # Adresy bez numeru (np. "ul. Niecała") są zbyt nieprecyzyjne dla mapy
        return None

    def extract_street_only(self, text: str) -> Optional[Dict[str, str]]:
        """
        Ekstrakcja samej nazwy ulicy (BEZ numeru domu) z opisu.
        Używana TYLKO gdy extract_address() zwróciło None — daje przybliżoną lokalizację.

        Decyzja 1a: wymaga JAWNEGO prefiksu (ul./ulica/al./aleja/aleje/pl./plac/os./osiedle).
        Bez prefiksu zwraca None — to chroni przed fałszywymi trafieniami typu "blisko Lipowej".

        Args:
            text: Tekst opisu oferty

        Returns:
            Dict z kluczami: street, number=None, full lub None jeśli nie znaleziono
        """
        if not text:
            return None

        candidates = []

        for match in self.STREET_ONLY_PATTERN.finditer(text):
            prefix_raw = match.group(1)
            street_raw = match.group(2).strip()

            # Normalizacja: pierwsze słowo z dużej litery
            street_words = street_raw.split()

            # Walidacja: każde słowo musi mieć min 3 znaki
            if any(len(w) < 3 for w in street_words):
                continue

            # Walidacja: pierwsze słowo nie może być na czarnej liście (lowercase comparison)
            first_word_lower = street_words[0].lower()
            if first_word_lower in self.EXCLUDED_WORDS:
                continue

            # Walidacja: żadne ze słów nie może być na czarnej liście
            if any(w.lower() in self.EXCLUDED_WORDS for w in street_words):
                continue

            # Normalizacja kapitalizacji — każde słowo z dużej litery
            street = ' '.join(w.capitalize() for w in street_words)

            # Mapowanie prefiksu na formę używaną przez geocoder
            prefix_lower = prefix_raw.lower().rstrip('.')
            prefix_full = self.PREFIX_MAP.get(prefix_raw.lower(), '')
            # PREFIX_MAP nie zawiera 'ul' (tylko 'ul.' i 'ulica'), dodaj fallback
            if prefix_lower in ('ul', 'ulica'):
                prefix_full = ''
            elif prefix_lower in ('al', 'aleja'):
                prefix_full = 'Aleja'
            elif prefix_lower == 'aleje':
                prefix_full = 'Aleje'
            elif prefix_lower in ('pl', 'plac'):
                prefix_full = 'Plac'
            elif prefix_lower in ('os', 'osiedle'):
                prefix_full = 'Osiedle'

            full_address = f"{prefix_full} {street}".strip() if prefix_full else street

            # Priorytet: dłuższa nazwa ulicy = wyższy priorytet (jak w extract_address)
            priority = len(street)

            candidates.append({
                'street': street,
                'full': full_address,
                'priority': priority
            })

        if not candidates:
            return None

        # Wybierz najdłuższą nazwę (najbardziej specyficzną)
        best = max(candidates, key=lambda x: x['priority'])
        return {
            'street': best['street'],
            'number': None,
            'full': best['full']
        }
    
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
        ("al. Andersa 13 lok. 5", "Aleja Andersa 13 lok. 5"),  # Prefiks zachowany
        ("Aleje Racławickie 12/2", "Aleje Racławickie 12/2"),
        ("Os. Przyjaźni 23", "Osiedle Przyjaźni 23"),  # Prefiks zachowany
        ("Langiewicza 3A", "Langiewicza 3A"),  # Z literą
        ("zimowa 10", "Zimowa 10"),  # Kapitalizacja
        ("Czechów okolice", None),  # brak numeru
        ("Przy rondzie Chatki Żaka", None),  # brak numeru
        ("5 minut od centrum", None),  # nie adres
        ("100 metrów od UMCS", None),  # metrów od
        # NOWE: Fałszywe adresy typu "X minut od"
        ("UMCS 10 minut pieszo", None),  # UMCS to nie ulica!
        ("Biedronka 5 min stąd", None),  # Biedronka to nie ulica!
        ("KUL 15 minut autobusem", None),  # KUL to nie ulica!
        ("Politechnika 3 min pieszo", None),  # Politechnika to nie ulica!
        ("LSM 10 minut od centrum", None),  # LSM to dzielnica, nie ulica!
        ("Galeria 5 minut stąd", None),  # Galeria to nie ulica!
        # Prawdziwe adresy powinny nadal działać
        ("ul. Lipowa 10, blisko UMCS", "Lipowa 10"),  # Prawdziwy adres
    ]
    
    print("🧪 Testy Address Parser:\n")
    for text, expected in test_cases:
        result = parser.extract_address(text)
        extracted = result['full'] if result else None
        status = "✅" if extracted == expected else "❌"
        print(f"{status} '{text}' → {extracted}")
        if extracted != expected:
            print(f"   Oczekiwano: {expected}")

    # ===== Testy extract_street_only =====
    print("\n🧪 Testy extract_street_only (ulica bez numeru):\n")
    street_only_cases = [
        # ZŁAPIE — jest prefiks, brak numeru
        ("pokój przy ul. Narutowicza", "Narutowicza"),
        ("ul. Lipowa, blisko centrum", "Lipowa"),
        ("al. Racławickie, blisko UMCS", "Aleja Racławickie"),
        ("pl. Litewski samo serce miasta", "Plac Litewski"),
        ("os. Kalinowszczyzna", None),  # Kalinowszczyzna jest w czarnej liście (dzielnica)
        ("aleja Kraśnicka super lokalizacja", "Aleja Kraśnicka"),
        ("ulica Lubartowska", "Lubartowska"),
        ("os. Przyjaźni", "Osiedle Przyjaźni"),
        ("Aleje Racławickie centrum", "Aleje Racławickie"),
        # Ulica wieloczłonowa
        ("ul. Krakowskie Przedmieście", "Krakowskie Przedmieście"),
        # NIE ZŁAPIE — brak prefiksu (decyzja 1a)
        ("blisko Narutowicza", None),
        ("okolice Lipowej", None),
        ("przy parku", None),
        ("Narutowicza super", None),  # bez prefiksu
        # NIE ZŁAPIE — czarna lista
        ("ul. blisko centrum", None),
        ("ul. UMCS", None),
        ("al. centrum", None),
        ("ul. Biedronka", None),
        ("os. Czuby", None),  # Czuby = dzielnica
        # Pierwszeństwo extract_address — gdy jest numer, ta metoda nie powinna być wołana,
        # ale jeśli zostanie wołana, to złapie ulicę (na poziomie main.py używamy fallback)
        ("ul. Narutowicza 5", "Narutowicza"),  # ta metoda nie sprawdza obecności numeru
    ]

    pass_count = 0
    fail_count = 0
    for text, expected in street_only_cases:
        result = parser.extract_street_only(text)
        extracted = result['full'] if result else None
        status = "✅" if extracted == expected else "❌"
        if extracted == expected:
            pass_count += 1
        else:
            fail_count += 1
        print(f"{status} '{text}' → {extracted}")
        if extracted != expected:
            print(f"   Oczekiwano: {expected}")

    print(f"\n📊 extract_street_only: {pass_count} OK / {fail_count} FAIL")

    # ===== FIX #1: Testy regresji "Lublin Witam/Oferuję" =====
    print("\n🧪 FIX #1 — blokada wzorca '[Ulica] Lublin Witam/Oferuję':\n")
    fix1_cases = [
        # NIE ZŁAPIE — śmieci z logów scanu #249
        ("pokój ul. Biskupińska Lublin Witam zapraszamy", None),
        ("pokój ul. Wyścigowa Lublin Witam wszystkich", None),
        ("pokój ul. Środkowa Lublin Witam", None),
        ("ul. Czeremchowa Lublin Oferuję ofertę", None),
        # POZYTYW: kontrolny — nazwa bez "Lublin" działa
        ("pokój ul. Biskupińska zapraszamy", "Biskupińska"),
        ("ul. Wyścigowa blisko centrum", "Wyścigowa"),
    ]
    fix1_pass = 0
    fix1_fail = 0
    for text, expected in fix1_cases:
        result = parser.extract_street_only(text)
        extracted = result['full'] if result else None
        status = "✅" if extracted == expected else "❌"
        if extracted == expected:
            fix1_pass += 1
        else:
            fix1_fail += 1
        print(f"{status} '{text}' → {extracted}")
        if extracted != expected:
            print(f"   Oczekiwano: {expected}")
    print(f"\n📊 FIX #1: {fix1_pass} OK / {fix1_fail} FAIL")

    # ===== FIX #2: Testy regresji extract_address dla false-positives =====
    print("\n🧪 FIX #2 — blokada false-positives w extract_address (śmieci z logów):\n")
    fix2_cases = [
        # NEGATYW: śmieci które przeciekały — powinny być None
        ("Kaucja 250 zł zwrotna", None),
        ("Depozyt 200 zł", None),
        ("WhatsApp 79 12 345", None),
        ("Piętro 6 z balkonem", None),
        ("Kawalerka 25 m kwadratowych", None),
        ("wieku 20 lat", None),
        ("Lublin duży 16 m kwadratowych", None),
        ("MPK i 10m od centrum", None),
        ("linia nr 2", None),
        ("Pozostałe 2 pokoje", None),
        ("autobusowego jest 5 min", None),
        ("apartamencie Gleboka 18", "Gleboka 18"),  # parser pomija "apartamencie" i znajduje realną ulicę Głęboka
        ("contact 53 12 345", None),
        ("DWIEŚCIE 8 osób", None),
        ("telewizor 42 cale", None),

        # POZYTYW: prawdziwe adresy — muszą nadal przechodzić
        ("ul. Narutowicza 5, pokój 12 m²", "Narutowicza 5"),
        ("Wynajmę pokój Lublin, Lipowa 14, kaucja 250 zł", "Lipowa 14"),
        ("al. Racławickie 10, blisko UMCS", "Aleja Racławickie 10"),
        ("ul. Krakowskie Przedmieście 5", "Krakowskie Przedmieście 5"),
        ("Pokój przy ul. Żelazowej Woli 7, piętro 3", "Żelazowej Woli 7"),
    ]
    fix2_pass = 0
    fix2_fail = 0
    for text, expected in fix2_cases:
        result = parser.extract_address(text)
        extracted = result['full'] if result else None
        status = "✅" if extracted == expected else "❌"
        if extracted == expected:
            fix2_pass += 1
        else:
            fix2_fail += 1
        # Krótszy print dla negatywnych
        if expected is None:
            print(f"{status} '{text[:50]}' → {extracted}")
        else:
            print(f"{status} '{text[:50]}' → {extracted}")
        if extracted != expected:
            print(f"   Oczekiwano: {expected}")
    print(f"\n📊 FIX #2: {fix2_pass} OK / {fix2_fail} FAIL")

    # ===== FIX #4: Testy extract_from_whitelist =====
    print("\n🧪 FIX #4 — extract_from_whitelist (znane ulice z geocoding_cache):\n")
    
    fix4_cases = [
        # POZYTYW - znana ulica w dopełniaczu w opisie OLX
        ("pokój przy Głębokiej, blisko centrum", "Głęboka"),
        ("blisko Lipowej", "Lipowa"),
        ("okolice Puławskiej", "Puławska"),
        # POZYTYW - znana ulica w mianowniku
        ("Lipowa 14", "Lipowa"),
        # NEGATYW - brak znanej ulicy
        ("pokój w spokojnym miejscu", None),
        ("kaucja 250 zł", None),
        ("blisko Stadionu", None),
        # NEGATYW - dzielnica (nie ulica)
        ("Pokój w Wieniawej", None),  # Wieniawa to dzielnica, nie w whitelist jako ulica
        # Edge cases
        ("", None),
        ("ma od 10 do 20", None),  # tylko krótkie słowa
    ]
    fix4_pass = 0
    fix4_fail = 0
    for text, expected in fix4_cases:
        r = parser.extract_from_whitelist(text)
        actual = r['full'] if r else None
        status = "✅" if actual == expected else "❌"
        if actual == expected:
            fix4_pass += 1
        else:
            fix4_fail += 1
        print(f"{status} '{text}' → {actual}")
        if actual != expected:
            print(f"   Oczekiwano: {expected}")
    print(f"\n📊 FIX #4: {fix4_pass} OK / {fix4_fail} FAIL")

    # Total summary
    total_pass = pass_count + fix1_pass + fix2_pass + fix4_pass
    total_fail = fail_count + fix1_fail + fix2_fail + fix4_fail
    print(f"\n{'='*60}")
    print(f"📊 ŁĄCZNIE: {total_pass} OK / {total_fail} FAIL")
    print(f"{'='*60}")
