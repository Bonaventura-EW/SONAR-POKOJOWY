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
    # FIX (2026-05-13): dodano 'ulicy' (forma dopełniacza: "na ulicy Foo"),
    #   'ulicą' (narzędnik: "ulicą Foo"), 'alei' (dopełniacz: "na alei Foo"),
    #   bez tych form parser brał formę gramatyczną jako część nazwy ulicy
    #   (np. "ulicy Kryształowej 29" zamiast "Kryształowej 29")
    PREFIX_PATTERN = r'(ulica|ulicy|ulicą|ul\.|ul|aleja|aleje|alei|alejami|al\.|al|plac|placu|pl\.|pl|osiedle|osiedlu|os\.|os)?\s*'
    
    # Główny pattern adresu - z prefixem jako opcjonalną grupą
    # UWAGA: Dłuższe prefiksy MUSZĄ być przed krótszymi (ulica przed ul, aleja przed al, itd.)
    ADDRESS_PATTERN = re.compile(
        rf'(ulica|ulicy|ulicą|ul\.|ul|aleja|aleje|alei|alejami|al\.|al|plac|placu|pl\.|pl|osiedle|osiedlu|os\.|os)?\s*([A-ZŚĆŁĄĘÓŻŹŃ][a-zśćłąęóżźń]+(?:\s+[A-ZŚĆŁĄĘÓŻŹŃ]?[a-zśćłąęóżźń]+)?)\s+(\d+[a-zA-Z]?(?:/\d+)?(?:\s+lok\.\s+\d+)?)',
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
        'ul': '',
        'ulica': '',
        'ulicy': '',   # FIX 2026-05-13: dopełniacz "na ulicy Foo"
        'ulicą': '',   # narzędnik "ulicą Foo"
        'al.': 'Aleja',  # al. zamieniamy na Aleja
        'al': 'Aleja',
        'aleja': 'Aleja',
        'aleje': 'Aleje',
        'alei': 'Aleja',     # dopełniacz "na alei Foo"
        'alejami': 'Aleja',  # narzędnik
        'pl.': 'Plac',
        'pl': 'Plac',
        'plac': 'Plac',
        'placu': 'Plac',     # dopełniacz "na placu Foo"
        'os.': 'Osiedle',
        'os': 'Osiedle',
        'osiedle': 'Osiedle',
        'osiedlu': 'Osiedle',  # miejscownik "na osiedlu Foo"
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
        'whatsapp', 'whats', 'app', 'mpk', 'linia', 'linie', 'autobus', 'autobusowe', 'autobusowego', 'tramwaj',
        'miejska', 'miejską', 'miejski', 'miejskie', 'miejskiej',  # "komunikacją miejską to 2"
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
        # === FIX #5 (2026-05-13): noise z analizy skipped_offers_sample.json ===
        # Rzeczowniki/przymiotniki które parser łapie z numerami z opisu jako "adres + nr"
        'oddzielnej', 'oddzielną', 'oddzielne', 'oddzielny',
        'telefonu', 'telefoniczny', 'telefoniczne', 'telefonicznego',
        # === Słowa z warunków umowy (mogą występować + numer "co najmniej 6 miesięcy") ===
        'co', 'najmniej', 'minimum', 'maksimum', 'maksymalnie', 'maksymalnym',
        'umowy', 'umowę', 'okres', 'okresu', 'okresem',
        'miesięcy', 'miesiące', 'miesiąc', 'miesiącu', 'miesięcznych',
        'rok', 'roku', 'lat', 'latach',
        'tydzień', 'tygodnia', 'tygodni',
        'razy', 'razu',
        # === noise z analizy (kontynuacja) ===
        'kondygnacji', 'kondygnacja',
        'dnia', 'dni',
        'pozostałych', 'pozostałe', 'pozostały', 'pozostałymi', 'zostały',
        'zajmie', 'zajmuje',
        'preferably', 'attractive', 'uniwercity', 'gyms', 'rent', 'monthly',
        'montly', 'within', 'choose', 'from', 'march', 'detached',
        'wg', 'oraz', 'tel',
        'miesięcznego', 'średnio', 'miesięcznie',
        'oznaczony', 'nr',
        'samodzielnym',
        'nowoczesnym',
        'użytku',
        'linii', 'linia',
        'częścią', 'częściej',
        'ochronę',
        'numerze', 'numerem',
        'cenie', 'cena',
        'wolne', 'wolny',
        'okolica',
        'odjeżdżają',
        'lokalu', 'lokal',
        'lubelski', 'lubelska', 'lubelskiej', 'lubelskie',
        'kontaktu',
        'również',
        'materacem',
        'spacer',
        'zaliczka',
        'opisduży', 'opisdwuosobowy', 'opispokój', 'opisstudio',
        # Słowa angielskie z opisów (powtórki dla pewności)
        'gyms', 'within', 'choose', 'monthly', 'attractive',
        # === FIX 2026-05-14 (fix 2): słowa z analizy skipped_debug po preprocessing ===
        # Bezsensowne "adresy" wyciągane przez parser z opisów
        'of',              # angielskie "amount of PLN 100Deposit" → "Of PLN 100"
        'floor',           # "floor 2.Fees" — angielski opis OLX
        'lokalizacja',     # "Lokalizacja 100m od Krwiodawców" — nazwa sekcji opisu
        'ostatnim',        # "na oddzielnym, ostatnim 3 piętrze" — przymiotnik opisowy
        'przestronne', 'przestronny', 'przestronna',  # "Przestronne 65m mieszkanie"
        'vpustreet',       # OLX/skrót w angielskich opisach
        'obowy',           # quick fix dla bugu regexu: "1-osobowy" → prefiks "os" + "obowy"
                           # (regex łapie 'os' w środku słowa — naprawa w osobnym fixie)
        # Inne częste słowa-szumy z analizy
        'street',          # "Nadbystrzycka Street" — ang. duplikat polskiej nazwy
        'large',           # "Large room with a balcony"
        'medical',         # "Medical University"
        'fees',            # "Fees and Internet included"
        'deposit',         # "deposit 1000PLN"
        'rent',            # już jest, ale duplikat dla pewności
        # Warianty "pokojowy" (mieszkanie 3-pokojowe / 1-pokojowym itp.)
        # Bez tego parser łapie "pokojowym 75m" jako adres
        'pokojowy', 'pokojowa', 'pokojowe', 'pokojowym', 'pokojowej', 'pokojowych',
        # === FIX 2026-05-14 (fix C - cache cleanup): śmieci znalezione w cache analiza ===
        # Te słowa-śmieci były wcześniej wyciągane przez parser, trafiały do cache jako None.
        # Dodaję do blacklisty żeby już więcej nie wychodziły jako adresy.
        'pokoj',           # literówka "pokój" (bez kreski) — "Pokoj 1", "Pokoj 25m"
        'wynajme',         # literówka "wynajmę"
        'dojazd',          # "Dojazd 15" - opis komunikacji
        'bliskość',        # "Bliskość 3" - opisowe
        'sześć',           # "SZEŚĆ 5" - liczebnik
        'czechowie',       # "Czechowie Pokoj 1" - locative dzielnicy
        'uczelni',         # "Uczelni OpisStudio 2" - lokalizacyjne
        'obowym',          # "Osiedle obowym 12" - fragment "1-osobowym" po obcięciu cyfry
        'położony',        # "Dom położony 2"
        # === FIX 2026-05-26: false-positive z "Wymagana 1-miesięczna kaucja" ===
        # Parser łapie "Wymagana 1" jako adres ulica+numer.
        'wymagana', 'wymagany', 'wymagane', 'wymagani', 'wymaganym', 'wymaganej',
    }

    # FIX 2026-05-26 (B): hardcoded ulice Lublina, których brak w geocoding_cache.
    # Lowercase. Merge'owane z _known_streets w __init__.
    HARDCODED_LUBLIN_STREETS = {
        'rycerska',
    }

    # Pattern dla ekstrakcji ulicy BEZ numeru (decyzja 1a — tylko z jawnym prefiksem)
    # Wymaga: prefiks + nazwa ulicy (1-3 słowa)
    # Prefiks: case-insensitive (przez inline flag (?i:...))
    # Pierwsze słowo nazwy: musi zaczynać się WIELKĄ literą (lub być znaną small-case ulicą — zimowa, etc.)
    # Słowa dodatkowe: MUSZĄ zaczynać się WIELKĄ literą (chroni przed "Racławickie centrum")
    # FIX (2026-05-13): dodano formy gramatyczne 'ulicy/ulicą/alei/placu/osiedlu'
    # FIX 2026-05-14 (P2a): prefiks z kropką (ul./al./pl./os.) może być BEZ spacji przed
    #   nazwą ulicy (np. "ul.Furmańska" — typowe na OLX). Inne prefiksy nadal wymagają \s+.
    STREET_ONLY_PATTERN = re.compile(
        r'\b(?i:'
            # Wariant 1: prefiks z kropką + opcjonalna spacja  
            r'(?:(ul\.|al\.|pl\.|os\.)\s*'
            r'|'
            # Wariant 2: prefiks BEZ kropki + wymagana spacja
            r'(ulica|ulicy|ulicą|ul|aleja|aleje|alei|alejami|al|plac|placu|pl|osiedle|osiedlu|os)\s+)'
        r')'
        r'([A-ZŚĆŁĄĘÓŻŹŃ][a-zśćłąęóżźń]{2,}'
        r'(?:\s+[A-ZŚĆŁĄĘÓŻŹŃ][a-zśćłąęóżźń]{2,}){0,2})',
        re.UNICODE
    )

    # === FIX 2026-05-14: preprocessing tekstu przed parsowaniem ===
    # Wzorce do rozdzielania sklejonych tokenów (typowe po HTML-stripping z OLX).
    # Łapie 2 przypadki kleszczenia:
    #   1. mała litera + WIELKA litera: "KryształowaMieszkanie" → "Kryształowa Mieszkanie"
    #   2. cyfra + WIELKA litera + mała litera: "PLN 100Deposit" → "PLN 100 Deposit"
    #      WAŻNE: wymagamy mała litery PO wielkiej, żeby nie psuć numerów domów typu "80A", "10A/15"
    # Nie rusza:
    #   - 1-osobowy, 3-pokojowym (cyfry-myślnik-słowo)
    #   - 80A, 10A, 15B (numery domów: cyfra + pojedyncza wielka litera)
    #   - 10A/15 (numer + lokal)
    #   - Polski Centrum, UMCS KUL (sekwencje słów z wielkich liter)
    _CAMELCASE_SPLIT = re.compile(r'(?<=[a-ząęćłńóśźż])(?=[A-ZĄĘĆŁŃÓŚŹŻ])')
    _DIGIT_CAPITAL_SPLIT = re.compile(r'(?<=\d)(?=[A-ZĄĘĆŁŃÓŚŹŻ][a-ząęćłńóśźż])')
    _MULTIPLE_WHITESPACE = re.compile(r'\s+')

    # === FIX 2026-05-26 (A): mapa dzielnic Lublina ===
    # Klucz: kanoniczna nazwa dzielnicy (przekazywana do geocodera, który zwróci centroid).
    # Wartość: lista form/wariantów (lowercase), w tym miejscownik/dopełniacz/potoczne nazwy.
    # Lista zweryfikowana z OSM/UM Lublin + potoczne formy z OLX (Bazylianówka, Kalina, LSM).
    LUBLIN_DISTRICTS = {
        'Sławin':         ['sławin', 'sławinie', 'slawin', 'slawinie'],
        'Sławinek':       ['sławinek', 'sławinku', 'slawinek', 'slawinku'],
        'Czechów':        ['czechów', 'czechow', 'czechowie'],
        'Ponikwoda':      ['ponikwoda', 'ponikwodzie'],
        'Kalinowszczyzna':['kalinowszczyzna', 'kalinowszczyźnie', 'kalina', 'kalinie'],
        'Tatary':         ['tatary', 'tatarach'],
        'Bronowice':      ['bronowice', 'bronowicach'],
        'Kośminek':       ['kośminek', 'kośminku', 'kosminek', 'kosminku'],
        'Dziesiąta':      ['dziesiąta', 'dziesiątej', 'dziesiata', 'dziesiatej'],
        'Abramowice':     ['abramowice', 'abramowicach'],
        'Głusk':          ['głusk', 'głusku', 'glusk', 'glusku'],
        'Zemborzyce':     ['zemborzyce', 'zemborzycach'],
        'Wrotków':        ['wrotków', 'wrotkowie', 'wrotkow', 'wrotkowie'],
        'Czuby':          ['czuby', 'czubach'],
        'Węglin':         ['węglin', 'węglinie', 'weglin', 'weglinie'],
        'Konstantynów':   ['konstantynów', 'konstantynowie'],
        'Rury':           ['rury', 'rurach'],
        'Szerokie':       ['szerokie', 'szerokiem'],
        'Śródmieście':    ['śródmieście', 'śródmieściu', 'srodmiescie', 'srodmiesciu'],
        'Wieniawa':       ['wieniawa', 'wieniawie'],
        'Stare Miasto':   ['stare miasto', 'starym mieście', 'starym miescie'],
        'Felin':          ['felin', 'felinie'],
        'Bazylianówka':   ['bazylianówka', 'bazylianowka', 'bazylianówce', 'bazylianowce'],
        'LSM':            ['lsm'],
    }

    # Pre-buduj reverse map (forma → kanoniczna) dla szybkiego lookup
    _DISTRICT_FORM_MAP = {form: canon for canon, forms in LUBLIN_DISTRICTS.items() for form in forms}

    # Konteksty lokalizacyjne, które potwierdzają że słowo jest dzielnicą (nie szumem).
    # Bez kontekstu nie ufamy — np. "Czuby" w "ul. Czuby 5" to nie dzielnica.
    # Kontekst: PRZED dzielnicą (na, w, dzielnica, osiedle, kierunku, na terenie) lub
    # PO dzielnicy (separator [,/.] + jeszcze coś, lub Lublin/koniec).
    _DISTRICT_CTX_BEFORE = re.compile(
        r'\b(?:na|w|we|dzielnic[aey]|osiedl[eu]|rejon[ie]?|okolic[ae]|stronie|teren[ie]?|'
        r'położon[ya]?|znajduj[eą]?\s+si[eę]|mieszkani[ea]?|pokój|pokoj|blok[iu]?)\s+'
        r'(?:dzielnic[aey]\s+|osiedl[eu]\s+)?'
    )

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        """
        Rozdziela kleszczone tokeny i normalizuje białe znaki.

        Naprawia typowe artefakty po HTML-strippingu opisów OLX, gdzie tekst
        sklejony jest bez spacji w miejscu znaczników HTML.

        Args:
            text: surowy tekst opisu/tytułu oferty

        Returns:
            tekst z rozdzielonymi sklejonymi tokenami i znormalizowanymi spacjami.
            Zwraca pustą wartość dla pustego inputu.

        Przykłady:
            "Ul.KryształowaMieszkanie 3-pokojowe" → "Ul.Kryształowa Mieszkanie 3-pokojowe"
            "1100złKaucja w wysokości"            → "1100zł Kaucja w wysokości"
            "PLN 100Deposit"                       → "PLN 100 Deposit"
            "Pokój  1-osobowy   w  3-pokojowym"   → "Pokój 1-osobowy w 3-pokojowym"

        Zachowuje (nie zmienia):
            "Polski Centrum"          → bez zmian (oba słowa z wielkich liter)
            "M5"                       → bez zmian (po cyfrze nie ma wielkiej litery)
            "1-osobowy", "10A"        → bez zmian (po cyfrze myślnik lub mała litera)
        """
        if not text:
            return text
        # Rozdziel CamelCase: małaWielka → mała Wielka
        text = cls._CAMELCASE_SPLIT.sub(' ', text)
        # Rozdziel cyfrę od wielkiej litery: 100D → 100 D
        text = cls._DIGIT_CAPITAL_SPLIT.sub(' ', text)
        # Normalizacja spacji: deduplikacja podwójnych spacji, taby, newliny
        text = cls._MULTIPLE_WHITESPACE.sub(' ', text)
        return text.strip()

    def __init__(self, geocoding_cache_path: str = "../data/geocoding_cache.json"):
        """
        Args:
            geocoding_cache_path: ścieżka do JSON z geocoding cache (do whitelist Fix #4).
                Jeśli plik nie istnieje, whitelist pozostaje pusty (parser działa bez fallbacku #4).
        """
        # === FIX #4 (2026-05-11): whitelist znanych ulic Lublina z geocoding_cache ===
        # Wczytuje 148+ znanych nazw ulic które już raz geokodowaliśmy.
        # Używane jako TRZECI fallback po extract_address i extract_street_only.
        # Fix #4.1: filtrujemy słowa z EXCLUDED_WORDS (np. "umcs", "pokoje", "kawalerka")
        self._known_streets = self._load_known_streets(geocoding_cache_path, self.EXCLUDED_WORDS)
        # FIX 2026-05-26: hardcoded whitelist znanych ulic Lublina, których brak w geocoding_cache.
        # Trafiają tu nazwy zweryfikowane z OSM/UM Lublin, niemożliwe do wyciągnięcia przez parser
        # z typowych opisów OLX (np. mało wystąpień, brak numeru w opisie).
        self._known_streets |= self.HARDCODED_LUBLIN_STREETS
    
    @staticmethod
    def _load_known_streets(cache_path: str, excluded_words: set = None) -> set:
        """
        Ekstraktuje unikalne nazwy ulic z geocoding_cache.json.
        Zwraca set z nazwami w lowercase dla szybkiego matching case-insensitive.
        
        Args:
            cache_path: ścieżka do geocoding_cache.json
            excluded_words: zbiór słów które NIE mogą być nazwą ulicy (z EXCLUDED_WORDS).
                            Wszystkie wpisy w whitelist są filtrowane przeciwko tej liście.
        """
        excluded_words = excluded_words or set()
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
                
                # KRYTYCZNE (Fix #4.1, 2026-05-11): odrzuć jeśli którekolwiek słowo
                # nazwy ulicy jest w EXCLUDED_WORDS (blackliście słów-szumów)
                # WYJĄTEK: znane ulice Lublina których pierwsze słowo jest w blackliście
                # bo zwykle jest przyimkiem (np. "Przy Stawie", "Na Stoku", "Do Dysa").
                # Lista oparta o OpenStreetMap, weryfikowane realne ulice.
                KNOWN_PREFIXED_STREETS = {
                    'przy stawie', 'przy bocznicy', 'na stoku', 'do dysa',
                }
                street_lower_full = street_name.lower()
                if street_lower_full not in KNOWN_PREFIXED_STREETS:
                    street_words_lower = [w.lower() for w in street_name.split()]
                    if any(w in excluded_words for w in street_words_lower):
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
        
        Strategia matchingu (Fix #4.2 - 2026-05-11):
        1. EXACT match: szukamy znanych ulic w oryginalnym tekście (lowercase).
           Łapie przypadki gdy ulica w opisie jest w tej samej formie co w cache
           (np. cache="Paganiniego" + tekst="ul. Paganiniego").
        2. NOMINATIVE match: jeśli exact nie znalazł, transformujemy słowa tekstu
           do mianownika i próbujemy ponownie (łapie "Lipowej" → "Lipowa").
        
        Returns:
            Dict z 'street', 'number'=None, 'full' lub None jeśli nie znaleziono.
            Adres jest precyzji street_only (brak numeru).
        """
        if not self._known_streets or not text:
            return None
        
        # FIX 2026-05-14: preprocessing — rozdziel sklejone tokeny i znormalizuj spacje.
        text = self._normalize_text(text)
        
        # Normalizacja tekstu: znaki interpunkcyjne na spacje
        normalized_raw = re.sub(r'[^\w\sśćłąęóżźńŚĆŁĄĘÓŻŹŃ]', ' ', text).lower()
        words_raw = normalized_raw.split()
        words_set_raw = set(words_raw)
        
        # === KROK 1: EXACT MATCH (bez transformacji) ===
        # Najczęstszy przypadek: cache i tekst mają tę samą formę nazwy.
        candidates = self._find_in_text(words_set_raw, normalized_raw)
        
        # === KROK 2: NOMINATIVE MATCH (z transformacją do mianownika) ===
        # Jeśli exact nic nie znalazł, próbujemy z mianownikiem ('Lipowej' → 'Lipowa').
        if not candidates:
            try:
                from geocoder import to_nominative
            except ImportError:
                to_nominative = lambda x: x
            
            # Transformacja per-word (tylko dla słów ≥4 znaków)
            nominative_words = []
            for w in words_raw:
                if len(w) >= 4 and w[0].isalpha():
                    nominative_words.append(to_nominative(w).lower())
                else:
                    nominative_words.append(w)
            
            normalized_nom = ' '.join(nominative_words)
            words_set_nom = set(nominative_words)
            
            candidates = self._find_in_text(words_set_nom, normalized_nom)
        
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
    
    def _find_in_text(self, words_set: set, text: str) -> list:
        """
        Pomocnicza: szuka znanych ulic w danym tekście.
        Zwraca listę kandydatów (street_lower, score=length).
        """
        candidates = []
        for street_lower in self._known_streets:
            street_words = street_lower.split()
            if len(street_words) == 1:
                if street_lower in words_set:
                    candidates.append((street_lower, len(street_lower)))
            else:
                pattern = r'\b' + re.escape(street_lower) + r'\b'
                if re.search(pattern, text):
                    candidates.append((street_lower, len(street_lower)))
        return candidates
    
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
        
        # FIX 2026-05-14: preprocessing — rozdziel sklejone tokeny (CamelCase, cyfra+wielka)
        # i znormalizuj spacje. Bez tego parser łapie śmieci typu "of PLN 100D" z "PLN 100Deposit".
        text = self._normalize_text(text)
        
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

        # SPECJALNY PRZYPADEK 2: znane ulice Lublina zaczynające się od słowa w EXCLUDED_WORDS
        # (np. "Przy Stawie", "Na Stoku" - słowa "przy"/"na" są w EXCLUDED_WORDS bo zwykle są
        # przyimkami, nie częścią adresu, ale tu są autentycznymi prefiksami nazwy ulicy).
        # Źródło: OpenStreetMap (potwierdzone realne ulice Lublina).
        # WYMAGA prefiksu adresowego (ul./ulica/ulicy/ulicą) aby uniknąć false-positive
        # np. "Pokój położony jest przy Stawie 5" (gdzie "Stawie 5" to nie adres).
        prefixed_streets = [
            'Przy Stawie',
            'Przy Bocznicy',
            'Na Stoku',
            'Do Dysa',
        ]

        for street_name in prefixed_streets:
            # WYMAGA prefiksu "ul./ulica/ulicy/ulicą" przed nazwą ulicy
            pattern_num = rf'\b(?:ul\.?|ulica|ulicy|ulicą)\s+{re.escape(street_name)}\s+(\d+[a-zA-Z]?(?:/\d+)?)'
            match = re.search(pattern_num, text, re.IGNORECASE)
            if match:
                number = match.group(1)
                try:
                    num_str = number.rstrip('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ/')
                    num_value = int(num_str)
                    if num_value <= 250:
                        return {
                            'street': street_name,
                            'number': number,
                            'full': f"{street_name} {number}"
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
            
            # FIX 2026-05-13: jeśli prefix jest None ale street zaczyna się od formy prefiksu
            # (np. 'ulicy Kryształowej'), oddziel prefiks od nazwy ulicy.
            # Dzieje się tak gdy regex matchuje bez prefiksu (opcjonalnego) i pochłania
            # prefiks-słowo jako pierwszy token nazwy (z IGNORECASE).
            PREFIX_FORMS = {
                'ulica', 'ulicy', 'ulicą', 'ul.', 'ul',
                'aleja', 'aleje', 'alei', 'alejami', 'al.', 'al',
                'plac', 'placu', 'pl.', 'pl',
                'osiedle', 'osiedlu', 'os.', 'os'
            }
            if prefix is None and street:
                first_word = street.split()[0].lower().rstrip('.')
                if first_word in PREFIX_FORMS or (first_word + '.') in PREFIX_FORMS:
                    parts = street.split(maxsplit=1)
                    if len(parts) == 2:
                        prefix = parts[0]
                        street = parts[1].strip()
            
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
                # Mapuj prefiks na pełną nazwę (FIX 2026-05-13: dodano formy gramatyczne)
                if prefix_lower in ['al', 'aleja', 'alei', 'alejami']:
                    full_address = f"Aleja {street}"
                elif prefix_lower in ['aleje']:
                    full_address = f"Aleje {street}"
                elif prefix_lower in ['pl', 'plac', 'placu']:
                    full_address = f"Plac {street}"
                elif prefix_lower in ['os', 'osiedle', 'osiedlu']:
                    full_address = f"Osiedle {street}"
                # ul./ulica/ulicy/ulicą - pomijamy, zostawiamy samą nazwę ulicy
            
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
        
        # FIX 2026-05-14: Jeśli w tekście WIDZIMY jawny prefiks ulicy (ul./al./ulica/aleja/...)
        # to wszystkie matche BEZ prefiksu są podejrzane (np. "co najmniej 6" gdy w tekście
        # jest też "ul. Wigilijnej" bez numeru). W takim wypadku odrzuć kandydatów bez
        # prefiksu - lepiej zwrócić None (fallback do extract_street_only) niż śmieci.
        PREFIX_REGEX = re.compile(
            r'\b(ulica|ulicy|ulicą|ul\.|ul\s|aleja|aleje|alei|alejami|al\.|al\s|'
            r'plac|placu|pl\.|pl\s|osiedle|osiedlu|os\.|os\s)',
            re.IGNORECASE
        )
        text_has_explicit_prefix = bool(PREFIX_REGEX.search(text))
        if text_has_explicit_prefix:
            candidates_with_prefix = [c for c in candidates if c['has_prefix']]
            if candidates_with_prefix:
                # Mamy kandydatów z prefiksem - tylko ich rozważamy
                candidates = candidates_with_prefix
            else:
                # Tekst zawiera prefiks (np. "ul. Wigilijnej") ale parser nie znalazł
                # match z prefiksem (bo nie ma numeru) - odrzuć WSZYSTKICH kandydatów
                # bez prefiksu. Niech fallback (extract_street_only) zadziała.
                print(f"      ⚠️ Tekst zawiera 'ul./al./...' ale parser ma tylko matche bez prefiksu - odrzucam (fallback do street_only)")
                candidates = []
        
        # Jeśli znaleziono kandydatów, wybierz najlepszego (najwyższy priorytet)
        if candidates:
            best = max(candidates, key=lambda x: x['priority'])
            return {
                'street': best['street'],
                'number': best['number'],
                'full': best['full']
            }
        
        # FIX 2026-05-26 (C1): jeśli tekst zawiera jawny prefiks (ul./al./...) i
        # wcześniejszy etap odrzucił matche bez prefiksu, NIE wpadaj w surname fallback —
        # bez tego "Wymagana 1-miesięczna kaucja" trafia jako adres mimo że w tekście
        # jest "ul. Rycerskiej" (właściwa ulica). Lepiej zwrócić None i pozwolić aby
        # extract_street_only / extract_from_whitelist znalazły poprawną ulicę.
        if text_has_explicit_prefix:
            return None

        # NOWY FALLBACK: Wzorzec dla polskich nazwisk w dopełniaczu
        # Łapie przypadki jak "Langiewicza 3A", "Słowackiego 12" bez prefiksu
        # FIX 2026-05-26 (B): match akceptowany TYLKO gdy
        #   (1) w pobliżu (±40 znaków) jest prefiks ul./al./pl./os./ulica/aleja/..., LUB
        #   (2) sama nazwa jest na whitelist znanych ulic Lublina.
        # Bez tego pattern łapie szumy typu "szafami wnękowymi 9", "balkonem w 3",
        # "osobach wychodzi 80", "only a 5" (5 z 9 ofert w no_coords).
        PROXIMITY_PREFIX = re.compile(
            r'\b(ul\.?|al\.?|pl\.?|os\.?|ulica|ulicy|ulicą|aleja|aleje|alei|plac|placu|osiedle|osiedlu)\b',
            re.IGNORECASE
        )
        WINDOW = 40

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

            # FIX 2026-05-26 (B): wymagaj kontekstu (prefiks w pobliżu LUB znana ulica)
            start = max(0, match.start() - WINDOW)
            window_text = text[start:match.start()]
            has_nearby_prefix = bool(PROXIMITY_PREFIX.search(window_text))
            street_lower = street.lower()
            is_known = street_lower in self._known_streets
            # Spróbuj też z mianownikiem (Langiewicza -> Langiewicz)
            if not is_known:
                try:
                    from geocoder import to_nominative
                    is_known = to_nominative(street).lower() in self._known_streets
                except ImportError:
                    pass
            # Spróbuj bez polskich akcentów (Gleboka -> Głęboka match)
            if not is_known:
                _PL = str.maketrans('ąćęłńóśźż', 'acelnoszz')
                street_ascii = street_lower.translate(_PL)
                is_known = any(s.translate(_PL) == street_ascii for s in self._known_streets)

            if not has_nearby_prefix and not is_known:
                continue

            return {
                'street': street,
                'number': number,
                'full': f"{street} {number}"
            }
        
        # BRAK FALLBACK - Wymagamy NUMERU domu!
        # Adresy bez numeru (np. "ul. Niecała") są zbyt nieprecyzyjne dla mapy
        return None

    def extract_district(self, text: str) -> Optional[Dict[str, Optional[str]]]:
        """
        FIX 2026-05-26 (A): czwarty fallback — rozpoznaje dzielnicę Lublina w tekście
        i zwraca jej kanoniczną nazwę. Geocoder zwróci centroid dzielnicy.

        Wymaga KONTEKSTU lokalizacyjnego ("na Sławinku", "dzielnica Czuby", "osiedlu LSM",
        "Bazylianówka/Ponikwoda") — bez tego ryzyko false-positive jest za duże
        (np. "Wieniawa" jako nazwisko właściciela).

        Args:
            text: tekst opisu/tytułu oferty

        Returns:
            Dict z 'street'=None, 'number'=None, 'full'=<Kanoniczna Nazwa Dzielnicy>
            lub None.
        """
        if not text:
            return None

        text = self._normalize_text(text)
        text_lower = text.lower()

        # Dla każdej dzielnicy: sprawdź czy któraś z form występuje w tekście
        # w kontekście lokalizacyjnym (przed nią słowo lokalizacyjne, lub po niej separator).
        candidates = []
        for form, canonical in self._DISTRICT_FORM_MAP.items():
            # Szukamy wystąpień jako oddzielne słowo
            pattern = r'\b' + re.escape(form) + r'\b'
            for m in re.finditer(pattern, text_lower):
                # Kontekst PRZED (±40 znaków): czy jest tam "na/w/dzielnica/osiedle/..."
                window_before = text_lower[max(0, m.start() - 40):m.start()]
                has_ctx_before = bool(self._DISTRICT_CTX_BEFORE.search(window_before))

                # Kontekst PO: separator [/,.\s]+koniec/Lublin, albo pierwsza linia tytułu
                window_after = text_lower[m.end():m.end() + 20]
                has_ctx_after = bool(re.match(
                    r'\s*[/,]\s*[a-ząęćłńóśźż]|\s+lublin\b|\s*\.|\s*$|\s*-',
                    window_after
                ))

                if has_ctx_before or has_ctx_after:
                    # Priorytet: dłuższa forma + kontekst PRZED ważniejszy
                    score = len(form) + (10 if has_ctx_before else 0)
                    candidates.append((canonical, score, m.start()))

        if not candidates:
            return None

        # Wybierz kandydata z najwyższym score, a przy remisie - pierwszy w tekście
        best = max(candidates, key=lambda x: (x[1], -x[2]))
        canonical = best[0]
        return {
            'street': None,
            'number': None,
            'full': canonical,
        }

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

        # FIX 2026-05-14: preprocessing — rozdziel sklejone tokeny i znormalizuj spacje.
        text = self._normalize_text(text)

        candidates = []

        for match in self.STREET_ONLY_PATTERN.finditer(text):
            # FIX 2026-05-14 (P2a): pattern ma teraz 3 grupy
            # - grupa 1: prefiks z kropką (ul./al./pl./os.) lub None
            # - grupa 2: prefiks bez kropki (ul/aleja/...) lub None
            # - grupa 3: nazwa ulicy
            prefix_raw = match.group(1) or match.group(2)
            street_raw = match.group(3).strip()
            match_pos = match.start()  # FIX 2026-05-17 (P3b): pozycja w tekście dla tie-breakera

            # Normalizacja: pierwsze słowo z dużej litery
            street_words = street_raw.split()

            # Walidacja: każde słowo musi mieć min 3 znaki
            if any(len(w) < 3 for w in street_words):
                continue

            # Walidacja: pierwsze słowo nie może być na czarnej liście (lowercase comparison)
            # WYJĄTEK: jeśli cała nazwa (z drugim słowem) jest znaną ulicą Lublina,
            # przepuszczamy mimo że pierwsze słowo jest na blackliście.
            # Powód: ulice typu "Przy Stawie", "Na Stoku" mają pierwsze słowo w EXCLUDED_WORDS
            # bo zwykle jest przyimkiem, ale tu jest częścią autentycznej nazwy ulicy.
            first_word_lower = street_words[0].lower()
            full_lower = ' '.join(w.lower() for w in street_words)
            is_known_full = full_lower in self._known_streets
            if first_word_lower in self.EXCLUDED_WORDS and not is_known_full:
                continue

            # Fix #4.3 (2026-05-11): jeśli któreś ze słów PO pierwszym jest na blackliście,
            # OBETNIJ nazwę do prefiksu zamiast odrzucać cały kandydat.
            # Przykład: "ul. Weteranów Lublin" → przed: None, po: "Weteranów"
            #          "ul. Krakowskie Przedmieście" → bez zmian (oba słowa OK)
            #          "ul. Aleja Racławickie centrum" → "Aleja Racławickie" (ucięte "centrum")
            # WYJĄTEK: jeśli pełna nazwa jest znaną ulicą Lublina (np. "Przy Stawie"),
            # nie ucinamy mimo że pierwsze słowo jest na blackliście.
            if is_known_full:
                # Cała nazwa to znana ulica → zachowaj bez zmian
                pass
            else:
                valid_words = []
                for w in street_words:
                    if w.lower() in self.EXCLUDED_WORDS:
                        break  # przerwij na pierwszym blacklisted słowie
                    valid_words.append(w)

                if not valid_words:
                    continue  # nic nie zostało (nie powinno się stać bo first_word już sprawdzony)

                street_words = valid_words

            # Normalizacja kapitalizacji — każde słowo z dużej litery
            street = ' '.join(w.capitalize() for w in street_words)

            # Mapowanie prefiksu na formę używaną przez geocoder
            prefix_lower = prefix_raw.lower().rstrip('.')
            prefix_full = self.PREFIX_MAP.get(prefix_raw.lower(), '')
            # PREFIX_MAP nie zawiera 'ul' (tylko 'ul.' i 'ulica'), dodaj fallback
            # FIX 2026-05-13: dodano formy gramatyczne (ulicy/ulicą/alei/placu/osiedlu)
            if prefix_lower in ('ul', 'ulica', 'ulicy', 'ulicą'):
                prefix_full = ''
            elif prefix_lower in ('al', 'aleja', 'alei', 'alejami'):
                prefix_full = 'Aleja'
            elif prefix_lower == 'aleje':
                prefix_full = 'Aleje'
            elif prefix_lower in ('pl', 'plac', 'placu'):
                prefix_full = 'Plac'
            elif prefix_lower in ('os', 'osiedle', 'osiedlu'):
                prefix_full = 'Osiedle'

            full_address = f"{prefix_full} {street}".strip() if prefix_full else street

            # FIX 2026-05-17 (P3): priorytet whitelist + fallback do ucinania.
            # Problem: regex może złapać przypadkowe sąsiednie słowo z wielkiej litery
            # jako część wielowyrazowej nazwy ulicy (np. "Skrzatów Super lokalizacja"
            # → "Skrzatów Super"). Stara heurystyka "najdłuższy wygrywa" wybierała wtedy
            # zły kandydat.
            #
            # Hierarchia priorytetów (większy = lepiej):
            #   2 = znana ulica (oryginalna lub ucięta do pierwszego słowa)
            #   1 = nieznana ulica (zachowanie legacy)
            is_known = street.lower() in self._known_streets
            truncated_to_known = False
            if not is_known and len(street_words) > 1:
                first_word = street_words[0]
                if first_word.lower() in self._known_streets:
                    # Ucinamy do pierwszego słowa — to znana ulica
                    street = first_word
                    full_address = f"{prefix_full} {street}".strip() if prefix_full else street
                    truncated_to_known = True

            if is_known or truncated_to_known:
                priority_class = 2
            else:
                priority_class = 1

            candidates.append({
                'street': street,
                'full': full_address,
                'priority_class': priority_class,
                'length': len(street),
                'pos': match_pos,
            })

        if not candidates:
            return None

        # FIX 2026-05-17 (P3b): w klasie znanych ulic (priority_class=2) decyduje
        # CZĘSTOTLIWOŚĆ wystąpień, a przy remisie pozycja PIERWSZEGO wystąpienia.
        # Powód: gdy w tekście jest wiele znanych ulic (np. prawdziwy adres na początku
        # + orientacyjne "al. Racławickie i Konstantynów" dalej), wybieramy tę
        # która jest najczęściej wymieniana (typowo prawdziwy adres pojawia się
        # w tytule i pierwszym akapicie opisu, czyli 2-3 razy, podczas gdy
        # orientacyjne odniesienia tylko raz).
        #
        # W klasie nieznanych (priority_class=1) zachowujemy zachowanie legacy
        # (długość rozstrzyga) — sytuacja gdy nie ma żadnej znanej ulicy
        # i polegamy na "im dłuższa nazwa, tym bardziej specyficzna".
        #
        # Liczenie wystąpień: per `full` (z prefixem), bo to ono trafi do geocodera.
        counts = {}
        first_pos = {}
        for c in candidates:
            key = (c['priority_class'], c['full'])
            counts[key] = counts.get(key, 0) + 1
            if key not in first_pos:
                first_pos[key] = c['pos']

        # Dla nieznanych (klasa 1) usuwamy efekt count/pos — używamy tylko długości,
        # żeby zachować dotychczasowe zachowanie (count=1, pos=0 nieistotne).
        def sort_key(c):
            key = (c['priority_class'], c['full'])
            if c['priority_class'] == 2:
                # znane: priority_class > count > -pos (wcześniej = lepiej) > length
                return (c['priority_class'], counts[key], -first_pos[key], c['length'])
            else:
                # nieznane: priority_class > length (legacy)
                return (c['priority_class'], 0, 0, c['length'])

        best = max(candidates, key=sort_key)
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
        # === FIX 2026-05-14 (P2a): prefiks z kropką BEZ spacji ===
        # Typowe sklejone prefiksy na OLX: "ul.Foo", "al.Foo" - powinny matchować
        ("Wynajmę pokój ul.Nałkowskich Lublin", "Nałkowskich"),
        ("Do wynajęcia studio ul.Furmańska", "Furmańska"),
        ("ul.Kiepury blisko centrum", "Kiepury"),
        ("al.Racławickie świetna okolica", "Aleja Racławickie"),
        ("pl.Litewski blisko", "Plac Litewski"),
        ("os.Sienkiewicza spokojnie", "Osiedle Sienkiewicza"),
        # NEGATYW — prefiks bez kropki i bez spacji NIE powinien matchować
        # (UWAGA: preprocessing wstawia spację dla CamelCase, więc to mimo wszystko
        # zachowuje się jak "al Foo" - znany istniejący artefakt, nie regresja P2a)
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
        # Fix #4.3 (2026-05-11): parser teraz OBCINA "Lublin Witam/Oferuję" zamiast 
        # odrzucać cały kandydat - więc dla "ul. Biskupińska Lublin Witam" zwraca "Biskupińska"
        # (lepszy wynik niż wcześniejszy None!)
        ("pokój ul. Biskupińska Lublin Witam zapraszamy", "Biskupińska"),
        ("pokój ul. Wyścigowa Lublin Witam wszystkich", "Wyścigowa"),
        ("pokój ul. Środkowa Lublin Witam", "Środkowa"),
        ("ul. Czeremchowa Lublin Oferuję ofertę", "Czeremchowa"),
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
        # Akceptujemy oba warianty (cache ma OBIE formy po Fix #3, identyczne coords)
        ("pokój przy Głębokiej, blisko centrum", ["Głęboka", "Głębokiej"]),
        ("blisko Lipowej", "Lipowa"),
        # Dla "Puławskiej" oba warianty (Puławska/Puławskiej) są akceptowalne
        # bo cache ma OBA wpisy z identycznymi coords po Fix #3
        ("okolice Puławskiej", ["Puławska", "Puławskiej"]),
        # POZYTYW - znana ulica w mianowniku
        ("Lipowa 14", "Lipowa"),
        # POZYTYW - kluczowy case z reportu użytkownika (oferta ID1aoyWG)
        # "Paganiniego" jest w cache - exact match musi go znaleźć
        ("Pokój przy ul. Paganiniego w Lublinie blisko UMCS, KUL", "Paganiniego"),
        # NEGATYW - brak znanej ulicy
        ("pokój w spokojnym miejscu", None),
        ("kaucja 250 zł", None),
        ("blisko Stadionu", None),
        # NEGATYW - dzielnica (nie ulica)
        ("Pokój w Wieniawej", None),  # Wieniawa to dzielnica, nie w whitelist jako ulica
        # NEGATYW - UMCS i Pokoje muszą być odfiltrowane z whitelist (Fix #4.1)
        ("Pokój blisko UMCS i KUL", None),
        ("Pokoje wynajmę 5 sztuk", None),
        # Edge cases
        ("", None),
        ("ma od 10 do 20", None),  # tylko krótkie słowa
    ]
    fix4_pass = 0
    fix4_fail = 0
    for text, expected in fix4_cases:
        r = parser.extract_from_whitelist(text)
        actual = r['full'] if r else None
        # Obsługa listy oczekiwanych (akceptowalne warianty)
        if isinstance(expected, list):
            ok = actual in expected
        else:
            ok = actual == expected
        status = "✅" if ok else "❌"
        if ok:
            fix4_pass += 1
        else:
            fix4_fail += 1
        print(f"{status} '{text}' → {actual}")
        if not ok:
            print(f"   Oczekiwano: {expected}")
    print(f"\n📊 FIX #4: {fix4_pass} OK / {fix4_fail} FAIL")

    # ===== FIX 2026-05-14: Testy preprocessing (_normalize_text) =====
    print("\n🧪 FIX 2026-05-14 — preprocessing tekstu (_normalize_text):\n")
    normalize_cases = [
        # CamelCase (P1.a): mała → wielka
        ("Ul.KryształowaMieszkanie 3-pokojowe", "Ul.Kryształowa Mieszkanie 3-pokojowe"),
        ("1100złKaucja w wysokości", "1100zł Kaucja w wysokości"),
        ("ulicaNarutowicza Pokój", "ulica Narutowicza Pokój"),
        # Cyfra → wielka (P1.b)
        ("PLN 100Deposit", "PLN 100 Deposit"),
        ("kwota 500Następnie", "kwota 500 Następnie"),
        ("100zł", "100zł"),  # po cyfrze mała litera — bez zmian
        # Deduplikacja spacji (P3)
        ("Pokój  1-osobowy   w   3-pokojowym", "Pokój 1-osobowy w 3-pokojowym"),
        ("Lublin\n\nul. Lipowa", "Lublin ul. Lipowa"),
        ("  pokój  ", "pokój"),  # trim
        # NEGATYW — nie rozbijać legitymnych konstrukcji
        ("Lublin UMCS KUL", "Lublin UMCS KUL"),
        ("Polski Centrum", "Polski Centrum"),
        ("1-osobowy w 3-pokojowym", "1-osobowy w 3-pokojowym"),
        ("M5", "M5"),  # po cyfrze nie ma wielkiej litery
        ("80A", "80A"),  # po cyfrze mała litera
        ("10A/15", "10A/15"),
        ("ul. Narutowicza 80A", "ul. Narutowicza 80A"),
        # Edge cases
        ("", ""),
        ("    ", ""),
    ]
    norm_pass = 0
    norm_fail = 0
    for text, expected in normalize_cases:
        actual = AddressParser._normalize_text(text)
        ok = actual == expected
        status = "✅" if ok else "❌"
        if ok:
            norm_pass += 1
        else:
            norm_fail += 1
        print(f"{status} {text!r} → {actual!r}")
        if not ok:
            print(f"   Oczekiwano: {expected!r}")
    print(f"\n📊 _normalize_text: {norm_pass} OK / {norm_fail} FAIL")

    # ===== FIX 2026-05-14: integracyjne testy preprocessing → extract_address =====
    # Sprawdzenie czy preprocessing rozwiązuje konkretne case-y z skipped_debug
    print("\n🧪 FIX 2026-05-14 — integracja preprocessing + extract_address:\n")
    integration_cases = [
        # Przypadki "brak współrzędnych" z bezsensownym parsed-adresem
        # PRZED preprocessing parser wyciągał śmieci, PO powinien znaleźć adres albo None
        # Case "of PLN 100D" — w opisie "amount of PLN 100Deposit", po preprocessing nic sensownego
        ("ogrzewanie w wysokości 100 złKaucja w wysokości jednomiesięcznego czynszu", None),
        # Case "KryształowaMieszkanie 3" — po preprocessing "Kryształowa Mieszkanie", a numer 3 to liczba pokoi
        ("Ul.KryształowaMieszkanie 3-pokojowe", None),  # "Mieszkanie" + cyfra-myślnik, brak adresu z numerem
        # NEGATYW (regresja): poprawny adres po preprocessing nadal działa
        ("ul. Narutowicza 80A", "Narutowicza 80A"),
        ("Wynajmę pokój ul. Lipowa 14, kaucja 250 zł", "Lipowa 14"),
    ]
    int_pass = 0
    int_fail = 0
    for text, expected in integration_cases:
        result = parser.extract_address(text)
        actual = result['full'] if result else None
        ok = actual == expected
        status = "✅" if ok else "❌"
        if ok:
            int_pass += 1
        else:
            int_fail += 1
        print(f"{status} {text!r} → {actual}")
        if not ok:
            print(f"   Oczekiwano: {expected}")
    print(f"\n📊 Integracja: {int_pass} OK / {int_fail} FAIL")

    # ===== FIX 2026-05-14 (fix 2): Testy nowych EXCLUDED_WORDS =====
    print("\n🧪 FIX 2026-05-14 (fix 2) — nowe EXCLUDED_WORDS:\n")
    fix2b_cases = [
        # Konkretne przypadki z skipped_debug które wciąż dawały śmieci po fix 1
        # "of PLN 100Deposit" → po preprocessing "of PLN 100 Deposit" → "of" w blackliście
        ("amount of PLN 100Deposit", None),
        # "floor 2.Fees" → po preprocessing "floor 2 Fees" → "floor" w blackliście
        ("on departure, floor 2.Fees and Internet", None),
        # "Lokalizacja 100m od Krwiodawców"
        ("Lokalizacja 100m od Ronda Krwiodawców", None),
        # "ostatnim 3 piętrze"
        ("na oddzielnym, ostatnim 3 piętrze są pokoje", None),
        # "Przestronne 65m mieszkanie"
        ("LUX po remoncie Przestronne 65m mieszkanie", None),
        # "1-osobowy w 3 pokojowym" → "Osiedle obowy w 3" — quick fix przez blacklist
        ("Pokój 1-osobowy w 3 pokojowym 75m mieszkaniu", None),
        # FIX 2026-05-14 hotfix: "komunikacją miejską to 2 przystanki"
        ("Dojazd komunikacją miejską to 2 przystanki od centrum", None),
        # POZYTYW — sprawdzenie regresji: prawdziwe adresy nadal działają
        ("ul. Lipowa 14, blisko centrum", "Lipowa 14"),
        ("Al. Racławickie 6", "Aleja Racławickie 6"),
        ("Narutowicza 38, mieszkanie 4-pokojowe", "Narutowicza 38"),
    ]
    fix2b_pass = 0
    fix2b_fail = 0
    for text, expected in fix2b_cases:
        result = parser.extract_address(text)
        actual = result['full'] if result else None
        ok = actual == expected
        status = "✅" if ok else "❌"
        if ok:
            fix2b_pass += 1
        else:
            fix2b_fail += 1
        print(f"{status} {text!r} → {actual}")
        if not ok:
            print(f"   Oczekiwano: {expected}")
    print(f"\n📊 Fix 2 EXCLUDED_WORDS: {fix2b_pass} OK / {fix2b_fail} FAIL")

    # Total summary
    total_pass = pass_count + fix1_pass + fix2_pass + fix4_pass + norm_pass + int_pass + fix2b_pass
    total_fail = fail_count + fix1_fail + fix2_fail + fix4_fail + norm_fail + int_fail + fix2b_fail
    print(f"\n{'='*60}")
    print(f"📊 ŁĄCZNIE: {total_pass} OK / {total_fail} FAIL")
    print(f"{'='*60}")
