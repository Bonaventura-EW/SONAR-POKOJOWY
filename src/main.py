"""
SONAR POKOJOWY - Główny agent
Koordynuje: scraping → parsowanie → geokodowanie → wykrywanie duplikatów → zapis
WERSJA 2.0: Równoległy scraping + monitoring
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
import pytz
from typing import List, Dict
import time
import random

# Import lokalnych modułów
from scraper import OLXScraper
from profiles_config import TRACKED_PROFILES
from address_parser import AddressParser
from price_parser import PriceParser
from geocoder import Geocoder
from duplicate_detector import DuplicateDetector
from scan_logger import ScanLogger

class SonarPokojowy:
    def __init__(self, data_file: str = "../data/offers.json"):
        self.data_file = Path(data_file)
        self.address_parser = AddressParser(geocoding_cache_path="../data/geocoding_cache.json")
        self.price_parser = PriceParser()
        self.geocoder = Geocoder(cache_file="../data/geocoding_cache.json")
        self.duplicate_detector = DuplicateDetector(similarity_threshold=0.95)
        self.scan_logger = ScanLogger(log_file="../data/scan_history.json")
        
        # Strefa czasowa polska
        self.tz = pytz.timezone('Europe/Warsaw')
        
        # Wczytaj istniejącą bazę
        self.database = self._load_database()
        
        # Inicjalizuj scraper Z istniejącymi ofertami (inteligentne pomijanie)
        existing_offers = self._build_existing_offers_index()
        self.scraper = OLXScraper(delay_range=(0.2, 0.5), max_workers=10, existing_offers=existing_offers)
    
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
                'address': offer.get('address', ''),
                'coordinates': offer.get('coordinates', {}),
                'profile_name': offer.get('profile_name'),
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
        """Zapisuje bazę danych do JSON."""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.database, f, ensure_ascii=False, indent=2)
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
    
    def _process_offer(self, raw_offer: Dict) -> Dict:
        """
        Przetwarza surowe ogłoszenie: parsuje adres, cenę, geokoduje.
        
        Returns:
            Dict z przetworzonymi danymi lub None jeśli oferta nieprawidłowa
        """
        # 1. Użyj pełnego opisu (scraper już go pobrał)
        full_text = raw_offer['title'] + " " + raw_offer.get('description', '')
        
        # FILTR: Wykluczamy ogłoszenia które nie są pokojami w mieszkaniach
        # FIX 2026-05-17: usunięto 'bliźniak', 'dom jednorodzinny', 'w domu jednorodzinnym'
        # po audycie skipped_offers_sample - generowały ~28% false positives w no_address
        # (pokoje na oddzielnej kondygnacji w domu są funkcjonalnie identyczne z pokojami
        # w mieszkaniu i powinny być uwzględniane). Patrz: discussion 2026-05-17.
        excluded_phrases = [
            'domek jednorodzinny',
            'willa',
            'domek',
            'dom w zabudowie',
            'segment'
        ]
        
        full_text_lower = full_text.lower()
        for phrase in excluded_phrases:
            if phrase in full_text_lower:
                print(f"      ⚠️ Wykluczono: {phrase}")
                return None
        
        # 2. Parsuj adres z pełnego tekstu (tytuł + opis)
        address_data = self.address_parser.extract_address(full_text)
        address_precision = 'exact'  # domyślnie: dokładny adres z numerem

        # Jeśli nie znaleziono adresu w tytule, spróbuj w samym opisie
        if not address_data and raw_offer.get('description'):
            print(f"      🔍 Brak adresu w tytule, szukam w opisie...")
            address_data = self.address_parser.extract_address(raw_offer['description'])

        # REAKTYWACJA: Jeśli brak adresu ale mamy cache (oferta była nieaktywna)
        use_cached_coords = False
        cached_coords = None
        if not address_data and raw_offer.get('cached_address'):
            cached_addr_raw = raw_offer.get('cached_address')

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
                cached_precision = 'exact'

            # Fix #4.4 (2026-05-11): Jeśli cached_address jest bogus (artefakt
            # starego parsera), IGNORUJ cache - wymuś re-parsowanie z aktualnym kodem.
            # Bez tego oferty z bogus address utknęłyby na zawsze, bo scraper omija
            # je przy same_price i nie wywołuje extract_address na świeżym opisie.
            # FIX 2026-05-14: używa wspólnej metody _is_bogus_address (dynamic heurystyka)
            is_bogus = self._is_bogus_address(cached_full)
            
            if is_bogus:
                print(f"      🔍 cached_address '{cached_full}' wygląda na bogus, próbuję re-parsować z opisu...")
                # Przeparsuj opis od nowa
                full_text = raw_offer.get('title', '') + ' ' + raw_offer.get('description', '')
                reparsed = (self.address_parser.extract_address(full_text)
                          or self.address_parser.extract_street_only(full_text)
                          or self.address_parser.extract_from_whitelist(full_text))
                if reparsed:
                    cached_full = reparsed['full']
                    cached_street = reparsed.get('street')
                    cached_number = reparsed.get('number')
                    cached_precision = 'exact' if reparsed.get('number') else 'street_only'
                    print(f"      ✅ Re-parsing: '{cached_full}' (precision={cached_precision})")
                    # NIE używamy starych cached_coordinates - są dla bogus adresu
                else:
                    print(f"      ❌ Re-parsing nieudany - oferta zostanie pominięta")
                    cached_full = ''  # pusta wartość → poniżej zostanie odrzucone

            if not cached_full:
                # Cache puste lub bogus i re-parse się nie udał — nie używaj
                print(f"      ⚠️ cached_address bez 'full', pomijam reaktywację z cache")
            else:
                if not is_bogus:
                    print(f"      🔄 Brak adresu w tekście, używam z cache: {cached_full}")
                address_data = {
                    'full': cached_full,
                    'street': cached_street,
                    'number': cached_number
                }
                # Jeśli mamy też współrzędne w cache, użyjemy ich zamiast geokodowania
                # (TYLKO jeśli nie był to bogus address - dla bogus chcemy świeżego geokodowania)
                if not is_bogus and raw_offer.get('cached_coordinates'):
                    cached_coords = raw_offer['cached_coordinates']
                    use_cached_coords = True
                address_precision = cached_precision

        # FALLBACK: spróbuj wyciągnąć samą ulicę (bez numeru) → marker "przybliżony"
        # Decyzja 1a: tylko jawny prefiks (ul./al./pl./os./aleja/aleje/ulica)
        if not address_data:
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
            whitelist_match = self.address_parser.extract_from_whitelist(full_text)
            if not whitelist_match and raw_offer.get('description'):
                whitelist_match = self.address_parser.extract_from_whitelist(raw_offer['description'])
            if whitelist_match:
                print(f"      📚 Znaleziono w whitelist: {whitelist_match['full']}")
                address_data = whitelist_match
                address_precision = 'street_only'

        if not address_data:
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
            return None  # Brak ceny → ignoruj
        
        # 4. Geokoduj adres (lub użyj cache dla reaktywacji)
        if use_cached_coords and cached_coords:
            coords = cached_coords
            print(f"      📍 Użyto współrzędnych z cache: {coords['lat']:.4f}, {coords['lon']:.4f}")
        else:
            # FIX 2026-05-14: używamy return_meta=True żeby wiedzieć czy geocoder zrobił
            # fallback "sama ulica bez numeru". Jeśli tak, obniżamy precision do street_only.
            coords, geo_meta = self.geocoder.geocode_address(
                address_data['full'], return_meta=True
            )
            if not coords:
                print(f"⚠️ Nie można geokodować: {address_data['full']}")
                return None  # Nie znaleziono współrzędnych → ignoruj
            
            if geo_meta.get('number_fallback'):
                # Geocoder nie znalazł konkretnego numeru, użył samej ulicy.
                # Adres na mapie pojawi się jako "przybliżony" (street_only).
                print(f"      📌 Fallback geocoder: '{address_data['full']}' "
                      f"→ koordynaty samej ulicy (precision=street_only)")
                address_precision = 'street_only'
        
        # 5. Stwórz ID z URL (unikalne)
        offer_id = raw_offer['url'].split('/')[-1].split('.')[0]
        
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
        }
    
    def _find_existing_offer(self, offer_id: str) -> Dict:
        """Znajduje istniejące ogłoszenie po ID."""
        for offer in self.database['offers']:
            if offer['id'] == offer_id:
                return offer
        return None

    def _find_existing_offer_by_short_id(self, short_id: str) -> Dict:
        """Znajduje istniejące ogłoszenie po krótkiej końcówce ID (IDxxxxx).
        OLX zmienia slug URL gdy edytowany tytuł — końcówka pozostaje ta sama."""
        if not short_id:
            return None
        suffix = f'-ID{short_id}'
        for offer in self.database['offers']:
            if offer.get('id', '').endswith(suffix):
                return offer
        return None
    
    def _update_existing_offer(self, existing: Dict, new_data: Dict):
        """Aktualizuje istniejące ogłoszenie z inteligentnym zarządzaniem ceną."""
        now = datetime.now(self.tz).isoformat()
        
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
            
            if price_diff_percent < 50:  # Max 50% zmiany
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
            # NOWE: Zapisz poprzednią cenę przed aktualizacją
            existing['price']['previous_price'] = old_price
            existing['price']['price_changed_at'] = now
            
            # Określ kierunek zmiany
            if new_price < old_price:
                existing['price']['price_trend'] = 'down'
                print(f"      📉 Cena SPADŁA: {old_price} → {new_price} zł (↓{old_price - new_price} zł)")
                print(f"      📝 Powód zmiany: {update_reason}")
            else:
                existing['price']['price_trend'] = 'up'
                print(f"      📈 Cena WZROSŁA: {old_price} → {new_price} zł (↑{new_price - old_price} zł)")
                print(f"      📝 Powód zmiany: {update_reason}")
            
            existing['price']['current'] = new_price
            existing['price']['source'] = new_source
            
            # Dodaj do historii
            existing['price']['history'].append(new_price)
            
            # NOWE 2026-05-17: zapis pełnej historii z timestampami
            if 'history_full' not in existing['price']:
                # Backfill dla starych ofert które jeszcze nie mają history_full
                existing['price']['history_full'] = []
                # Pierwsza znana cena = pierwszy wpis history (data first_seen)
                if existing['price']['history']:
                    existing['price']['history_full'].append({
                        'price': existing['price']['history'][0],
                        'date': existing.get('first_seen', now),
                        'approximated': False
                    })
            existing['price']['history_full'].append({
                'price': new_price,
                'date': now,
                'approximated': False
            })
        
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

        # Śledź odświeżenia (bump) dla ofert firmowych
        # api_last_refresh = data ostatniego pushup/odświeżenia z API OLX
        new_refresh = new_data.get('api_last_refresh', '')
        if new_refresh and existing.get('profile_name'):
            # Wyciągnij tylko datę (YYYY-MM-DD) z ISO timestamp
            try:
                new_refresh_date = new_refresh[:10]  # 'YYYY-MM-DD'
                stored_date = existing.get('last_refresh_date', '')[:10] if existing.get('last_refresh_date') else ''
                refresh_dates = existing.get('refresh_dates', [])

                if new_refresh_date and new_refresh_date != stored_date:
                    # Nowa data odświeżenia — max 1/dzień
                    if new_refresh_date not in refresh_dates:
                        refresh_dates.append(new_refresh_date)
                        existing['refresh_dates'] = refresh_dates
                        existing['refresh_count'] = len(refresh_dates)
                        existing['last_refresh_date'] = new_refresh
                        print(f"      🔄 Odświeżenie #{existing['refresh_count']}: {new_refresh_date}")
            except (ValueError, TypeError, AttributeError):
                pass

        # Śledź reaktywacje — inkrementuj licznik przy każdej reaktywacji
        if was_inactive:
            existing['reactivation_count'] = existing.get('reactivation_count', 0) + 1
            print(f"      ♻️ Reaktywacja #{existing['reactivation_count']}")
    
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
    
    def _mark_inactive_offers(self, current_offer_ids: List[str], skipped_offer_ids: List[str] = None):
        """
        Oznacza ogłoszenia jako nieaktywne jeśli nie ma ich w bieżącym scanie.
        Reaktywuje oferty które pojawiły się ponownie (w skipped_ids).
        
        Args:
            current_offer_ids: Lista ID ofert które zostały przetworzone (nowe + zaktualizowane)
            skipped_offer_ids: Lista ID ofert które zostały pominięte przez inteligentne skanowanie
        """
        if skipped_offer_ids is None:
            skipped_offer_ids = []
        
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
                        reactivated_from_skipped += 1
                    # Aktualizuj last_seen dla skipped ofert
                    offer['last_seen'] = now
            elif offer['active']:
                # Oferta nie jest w scanie - dezaktywuj
                offer['active'] = False
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
        import requests
        from bs4 import BeautifulSoup
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        stats = {
            'verified': 0,
            'reactivated': 0,
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
        
        # Użyj sesji scrapera z odpowiednimi headerami (Session jest thread-safe dla GET)
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pl-PL,pl;q=0.9,en;q=0.8'
        })
        
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
                
                # Sprawdź status oferty przez JSON-LD (najbardziej wiarygodne źródło)
                is_active = False
                
                scripts = soup.find_all('script', type='application/ld+json')
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict) and data.get('@type') == 'Product':
                            availability = data.get('offers', {}).get('availability', '')
                            # InStock = aktywna oferta
                            if 'InStock' in availability:
                                is_active = True
                            break
                    except (json.JSONDecodeError, AttributeError, TypeError):
                        pass
                
                # Jeśli nie ma JSON-LD, sprawdź elementy HTML
                if not is_active:
                    price_element = soup.select_one('[data-testid="ad-price-container"]')
                    contact_btns = soup.select('[data-testid*="phone"], [data-testid*="contact"]')
                    
                    if price_element and len(contact_btns) > 0:
                        is_active = True
                
                if is_active:
                    return (offer, 'reactivated', {'last_seen': now, 'reactivated_at': now})
                else:
                    return (offer, 'confirmed_inactive', None)
                    
            except requests.RequestException:
                return (offer, 'error', None)
            except Exception:
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
                        offer['active'] = True
                        offer['last_seen'] = reactivation_data['last_seen']
                        offer['reactivated_at'] = reactivation_data['reactivated_at']
                        offer['reactivation_source'] = 'verification'
                        with stats_lock:
                            stats['reactivated'] += 1
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

            # Zbieram próbki odrzuconych ofert do analizy (max 50 per kategorię)
            skipped_samples = {
                'no_address': [],
                'no_price': [],
                'no_coords': [],
                'duplicate': []
            }
            SAMPLE_LIMIT = 50

            for i, raw_offer in enumerate(raw_offers, 1):
                print(f"   [{i}/{len(raw_offers)}] Przetwarzam: {raw_offer['title'][:50]}...")
                
                # Stwórz ID z URL
                offer_id = raw_offer['url'].split('/')[-1].split('.')[0]

                # SKIPPED + profil firmowy: zaktualizuj tylko profile_name w istniejącej ofercie
                # (skip = ta sama cena, nie trzeba przetwarzać od nowa)
                if raw_offer.get('skipped') and raw_offer.get('profile_name'):
                    short_id = offer_id.split('-ID')[-1] if '-ID' in offer_id else None
                    existing = (self._find_existing_offer(offer_id)
                                or (self._find_existing_offer_by_short_id(short_id) if short_id else None))
                    if existing and not existing.get('profile_name'):
                        existing['profile_name'] = raw_offer['profile_name']
                        if raw_offer.get('offer_type') and not existing.get('offer_type'):
                            existing['offer_type'] = raw_offer['offer_type']
                        print(f"      🏢 Przypisano profil (skip): {raw_offer['profile_name']}")
                    # Dodaj do current_offer_ids żeby nie była dezaktywowana
                    # (będzie obsłużone przez skipped_ids dalej)
                    geocoding_time += 0
                    continue
                
                # Pomiar czasu geokodowania
                geo_start = time.time()
                processed = self._process_offer(raw_offer)
                geocoding_time += time.time() - geo_start

                if not processed:
                    # Zlicz powody odrzucenia + zachowaj próbkę do analizy
                    full_text = raw_offer['title'] + " " + raw_offer.get('description', '')
                    sample = {
                        'url': raw_offer.get('url', ''),
                        'title': raw_offer.get('title', '')[:200],
                        'description_preview': (raw_offer.get('description', '') or '')[:500]
                    }
                    if not self.address_parser.extract_address(full_text):
                        # Może parser znalazł ulicę bez numeru — sprawdź
                        street_only = self.address_parser.extract_street_only(full_text)
                        if street_only:
                            sample['note'] = f"extract_street_only znalazłby: {street_only['full']}"
                        skipped_no_address += 1
                        if len(skipped_samples['no_address']) < SAMPLE_LIMIT:
                            skipped_samples['no_address'].append(sample)
                    elif not self.price_parser.extract_price(full_text) and not raw_offer.get('official_price'):
                        skipped_no_price += 1
                        if len(skipped_samples['no_price']) < SAMPLE_LIMIT:
                            skipped_samples['no_price'].append(sample)
                    else:
                        skipped_no_coords += 1
                        if len(skipped_samples['no_coords']) < SAMPLE_LIMIT:
                            # Dodaj info o adresie który nie dał się zgeokodować
                            addr = self.address_parser.extract_address(full_text)
                            sample['address_parsed'] = addr['full'] if addr else None
                            skipped_samples['no_coords'].append(sample)
                    continue
                
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
                    continue
                
                processed_offers.append(processed)
                print(f"      ✅ {processed['address']['full']} - {processed['price']['current']} zł")

            # Zapisz próbki odrzuconych do analizy (nadpisuje przy każdym scanie)
            try:
                samples_path = self.data_file.parent / 'skipped_offers_sample.json'
                with open(samples_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        'scan_timestamp': datetime.now(self.tz).isoformat(),
                        'counts': {
                            'no_address': skipped_no_address,
                            'no_price': skipped_no_price,
                            'no_coords': skipped_no_coords,
                            'duplicate': skipped_duplicate
                        },
                        'samples': skipped_samples
                    }, f, ensure_ascii=False, indent=2)
                print(f"   📊 Zapisano próbki odrzuconych do {samples_path.name}")
            except Exception as e:
                print(f"   ⚠️ Nie udało się zapisać skipped_offers_sample.json: {e}")
            
            processing_duration = time.time() - processing_start
            self.scan_logger.log_phase('processing', processing_duration, {
                'processed': len(processed_offers),
                'skipped_no_address': skipped_no_address,
                'skipped_no_price': skipped_no_price,
                'skipped_no_coords': skipped_no_coords,
                'skipped_duplicate': skipped_duplicate
            })
            
            # Dodaj metryki geokodowania
            self.scan_logger.log_phase('geocoding', geocoding_time, {
                'geocoded_addresses': len(processed_offers)
            })
            
            print(f"\n✅ Przetworzone oferty: {len(processed_offers)}")
            print(f"   Pominięte - brak adresu: {skipped_no_address}")
            print(f"   Pominięte - brak ceny: {skipped_no_price}")
            print(f"   Pominięte - brak współrzędnych: {skipped_no_coords}")
            print(f"   Pominięte - duplikaty: {skipped_duplicate}\n")
            
            # 3. Aktualizacja bazy danych
            print("💾 Krok 3: Aktualizacja bazy danych...")
            
            current_offer_ids = []
            new_offers_count = 0
            updated_offers_count = 0
            reactivated_count = 0
            
            for processed in processed_offers:
                current_offer_ids.append(processed['id'])
                
                existing = self._find_existing_offer(processed['id'])
                
                if existing:
                    was_inactive = not existing.get('active', True)
                    self._update_existing_offer(existing, processed)
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

            # ZABEZPIECZENIE: Ochrona przed masową dezaktywacją przy blokadzie OLX
            # (Cloudflare, rate limit, pusta odpowiedź, itp.)
            # Jeśli scraper zwrócił 0 ofert lub podejrzanie mało w stosunku do bazy,
            # NIE dezaktywuj niczego - to prawie na pewno problem ze scrapem, nie z ofertami.
            active_in_db = sum(1 for o in self.database['offers'] if o.get('active'))
            MIN_RATIO = 0.3  # Scrape musi zwrócić co najmniej 30% wcześniejszej liczby aktywnych
            scraped_count = len(raw_offers)

            if scraped_count == 0 and active_in_db > 0:
                print(f"   ⚠️  OCHRONA: Scraper zwrócił 0 ofert a baza ma {active_in_db} aktywnych.")
                print(f"       Pomijam dezaktywację (prawdopodobna blokada OLX).")
            elif active_in_db >= 10 and scraped_count < active_in_db * MIN_RATIO:
                print(f"   ⚠️  OCHRONA: Scraper zwrócił tylko {scraped_count} ofert, w bazie jest {active_in_db} aktywnych.")
                print(f"       Próg bezpieczeństwa: {int(active_in_db * MIN_RATIO)}. Pomijam dezaktywację.")
                print(f"       Prawdopodobna blokada OLX lub częściowa awaria scrapera.")
            else:
                self._mark_inactive_offers(current_offer_ids, skipped_ids)
            
            # Aktualizuj days_active dla WSZYSTKICH ofert
            self._update_days_active()
            
            print(f"   Nowe oferty: {new_offers_count}")
            print(f"   Zaktualizowane: {updated_offers_count}")
            if reactivated_count > 0:
                print(f"   🔄 Reaktywowane: {reactivated_count}")
            
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
                'verification': verification_stats
            })
            
            self.scan_logger.end_scan('completed', total_duration)
            
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
