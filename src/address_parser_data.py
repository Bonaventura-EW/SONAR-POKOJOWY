"""
Dane (slowniki / zbiory / mapy) dla AddressParser.
Wydzielone z address_parser.py — czyste dane, bez logiki.

Edytuj TUTAJ: blocklisty slow (EXCLUDED_WORDS), mapy dzielnic (LUBLIN_DISTRICTS),
prefiksy (PREFIX_MAP), hardcoded ulice (HARDCODED_LUBLIN_STREETS).

Po zmianie: python test_address_parser_golden.py
Jesli zmiana zamierzona: python scripts/build_golden.py (aktualizuje golden).
"""

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
    # === FIX 2026-06-09: słowa wyciągane jako pierwszy człon nazwy ulicy ===
    # "Adres Paganiniego 4" → parser brał "Adres" jako część nazwy ulicy.
    # "Głęboka Samochód 9m" → "Samochód" wciągany jako drugi człon nazwy.
    'adres', 'adresie', 'adresu', 'adresem',
    'samochód', 'samochodem', 'samochodu', 'samochody', 'auto', 'autem',
    # === FIX 2026-07-09: szum odsłonięty przez priorytet pozycyjny ===
    # "(całość 72m²)" → "całość 72", "TV SAMSUNG SMART 32" → "SAMSUNG SMART 32"
    'całość', 'całości', 'samsung', 'smart', 'orange', 'światłowodowy',
    # === FIX 2026-07-09b: śmieciowe drugie człony nazw ulic (audyt dry-run bazy) ===
    # "Nadbystrzycka Szukasz", "Nowowiejskiego Odstąpię", "Kleeberga Koszt",
    # "Emancypantek Zarówno", "Panorama Podnajmę"
    # UWAGA: NIE dodawaj 'przytulna/przytulny' — ul. Przytulna to realna ulica Lublina!
    'szukasz', 'odstąpię', 'odstapie', 'podnajmę', 'podnajme', 'zarówno',
    'koszt', 'koszty',
}


HARDCODED_LUBLIN_STREETS = {
    'rycerska',
    # FIX 2026-07-09: "pokoju" jest w EXCLUDED_WORDS, więc ulica nigdy nie
    # przechodzi filtra słów ani nie trafia na whitelistę z geocoding_cache.
    'obrońców pokoju',
}


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
