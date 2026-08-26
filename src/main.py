"""
SONAR POKOJOWY - Główny agent
Koordynuje: scraping → parsowanie → geokodowanie → wykrywanie duplikatów → zapis
WERSJA 2.0: Równoległy scraping + monitoring
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
import pytz
from typing import List, Dict, Optional
import time
import random
import statistics

# Import lokalnych modułów
from scraper import OLXScraper
from profiles_config import TRACKED_PROFILES
from address_parser import AddressParser
from price_parser import PriceParser
from geocoder import Geocoder
from duplicate_detector import DuplicateDetector
from scan_logger import ScanLogger
from shared_utils import write_json_atomic, DATA_DIR

class SonarPokojowy:
    # Hierarchia precyzji adresu — im wyżej, tym lepszy marker. Używane przy
    # rozstrzyganiu "świeży parsing vs adres z cache" w _process_offer.
    _PRECISION_RANK = {'exact': 2, 'street_only': 1, 'district': 0}

    def __init__(self, data_file: str = "../data/offers.json"):
        self.data_file = Path(data_file)
        self.address_parser = AddressParser(geocoding_cache_path="../data/geocoding_cache.json")
        self.price_parser = PriceParser()
        self.geocoder = Geocoder(cache_file="../data/geocoding_cache.json")
        self.duplicate_detector = DuplicateDetector(similarity_threshold=0.95)
        self.scan_logger = ScanLogger(log_file="../data/scan_history.json")
        
        # Strefa czasowa polska
        self.tz = pytz.timezone('Europe/Warsaw')

        # Licznik korekt adresu z re-parsingu (ten sam tekst, lepszy wynik parsera).
        # Raportowany w scan_history.json — nagły skok = zmiana w parserze przepisała
        # pół bazy i warto na to spojrzeć, zamiast odkryć to przypadkiem na mapie.
        self._addr_corrections_count = 0
        
        # Wczytaj istniejącą bazę
        self.database = self._load_database()

        # Inicjalizuj scraper Z istniejącymi ofertami (inteligentne pomijanie)
        existing_offers = self._build_existing_offers_index()
        self.scraper = OLXScraper(delay_range=(0.2, 0.5), max_workers=10, existing_offers=existing_offers)

        # Próg cenowych outlierów (10x średnia aktywnej bazy) — liczony raz na scan,
        # z bazy sprzed scanu. Chroni przed literówkami/błędami parsera cen
        # (np. "9500" zamiast "950") i ofertami nie-pokojowymi z absurdalną ceną.
        self._price_outlier_threshold = self._compute_price_outlier_threshold()
    
    def _build_existing_offers_index(self) -> Dict:
        """
        Buduje indeks istniejących ofert dla inteligentnego pomijania.
        Zawiera WSZYSTKIE oferty (aktywne + nieaktywne z ostatnich 30 dni)
        aby umożliwić reaktywację ofert które tymczasowo zniknęły.
        Returns: {offer_id: {'price': X, 'description': '...', 'was_active': bool}}
        """
        index = {}
        active_count = 0
        inactive_count = 0
        cutoff_date = datetime.now(self.tz) - timedelta(days=30)
        
        for offer in self.database.get('offers', []):
            is_active = offer.get('active', False)
            
            # Nieaktywne oferty: tylko te z ostatnich 30 dni
            if not is_active:
                try:
                    last_seen = datetime.fromisoformat(offer['last_seen'])
                    if last_seen < cutoff_date:
                        continue  # Pomiń stare nieaktywne oferty
                except (ValueError, KeyError):
                    continue
            
            offer_entry = {
                'price': offer.get('price', {}).get('current'),
                'description': offer.get('description', ''),
                'previous_price': offer.get('price', {}).get('previous_price'),
                'was_active': is_active,
                'address': offer.get('address', {}),
                # LEGACY: top-level 'coordinates' (122 ofert sprzed migracji do address.coords).
                # Scraper czyta najpierw address.coords, ten klucz tylko jako fallback.
                # Pole jest stopniowo wycofywane.
                'coordinates': offer.get('coordinates', {}),
                'profile_name': offer.get('profile_name'),
                # FIX 2026-08-18 (audyt markerów, klasa E): scraper porównuje tytuł
                # z listingu z tym z bazy — przepisany tytuł (podmienione mieszkanie
                # w tym samym ogłoszeniu) musi wymusić pobranie szczegółów i re-parsing
                # adresu, inaczej marker zostaje pod starym adresem.
                'title': offer.get('title'),
            }
            # Indeksuj po pełnym ID
            index[offer['id']] = offer_entry
            # Indeksuj też po krótkim ID końcowym (IDxxxxx)
            # OLX zmienia slug w URL gdy edytowany tytuł — końcówka pozostaje taka sama
            if '-ID' in offer['id']:
                short_id = offer['id'].split('-ID')[-1]
                if len(short_id) >= 3:
                    index[f'_short_{short_id}'] = offer_entry
            
            if is_active:
                active_count += 1
            else:
                inactive_count += 1
        
        print(f"📚 Zaindeksowano {len(index)} ofert do inteligentnego pomijania "
              f"({active_count} aktywnych, {inactive_count} nieaktywnych z ostatnich 30 dni)")
        return index
    
    def _compute_price_outlier_threshold(self, multiplier: float = 10) -> float:
        """
        Liczy próg cenowego outliera: multiplier x średnia cena aktywnych ofert
        w bazie (stan sprzed bieżącego scanu). Oferty z ceną >= progu są
        odrzucane w _process_offer jako podejrzane (literówka/błąd parsera,
        oferta nie-pokojowa z absurdalną ceną).

        Zwraca None gdy baza ma za mało aktywnych ofert z ceną (świeży start) -
        wtedy filtr jest wyłączony, bo średnia byłaby niemiarodajna.
        """
        prices = [
            o['price']['current']
            for o in self.database.get('offers', [])
            if o.get('active') and o.get('price', {}).get('current')
        ]
        if len(prices) < 10:
            return None
        avg_price = sum(prices) / len(prices)
        threshold = avg_price * multiplier
        print(f"📊 Próg outlierów cenowych: {multiplier}x średnia ({avg_price:.0f} zł) = {threshold:.0f} zł")
        return threshold

    def _load_database(self) -> Dict:
        """Wczytuje bazę danych z JSON."""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print("⚠️ Uszkodzony plik bazy danych, tworzę nowy")
                return self._create_empty_database()
        else:
            return self._create_empty_database()
    
    def _create_empty_database(self) -> Dict:
        """Tworzy pustą strukturę bazy danych."""
        return {
            "last_scan": None,
            "next_scan": None,
            "offers": []
        }
    
    def _save_database(self):
        """Zapisuje bazę danych do JSON (atomowo — crash nie utnie offers.json)."""
        write_json_atomic(self.data_file, self.database)
        print(f"💾 Baza zapisana: {self.data_file}")
    
    def _calculate_next_scan_time(self) -> str:
        """Oblicza czas następnego scanu (9:00, 15:00 lub 21:00)."""
        now = datetime.now(self.tz)
        scan_hours = [9, 15, 21]
        
        for hour in scan_hours:
            next_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if next_time > now:
                return next_time.isoformat()
        
        # Jeśli po 21:00, to następny scan o 9:00 następnego dnia
        tomorrow = now + timedelta(days=1)
        next_time = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
        return next_time.isoformat()
    
    def _is_bogus_address(self, address_full: str) -> bool:
        """
        Sprawdza czy adres jest "bogus" - artefakt starego parsera, słowa
        z opisu które nie są ulicami (np. "Pokoje", "UMCS", "Lublin Studio").
        
        Heurystyka łączona (Fix 2026-05-14):
        1. Statyczna lista BOGUS_ADDRESSES (dla wzorców złożonych typu "Lublin Studio")
        2. DYNAMIC: pierwsze słowo (lower) w EXCLUDED_WORDS parsera
           - to łapie wszystko co parser by ODRZUCIŁ przy świeżym parsowaniu
           - więc jest spójne z aktualną logiką parsera (jeden source of truth)
        
        Args:
            address_full: string z address.full w bazie
        
        Returns:
            True jeśli adres wygląda na artefakt, False jeśli wygląda na prawdziwy adres
        """
        if not address_full:
            return True  # pusty/None = bogus
        
        # Lista wzorców złożonych (multi-word prefixów) - musi pozostać statyczna
        BOGUS_PREFIXES = (
            'Lublin Studio', 'Lublin Witam', 'Lublin Oferuję',
            'Lublin Duży', 'Lublin Pokoje', 'Witam ', 'Oferuję ',
            'Kaucja', 'Depozyt'
        )
        if any(address_full.startswith(p) for p in BOGUS_PREFIXES):
            return True
        
        # Dynamiczna heurystyka: pierwsze słowo (case-insensitive) w EXCLUDED_WORDS parsera
        tokens = address_full.split()
        if not tokens:
            return True
        first_word = tokens[0].lower().rstrip('.,;:')
        if first_word in self.address_parser.EXCLUDED_WORDS:
            return True
        
        return False

    def _geocode_with_fallbacks(self, address_data: Dict, address_precision: str,
                                full_text: str, raw_offer: Dict):
        """
        FIX 2026-06-09: geokoduje adres z łańcuchem fallbacków na poziomie ekstraktorów.

        Próbuje geokodować KOLEJNO kandydatów adresu, od najbardziej precyzyjnego:
          1. address_data (główny — zwykle z extract_address, precision='exact')
          2. extract_street_only  (precision='street_only')
          3. extract_from_whitelist (precision='street_only')
          4. extract_district     (precision='district')

        Pierwszy kandydat który się zgeokoduje wygrywa. Bez tego błędnie sparsowany
        adres z numerem (np. "Gabriela Narutowicza 50" → centroid poza Lublinem,
        "Adres Paganiniego 4", "Głęboka Samochód 9m") zabija ofertę, mimo że poprawna
        ulica jest dostępna z innego ekstraktora.

        Returns:
            (coords, chosen_address_data, chosen_precision)
            coords=None jeśli ŻADEN kandydat się nie zgeokodował (wtedy zwracamy
            oryginalny address_data/precision dla logu).

        Efekt uboczny: ustawia self._geocode_transient=True jeśli któryś kandydat
        padł na TYMCZASOWY błąd Nominatim (timeout/429/5xx) — run_scan użyje tego
        do ponowienia oferty w kolejce retry (zamiast liczyć ją jako no_coords).
        """
        description = raw_offer.get('description', '')

        # Zbuduj listę kandydatów w kolejności precyzji, deduplikując po 'full'.
        candidates = [(address_data, address_precision)]

        def _add(extractor_result, precision):
            if extractor_result and extractor_result.get('full'):
                candidates.append((extractor_result, precision))

        # street_only / whitelist / district — liczone leniwie tylko jako fallback
        _add(self.address_parser.extract_street_only(full_text)
             or (self.address_parser.extract_street_only(description) if description else None),
             'street_only')
        _add(self.address_parser.extract_from_whitelist(full_text)
             or (self.address_parser.extract_from_whitelist(description) if description else None),
             'street_only')
        _add(self.address_parser.extract_district(full_text)
             or (self.address_parser.extract_district(description) if description else None),
             'district')

        tried_full = set()
        transient = False
        for cand, precision in candidates:
            full = cand['full']
            if full in tried_full:
                continue
            tried_full.add(full)

            # FIX 2026-05-14: return_meta=True → wiemy czy geocoder zrobił fallback
            # "sama ulica bez numeru" (wtedy obniżamy precision do street_only).
            coords, geo_meta = self.geocoder.geocode_address(full, return_meta=True)
            if geo_meta.get('transient_error'):
                transient = True
            if not coords:
                continue

            if len(tried_full) > 1:
                print(f"      🔁 Fallback ekstraktora: główny adres nie geokodował się, "
                      f"użyto '{full}' (precision={precision})")

            if geo_meta.get('number_fallback') and precision != 'district':
                # Geocoder nie znalazł konkretnego numeru, użył samej ulicy → przybliżony.
                # FIX 2026-05-26 (A): nie nadpisujemy precision='district'.
                print(f"      📌 Fallback geocoder: '{full}' "
                      f"→ koordynaty samej ulicy (precision=street_only)")
                precision = 'street_only'

            return coords, cand, precision

        # Żaden kandydat się nie zgeokodował — zapamiętaj czy to był transient fail.
        if transient:
            self._geocode_transient = True
        return None, address_data, address_precision

    def _process_offer(self, raw_offer: Dict) -> Dict:
        """
        Przetwarza surowe ogłoszenie: parsuje adres, cenę, geokoduje.
        
        Returns:
            Dict z przetworzonymi danymi lub None jeśli oferta nieprawidłowa
        """
        # Reset flagi transient-fail geokodera (ustawiana w _geocode_with_fallbacks,
        # odczytywana przez run_scan do kolejki retry).
        self._geocode_transient = False
        # FIX 2026-06-09: jawny powód odrzucenia oferty (zamiast zgadywania przez
        # re-derywację w run_scan). Ustawiany przed każdym `return None`.
        # Wartości: 'excluded' | 'no_address' | 'no_price' | 'no_coords' | 'price_outlier' | None.
        self._skip_reason = None
        self._skip_detail = None  # dodatkowy kontekst (np. dopasowana fraza wykluczenia)

        # 1. Użyj pełnego opisu (scraper już go pobrał)
        full_text = raw_offer['title'] + " " + raw_offer.get('description', '')
        
        # FILTR: Wykluczamy ogłoszenia które nie są pokojami w mieszkaniach
        # FIX 2026-05-17: usunięto 'bliźniak', 'dom jednorodzinny', 'w domu jednorodzinnym'
        # po audycie skipped_offers_sample - generowały ~28% false positives w no_address
        # (pokoje na oddzielnej kondygnacji w domu są funkcjonalnie identyczne z pokojami
        # w mieszkaniu i powinny być uwzględniane). Patrz: discussion 2026-05-17.
        # FIX 2026-06-09: usunięto 'domek jednorodzinny', 'willa', 'domek',
        # 'dom w zabudowie', 'segment' — łapały LEGALNE pokoje do wynajęcia, w których
        # budynek opisano jako domek/segment/willa (Chodźki/Wilczej/Chmielewskiego).
        # To pokoje, nie całe nieruchomości — mają trafiać na mapę. Decyzja Mateusza.
        excluded_phrases = []
        
        full_text_lower = full_text.lower()
        for phrase in excluded_phrases:
            if phrase in full_text_lower:
                print(f"      ⚠️ Wykluczono: {phrase}")
                self._skip_reason = 'excluded'
                self._skip_detail = phrase
                return None
        
        # 2. Parsuj adres — TYTUŁ MA PIERWSZEŃSTWO (decyzja Mateusza 2026-07-09):
        # adres z tytułu to adres oferty; opisy firm wymieniają też inne lokalizacje
        # i adres z opisu może dotyczyć innego mieszkania tego samego wynajmującego.
        address_data = self.address_parser.extract_address(raw_offer['title'])
        address_precision = 'exact'  # domyślnie: dokładny adres z numerem
        # Czy adres pochodzi z SAMEGO tytułu? Potrzebne niżej: adres wyciągnięty
        # z opisu firmówki bywa adresem innego mieszkania tego samego wynajmującego.
        address_from_title = bool(address_data)

        # Tytuł bez adresu → szukaj w pełnym tekście (tytuł + opis), potem w samym opisie
        if not address_data:
            address_data = self.address_parser.extract_address(full_text)
        if not address_data and raw_offer.get('description'):
            print(f"      🔍 Brak adresu w tytule, szukam w opisie...")
            address_data = self.address_parser.extract_address(raw_offer['description'])

        # FALLBACK: spróbuj wyciągnąć samą ulicę (bez numeru) → marker "przybliżony"
        # Decyzja 1a: tylko jawny prefiks (ul./al./pl./os./aleja/aleje/ulica)
        if not address_data:
            street_only = self.address_parser.extract_street_only(raw_offer['title'])
            address_from_title = bool(street_only)
            if not street_only:
                street_only = self.address_parser.extract_street_only(full_text)
            if not street_only and raw_offer.get('description'):
                street_only = self.address_parser.extract_street_only(raw_offer['description'])
            if street_only:
                print(f"      📍 Brak numeru, używam przybliżonego adresu: {street_only['full']}")
                address_data = street_only
                address_precision = 'street_only'
        
        # FIX #4 (2026-05-11): Whitelist znanych ulic z geocoding_cache
        # Trzeci fallback - jeśli żaden z poprzednich parserów nic nie złapał,
        # szukamy w tekście jakiejkolwiek znanej nazwy ulicy z bazy.
        if not address_data:
            whitelist_match = self.address_parser.extract_from_whitelist(raw_offer['title'])
            address_from_title = bool(whitelist_match)
            if not whitelist_match:
                whitelist_match = self.address_parser.extract_from_whitelist(full_text)
            if not whitelist_match and raw_offer.get('description'):
                whitelist_match = self.address_parser.extract_from_whitelist(raw_offer['description'])
            if whitelist_match:
                print(f"      📚 Znaleziono w whitelist: {whitelist_match['full']}")
                address_data = whitelist_match
                address_precision = 'street_only'

        # FIX 2026-05-26 (A): czwarty fallback — rozpoznaj DZIELNICĘ Lublina.
        # Markery na poziomie centroidu dzielnicy (precision='district') — mniej dokładne,
        # ale lepsze niż pomijanie ofert mówiących tylko "na Sławinku", "Czuby", "LSM".
        if not address_data:
            district_match = self.address_parser.extract_district(full_text)
            if not district_match and raw_offer.get('description'):
                district_match = self.address_parser.extract_district(raw_offer['description'])
            if district_match:
                print(f"      🗺️  Rozpoznano dzielnicę: {district_match['full']}")
                address_data = district_match
                address_precision = 'district'

        # ADRES Z CACHE — oferta pominięta przez inteligentne skanowanie (ta sama cena)
        # albo reaktywowana po okresie nieaktywności.
        #
        # FIX 2026-07-26: ten blok stał WYŻEJ, przed fallbackami street_only/whitelist/
        # district, i wygrywał z nimi bezwarunkowo. Efekt: oferta bez adresu Z NUMEREM
        # w tekście dostawała przy każdym skanie z powrotem swój stary adres, więc raz
        # źle sparsowany marker był zamrożony NA ZAWSZE — żadna późniejsza poprawka
        # parsera do niego nie docierała (ID13SWxI: 'Braci Wieniawskich' z opisu
        # "pasaż handlowy przy ul. …" zamiast 'ul. Kaprysowa' z tytułu).
        #
        # Teraz cache jest OSTATNIĄ deską ratunku i wygrywa tylko wtedy, gdy jest
        # PRECYZYJNIEJSZY od świeżego parsingu (numer bije samą ulicę, ulica bije
        # dzielnicę). Dzięki temu re-parsing nie degraduje ofert z dokładnym adresem
        # w bazie (ID1buaHj: 'Nadbystrzycka 39' nie może przegrać z landmarkiem 'Zana').
        use_cached_coords = False
        cached_coords = None
        cached_addr_raw = raw_offer.get('cached_address')
        if cached_addr_raw:
            # NORMALIZACJA: cached_address może być dictem (nowy schema z address dict)
            # lub stringiem (legacy). Geocoder.geocode_address() oczekuje stringa,
            # a używanie dict-a jako klucza cache crashuje z 'unhashable type: dict'.
            if isinstance(cached_addr_raw, dict):
                cached_full = cached_addr_raw.get('full', '')
                cached_street = cached_addr_raw.get('street')
                cached_number = cached_addr_raw.get('number')
                cached_precision = cached_addr_raw.get('precision', 'exact')
            else:
                # legacy: string
                cached_full = str(cached_addr_raw)
                cached_street = None
                cached_number = None
                # FIX 2026-08-01: goły string cache domyślnie dostawał precision='exact'
                # (rank 2) — mina, przez którą ZGRUBNA etykieta (np. lokalizacja z OLX
                # API "Szerokie", bez numeru, będąca nazwą dzielnicy/miejscowości) biła
                # realną ulicę sparsowaną z tytułu (ID1aTdJS: "ul. Biedronki" → marker
                # 2 km obok). String bez cyfry, który parser rozpoznaje jako dzielnicę,
                # to poziom dzielnicy, nie exact. Realne ulice (z numerem albo spoza
                # listy dzielnic, np. "Krakowskie Przedmieście") zostają exact.
                if not any(ch.isdigit() for ch in cached_full) \
                        and self.address_parser.extract_district(cached_full):
                    cached_precision = 'district'
                else:
                    cached_precision = 'exact'

            cached_same_as_fresh = bool(
                address_data
                and (address_data.get('full') or '').strip().lower() == cached_full.strip().lower()
            )

            cached_rank = self._PRECISION_RANK.get(cached_precision, 0)
            fresh_rank = self._PRECISION_RANK.get(address_precision, 0)

            def _is_estate(name: str) -> bool:
                """Nazwa osiedla ('Osiedle Panorama') to nie ulica — lokalizuje z
                dokładnością osiedla, choć parser oznacza ją jako street_only."""
                return (name or '').strip().lower().startswith(('osiedle ', 'os. ', 'os '))

            # REMIS PRECYZJI — kto wygrywa, gdy świeży parsing i baza są tak samo dokładne.
            # Domyślnie świeży (o to chodzi w odmrożeniu re-parsingu), z dwoma wyjątkami:
            cache_wins_tie = bool(address_data) and cached_rank == fresh_rank and (
                # 1. Firmówka + adres z OPISU: opisy firm wymieniają wszystkie swoje
                #    lokalizacje ("Dostępność innych lokalizacji: ul. X, ul. Y"), więc
                #    taki adres potrafi dotyczyć innego mieszkania tego wynajmującego
                #    (ID19xpQK: 'Zana 58' → 'Kazimierza Wielkiego 3'). Tytuł ma
                #    pierwszeństwo nad opisem — decyzja z 2026-07-09.
                (raw_offer.get('profile_name') and not address_from_title)
                # 2. Nazwa osiedla nie nadpisuje konkretnej ulicy z bazy
                #    (ID1765JD: 'Garbarskiej' z "przy ulicy Garbarskiej" w opisie
                #    przegrywało z 'Osiedle Panorama' z tytułu).
                or (_is_estate(address_data.get('full')) and not _is_estate(cached_full))
            )

            if not cached_full:
                print(f"      ⚠️ cached_address bez 'full', pomijam reaktywację z cache")
            elif self._is_bogus_address(cached_full):
                # Fix #4.4 (2026-05-11): bogus w cache NIE wraca do bazy. Świeży parsing
                # miał już swoją szansę wyżej — jeśli nic nie dał, oferta poleci w
                # no_address (Fix #4.5 dezaktywuje ją w _mark_inactive_offers).
                print(f"      🔍 cached_address '{cached_full}' wygląda na bogus — ignoruję cache")
            elif not address_data or cached_rank > fresh_rank or cache_wins_tie:
                if address_data:
                    print(f"      🔒 Zachowano adres z bazy: '{cached_full}' ({cached_precision}) "
                          f"zamiast '{address_data['full']}' ({address_precision})")
                else:
                    print(f"      🔄 Brak adresu w tekście, używam z cache: {cached_full}")
                address_data = {
                    'full': cached_full,
                    'street': cached_street,
                    'number': cached_number
                }
                if raw_offer.get('cached_coordinates'):
                    cached_coords = raw_offer['cached_coordinates']
                    use_cached_coords = True
                address_precision = cached_precision
            elif cached_same_as_fresh and raw_offer.get('cached_coordinates'):
                # Świeży parsing dał DOKŁADNIE ten sam adres co w bazie (przypadek
                # zdecydowanej większości ofert pominiętych) — nie ma po co geokodować
                # drugi raz, bierzemy gotowe współrzędne.
                cached_coords = raw_offer['cached_coordinates']
                use_cached_coords = True

        if not address_data:
            self._skip_reason = 'no_address'
            return None  # Brak adresu → ignoruj
        
        # 3. Parsuj cenę - NOWA LOGIKA TRÓJPOZIOMOWA (2C)
        # PRIORYTET 1: JSON-LD z OLX (najbardziej niezawodne, oficjalne dane)
        # PRIORYTET 2: Cache (dane z poprzedniego skanu - równie niezawodne jak JSON-LD)
        # PRIORYTET 3: Parser ceny z treści (wyciąga czystą cenę pokoju bez mediów)
        # PRIORYTET 4: Fallback HTML (jeśli JSON-LD i parser zawiodły)
        
        price = None
        media_info = "brak informacji"
        price_source = None
        
        # Sprawdź czy mamy JSON-LD z niezawodną ceną
        if raw_offer.get('official_price') and raw_offer.get('price_source') == 'json-ld':
            # PRIORYTET 1: JSON-LD - najbardziej niezawodne źródło
            price = raw_offer['official_price']
            price_source = "JSON-LD (OLX)"
            
            # Wykryj info o mediach używając parsera (BEZ parsowania ceny!)
            media_info = self.price_parser.detect_media_info_only(full_text)
            
            print(f"      💰 Użyto ceny JSON-LD: {price} zł ({media_info})")
        
        # PRIORYTET 2: Cache - dane z poprzedniego skanu (równie niezawodne)
        elif raw_offer.get('official_price') and raw_offer.get('price_source') == 'cache':
            # Cache - oferta pominięta w scraping bo cena się nie zmieniła
            price = raw_offer['official_price']
            price_source = "cache"
            
            # Wykryj info o mediach używając parsera (BEZ parsowania ceny!)
            media_info = self.price_parser.detect_media_info_only(full_text)
            
            print(f"      💰 Użyto ceny z cache (pominięto pobieranie): {price} zł ({media_info})")
        
        # PRIORYTET 3: Parser tekstowy - wyciąga czystą cenę pokoju
        if not price:
            price_data = self.price_parser.extract_price(full_text)
            if price_data:
                price = price_data['price']
                media_info = price_data['media_info']
                price_source = "Parser tekstowy"
                print(f"      💰 Użyto parsera ceny z opisu: {price} zł ({media_info})")
        
        # PRIORYTET 4: Fallback - cena z HTML (jeśli JSON-LD i parser zawiodły)
        if not price and raw_offer.get('official_price'):
            price = raw_offer['official_price']
            media_info = self.price_parser.detect_media_info_only(full_text)
            price_source = "HTML fallback"
            print(f"      💰 Użyto ceny HTML (fallback): {price} zł ({media_info})")
        
        if not price:
            self._skip_reason = 'no_price'
            return None  # Brak ceny → ignoruj

        # FILTR: cena-outlier (>= 10x średnia aktywnej bazy) — nie zbieramy takich
        # ofert. Zwykle to literówka/błąd parsera (np. "9500" zamiast "950") albo
        # oferta nie-pokojowa (całe mieszkanie/dom) z absurdalną ceną.
        if self._price_outlier_threshold and price >= self._price_outlier_threshold:
            print(f"      🚫 Cena-outlier: {price} zł >= {self._price_outlier_threshold:.0f} zł "
                  f"(10x średnia) — pomijam")
            self._skip_reason = 'price_outlier'
            return None

        # 4. Geokoduj adres (lub użyj cache dla reaktywacji)
        if use_cached_coords and cached_coords:
            coords = cached_coords
            print(f"      📍 Użyto współrzędnych z cache: {coords['lat']:.4f}, {coords['lon']:.4f}")
        else:
            # FIX 2026-06-09: geokodowanie z łańcuchem fallbacków na poziomie EKSTRAKTORÓW.
            # Jeśli główny (zwykle exact) adres nie geokoduje się, próbujemy alternatyw
            # z pozostałych ekstraktorów (street_only / whitelist / district) ZANIM
            # porzucimy ofertę. Bez tego błędnie sparsowany adres z numerem
            # (np. "Gabriela Narutowicza 50" → poza Lublinem, "Adres Paganiniego 4",
            # "Głęboka Samochód 9m") zabijał ofertę, mimo że poprawna ulica
            # ("Narutowicza", "Paganiniego", "Bursztynowa") była dostępna z innego ekstraktora.
            coords, address_data, address_precision = self._geocode_with_fallbacks(
                address_data, address_precision, full_text, raw_offer
            )
            if not coords:
                print(f"⚠️ Nie można geokodować: {address_data['full']}")
                self._skip_reason = 'no_coords'
                return None  # Nie znaleziono współrzędnych → ignoruj
        
        # 5. Stwórz ID z URL (unikalne)
        offer_id = raw_offer['url'].split('/')[-1].split('.')[0]

        # Tytuł ogłoszenia — czysty og:title (fallback: title z listingu). Do wyświetlania
        # i śledzenia zmian tytułu (title_versions). NIE mylić z raw_offer['title'],
        # którego używa parser adresu.
        _now_iso = datetime.now(self.tz).isoformat()
        _title0 = (raw_offer.get('og_title') or raw_offer.get('title') or '').strip()

        return {
            'id': offer_id,
            'url': raw_offer['url'],
            'address': {
                'full': address_data['full'],
                'street': address_data.get('street'),
                'number': address_data.get('number'),
                'coords': coords,
                'precision': address_precision  # 'exact' lub 'street_only'
            },
            'price': {
                'current': price,
                'history': [price],
                'history_full': [{'price': price, 'date': datetime.now(self.tz).isoformat(), 'approximated': False}],
                'media_info': media_info,
                'source': price_source  # Dodane: JSON-LD / Parser / HTML fallback
            },
            'description': full_text,
            'title': _title0,           # tytuł ogłoszenia (og:title) — do wyświetlania i historii
            'title_versions': ([{'title': _title0, 'first_seen': _now_iso, 'last_seen': None}]
                               if _title0 else []),
            'title_change_count': 0,
            'title_changed_at': None,
            'first_seen': datetime.now(self.tz).isoformat(),
            'last_seen': datetime.now(self.tz).isoformat(),
            'active': True,
            'days_active': 0,
            'profile_name': raw_offer.get('profile_name'),  # None lub klucz profilu firmowego
            'offer_type': raw_offer.get('offer_type'),  # 'pokoj'/'mieszkanie'/'inne'
            'city': raw_offer.get('city', ''),  # miasto z API OLX
            # Śledzenie odświeżeń (bump) i reaktywacji — tylko dla ofert firmowych
            'refresh_count': 0,          # ile razy odświeżono (max 1/dzień)
            'refresh_dates': [],         # lista dat odświeżeń ['YYYY-MM-DD', ...]
            'last_refresh_date': raw_offer.get('api_last_refresh', ''),
            'reactivation_count': 0,     # ile razy reaktywowano po zniknięciu
            'reactivation_dates': [],    # daty reaktywacji ['YYYY-MM-DDT...', ...]
            # Płatne wyróżnienie na listingu OLX (scraper._is_promoted_href).
            # `promoted` = stan z OSTATNIEGO skanu, `promoted_dates` = dni, w
            # których ofertę widzieliśmy jako promowaną (max 1/dzień) — z tego
            # trend_generator buduje dzienny szereg „ile ofert jest promowanych".
            'promoted': bool(raw_offer.get('promoted')),
            'promoted_dates': ([datetime.now(self.tz).strftime('%Y-%m-%d')]
                               if raw_offer.get('promoted') else []),
            'promoted_count': 1 if raw_offer.get('promoted') else 0,
        }
    
    def _find_existing_offer(self, offer_id: str) -> Dict:
        """Znajduje istniejące ogłoszenie po ID."""
        for offer in self.database['offers']:
            if offer['id'] == offer_id:
                return offer
        return None

    def _find_existing_offer_by_short_id(self, short_id: str) -> Dict:
        """Znajduje istniejące ogłoszenie po krótkiej końcówce ID (IDxxxxx).
        OLX zmienia slug URL gdy edytowany tytuł/adres — końcówka (ID OLX) pozostaje ta sama.
        Gdy w bazie jest kilka rekordów z tą samą końcówką (historyczne duplikaty),
        zwraca najlepszego kandydata: aktywny > najświeższy last_seen."""
        if not short_id or len(short_id) < 3:
            return None
        suffix = f'-ID{short_id}'
        candidates = [o for o in self.database['offers'] if o.get('id', '').endswith(suffix)]
        if not candidates:
            return None
        candidates.sort(key=lambda o: (o.get('active', False), o.get('last_seen', '')), reverse=True)
        return candidates[0]

    def _title_changed(self, old_title: str, new_title: str) -> bool:
        """Czy tytuł realnie się zmienił? Ignoruje szum: wielkość liter,
        wielokrotne spacje, otaczające białe znaki. Drobne różnice zapisu OLX
        (np. podwójna spacja) NIE są zmianą tytułu."""
        def norm(t: str) -> str:
            return ' '.join((t or '').lower().split())
        o, n = norm(old_title), norm(new_title)
        return bool(o) and bool(n) and o != n

    def _source_text_changed(self, existing: Dict, new_data: Dict) -> bool:
        """Czy zmienił się TEKST, z którego wyciągamy adres (tytuł + opis)?

        Rozstrzyga, czy inny adres oznacza przeprowadzkę, czy naszą poprawkę:
        ten sam tekst + inny wynik = poprawiliśmy parser, a nie ktoś przepisał
        ogłoszenie. Bez tego każda poprawka parsera dopisywałaby ofercie fałszywą
        "zmianę adresu" do versions[] i zapalała plakietkę historii na mapie.
        (2026-07-26)
        """
        if self._title_changed(existing.get('title', ''), new_data.get('title', '')):
            return True

        def norm(t: str) -> str:
            return ' '.join((t or '').lower().split())

        old = norm(existing.get('description'))
        new = norm(new_data.get('description'))
        if not old or not new:
            return False  # brak materiału do porównania → nie zgaduj przeprowadzki

        # PORÓWNANIE SUFIKSOWE, nie równościowe. Oferta pominięta dostaje opis z bazy
        # (scraper.py: offer['description'] = existing['description']), a _process_offer
        # zapisuje pod 'description' sklejkę TYTUŁ + ' ' + opis. Przetworzony opis jest
        # więc o jeden tytuł dłuższy od tego w bazie mimo IDENTYCZNEJ treści z OLX —
        # zwykłe '!=' oznaczałoby każdą pominiętą ofertę jako "przepisaną" i wpychało
        # korekty parsera do historii adresu.
        return not (new.endswith(old) or old.endswith(new))

    def _addr_changed(self, old_addr: Dict, new_addr: Dict) -> bool:
        """Czy adres realnie się zmienił (ten sam listing OLX, inne miejsce)?
        Liczy się zmiana numeru ALBO znacząca zmiana ulicy. Drobne różnice zapisu
        (dopełniacz 'Glinianej'/'Gliniana', zgubione imię) NIE są zmianą adresu."""
        import difflib
        if not isinstance(old_addr, dict) or not isinstance(new_addr, dict):
            return False
        o_full = (old_addr.get('full') or '').strip().lower()
        n_full = (new_addr.get('full') or '').strip().lower()
        if not o_full or not n_full or o_full == n_full:
            return False
        o_num = str(old_addr.get('number') or '').strip().lower()
        n_num = str(new_addr.get('number') or '').strip().lower()
        # Zmiana numeru (nawet sam numer) = zmiana adresu
        if o_num and n_num and o_num != n_num:
            return True
        # Ulica: porównaj z tolerancją na odmianę/zapis
        o_st = (old_addr.get('street') or '').strip().lower() or o_full
        n_st = (new_addr.get('street') or '').strip().lower() or n_full
        # Ten sam rdzeń ulicy, różny zapis (zgubione imię/prefiks): 'Żywnego' ⊆
        # 'Wojciecha Żywnego', 'Racławickie' ⊆ 'Aleja Racławickie' → NIE zmiana.
        o_tok, n_tok = set(o_st.split()), set(n_st.split())
        if o_tok and n_tok and (o_tok <= n_tok or n_tok <= o_tok):
            return False
        # Próg 0.75: realna zmiana ulicy ma niskie podobieństwo; sama fleksja
        # ('Bajkowa'/'Bajkowej' ≈ 0.80) NIE jest zmianą.
        return difflib.SequenceMatcher(None, o_st, n_st).ratio() < 0.75
    
    def _track_refresh(self, existing: Dict, new_refresh: str) -> bool:
        """Rejestruje odświeżenie (bump/pushup) oferty firmowej — max 1/dzień.

        `new_refresh` = data ostatniego pushup/odświeżenia z API OLX
        (api_last_refresh, format ISO). Działa dla dwóch wywołań:
        pełnej aktualizacji (_update_existing_offer) oraz ofert pominiętych
        przez inteligentne skanowanie (_mark_inactive_offers), więc bump bez
        zmiany ceny też jest łapany. Zwraca True gdy dodano nową datę.
        """
        if not new_refresh or not existing.get('profile_name'):
            return False
        try:
            new_refresh_date = new_refresh[:10]  # 'YYYY-MM-DD'
            stored_raw = existing.get('last_refresh_date', '')
            stored_date = stored_raw[:10] if stored_raw else ''
            refresh_dates = existing.get('refresh_dates', [])

            # Nowa data odświeżenia — max 1/dzień
            if (new_refresh_date and new_refresh_date != stored_date
                    and new_refresh_date not in refresh_dates):
                refresh_dates.append(new_refresh_date)
                existing['refresh_dates'] = refresh_dates
                existing['refresh_count'] = len(refresh_dates)
                existing['last_refresh_date'] = new_refresh
                print(f"      🔄 Odświeżenie #{existing['refresh_count']}: {new_refresh_date}")
                return True
        except (ValueError, TypeError, AttributeError):
            pass
        return False

    def _track_promoted(self, existing: Dict, promoted: bool) -> bool:
        """Zapisuje płatne wyróżnienie oferty na listingu OLX — max 1 dzień/wpis.

        `promoted` = flaga z bieżącego skanu (scraper czyta ją z parametru
        atrybucji w href kafelka). Aktualizuje stan bieżący i dopisuje dzisiejszą
        datę do `promoted_dates`, jeśli jeszcze jej tam nie ma. Skanujemy 3×
        dziennie, więc dzień z choć jednym promowanym wystąpieniem liczy się raz.
        Zwraca True, gdy dopisano nowy dzień.
        """
        existing['promoted'] = bool(promoted)
        if not promoted:
            return False
        today = datetime.now(self.tz).strftime('%Y-%m-%d')
        dates = existing.setdefault('promoted_dates', [])
        if today in dates:
            return False
        dates.append(today)
        existing['promoted_count'] = len(dates)
        return True

    def _apply_price_change(self, offer: Dict, new_price: int, new_source: str,
                            update_reason: str):
        """
        Zapisuje zmianę ceny w rekordzie oferty: previous_price, trend,
        history + history_full. Wspólne dla _update_existing_offer oraz
        reaktywacji przez weryfikację URL (_verify_inactive_offers).
        """
        now = datetime.now(self.tz).isoformat()
        price = offer['price']
        old_price = price['current']

        price['previous_price'] = old_price
        price['price_changed_at'] = now

        # Określ kierunek zmiany
        if new_price < old_price:
            price['price_trend'] = 'down'
            print(f"      📉 Cena SPADŁA: {old_price} → {new_price} zł (↓{old_price - new_price} zł)")
        else:
            price['price_trend'] = 'up'
            print(f"      📈 Cena WZROSŁA: {old_price} → {new_price} zł (↑{new_price - old_price} zł)")
        print(f"      📝 Powód zmiany: {update_reason}")

        price['current'] = new_price
        price['source'] = new_source

        # Dodaj do historii
        price['history'].append(new_price)

        # Zapis pełnej historii z timestampami
        if 'history_full' not in price:
            # Backfill dla starych ofert które jeszcze nie mają history_full
            price['history_full'] = []
            # Pierwsza znana cena = pierwszy wpis history (data first_seen)
            if price['history']:
                price['history_full'].append({
                    'price': price['history'][0],
                    'date': offer.get('first_seen', now),
                    'approximated': False
                })
        price['history_full'].append({
            'price': new_price,
            'date': now,
            'approximated': False
        })

    def _update_existing_offer(self, existing: Dict, new_data: Dict):
        """Aktualizuje istniejące ogłoszenie z inteligentnym zarządzaniem ceną."""
        now = datetime.now(self.tz).isoformat()

        # === WYKRYCIE ZMIANY ADRESU (ten sam listing OLX, inne miejsce) ===
        # Zrób to PRZED logiką cenową — żeby zrzucić starą wersję z jej własną,
        # nietkniętą historią cen. Nową wersję otwieramy na końcu funkcji.
        #
        # UWAGA: musi zostać policzone TUTAJ, przed blokiem historii tytułu niżej —
        # ten backfilluje existing['title'], więc po nim _source_text_changed
        # porównywałby nowy tytuł sam ze sobą i nigdy nie wykryłby edycji.
        prev_last_seen = existing.get('last_seen', now)
        _new_addr = new_data.get('address', {}) or {}
        _new_addr_full = _new_addr.get('full', '')
        _existing_addr_full = existing.get('address', {}).get('full', '')
        _addr_differs = bool(
            _new_addr_full and _existing_addr_full
            and not self._is_bogus_address(_existing_addr_full)
            and self._addr_changed(existing.get('address', {}), _new_addr)
        )
        # Inny adres z TEGO SAMEGO tekstu = korekta parsera, nie przeprowadzka.
        # Wchodzi in-place (bez versions[], bez plakietki historii na mapie),
        # ślad diagnostyczny ląduje w address_corrections[]. (2026-07-26)
        _text_changed = self._source_text_changed(existing, new_data)
        addr_change = _addr_differs and _text_changed
        addr_correction = _addr_differs and not _text_changed
        addr_snapshot = None
        if addr_change:
            addr_snapshot = {
                'address': dict(existing.get('address', {})),
                'title': existing.get('title', ''),   # tytuł tej wersji adresu
                'price_history': list(existing.get('price', {}).get('history_full', [])),
                'first_seen': existing.get('version_first_seen') or existing.get('first_seen', ''),
                'last_seen': prev_last_seen,
                'refresh_count': existing.get('refresh_count', 0),
                'refresh_dates': list(existing.get('refresh_dates', [])),
                'reactivation_count': existing.get('reactivation_count', 0),
                'reactivation_dates': list(existing.get('reactivation_dates', [])),
                'last_price': existing.get('price', {}).get('current'),
            }

        # === ZMIANA TYTUŁU (ten sam listing OLX, edytowany tytuł) ===
        # OLX zmienia slug URL przy edycji tytułu, ale końcówka ID zostaje → trafiamy tutaj.
        # Śledzimy niezależnie od zmiany adresu (tytuł może się zmienić sam).
        new_title = (new_data.get('title') or '').strip()
        if new_title:
            old_title = (existing.get('title') or '').strip()
            if not old_title:
                # Pierwszy znany tytuł (backfill starych ofert) — baseline, bez liczenia zmiany
                existing['title'] = new_title
                existing['title_versions'] = [{
                    'title': new_title,
                    'first_seen': existing.get('first_seen', now),
                    'last_seen': None,
                }]
            elif self._title_changed(old_title, new_title):
                versions = existing.setdefault('title_versions', [])
                if not versions:
                    versions.append({'title': old_title,
                                     'first_seen': existing.get('first_seen', now),
                                     'last_seen': None})
                versions[-1]['last_seen'] = prev_last_seen
                versions.append({'title': new_title, 'first_seen': now, 'last_seen': None})
                existing['title'] = new_title
                existing['title_change_count'] = existing.get('title_change_count', 0) + 1
                existing['title_changed_at'] = now
                print(f"      📝 Zmiana tytułu: '{old_title[:40]}…' → '{new_title[:40]}…'")
            # else: tytuł bez zmian

        # Aktualizuj last_seen
        existing['last_seen'] = now

        # INTELIGENTNA AKTUALIZACJA CENY - priorytetyzuj źródła
        old_price = existing['price']['current']
        new_price = new_data['price']['current']
        old_source = existing['price'].get('source', 'unknown')
        new_source = new_data['price'].get('source', 'unknown')
        
        # Hierarchia źródeł (od najlepszego do najgorszego)
        source_priority = {
            'JSON-LD (OLX)': 3,
            'cache': 3,  # Cache ma ten sam priorytet co JSON-LD (bo pochodzi z niego)
            'HTML fallback': 2,
            'Parser tekstowy': 1,
            'unknown': 0
        }
        
        old_priority = source_priority.get(old_source, 0)
        new_priority = source_priority.get(new_source, 0)
        
        # SZCZEGÓŁOWE LOGOWANIE ZMIAN CEN
        print(f"      🔍 Analiza ceny dla oferty: {existing['id']}")
        print(f"         Stara cena: {old_price} zł (źródło: {old_source}, priorytet: {old_priority})")
        print(f"         Nowa cena: {new_price} zł (źródło: {new_source}, priorytet: {new_priority})")
        
        # DECYZJA: Aktualizuj cenę tylko jeśli:
        # 1. Nowe źródło ma wyższy priorytet, LUB
        # 2. Ten sam priorytet ale cena się zmieniła (realna zmiana ceny), LUB
        # 3. Różnica ceny jest mniejsza niż 50% (zabezpieczenie przed błędami parsera)
        
        should_update = False
        update_reason = None
        
        if new_priority > old_priority:
            # Lepsze źródło - aktualizuj
            should_update = True
            update_reason = f"Upgrade źródła: {old_source} → {new_source}"
            print(f"      💰 {update_reason}")
        elif new_priority == old_priority and old_price != new_price:
            # To samo źródło ale inna cena - sprawdź czy zmiana sensowna
            price_diff_percent = abs(new_price - old_price) / old_price * 100

            if new_source == 'JSON-LD (OLX)':
                # JSON-LD ze świeżo pobranej strony oferty = źródło prawdy, bez limitu %.
                # Próg 50% blokował realne podwyżki (600→920 zł = 53%) NA ZAWSZE,
                # bo baza trzymała starą cenę i każdy kolejny scan liczył tę samą różnicę.
                should_update = True
                update_reason = f"Zmiana ceny (JSON-LD): {old_price} → {new_price} zł ({price_diff_percent:.1f}%)"
                print(f"      💰 {update_reason}")
            elif price_diff_percent < 50:  # Max 50% zmiany dla słabszych źródeł
                should_update = True
                update_reason = f"Zmiana ceny (to samo źródło): {old_price} → {new_price} zł ({price_diff_percent:.1f}%)"
                print(f"      💰 {update_reason}")
            else:
                # Zbyt duża zmiana - podejrzane, nie aktualizuj
                print(f"      ⚠️ PODEJRZANA zmiana ceny: {old_price} → {new_price} zł ({price_diff_percent:.1f}%) - IGNORUJĘ")
        elif new_priority < old_priority:
            # Gorsze źródło - nie aktualizuj
            print(f"      ℹ️ Zachowano cenę z lepszego źródła: {old_source} ({old_price} zł)")
        else:
            # Ta sama cena, to samo źródło - brak zmian
            print(f"      ✓ Cena bez zmian: {old_price} zł")
        
        if should_update and old_price != new_price:
            self._apply_price_change(existing, new_price, new_source, update_reason)

        # Zawsze aktualizuj media_info (może się zmienić niezależnie)
        existing['price']['media_info'] = new_data['price']['media_info']
        
        # === FIX 2026-05-14: napraw bogus address w istniejących ofertach ===
        # Jeśli existing.address jest "bogus" (artefakt starego parsera, np. 'Pokoje'),
        # a nowy świeży _process_offer wyciągnął prawdziwy adres - podmień.
        # Bez tego stare oferty z buggy address pozostają na mapie wieczyście,
        # bo update_existing_offer normalnie NIE aktualizuje pola address.
        existing_addr_full = existing.get('address', {}).get('full', '')
        new_addr = new_data.get('address', {})
        new_addr_full = new_addr.get('full', '')
        
        if (existing_addr_full and new_addr_full
                and existing_addr_full != new_addr_full
                and self._is_bogus_address(existing_addr_full)
                and not self._is_bogus_address(new_addr_full)):
            print(f"      🔧 Naprawiam bogus address: '{existing_addr_full}' → '{new_addr_full}'")
            # Zachowaj poprzedni adres do historii diagnostycznej
            existing['address']['previous_bogus'] = existing_addr_full
            existing['address']['fixed_at'] = now
            # Podmień adres + współrzędne + precision
            existing['address']['full'] = new_addr_full
            existing['address']['street'] = new_addr.get('street')
            existing['address']['number'] = new_addr.get('number')
            if new_addr.get('coords'):
                existing['address']['coords'] = new_addr['coords']
            if new_addr.get('precision'):
                existing['address']['precision'] = new_addr['precision']

        # === KOREKTA PARSERA (2026-07-26) ===
        # Ten sam tekst ogłoszenia, inny wynik parsera → poprawiliśmy odczyt, a nie
        # ktoś się przeprowadził. Podmiana in-place: NIE ruszamy versions[],
        # address_change_count, address_changed_at, version_first_seen ani historii
        # cen, więc popup na mapie nie pokaże fałszywej "Historii adresu".
        elif addr_correction:
            _old = dict(existing.get('address', {}))
            corrections = existing.get('address_corrections', [])
            # ANTY-MIGOTANIE: jeśli wracamy do adresu, z którego już kiedyś korygowaliśmy,
            # to dwa ekstraktory kłócą się między skanami (typowo dwa równorzędne
            # landmarki, np. dwa przystanki: 'Jutrzenki' ↔ 'Wiklinowa'). Zostaw obecny —
            # inaczej marker skacze, a offers.json i docs/data.json puchną diffem
            # przy każdym skanie.
            if _new_addr_full in {c.get('from') for c in corrections}:
                print(f"      ⚖️ Pomijam korektę '{_old.get('full')}' → '{_new_addr_full}' "
                      f"— ten adres już raz był korygowany w drugą stronę (migotanie ekstraktorów)")
            else:
                existing['address'] = {
                    'full': _new_addr_full,
                    'street': _new_addr.get('street'),
                    'number': _new_addr.get('number'),
                    'coords': _new_addr.get('coords') or _old.get('coords'),
                    'precision': _new_addr.get('precision', 'exact'),
                }
                corrections = existing.setdefault('address_corrections', [])
                corrections.append({
                    'from': _old.get('full'),
                    'from_precision': _old.get('precision'),
                    'to': _new_addr_full,
                    'to_precision': _new_addr.get('precision'),
                    'at': now,
                })
                del corrections[:-5]  # trzymaj tylko 5 ostatnich, rekord ma nie puchnąć
                self._addr_corrections_count += 1
                print(f"      🔧 Korekta parsera: '{_old.get('full')}' ({_old.get('precision')}) → "
                      f"'{_new_addr_full}' ({_new_addr.get('precision')}) — bez wpisu do historii adresu")

        # Upewnij się że jest aktywne (REAKTYWACJA nieaktywnych ofert)
        was_inactive = not existing.get('active', True)
        existing['active'] = True
        
        if was_inactive:
            print(f"      🔄 REAKTYWOWANO ofertę: {existing['id']} (była nieaktywna)")
            existing['reactivated_at'] = now
        
        # Aktualizuj profile_name jeśli oferta pojawiła się w scanie profilu
        new_profile = new_data.get('profile_name')
        if new_profile and not existing.get('profile_name'):
            existing['profile_name'] = new_profile
            print(f"      🏢 Przypisano profil: {new_profile}")

        # Śledź odświeżenia (bump) dla ofert firmowych.
        # _process_offer zapisuje świeże api_last_refresh pod kluczem
        # 'last_refresh_date' (patrz szablon nowej oferty), więc czytamy TEN
        # klucz — nie 'api_last_refresh', którego przetworzona oferta nie ma.
        self._track_refresh(existing, new_data.get('last_refresh_date', ''))

        # Śledź płatne wyróżnienie na listingu (dotyczy każdej oferty, nie tylko firmowej)
        self._track_promoted(existing, new_data.get('promoted', False))

        # Śledź reaktywacje — inkrementuj licznik i dopisz datę przy każdej reaktywacji
        if was_inactive:
            existing['reactivation_count'] = existing.get('reactivation_count', 0) + 1
            existing.setdefault('reactivation_dates', []).append(now)
            print(f"      ♻️ Reaktywacja #{existing['reactivation_count']}")

        # === OTWARCIE NOWEJ WERSJI po zmianie adresu ===
        # Stara wersja (z własną historią cen / odświeżeniami / reaktywacjami)
        # ląduje w versions[]; top-level reprezentuje nową, świeżą wersję.
        if addr_change:
            existing.setdefault('versions', []).append(addr_snapshot)
            existing['address_change_count'] = len(existing['versions'])
            existing['address_changed_at'] = now
            print(f"      ✏️ ZMIANA ADRESU #{existing['address_change_count']}: "
                  f"'{addr_snapshot['address'].get('full','')}' → '{_new_addr_full}'")
            # Podmień adres na nowy
            existing['address'] = {
                'full': _new_addr_full,
                'street': _new_addr.get('street'),
                'number': _new_addr.get('number'),
                'coords': _new_addr.get('coords') or existing.get('address', {}).get('coords'),
                'precision': _new_addr.get('precision', 'exact'),
            }
            # Świeża historia cen dla nowej wersji
            npv = new_data.get('price', {}).get('current')
            existing['price']['current'] = npv
            existing['price']['history'] = [npv] if npv else []
            existing['price']['history_full'] = (
                [{'price': npv, 'date': now, 'approximated': False}] if npv else []
            )
            existing['price'].pop('previous_price', None)
            existing['price'].pop('price_trend', None)
            existing['price'].pop('price_changed_at', None)
            # Reset liczników — nowa wersja zaczyna od zera
            existing['version_first_seen'] = now
            existing['refresh_count'] = 0
            existing['refresh_dates'] = []
            existing['last_refresh_date'] = ''
            existing['reactivation_count'] = 0
            existing['reactivation_dates'] = []
            existing.pop('reactivated_at', None)
            existing['promoted_dates'] = ([datetime.now(self.tz).strftime('%Y-%m-%d')]
                                          if existing.get('promoted') else [])
            existing['promoted_count'] = len(existing['promoted_dates'])

    def _update_days_active(self):
        """
        Aktualizuje pole days_active dla WSZYSTKICH ofert (aktywnych i nieaktywnych).
        Oblicza różnicę w dniach między first_seen a last_seen.
        """
        for offer in self.database['offers']:
            try:
                first_seen = datetime.fromisoformat(offer['first_seen'])
                last_seen = datetime.fromisoformat(offer['last_seen'])
                offer['days_active'] = (last_seen - first_seen).days
            except (ValueError, KeyError) as e:
                print(f"⚠️ Błąd obliczania days_active dla oferty {offer.get('id')}: {e}")
                offer['days_active'] = 0
    
    def _reference_scrape_size(self, lookback: int = 8) -> Optional[int]:
        """
        Mediana liczby surowych ofert (raw_offers) z ostatnich ZDROWYCH skanów.

        Punkt odniesienia dla wykrycia częściowego scrape'u: realny rynek zmienia
        się o kilka-kilkanaście ofert między skanami, więc nagły spadek o 40%
        oznacza urwany listing (soft-block OLX), a nie zniknięcie ofert.
        Skany oznaczone SCRAPE_PARTIAL/SCRAPE_BLOCKED są pomijane, żeby jedna
        awaria nie obniżyła progu dla następnych.
        """
        healthy = []
        for scan in self.scan_logger.get_recent_scans(count=lookback):
            if scan.get('status') not in ('completed', 'warning'):
                continue
            if any(str(e.get('message', '')).startswith(('SCRAPE_PARTIAL', 'SCRAPE_BLOCKED'))
                   for e in scan.get('errors', [])):
                continue
            raw = scan.get('stats', {}).get('raw_offers', 0)
            if raw:
                healthy.append(raw)

        if len(healthy) < 3:
            return None
        return int(statistics.median(healthy))

    def _mark_inactive_offers(self, current_offer_ids: List[str], skipped_offer_ids: List[str] = None,
                              skipped_refresh_map: Dict[str, str] = None,
                              promoted_ids: List[str] = None):
        """
        Oznacza ogłoszenia jako nieaktywne jeśli nie ma ich w bieżącym scanie.
        Reaktywuje oferty które pojawiły się ponownie (w skipped_ids).

        Args:
            current_offer_ids: Lista ID ofert które zostały przetworzone (nowe + zaktualizowane)
            skipped_offer_ids: Lista ID ofert które zostały pominięte przez inteligentne skanowanie
            skipped_refresh_map: id oferty pominiętej → api_last_refresh (do śledzenia bumpów
                                 bez zmiany ceny — oferta skipped nie przechodzi _update_existing_offer)
            promoted_ids: ID ofert, które w TYM skanie były płatnie wyróżnione na listingu
                          (ratunek dla ofert skipped, które nie przeszły _process_offer)
        """
        if skipped_offer_ids is None:
            skipped_offer_ids = []
        if skipped_refresh_map is None:
            skipped_refresh_map = {}
        promoted_set = set(promoted_ids or [])

        # Wszystkie oferty które powinny być aktywne = przetworzone + pominięte
        all_active_ids = set(current_offer_ids + skipped_offer_ids)
        skipped_set = set(skipped_offer_ids)
        # Set ofert które przeszły pełen _process_offer (nie tylko skipped)
        processed_set = set(current_offer_ids)
        
        # Fix #4.5 (2026-05-11): Oferty z bogus address w bazie nie powinny być
        # chronione przez skipped_ids - jeśli _process_offer ich nie zwrócił
        # (np. bogus + reparse fail), to powinny być dezaktywowane.
        BOGUS_ADDRESSES = {'Pokoje', 'UMCS', 'Kul', 'KUL', 'Apteka', 'Park', 'Stadion',
                          'Lublin', 'Centrum', 'Witam', 'Oferuję'}
        BOGUS_PREFIXES = ('Lublin Studio', 'Lublin Witam', 'Lublin Oferuję',
                         'Lublin Duży', 'Lublin Pokoje', 'Witam ', 'Oferuję ',
                         'Kaucja', 'Depozyt')
        
        def is_bogus_offer(offer):
            addr_full = offer.get('address', {}).get('full', '')
            return (addr_full in BOGUS_ADDRESSES
                   or any(addr_full.startswith(p) for p in BOGUS_PREFIXES))
        
        now = datetime.now(self.tz).isoformat()
        deactivated_count = 0
        deactivated_bogus_count = 0
        reactivated_from_skipped = 0
        
        for offer in self.database['offers']:
            # Sprawdź czy oferta ma bogus address i NIE przeszła pełnego _process_offer w tym scanie
            # (była tylko skipped) - wtedy DEZAKTYWUJ ją zamiast chronić.
            if (is_bogus_offer(offer) 
                and offer['id'] in skipped_set 
                and offer['id'] not in processed_set):
                if offer.get('active', True):
                    offer['active'] = False
                    deactivated_bogus_count += 1
                continue
            
            if offer['id'] in all_active_ids:
                # Oferta jest aktywna - upewnij się że ma active=True
                # i zaktualizuj last_seen dla pominiętych ofert
                if offer['id'] in skipped_set:
                    if not offer.get('active', True):
                        # Reaktywacja oferty która była nieaktywna
                        offer['active'] = True
                        offer['reactivated_at'] = now
                        offer['reactivation_count'] = offer.get('reactivation_count', 0) + 1
                        offer.setdefault('reactivation_dates', []).append(now)
                        reactivated_from_skipped += 1
                    # Aktualizuj last_seen dla skipped ofert
                    offer['last_seen'] = now
                    # Śledź odświeżenie (bump) — skipped nie wchodzi w _update_existing_offer,
                    # więc bez tego bump bez zmiany ceny nigdy nie trafia do licznika
                    self._track_refresh(offer, skipped_refresh_map.get(offer['id'], ''))
                    # Wyróżnienie — jw., skipped omija _update_existing_offer
                    self._track_promoted(offer, offer['id'] in promoted_set)
            elif offer['active']:
                # Oferta nie jest w scanie - dezaktywuj
                offer['active'] = False
                # Nie ma jej na listingu → nie jest już promowana. Historia dni
                # (promoted_dates) zostaje — z niej liczy się szereg czasowy.
                offer['promoted'] = False
                deactivated_count += 1
        
        if deactivated_count > 0:
            print(f"   ⏸️  Oznaczono jako nieaktywne: {deactivated_count}")
        if deactivated_bogus_count > 0:
            print(f"   🧹 Dezaktywowano oferty z bogus address: {deactivated_bogus_count}")
        if reactivated_from_skipped > 0:
            print(f"   🔄 Reaktywowano (skipped): {reactivated_from_skipped}")
    
    def _verify_inactive_offers(self, max_to_verify: int = 50) -> Dict:
        """
        Weryfikuje nieaktywne oferty sprawdzając bezpośrednio ich URL na OLX.
        Reaktywuje oferty które nadal istnieją na OLX.
        WERSJA 2.0: Równoległa weryfikacja (ThreadPoolExecutor)
        
        Args:
            max_to_verify: Maksymalna liczba ofert do zweryfikowania na jeden skan
            
        Returns:
            Dict ze statystykami: {'verified': N, 'reactivated': N, 'confirmed_inactive': N, 'errors': N}
        """
        from bs4 import BeautifulSoup
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        from scraper import NETWORK_EXCEPTIONS
        
        stats = {
            'verified': 0,
            'reactivated': 0,
            'kept_alive': 0,   # żywe firmówki spoza listingu — podtrzymane bez liczenia reaktywacji
            'confirmed_inactive': 0,
            'errors': 0
        }
        stats_lock = threading.Lock()
        
        # Pobierz nieaktywne oferty, posortowane od najnowszych (ostatnio dezaktywowane)
        inactive_offers = [
            offer for offer in self.database.get('offers', [])
            if not offer.get('active', True)
        ]
        
        if not inactive_offers:
            print("   ℹ️  Brak nieaktywnych ofert do weryfikacji")
            return stats
        
        # Sortuj od najnowszych (last_seen malejąco)
        inactive_offers.sort(
            key=lambda x: x.get('last_seen', '1970-01-01'),
            reverse=True
        )
        
        # Ogranicz do max_to_verify
        to_verify = inactive_offers[:max_to_verify]
        
        print(f"   🔍 Weryfikuję {len(to_verify)} nieaktywnych ofert (z {len(inactive_offers)} łącznie) [10 wątków]...")
        
        # Sesja z impersonacją TLS Safari (WAF CloudFront tnie po JA3 —
        # patrz scraper.py IMPERSONATE). Thread-safe dla GET.
        session = OLXScraper.make_olx_session()
        
        now = datetime.now(self.tz).isoformat()
        # Per-thread rate limiter dla weryfikacji (delay 0.2-0.5s per wątek)
        thread_local = threading.local()
        
        def verify_single(offer: Dict) -> tuple:
            """
            Weryfikuje pojedynczą ofertę. Zwraca (offer, result_type, reactivation_data)
            result_type: 'reactivated' | 'confirmed_inactive' | 'error'
            """
            url = offer.get('url', '')
            offer_id = offer.get('id', 'unknown')
            
            if not url:
                return (offer, 'error', None)
            
            # Per-thread delay (0.2-0.5s między requestami tego samego wątku)
            last_req = getattr(thread_local, 'last_request', 0)
            elapsed = time.time() - last_req
            if elapsed < 0.2:
                time.sleep(0.2 - elapsed + random.uniform(0, 0.3))
            
            try:
                response = session.get(url, timeout=15)
                thread_local.last_request = time.time()
                
                with stats_lock:
                    stats['verified'] += 1
                
                # Sprawdź czy oferta istnieje
                if response.status_code in (404, 410):
                    return (offer, 'confirmed_inactive', None)
                
                if response.status_code != 200:
                    return (offer, 'error', None)
                
                soup = BeautifulSoup(response.text, 'lxml')

                # FIX (2026-05-23): Verification NIE reaktywuje już ofert na podstawie
                # availability=InStock. OLX trzyma strony z InStock dla ofert które
                # wypadły z listingu kategorii (uśpione/zarchiwizowane), co powodowało
                # nieskończoną pętlę: scrape→inactive→verification→reactivate→scrape→inactive...
                # Reaktywacja teraz nastąpi TYLKO gdy oferta wróci do listingu kategorii.
                # Tu sprawdzamy jedynie czy strona dalej istnieje (200 = nadal trzymana
                # przez OLX, ale nie ma jej w listingu → traktujemy jako inactive).

                # Dodatkowe potwierdzenie inactive przez marker w treści strony
                # (np. "Ogłoszenie nieaktywne") - jeśli OLX explicit mówi że nieaktywne.
                page_text_lower = soup.get_text().lower()
                inactive_markers = [
                    'ogłoszenie nieaktywne', 'oferta nieaktywna',
                    'ogłoszenie zakończ', 'to ogłoszenie zostało zakończone',
                    'oferta wygasła', 'ogłoszenie wygasło'
                ]
                if any(m in page_text_lower for m in inactive_markers):
                    return (offer, 'confirmed_inactive', None)

                # FIX (2026-07-02): Dla ofert ze śledzonych profili firmowych
                # (offer['profile_name'] ustawiony przez scrape_all_profiles) ufamy
                # bezpośredniej weryfikacji URL - to nie anonimowy listing kategorii,
                # tylko konkretna, znana firma. HTTP 200 + availability=InStock +
                # brak markera nieaktywności = oferta faktycznie żyje, nawet jeśli
                # spadła w rankingu listingu/profilu (brak odświeżenia).
                if offer.get('profile_name') and 'availability":"https://schema.org/instock"' in response.text.lower():
                    reactivation_data = {
                        'last_seen': datetime.now(self.tz).isoformat(),
                        'reactivated_at': datetime.now(self.tz).isoformat()
                    }
                    # FIX (2026-07-15): przy reaktywacji zaktualizuj też cenę z JSON-LD
                    # już pobranej strony. Dla ofert niewidocznych w listingu/API profilu
                    # (np. OLX city="Szerokie") weryfikacja to JEDYNA ścieżka dotykająca
                    # rekordu — bez tego cena była zamrożona mimo zmiany na OLX.
                    try:
                        ld_script = soup.find('script', {'type': 'application/ld+json'})
                        if ld_script and ld_script.string:
                            ld_price = (json.loads(ld_script.string).get('offers') or {}).get('price')
                            if ld_price:
                                ld_price = int(float(ld_price))
                                # Ten sam zakres sanity co w scraperze
                                if 200 <= ld_price <= 5000:
                                    reactivation_data['price'] = ld_price
                    except (ValueError, TypeError, json.JSONDecodeError):
                        pass
                    return (offer, 'reactivated', reactivation_data)

                # HTTP 200 + brak markera = OLX trzyma stronę, ale nie ma jej w listingu.
                # NIE reaktywujemy - oferta zostanie inactive aż wróci do listingu.
                return (offer, 'confirmed_inactive', None)
                    
            except NETWORK_EXCEPTIONS:
                return (offer, 'error', None)
            except Exception as e:
                # Nie-sieciowy wyjątek (np. zmiana HTML) — loguj, nie połykaj po cichu
                print(f"      ⚠️ Weryfikacja {offer.get('id', '?')}: "
                      f"{type(e).__name__}: {e}")
                return (offer, 'error', None)
        
        # Równoległa weryfikacja (10 wątków - tak samo jak scraper)
        verify_start = time.time()
        reactivated_ids = []
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(verify_single, offer): offer for offer in to_verify}
            
            completed = 0
            total = len(to_verify)
            for future in as_completed(futures):
                completed += 1
                try:
                    offer, result_type, reactivation_data = future.result()
                    
                    if result_type == 'reactivated':
                        # Realna reaktywacja TYLKO gdy oferta była nieaktywna już wchodząc
                        # w skan. Jeśli była aktywna i tylko przeleciała inactive→active w tym
                        # samym skanie (firmówka spoza listingu, InStock) — to nie reaktywacja,
                        # a podtrzymanie żywej oferty: ustaw active, odśwież cenę, ale bez count++.
                        was_inactive_before = offer.get('id') not in getattr(
                            self, '_active_before_deactivation', set())
                        offer['active'] = True
                        offer['last_seen'] = reactivation_data['last_seen']
                        if was_inactive_before:
                            offer['reactivated_at'] = reactivation_data['reactivated_at']
                            offer['reactivation_source'] = 'verification'
                            offer['reactivation_count'] = offer.get('reactivation_count', 0) + 1
                            offer.setdefault('reactivation_dates', []).append(reactivation_data['reactivated_at'])
                        # Cena z JSON-LD strony oferty (zawsze — niezależnie od reaktywacji)
                        verified_price = reactivation_data.get('price')
                        if verified_price and verified_price != offer.get('price', {}).get('current'):
                            self._apply_price_change(
                                offer, verified_price, 'JSON-LD (OLX)',
                                'Reaktywacja przez weryfikację URL — cena z JSON-LD'
                            )
                        with stats_lock:
                            if was_inactive_before:
                                stats['reactivated'] += 1
                            else:
                                stats['kept_alive'] += 1
                        if was_inactive_before:
                            reactivated_ids.append(offer.get('id', 'unknown'))
                    elif result_type == 'confirmed_inactive':
                        with stats_lock:
                            stats['confirmed_inactive'] += 1
                    else:  # error
                        with stats_lock:
                            stats['errors'] += 1
                    
                    if completed % 10 == 0 or completed == total:
                        print(f"      Postęp: [{completed}/{total}]", flush=True)
                except Exception as e:
                    with stats_lock:
                        stats['errors'] += 1
        
        verify_elapsed = time.time() - verify_start
        
        # Wyświetl reaktywowane
        for rid in reactivated_ids[:10]:  # max 10 żeby nie spamować
            print(f"      ✅ Reaktywowano: {rid[:50]}...")
        if len(reactivated_ids) > 10:
            print(f"      ... i {len(reactivated_ids) - 10} więcej")
        
        # Podsumowanie
        print(f"   📊 Weryfikacja zakończona w {verify_elapsed:.1f}s:")
        print(f"      Sprawdzono: {stats['verified']}")
        print(f"      Reaktywowano: {stats['reactivated']}")
        if stats.get('kept_alive'):
            print(f"      Podtrzymane żywe (firmówki spoza listingu, bez licznika): {stats['kept_alive']}")
        print(f"      Potwierdzone nieaktywne: {stats['confirmed_inactive']}")
        if stats['errors'] > 0:
            print(f"      Błędy: {stats['errors']}")
        
        return stats

    def _cleanup_old_offers(self, max_age_days: int = 548):
        """
        Usuwa oferty starsze niż 1.5 roku (548 dni).
        """
        cutoff_date = datetime.now(self.tz) - timedelta(days=max_age_days)
        
        original_count = len(self.database['offers'])
        
        self.database['offers'] = [
            offer for offer in self.database['offers']
            if datetime.fromisoformat(offer['first_seen']) > cutoff_date
        ]
        
        removed = original_count - len(self.database['offers'])
        if removed > 0:
            print(f"🗑️ Usunięto {removed} ofert starszych niż 1.5 roku")
    
    def run_scan(self):
        """Główny proces skanowania z logowaniem statystyk."""
        print("\n" + "="*60)
        print("🎯 SONAR POKOJOWY - Scan Started")
        print("="*60 + "\n")
        
        scan_start_time = time.time()
        now = datetime.now(self.tz)
        print(f"⏰ Czas: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")
        
        # Rozpocznij logowanie
        self.scan_logger.start_scan()
        
        try:
            # 1. Scraping OLX
            print("📡 Krok 1: Scraping OLX...")
            scraping_start = time.time()
            
            raw_offers = self.scraper.scrape_all_pages(max_pages=50)
            
            scraping_duration = time.time() - scraping_start
            self.scan_logger.log_phase('scraping', scraping_duration, {
                'offers_found': len(raw_offers),
                'max_pages': 50
            })
            
            print(f"✅ Pobrano {len(raw_offers)} surowych ofert\n")

            # 1a. Mapa pozycji: short_id → strona listingu OLX w sorcie
            # "od najnowszych" — pozycja ORGANICZNA (bez zaburzenia płatnymi
            # wyróżnieniami), możliwie najbliższa realnej kolejności oferty.
            # Osobne RÓWNOLEGŁE przejście samego listingu (~5s, bez pobierania
            # szczegółów). favorites_tracker dokleja stronę do snapshotów
            # ulubionych ("na której stronie jest oferta w dniu odczytu").
            listing_sort = 'created_at:desc'
            listing_positions = self.scraper.fetch_listing_positions(sort=listing_sort)
            write_json_atomic(DATA_DIR / 'listing_positions.json', {
                'scanned_at': now.isoformat(),
                'sort': listing_sort,
                'positions': listing_positions,
            })
            print(f"📄 Pozycje listingu: {len(listing_positions)} ofert (sort={listing_sort})\n")

            # 1b. Scraping profili firmowych
            print("🏢 Krok 1b: Scraping profili firmowych...")
            profile_scraping_start = time.time()
            
            profile_raw_offers = self.scraper.scrape_all_profiles(
                TRACKED_PROFILES, max_pages_per_profile=10
            )
            
            profile_scraping_duration = time.time() - profile_scraping_start
            
            # Merge: oferty z profili do raw_offers
            # URL-y już w regular scan → dodaj tylko tag profile_name
            # URL-y nowe (nie w regular scan) → dodaj do raw_offers
            regular_urls = {o['url'].split('?')[0] for o in raw_offers}
            profile_new_count = 0
            profile_tag_count = 0
            
            for p_offer in profile_raw_offers:
                clean_url = p_offer['url'].split('?')[0]
                if clean_url in regular_urls:
                    # Dodaj tag do istniejącej oferty z regular scanu
                    for r in raw_offers:
                        if r['url'].split('?')[0] == clean_url:
                            r['profile_key'] = p_offer['profile_key']
                            r['profile_name'] = p_offer['profile_name']
                            # Regular scan (HTML) nie zna api_last_refresh — przenieś z API v1,
                            # inaczej skipped oferty firmowe nie mają skąd wziąć daty bumpu
                            if p_offer.get('api_last_refresh'):
                                r['api_last_refresh'] = p_offer['api_last_refresh']
                            if p_offer.get('api_created') and not r.get('api_created'):
                                r['api_created'] = p_offer['api_created']
                            profile_tag_count += 1
                            break
                else:
                    # Nowa oferta tylko z profilu - dodaj do puli
                    raw_offers.append(p_offer)
                    regular_urls.add(clean_url)
                    profile_new_count += 1
            
            self.scan_logger.log_phase('profile_scraping', profile_scraping_duration, {
                'profiles': len(TRACKED_PROFILES),
                'profile_offers': len(profile_raw_offers),
                'new_from_profiles': profile_new_count,
                'tagged_existing': profile_tag_count
            })
            
            print(f"✅ Profil: {len(profile_raw_offers)} ofert ({profile_new_count} nowych, ")
            print(f"         {profile_tag_count} otagowanych w regular scan)\n")
            
            # 2. Przetwarzanie ofert
            print("🔧 Krok 2: Przetwarzanie ofert...")
            processing_start = time.time()
            geocoding_time = 0  # Czas geokodowania
            
            processed_offers = []
            skipped_no_address = 0
            skipped_no_price = 0
            skipped_no_coords = 0
            skipped_duplicate = 0
            skipped_excluded = 0  # FIX 2026-06-09: oferty odrzucone przez filtr excluded_phrases
            skipped_price_outlier = 0  # oferty odrzucone jako cena-outlier (>= 10x średnia)

            # Zbieram próbki odrzuconych ofert do analizy (max 50 per kategorię)
            skipped_samples = {
                'no_address': [],
                'no_price': [],
                'no_coords': [],
                'duplicate': [],
                'excluded': [],  # FIX 2026-06-09: osobna kategoria (nie myl z no_coords)
                'price_outlier': []
            }
            SAMPLE_LIMIT = 50

            # FIX 2026-06-09: kolejka retry dla ofert które padły na TYMCZASOWY błąd
            # Nominatim (timeout/429/5xx). Bez tego pojedynczy chwilowy błąd geokodera
            # wyrzucał ofertę z poprawnym adresem do no_coords (Chodźki/Chmielewskiego/
            # Wilczej). Te oferty ponawiamy po głównej pętli (z odstępem).
            transient_retry_queue = []

            def consume(raw_offer, processed):
                """Obsługuje wynik _process_offer: liczy skip/sample LUB dodaje ofertę
                (z dedupem). Wspólne dla głównej pętli i przebiegu retry."""
                nonlocal skipped_no_address, skipped_no_price, skipped_no_coords
                nonlocal skipped_duplicate, skipped_excluded, skipped_price_outlier

                if not processed:
                    # FIX 2026-06-09: klasyfikuj wg JAWNEGO powodu ustawionego przez
                    # _process_offer (self._skip_reason), zamiast zgadywać przez
                    # re-derywację adresu/ceny. Poprzednio oferty odrzucone z innego
                    # powodu (np. filtr excluded_phrases) z parsowalnym adresem+ceną
                    # lądowały błędnie w no_coords.
                    full_text = raw_offer['title'] + " " + raw_offer.get('description', '')
                    sample = {
                        'url': raw_offer.get('url', ''),
                        'title': raw_offer.get('title', '')[:200],
                        'description_preview': (raw_offer.get('description', '') or '')[:500]
                    }
                    reason = getattr(self, '_skip_reason', None)

                    if reason == 'excluded':
                        skipped_excluded += 1
                        if len(skipped_samples['excluded']) < SAMPLE_LIMIT:
                            sample['excluded_phrase'] = getattr(self, '_skip_detail', None)
                            skipped_samples['excluded'].append(sample)
                    elif reason == 'price_outlier':
                        skipped_price_outlier += 1
                        if len(skipped_samples['price_outlier']) < SAMPLE_LIMIT:
                            skipped_samples['price_outlier'].append(sample)
                    elif reason == 'no_price':
                        skipped_no_price += 1
                        if len(skipped_samples['no_price']) < SAMPLE_LIMIT:
                            skipped_samples['no_price'].append(sample)
                    elif reason == 'no_coords':
                        skipped_no_coords += 1
                        if len(skipped_samples['no_coords']) < SAMPLE_LIMIT:
                            # Wzbogać próbkę o sparsowany adres (diagnostyka który adres
                            # geocoder odrzucił + który ekstraktor go znalazł).
                            addr_exact = self.address_parser.extract_address(full_text)
                            addr_street = self.address_parser.extract_street_only(full_text) if not addr_exact else None
                            addr_white = self.address_parser.extract_from_whitelist(full_text) if not (addr_exact or addr_street) else None
                            addr_district = self.address_parser.extract_district(full_text) if not (addr_exact or addr_street or addr_white) else None
                            any_addr = addr_exact or addr_street or addr_white or addr_district
                            if any_addr:
                                sample['address_parsed'] = any_addr['full']
                                sample['address_source'] = (
                                    'extract_address' if addr_exact else
                                    'extract_street_only' if addr_street else
                                    'extract_from_whitelist' if addr_white else
                                    'extract_district'
                                )
                            skipped_samples['no_coords'].append(sample)
                    else:
                        # reason == 'no_address' lub None (defensywnie)
                        skipped_no_address += 1
                        if len(skipped_samples['no_address']) < SAMPLE_LIMIT:
                            skipped_samples['no_address'].append(sample)
                    return

                # Sprawdź duplikaty
                original_dup = self.duplicate_detector.find_duplicate(processed, processed_offers)
                if original_dup is not None:
                    skipped_duplicate += 1
                    print(f"      ⚠️ Duplikat - ignoruję")
                    if len(skipped_samples['duplicate']) < SAMPLE_LIMIT:
                        # Oblicz podobieństwo opisów dla diagnostyki
                        similarity = self.duplicate_detector.calculate_similarity(
                            processed.get('description', ''),
                            original_dup.get('description', '')
                        )
                        skipped_samples['duplicate'].append({
                            'url': raw_offer.get('url', ''),
                            'title': raw_offer.get('title', '')[:200],
                            'address_parsed': processed['address']['full'],
                            'price': processed.get('price', {}).get('current'),
                            # NOWE: referencja do oryginału, żeby user mógł porównać oba
                            'duplicate_of': {
                                'url': original_dup.get('url', ''),
                                'id': original_dup.get('id', ''),
                                'address': original_dup.get('address', {}).get('full', ''),
                                'price': original_dup.get('price', {}).get('current')
                            },
                            'similarity': round(similarity, 4)
                        })
                    return

                processed_offers.append(processed)
                print(f"      ✅ {processed['address']['full']} - {processed['price']['current']} zł")

            for i, raw_offer in enumerate(raw_offers, 1):
                print(f"   [{i}/{len(raw_offers)}] Przetwarzam: {raw_offer['title'][:50]}...")
                
                # Stwórz ID z URL
                offer_id = raw_offer['url'].split('/')[-1].split('.')[0]

                # SKIPPED + profil firmowy: uzupełnij metadane profilu w istniejącym
                # rekordzie (offer_type nie przechodzi przez _update_existing_offer).
                #
                # FIX 2026-07-26: tu było `continue` — oferty firmowe z niezmienioną ceną
                # NIGDY nie wchodziły do _process_offer, więc ich adres był zamrożony na
                # zawsze (70 z 719 aktywnych; ID1biwCt trzymało 'Krakowskie Przedmieście'
                # z listy przystanków, choć tytuł mówi "ul. Wieniawska 11"). Teraz lecą
                # normalną ścieżką — opis i tak jest z cache, więc to ZERO dodatkowych
                # requestów do OLX, a tytuł z listingu jest świeży.
                if raw_offer.get('skipped') and raw_offer.get('offer_type'):
                    short_id = offer_id.split('-ID')[-1] if '-ID' in offer_id else None
                    existing = (self._find_existing_offer(offer_id)
                                or (self._find_existing_offer_by_short_id(short_id) if short_id else None))
                    if existing and not existing.get('offer_type'):
                        existing['offer_type'] = raw_offer['offer_type']


                # Pomiar czasu geokodowania
                geo_start = time.time()
                processed = self._process_offer(raw_offer)
                geocoding_time += time.time() - geo_start

                # FIX 2026-06-09: jeśli oferta padła na TYMCZASOWY błąd geokodera,
                # nie licz jej jako no_coords — odłóż do kolejki retry (po pętli).
                if not processed and getattr(self, '_geocode_transient', False):
                    print(f"      ⏳ Transient fail geokodera — kolejka retry")
                    transient_retry_queue.append(raw_offer)
                    continue

                consume(raw_offer, processed)

            # FIX 2026-06-09: przebieg RETRY dla ofert z transient-failem geokodera.
            # Backoff 5/10/20s — pojedyncza próba po 5s nie wystarczała przy dłuższych
            # oknach rate-limitu Nominatim i oferty cicho spadały do no_coords.
            if transient_retry_queue:
                retry_queue = transient_retry_queue
                retry_delays = (5, 10, 20)
                for attempt, delay in enumerate(retry_delays, start=1):
                    print(f"\n   ⏳ Retry geokodowania (próba {attempt}/{len(retry_delays)}): "
                          f"{len(retry_queue)} ofert (transient fail Nominatim), czekam {delay}s...")
                    time.sleep(delay)
                    still_transient = []
                    for raw_offer in retry_queue:
                        geo_start = time.time()
                        processed = self._process_offer(raw_offer)
                        geocoding_time += time.time() - geo_start
                        if processed:
                            print(f"      ✅ Retry OK: {raw_offer['title'][:50]}")
                            consume(raw_offer, processed)
                        elif (getattr(self, '_geocode_transient', False)
                              and attempt < len(retry_delays)):
                            still_transient.append(raw_offer)
                        else:
                            # Nie-transient None albo ostatnia próba — konsumujemy,
                            # oferta trafi do właściwej kategorii skip (zwykle no_coords).
                            consume(raw_offer, processed)
                    retry_queue = still_transient
                    if not retry_queue:
                        break

            # Zapisz próbki odrzuconych do analizy (nadpisuje przy każdym scanie)
            try:
                samples_path = self.data_file.parent / 'skipped_offers_sample.json'
                write_json_atomic(samples_path, {
                    'scan_timestamp': datetime.now(self.tz).isoformat(),
                    'counts': {
                        'no_address': skipped_no_address,
                        'no_price': skipped_no_price,
                        'no_coords': skipped_no_coords,
                        'duplicate': skipped_duplicate,
                        'excluded': skipped_excluded,
                        'price_outlier': skipped_price_outlier
                    },
                    'samples': skipped_samples
                })
                print(f"   📊 Zapisano próbki odrzuconych do {samples_path.name}")
            except Exception as e:
                print(f"   ⚠️ Nie udało się zapisać skipped_offers_sample.json: {e}")
            
            processing_duration = time.time() - processing_start
            self.scan_logger.log_phase('processing', processing_duration, {
                'processed': len(processed_offers),
                'skipped_no_address': skipped_no_address,
                'skipped_no_price': skipped_no_price,
                'skipped_no_coords': skipped_no_coords,
                'skipped_duplicate': skipped_duplicate,
                'skipped_excluded': skipped_excluded,
                'skipped_price_outlier': skipped_price_outlier
            })

            # Dodaj metryki geokodowania
            self.scan_logger.log_phase('geocoding', geocoding_time, {
                'geocoded_addresses': len(processed_offers)
            })
            
            print(f"\n✅ Przetworzone oferty: {len(processed_offers)}")
            print(f"   Pominięte - brak adresu: {skipped_no_address}")
            print(f"   Pominięte - brak ceny: {skipped_no_price}")
            print(f"   Pominięte - brak współrzędnych: {skipped_no_coords}")
            print(f"   Pominięte - duplikaty: {skipped_duplicate}")
            print(f"   Pominięte - wykluczone (filtr): {skipped_excluded}")
            print(f"   Pominięte - cena-outlier (10x średnia): {skipped_price_outlier}\n")
            
            # 3. Aktualizacja bazy danych
            print("💾 Krok 3: Aktualizacja bazy danych...")
            
            current_offer_ids = []
            new_offers_count = 0
            updated_offers_count = 0
            reactivated_count = 0
            
            for processed in processed_offers:
                current_offer_ids.append(processed['id'])

                # 1) Dopasowanie po pełnym ID (slug). 2) Fallback po końcówce ID OLX —
                # gdy właściciel edytował tytuł/adres, OLX zmienia slug, ale ID OLX zostaje.
                # Bez tego ta sama oferta rozdwajała się na duplikaty.
                existing = self._find_existing_offer(processed['id'])
                matched_by_short = False
                if not existing and '-ID' in processed['id']:
                    short_id = processed['id'].split('-ID')[-1]
                    existing = self._find_existing_offer_by_short_id(short_id)
                    matched_by_short = existing is not None

                if existing:
                    was_inactive = not existing.get('active', True)
                    self._update_existing_offer(existing, processed)
                    # Slug się zmienił → zaktualizuj id/url do aktualnego,
                    # żeby _mark_inactive_offers nie uznał rekordu za zniknięty.
                    if matched_by_short:
                        existing['id'] = processed['id']
                        existing['url'] = processed['url']
                    updated_offers_count += 1
                    if was_inactive:
                        reactivated_count += 1
                else:
                    self.database['offers'].append(processed)
                    new_offers_count += 1
            
            # Oznacz nieaktywne (ale pominij oferty które były skipped - one są nadal aktywne)
            # UWAGA: raw_offers nie mają klucza 'id', trzeba go wyciągnąć z URL
            skipped_ids = [
                offer['url'].split('/')[-1].split('.')[0]
                for offer in raw_offers
                if offer.get('skipped', False)
            ]
            # Mapa id → api_last_refresh dla ofert pominiętych (śledzenie bumpów bez zmiany ceny)
            skipped_refresh_map = {
                offer['url'].split('/')[-1].split('.')[0]: offer.get('api_last_refresh')
                for offer in raw_offers
                if offer.get('skipped', False) and offer.get('api_last_refresh')
            }
            # ID ofert płatnie wyróżnionych na listingu w TYM skanie
            promoted_ids = [
                offer['url'].split('/')[-1].split('.')[0]
                for offer in raw_offers
                if offer.get('promoted')
            ]
            print(f"   ⭐ Promowane na listingu: {len(promoted_ids)} ofert")

            # ZABEZPIECZENIE: Ochrona przed masową dezaktywacją przy blokadzie OLX
            # (Cloudflare, rate limit, pusta odpowiedź, itp.)
            # Jeśli scraper zwrócił 0 ofert lub podejrzanie mało w stosunku do bazy,
            # NIE dezaktywuj niczego - to prawie na pewno problem ze scrapem, nie z ofertami.
            active_in_db = sum(1 for o in self.database['offers'] if o.get('active'))
            MIN_RATIO = 0.3   # Scrape musi zwrócić co najmniej 30% wcześniejszej liczby aktywnych
            SOFT_RATIO = 0.7  # ...i co najmniej 70% mediany ostatnich ZDROWYCH skanów
            TRUNCATED_RATIO = 0.9  # przy urwanej paginacji wystarczy 10% spadku
            scraped_count = len(raw_offers)
            reference_scrape = self._reference_scrape_size()
            pagination_truncated = getattr(self.scraper, 'pagination_truncated', False)

            # Snapshot ofert AKTYWNYCH przed dezaktywacją — pozwala odróżnić realną
            # reaktywację (oferta była nieaktywna JUŻ WCHODZĄC w skan) od artefaktu pętli
            # scrape→inactive→verify→reactivate (firmówka spoza listingu z InStock była
            # aktywna, zdjęta i wskrzeszona w TYM SAMYM skanie). Bez tego licznik
            # reaktywacji puchł o +1/skan (zgłoszenie Mateusza: Nadbystrzycka/Głębokiej ×5).
            self._active_before_deactivation = {
                o['id'] for o in self.database['offers'] if o.get('active')
            }

            scrape_blocked = False
            if scraped_count == 0 and active_in_db > 0:
                print(f"   ⚠️  OCHRONA: Scraper zwrócił 0 ofert a baza ma {active_in_db} aktywnych.")
                print(f"       Pomijam dezaktywację (prawdopodobna blokada OLX).")
                scrape_blocked = True
                self.scan_logger.log_error(
                    f"SCRAPE_BLOCKED: scraper zwrócił 0 ofert (baza: {active_in_db} aktywnych). "
                    f"Prawdopodobna blokada OLX/Cloudflare lub zmiana struktury HTML."
                )
            elif active_in_db >= 10 and scraped_count < active_in_db * MIN_RATIO:
                print(f"   ⚠️  OCHRONA: Scraper zwrócił tylko {scraped_count} ofert, w bazie jest {active_in_db} aktywnych.")
                print(f"       Próg bezpieczeństwa: {int(active_in_db * MIN_RATIO)}. Pomijam dezaktywację.")
                print(f"       Prawdopodobna blokada OLX lub częściowa awaria scrapera.")
                scrape_blocked = True
                self.scan_logger.log_error(
                    f"SCRAPE_PARTIAL: scraper zwrócił tylko {scraped_count} ofert "
                    f"(baza: {active_in_db} aktywnych, próg: {int(active_in_db * MIN_RATIO)}). "
                    f"Prawdopodobna blokada OLX lub awaria scrapera."
                )
            elif reference_scrape and scraped_count < reference_scrape * SOFT_RATIO:
                # Scrape mieści się w progu 30%, ale jest DUŻO mniejszy niż zwykle.
                # Realny listing waha się o kilkanaście ofert, nie o setki — spadek
                # o >30% względem mediany ostatnich skanów = urwana paginacja.
                # (25.07.2026: dwa równoległe scany → OLX oddał pustą stronę 11,
                #  scrape 520 zamiast ~870, 311 ofert fałszywie zdeaktywowanych.)
                print(f"   ⚠️  OCHRONA: Scrape {scraped_count} ofert vs mediana {reference_scrape} "
                      f"z ostatnich zdrowych skanów (próg: {int(reference_scrape * SOFT_RATIO)}).")
                print(f"       Pomijam dezaktywację — prawdopodobnie urwany listing OLX.")
                scrape_blocked = True
                self.scan_logger.log_error(
                    f"SCRAPE_PARTIAL: scrape {scraped_count} ofert to mniej niż "
                    f"{int(SOFT_RATIO * 100)}% mediany ostatnich zdrowych skanów ({reference_scrape}). "
                    f"Prawdopodobnie urwana paginacja / soft-block OLX."
                    + (" Paginacja urwana na pustej stronie." if pagination_truncated else "")
                )
            elif pagination_truncated and reference_scrape and scraped_count < reference_scrape * TRUNCATED_RATIO:
                # Paginacja urwana na pustej stronie/błędzie + zauważalny spadek —
                # sam fakt urwania nie wystarcza (OLX bywa, że kończy pustą stroną),
                # ale w parze ze spadkiem to sygnał blokady.
                print(f"   ⚠️  OCHRONA: Paginacja urwana (pusta strona), scrape {scraped_count} "
                      f"vs mediana {reference_scrape}. Pomijam dezaktywację.")
                scrape_blocked = True
                self.scan_logger.log_error(
                    f"SCRAPE_PARTIAL: paginacja urwana na pustej stronie, scrape {scraped_count} ofert "
                    f"(mediana zdrowych skanów: {reference_scrape}). Prawdopodobny soft-block OLX."
                )
            elif pagination_truncated and active_in_db >= 10 and scraped_count < active_in_db * TRUNCATED_RATIO:
                # ZAPORA BEZ MEDIANY (2026-08-11): po serii SCRAPE_BLOCKED mediana
                # zdrowych skanów znika (_reference_scrape_size → None), więc dwie
                # zapory wyżej są WYŁĄCZONE. Wtedy sam fakt urwanej paginacji przy
                # scrape mniejszym niż baza aktywnych = nie ufaj, nie dezaktywuj.
                # Bez tego scrape 385 (urwany na str. 3) zdeaktywował 773→336.
                print(f"   ⚠️  OCHRONA: Paginacja urwana, scrape {scraped_count} < baza "
                      f"{active_in_db} aktywnych (brak mediany — seria blokad). Pomijam dezaktywację.")
                scrape_blocked = True
                self.scan_logger.log_error(
                    f"SCRAPE_PARTIAL: paginacja urwana, scrape {scraped_count} ofert < baza "
                    f"{active_in_db} aktywnych, brak mediany odniesienia (seria blokad OLX)."
                )
            elif reference_scrape is None and active_in_db >= 10 and scraped_count < active_in_db * 0.6:
                # Mediana niedostępna (seria blokad) I scrape < 60% aktywnej bazy —
                # nawet bez urwanej paginacji nie ufamy tak dużemu spadkowi zaraz
                # po blokadach. Realny rynek nie kurczy się o 40% między skanami.
                print(f"   ⚠️  OCHRONA: Brak mediany (seria blokad), scrape {scraped_count} < 60% "
                      f"bazy {active_in_db} aktywnych. Pomijam dezaktywację.")
                scrape_blocked = True
                self.scan_logger.log_error(
                    f"SCRAPE_PARTIAL: scrape {scraped_count} ofert < 60% bazy {active_in_db} "
                    f"aktywnych, brak mediany odniesienia (seria blokad OLX)."
                )
            else:
                self._mark_inactive_offers(current_offer_ids, skipped_ids, skipped_refresh_map,
                                           promoted_ids=promoted_ids)
            
            # Aktualizuj days_active dla WSZYSTKICH ofert
            self._update_days_active()
            
            print(f"   Nowe oferty: {new_offers_count}")
            print(f"   Zaktualizowane: {updated_offers_count}")
            if reactivated_count > 0:
                print(f"   🔄 Reaktywowane: {reactivated_count}")
            if self._addr_corrections_count > 0:
                print(f"   🔧 Korekty adresu (re-parsing, bez zmiany tekstu): "
                      f"{self._addr_corrections_count}")
            self.scan_logger.log_phase('address_corrections', 0.0, {
                'corrected': self._addr_corrections_count
            })
            
            # 4. Weryfikacja nieaktywnych ofert
            print("\n🔍 Krok 4: Weryfikacja nieaktywnych ofert...")
            verification_stats = self._verify_inactive_offers(max_to_verify=50)
            reactivated_count += verification_stats.get('reactivated', 0)
            
            # 5. Czyszczenie starych ofert - WYŁĄCZONE (historia zbierana bezterminowo)
            
            # 6. Aktualizacja metadanych
            self.database['last_scan'] = now.isoformat()
            self.database['next_scan'] = self._calculate_next_scan_time()
            
            # 7. Zapisz bazę
            print("\n💾 Krok 6: Zapisywanie bazy danych...")
            self._save_database()
            
            # 8. Loguj statystyki
            total_duration = time.time() - scan_start_time
            
            active = sum(1 for o in self.database['offers'] if o['active'])
            inactive = len(self.database['offers']) - active
            
            self.scan_logger.log_stats({
                'raw_offers': len(raw_offers),
                'processed': len(processed_offers),
                'new': new_offers_count,
                'updated': updated_offers_count,
                'reactivated': reactivated_count,
                'total_in_db': len(self.database['offers']),
                'active': active,
                'inactive': inactive,
                'skipped_no_address': skipped_no_address,
                'skipped_no_price': skipped_no_price,
                'skipped_no_coords': skipped_no_coords,
                'skipped_duplicate': skipped_duplicate,
                'skipped_excluded': skipped_excluded,
                'skipped_price_outlier': skipped_price_outlier,
                'verification': verification_stats
            })
            
            final_status = 'warning' if scrape_blocked else 'completed'
            self.scan_logger.end_scan(final_status, total_duration)
            
            # 9. Podsumowanie
            print("\n" + "="*60)
            print("📊 PODSUMOWANIE SCANU")
            print("="*60)
            print(f"✅ Oferty aktywne: {active}")
            print(f"📁 Oferty nieaktywne (historia): {inactive}")
            print(f"📦 Łącznie w bazie: {len(self.database['offers'])}")
            print(f"⏱️ Czas wykonania: {total_duration:.1f}s")
            print(f"⏰ Następny scan: {datetime.fromisoformat(self.database['next_scan']).strftime('%Y-%m-%d %H:%M')}")
            print("="*60 + "\n")
            
        except Exception as e:
            # W przypadku błędu, zaloguj i zakończ jako failed
            print(f"\n❌ Błąd podczas skanowania: {e}")
            self.scan_logger.log_error(str(e))
            self.scan_logger.end_scan('failed', time.time() - scan_start_time)
            raise


if __name__ == "__main__":
    agent = SonarPokojowy(data_file="../data/offers.json")
    agent.run_scan()
