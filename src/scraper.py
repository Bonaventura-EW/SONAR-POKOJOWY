"""
OLX Scraper - pobiera wszystkie oferty pokoi w Lublinie
Obsługuje paginację (wszystkie strony), opóźnienia anti-block
WERSJA 2.0: Równoległe pobieranie szczegółów (ThreadPoolExecutor)
"""

import requests
from bs4 import BeautifulSoup
import time
import random
import re
import json
from typing import List, Dict, Optional
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

class OLXScraper:
    BASE_URL = "https://www.olx.pl/nieruchomosci/stancje-pokoje/lublin/"
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'pl,en-US;q=0.7,en;q=0.3',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    def __init__(self, delay_range: tuple = (2, 4), max_workers: int = 5, existing_offers: dict = None):
        """
        Args:
            delay_range: Zakres opóźnień między requestami (min, max) w sekundach
                         UWAGA: to delay PER-THREAD, nie globalny. Każdy wątek niezależnie
                         odczekuje swój delay między swoimi requestami.
            max_workers: Liczba równoległych wątków dla pobierania szczegółów
            existing_offers: Słownik istniejących ofert {id: {'price': X, ...}} do inteligentnego pomijania
        """
        self.delay_min, self.delay_max = delay_range
        self.max_workers = max_workers
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        
        # Per-thread rate limiter (KAŻDY WĄTEK MA SWÓJ LICZNIK)
        # Wcześniej globalny self._lock + self._last_request_time powodował, że
        # 5 wątków czekało sekwencyjnie w kolejce na delay - efektywnie 1 wątek.
        # Teraz każdy wątek czeka tylko na SWÓJ ostatni request, więc 10 wątków
        # robi 10× więcej requestów/s niż 1 wątek (ograniczone tylko siecią/serwerem).
        self._thread_local = threading.local()
        # Globalny "soft cap" jako zabezpieczenie przed CF - max QPS dla CAŁEGO scrapera
        self._global_lock = threading.Lock()
        self._global_last_request = 0
        self._global_min_interval = 0.05  # 20 req/s górny limit (CF zwykle limituje przy 30+)
        
        # Inteligentne pomijanie - istniejące oferty
        self.existing_offers = existing_offers or {}
        
        # Statystyki pomijania
        self.stats = {
            'skipped_same_price': 0,
            'fetched_new': 0,
            'fetched_price_changed': 0
        }
    
    def _extract_price_number(self, price_raw: str) -> Optional[int]:
        """
        Wyciąga samą liczbę z tekstu ceny.
        '850 zł' → 850
        'od 850 zł' → 850
        '1 200 zł' → 1200
        """
        if not price_raw:
            return None
        
        # Usuń "od", "do", "zł", "PLN" i białe znaki
        cleaned = re.sub(r'[^\d\s]', '', price_raw)
        # Połącz cyfry (usuń spacje z "1 200")
        cleaned = cleaned.replace(' ', '').strip()
        
        if cleaned.isdigit():
            return int(cleaned)
        return None
    
    def _random_delay(self):
        """
        Per-thread rate limiter z globalnym soft cap.
        
        Logika:
        1. Każdy wątek czeka SWÓJ delay (delay_min..delay_max) między swoimi requestami.
           Wątek A i wątek B mogą wystrzelić requesty równocześnie - to celowe.
        2. Globalny soft cap (20 QPS) chroni przed wystrzeleniem zbyt wielu requestów
           naraz gdyby wszystkie wątki zsynchronizowały się przypadkiem.
        """
        # === KROK 1: Per-thread delay ===
        last_req = getattr(self._thread_local, 'last_request_time', 0)
        now = time.time()
        time_since_last = now - last_req
        
        if time_since_last < self.delay_min:
            sleep_time = self.delay_min - time_since_last
            # Dodaj losowy jitter w zakresie [delay_min, delay_max]
            jitter = random.uniform(0, self.delay_max - self.delay_min)
            time.sleep(sleep_time + jitter)
        else:
            # Już minął delay_min - dodaj tylko jitter (jeśli jest)
            jitter = random.uniform(0, self.delay_max - self.delay_min)
            if jitter > 0:
                time.sleep(jitter)
        
        # === KROK 2: Globalny soft cap (max 20 QPS dla całego scrapera) ===
        with self._global_lock:
            now = time.time()
            global_since_last = now - self._global_last_request
            if global_since_last < self._global_min_interval:
                time.sleep(self._global_min_interval - global_since_last)
            self._global_last_request = time.time()
        
        self._thread_local.last_request_time = time.time()
    
    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """
        Pobiera stronę i zwraca BeautifulSoup object.
        Wykrywa Cloudflare/rate-limit i automatycznie spowalnia scraper.
        """
        try:
            response = self.session.get(url, timeout=15)
            
            # === WYKRYWANIE BLOKADY CLOUDFLARE / RATE LIMIT ===
            # 403 + Cloudflare lub 429 = serwer nas hamuje
            if response.status_code in (403, 429, 503):
                content_lower = response.text[:2000].lower() if response.text else ''
                is_cf = ('cloudflare' in content_lower or 'cf-ray' in str(response.headers).lower()
                         or 'just a moment' in content_lower or 'attention required' in content_lower)
                
                if is_cf or response.status_code == 429:
                    with self._global_lock:
                        # Podwój globalny min_interval (auto-spowolnienie)
                        old_interval = self._global_min_interval
                        self._global_min_interval = min(old_interval * 2, 2.0)
                        print(f"\n🛑 Wykryto blokadę ({response.status_code}) - spowalniam: "
                              f"{old_interval:.2f}s → {self._global_min_interval:.2f}s globalny interval")
                    # Cooldown 30s
                    time.sleep(30)
                    return None
            
            response.raise_for_status()
            return BeautifulSoup(response.text, 'lxml')
        except requests.RequestException as e:
            print(f"❌ Błąd pobierania {url}: {e}")
            return None
    
    def _extract_offers_from_page(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Wyciąga wszystkie oferty z pojedynczej strony.
        
        Returns:
            Lista Dict z kluczami: url, title, description_snippet, price_raw
        """
        offers = []
        seen_urls = set()  # Deduplikacja
        
        # Nowa strategia: znajdź wszystkie linki do /d/oferta/ i wyciągnij dane z kontekstu
        all_links = soup.find_all('a', href=lambda x: x and '/d/oferta/' in str(x))
        
        for link_tag in all_links:
            try:
                # URL ogłoszenia
                url = link_tag.get('href', '')
                if not url.startswith('http'):
                    url = urljoin(self.BASE_URL, url)
                
                # Deduplikacja - normalizuj URL (bez query params)
                clean_url = url.split('?')[0]
                if clean_url in seen_urls:
                    continue
                seen_urls.add(clean_url)
                
                # Znajdź kontener ogłoszenia - idź w górę maksymalnie 6 poziomów
                container = None
                title_tag = None
                price_tag = None
                current = link_tag
                
                for _ in range(6):
                    current = current.find_parent()
                    if not current:
                        break
                    
                    # Sprawdź czy ten poziom ma tytuł i cenę
                    title_tag = current.find('h6') or current.find('h4') or current.find('h3')
                    price_tag = current.find('p', {'data-testid': 'ad-price'})
                    
                    if title_tag and price_tag:
                        container = current
                        break
                
                if not container or not title_tag or not price_tag:
                    continue
                
                # Wyciągnij dane
                title = title_tag.get_text(strip=True)
                price_raw = price_tag.get_text(strip=True)
                
                # Minimum validation - tytuł musi mieć >5 znaków
                if len(title) < 5:
                    continue
                
                offers.append({
                    'url': url,
                    'title': title,
                    'description_snippet': "",
                    'price_raw': price_raw
                })
                
            except (AttributeError, TypeError, KeyError) as e:
                print(f"⚠️ Błąd parsowania ogłoszenia: {e}")
                continue
        
        return offers
    
    def _get_next_page_url(self, soup: BeautifulSoup, current_page: int,
                           base_url: str = None) -> Optional[str]:
        """
        Znajduje URL następnej strony.
        
        Args:
            base_url: opcjonalny base URL (domyślnie self.BASE_URL) - używany dla profili
            
        Returns:
            URL następnej strony lub None jeśli to ostatnia
        """
        _base = base_url or self.BASE_URL
        
        # PRIORYTET 1: Szukamy linku "pagination-forward" (oficjalny przycisk OLX)
        next_link = soup.find('a', {'data-testid': 'pagination-forward'})
        
        if next_link and next_link.get('href'):
            return urljoin(_base, next_link['href'])
        
        # PRIORYTET 2 (FALLBACK): Szukamy linku z ?page=N+1 w HTML.
        # Jeśli OLX zmieni atrybut data-testid, ten fallback ratuje paginację.
        # Nie robimy requesta - tylko parsujemy HTML co już mamy.
        next_page_num = current_page + 1
        next_page_links = soup.find_all(
            'a',
            href=lambda x: x and f'page={next_page_num}' in str(x)
        )
        if next_page_links:
            href = next_page_links[0].get('href', '')
            if href:
                return urljoin(_base, href)
        
        # Brak następnej strony
        return None
    
    def scrape_all_pages(self, max_pages: int = 20) -> List[Dict]:
        """
        Scrapuje wszystkie strony z ofertami (z limitem max_pages).
        NOWE: Równoległe pobieranie szczegółów ofert.
        
        Args:
            max_pages: Maksymalna liczba stron do przejrzenia (zabezpieczenie)
            
        Returns:
            Lista wszystkich ofert ze wszystkich stron
        """
        all_offers = []
        current_url = self.BASE_URL
        page_num = 1
        
        print(f"🔍 Rozpoczynam scraping OLX Lublin - Pokoje...")
        print(f"⚡ Tryb równoległy: {self.max_workers} wątków\n")
        
        # FAZA 1: Pobierz wszystkie podstawowe oferty ze stron listingowych
        while current_url and page_num <= max_pages:
            print(f"📄 Strona {page_num}: {current_url}")
            
            soup = self._fetch_page(current_url)
            if not soup:
                print(f"⚠️ Nie udało się pobrać strony {page_num}")
                break
            
            # Wyciągamy oferty z tej strony
            offers = self._extract_offers_from_page(soup)
            print(f"   Znaleziono {len(offers)} ofert")
            
            if not offers:
                print("   ⚠️ Brak ofert na stronie - koniec paginacji")
                break
            
            all_offers.extend(offers)
            
            # Sprawdzamy czy jest następna strona
            next_url = self._get_next_page_url(soup, page_num)
            
            if not next_url:
                print(f"✅ Osiągnięto ostatnią stronę")
                break
            
            current_url = next_url
            page_num += 1
            
            # Opóźnienie przed następną stroną
            if page_num <= max_pages:
                self._random_delay()
        
        print(f"\n✅ Faza 1: Pobrano {len(all_offers)} podstawowych ofert z {page_num} stron")
        
        # FAZA 2: Inteligentne pobieranie szczegółów (pomijamy oferty ze stałą ceną)
        if all_offers:
            # Rozdziel oferty na: do pobrania vs do pominięcia
            offers_to_fetch = []
            offers_to_skip = []
            
            for offer in all_offers:
                offer_id = offer['url'].split('/')[-1].split('.')[0]
                listing_price = self._extract_price_number(offer['price_raw'])
                
                # Sprawdź czy oferta istnieje w bazie
                if offer_id in self.existing_offers:
                    existing = self.existing_offers[offer_id]
                    existing_price = existing.get('price')
                    
                    # Porównaj ceny (tylko cyfry)
                    if listing_price and existing_price and listing_price == existing_price:
                        # Ta sama cena → pomiń pobieranie szczegółów
                        offers_to_skip.append({
                            'offer': offer,
                            'existing': existing,
                            'reason': 'same_price'
                        })
                        self.stats['skipped_same_price'] += 1
                    else:
                        # Cena się zmieniła → pobierz szczegóły
                        offers_to_fetch.append({
                            'offer': offer,
                            'old_price': existing_price,
                            'new_price': listing_price,
                            'reason': 'price_changed'
                        })
                        self.stats['fetched_price_changed'] += 1
                else:
                    # Nowa oferta → pobierz szczegóły
                    offers_to_fetch.append({
                        'offer': offer,
                        'reason': 'new'
                    })
                    self.stats['fetched_new'] += 1
            
            print(f"\n📊 Inteligentne pobieranie:")
            print(f"   ⏭️  Pominięto (ta sama cena): {len(offers_to_skip)}")
            print(f"   🆕 Nowe oferty do pobrania: {self.stats['fetched_new']}")
            print(f"   💰 Zmieniona cena: {self.stats['fetched_price_changed']}")
            
            # Uzupełnij oferty pominięte danymi z istniejącej bazy
            for item in offers_to_skip:
                offer = item['offer']
                existing = item['existing']
                offer['description'] = existing.get('description', offer['title'])
                offer['official_price'] = existing.get('price')
                offer['official_price_raw'] = f"{existing.get('price')} zł (cache)"
                offer['price_source'] = 'cache'
                offer['skipped'] = True  # Flaga że pominięto pobieranie
                
                # Dodaj adres i współrzędne z cache (dla reaktywacji nieaktywnych ofert)
                if existing.get('address'):
                    offer['cached_address'] = existing.get('address')
                # Współrzędne: PRIORYTET 1 = address.coords (canonical),
                # FALLBACK = top-level 'coordinates' (legacy, do usunięcia z bazy).
                _coords = (existing.get('address', {}) or {}).get('coords') or existing.get('coordinates')
                if _coords:
                    offer['cached_coordinates'] = _coords
                # Oznacz czy oferta była nieaktywna (do potencjalnej reaktywacji)
                offer['was_inactive'] = not existing.get('was_active', True)
            
            # Pobierz szczegóły tylko dla ofert które tego wymagają
            if offers_to_fetch:
                print(f"\n⚡ Faza 2: Pobieranie szczegółów dla {len(offers_to_fetch)} ofert ({self.max_workers} wątków)...")
                start_time = time.time()
                
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    # Submit tylko oferty do pobrania
                    future_to_item = {
                        executor.submit(self._fetch_single_offer_details, item['offer']): item 
                        for item in offers_to_fetch
                    }
                    
                    # Zbierz wyniki
                    completed = 0
                    total = len(offers_to_fetch)
                    
                    for future in as_completed(future_to_item):
                        completed += 1
                        item = future_to_item[future]
                        try:
                            updated_offer = future.result()
                            # Dodaj info o poprzedniej cenie jeśli się zmieniła
                            if item.get('reason') == 'price_changed':
                                updated_offer['previous_price'] = item.get('old_price')
                            
                            # Zaktualizuj w all_offers
                            for i, o in enumerate(all_offers):
                                if o['url'] == updated_offer['url']:
                                    all_offers[i] = updated_offer
                                    break
                            
                            progress = (completed / total) * 100
                            print(f"\r   Postęp: [{completed}/{total}] {progress:.1f}%", end='', flush=True)
                        except (requests.RequestException, AttributeError, TypeError) as e:
                            print(f"\n   ⚠️ Błąd pobierania: {e}")
                
                elapsed = time.time() - start_time
                print(f"\n✅ Szczegóły pobrane w {elapsed:.1f}s (średnio {elapsed/len(offers_to_fetch):.2f}s/oferta)")
            else:
                print(f"\n✅ Wszystkie oferty pominięte (brak zmian cen)")
        
        print(f"\n✅ Scraping zakończony: {len(all_offers)} ofert z {page_num} stron")
        print(f"   📈 Zaoszczędzono {self.stats['skipped_same_price']} requestów!")
        return all_offers
    
    # ------------------------------------------------------------------
    # PROFILE SCRAPING — via OLX API v1 (user_id parameter)
    # ------------------------------------------------------------------

    def _fetch_profile_offers_api(self, user_id: int, profile_key: str,
                                   profile_name: str, profile_url: str,
                                   max_pages: int = 10) -> List[Dict]:
        """
        Pobiera oferty profilu firmowego przez OLX API v1 (/api/v1/offers/?user_id=X).
        Zwraca listę surowych ofert w tym samym formacie co _extract_offers_from_page.
        """
        all_offers: List[Dict] = []
        offset = 0
        limit = 50
        page_num = 1

        print(f"\n👤 Profil \'{profile_name}\' (id={user_id}): API v1")

        while page_num <= max_pages:
            url = (f"https://www.olx.pl/api/v1/offers/?offset={offset}"
                   f"&limit={limit}&user_id={user_id}")
            try:
                resp = self.session.get(url, timeout=15)
                if resp.status_code != 200:
                    print(f"   ⚠️ API status {resp.status_code} na stronie {page_num}")
                    break

                data = resp.json()
                api_offers = data.get('data', [])
                total = data.get('metadata', {}).get('total_elements', 0)

                if not api_offers:
                    if page_num == 1:
                        print(f"   ℹ️ Profil nie ma aktywnych ogłoszeń")
                    else:
                        print(f"   ✅ Koniec wyników na stronie {page_num}")
                    break

                print(f"   📄 Strona {page_num}: {len(api_offers)} ofert (łącznie w API: {total})")

                for api_offer in api_offers:
                    # Konwertuj format API do formatu scrapera
                    offer_url = api_offer.get('url', '')
                    if not offer_url:
                        continue

                    params = api_offer.get('params', [])
                    price_value = None
                    for p in params:
                        if p.get('key') == 'price':
                            price_value = p.get('value', {}).get('value')
                            break

                    if not price_value:
                        price_obj = api_offer.get('price', {})
                        price_value = price_obj.get('value') if price_obj else None

                    price_raw = f"{price_value} zł" if price_value else "Zapytaj o cenę"

                    cat_id = api_offer.get('category', {}).get('id')
                    if cat_id == 11:
                        offer_type = 'pokoj'
                    elif cat_id == 15:
                        offer_type = 'mieszkanie'
                    else:
                        offer_type = 'inne'

                    city_name = (api_offer.get('location', {}) or {}).get('city', {}).get('name', '')
                    
                    # Filtr: tylko Lublin (profil może mieć oferty z całej Polski)
                    if city_name and city_name.lower() != 'lublin':
                        continue

                    offer = {
                        'title': api_offer.get('title', ''),
                        'url': offer_url,
                        'price_raw': price_raw,
                        'profile_key': profile_key,
                        'profile_name': profile_name,
                        'offer_type': offer_type,
                        'city': city_name,
                        'api_last_refresh': api_offer.get('last_refresh_time') or api_offer.get('pushup_time'),
                        'api_created': api_offer.get('created_time'),
                        '_api_data': api_offer,
                    }
                    all_offers.append(offer)

                offset += limit
                page_num += 1

                # Sprawdź czy nie przekraczamy dostępnej liczby
                if offset >= total:
                    print(f"   ✅ Pobrano wszystkie {total} ofert")
                    break

                self._random_delay()

            except (requests.RequestException, ValueError, KeyError) as e:
                print(f"   ⚠️ Błąd API strona {page_num}: {e}")
                break

        print(f"   ✅ \'{profile_name}\': {len(all_offers)} ofert z {page_num - 1} stron")
        return all_offers

    def scrape_all_profiles(self, profiles_config: dict,
                            max_pages_per_profile: int = 10) -> List[Dict]:
        """
        Scrapuje wszystkie profile firmowe przez OLX API v1.
        Zwraca listę ofert z tagiem profile_key/profile_name.
        """
        all_raw: List[Dict] = []
        seen_urls: set = set()
        profile_keys = list(profiles_config.keys())

        print(f"\n🏢 Scraping {len(profiles_config)} profili firmowych przez API v1...")

        for key, cfg in profiles_config.items():
            user_id = cfg.get('user_id')
            if not user_id:
                print(f"   ⚠️ Brak user_id dla profilu {key} — pomijam")
                continue

            profile_offers = self._fetch_profile_offers_api(
                user_id=user_id,
                profile_key=key,
                profile_name=cfg['name'],
                profile_url=cfg['url'],
                max_pages=max_pages_per_profile
            )

            for offer in profile_offers:
                clean = offer['url'].split('?')[0]
                if clean not in seen_urls:
                    seen_urls.add(clean)
                    all_raw.append(offer)

            if key != profile_keys[-1]:
                self._random_delay()

        print(f"\n📊 Profile Faza 1: {len(all_raw)} unikalnych ofert ze wszystkich profili")

        if not all_raw:
            return []

        # Faza 2: fetch szczegółów dla ofert bez pełnych danych
        # Oferty z API mają tylko podstawowe dane — potrzebujemy adresu
        offers_to_fetch = []
        offers_to_skip = []

        for offer in all_raw:
            offer_id = offer['url'].split('/')[-1].split('.')[0]
            api_data = offer.pop('_api_data', {})
            # Przekaż datę odświeżenia z API jeśli nie została już dodana
            if not offer.get('api_last_refresh'):
                offer['api_last_refresh'] = api_data.get('last_refresh_time') or api_data.get('pushup_time')
            if not offer.get('api_created'):
                offer['api_created'] = api_data.get('created_time')

            # Wyciągnij adres z danych API jeśli dostępny
            loc = api_data.get('map', {}) or {}
            if loc.get('lat') and loc.get('lon'):
                offer['cached_coordinates'] = {'lat': loc['lat'], 'lon': loc['lon']}

            location = api_data.get('location', {}) or {}
            city = location.get('city', {}) or {}
            district = location.get('district', {}) or {}
            city_name = city.get('name', '')
            district_name = district.get('name', '')
            if city_name:
                offer['cached_address'] = f"{district_name + ', ' if district_name else ''}{city_name}"

            # Sprawdź cache - próbuj pełny ID, potem krótki (IDxxxxx)
            # OLX zmienia slug URL gdy tytuł ogłoszenia jest edytowany
            listing_price = self._extract_price_number(offer['price_raw'])
            short_key = f'_short_{offer_id.split("-ID")[-1]}' if '-ID' in offer_id else None
            existing = (self.existing_offers.get(offer_id)
                        or (self.existing_offers.get(short_key) if short_key else None))
            if existing:
                existing_price = existing.get('price')
                if listing_price and existing_price and listing_price == existing_price:
                    offers_to_skip.append({'offer': offer, 'existing': existing})
                else:
                    offers_to_fetch.append({'offer': offer})
            else:
                offers_to_fetch.append({'offer': offer})

        print(f"   ⏭️  Pominięto (ta sama cena): {len(offers_to_skip)}")
        print(f"   🆕 Do pobrania szczegółów: {len(offers_to_fetch)}")

        # Uzupełnij skip-owane z cache
        for item in offers_to_skip:
            offer = item['offer']
            existing = item['existing']
            offer['description'] = existing.get('description', offer['title'])
            offer['official_price'] = existing.get('price')
            offer['official_price_raw'] = f"{existing.get('price')} zł (cache)"
            offer['price_source'] = 'cache'
            offer['skipped'] = True
            if existing.get('address') and 'cached_address' not in offer:
                offer['cached_address'] = existing.get('address')
            # Współrzędne: PRIORYTET 1 = address.coords, FALLBACK = legacy top-level
            _coords = (existing.get('address', {}) or {}).get('coords') or existing.get('coordinates')
            if _coords:
                offer['cached_coordinates'] = _coords
            # WAŻNE: zachowaj profile_name i offer_type z aktualnego scanu
            # (existing może mieć profile_name=None jeśli wcześniej nie był w profilu)
            if not offer.get('profile_name') and existing.get('profile_name'):
                offer['profile_name'] = existing['profile_name']

        # Pobierz szczegóły dla nowych
        if offers_to_fetch:
            print(f"   ⚡ Pobieranie szczegółów dla {len(offers_to_fetch)} ofert "
                  f"({self.max_workers} wątków)...")

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_item = {
                    executor.submit(self._fetch_single_offer_details, item['offer']): item
                    for item in offers_to_fetch
                }
                completed = 0
                total_fetch = len(offers_to_fetch)
                for future in as_completed(future_to_item):
                    completed += 1
                    try:
                        updated_offer = future.result()
                        for i, o in enumerate(all_raw):
                            if o['url'] == updated_offer['url']:
                                all_raw[i] = updated_offer
                                break
                        if completed % 10 == 0 or completed == total_fetch:
                            print(f"\r   Postęp: [{completed}/{total_fetch}] "
                                  f"{completed/total_fetch*100:.0f}%", end='', flush=True)
                    except (requests.RequestException, AttributeError, TypeError) as e:
                        print(f"\n   ⚠️ Błąd: {e}")

            print(f"\n   ✅ Szczegóły profili pobrane")

        print(f"\n✅ Profile Faza 2: {len(all_raw)} ofert gotowych do przetworzenia")
        return all_raw
    
    def fetch_offer_details(self, url: str) -> Optional[Dict]:
        """
        Pobiera pełne szczegóły ogłoszenia (pełny opis + oficjalna cena).
        
        STRATEGIA EKSTRAKCJI CENY (według priorytetu):
        1. JSON-LD schema.org (najbardziej niezawodne - OLX oficjalne dane)
        2. Fallback: HTML <h3> z ceną
        
        Args:
            url: URL ogłoszenia
            
        Returns:
            Dict z pełnym opisem, oficjalną ceną i innymi danymi
        """
        self._random_delay()
        soup = self._fetch_page(url)
        if not soup:
            return None
        
        try:
            # NOWE: Pobierz tytuł z og:title (bardziej niezawodne niż h1)
            title_from_page = ""
            og_title = soup.find('meta', property='og:title')
            if og_title:
                title_from_page = og_title.get('content', '').replace(' • OLX.pl', '').strip()
            
            # Pełny opis
            desc_div = soup.find('div', {'data-cy': 'ad_description'})
            if not desc_div:
                desc_div = soup.find('div', class_=lambda x: x and 'description' in str(x).lower())
            
            description = desc_div.get_text(strip=True) if desc_div else ""
            
            # Usuń prefix "Opis" który OLX dodaje
            if description.startswith('Opis'):
                description = description[4:]
            
            # Połącz tytuł z opisem dla lepszego parsowania adresu
            if title_from_page:
                description = title_from_page + ' ' + description
            
            # === PRIORYTET 1: JSON-LD (najbardziej niezawodne) ===
            official_price = None
            official_price_raw = None
            
            json_ld_script = soup.find('script', {'type': 'application/ld+json'})
            if json_ld_script:
                try:
                    json_data = json.loads(json_ld_script.string)
                    # Schema.org Product -> offers -> price
                    if json_data.get('@type') == 'Product' and 'offers' in json_data:
                        price = json_data['offers'].get('price')
                        if price and isinstance(price, (int, float)):
                            official_price = int(price)
                            official_price_raw = f"{official_price} zł (JSON-LD)"
                            
                            # Walidacja - sensowny zakres dla pokoi w Lublinie
                            if 200 <= official_price <= 5000:
                                # Sukces - mamy niezawodną cenę z JSON-LD
                                return {
                                    'description': description,
                                    'official_price': official_price,
                                    'official_price_raw': official_price_raw,
                                    'price_source': 'json-ld'
                                }
                            else:
                                # Cena poza zakresem - odrzuć i użyj fallback
                                official_price = None
                                official_price_raw = None
                except (json.JSONDecodeError, KeyError, TypeError):
                    # JSON-LD nie zadziałało - przejdź do fallback
                    pass
            
            # === FALLBACK: HTML <h3> z ceną ===
            # Tylko jeśli JSON-LD nie zadziałało
            if not official_price:
                for h3 in soup.find_all('h3'):
                    text = h3.get_text(strip=True)
                    # Sprawdź czy zawiera cenę (cyfry + zł)
                    if 'zł' in text.lower() and any(char.isdigit() for char in text):
                        official_price_raw = text
                        # Wyciągnij liczbę - obsługa separatorów tysięcy
                        match = re.search(r'(\d[\d\s]*)', text)
                        if match:
                            price_str = match.group(1).replace(' ', '').replace('\xa0', '')
                            try:
                                price_candidate = int(price_str)
                                # Walidacja
                                if 200 <= price_candidate <= 5000:
                                    official_price = price_candidate
                                    break
                            except ValueError:
                                pass
            
            return {
                'description': description,
                'official_price': official_price,
                'official_price_raw': official_price_raw,
                'price_source': 'html-fallback' if official_price else None
            }
            
        except (AttributeError, TypeError, KeyError, json.JSONDecodeError) as e:
            print(f"⚠️ Błąd parsowania szczegółów ogłoszenia {url}: {e}")
            return None
    
    def _fetch_single_offer_details(self, offer: Dict) -> Dict:
        """
        Wrapper do równoległego pobierania szczegółów pojedynczej oferty.
        Zwraca ofertę z dodanymi szczegółami.
        """
        details = self.fetch_offer_details(offer['url'])
        if details:
            offer['description'] = details['description']
            if details.get('official_price'):
                offer['official_price'] = details['official_price']
                offer['official_price_raw'] = details['official_price_raw']
                offer['price_source'] = details['price_source']  # FIX: kopiuj price_source!
        else:
            # Fallback - użyj tytułu jako opisu
            offer['description'] = offer['title']
        
        return offer


# Testy jednostkowe
if __name__ == "__main__":
    scraper = OLXScraper(delay_range=(0.5, 1), max_workers=5)  # Szybsze dla testów
    
    print("🧪 Test scrapera równoległego - pierwsze 2 strony:\n")
    offers = scraper.scrape_all_pages(max_pages=2)
    
    print(f"\n📊 Podsumowanie:")
    print(f"   Łącznie ofert: {len(offers)}")
    
    if offers:
        print(f"\n📝 Przykładowa oferta:")
        sample = offers[0]
        print(f"   Tytuł: {sample['title'][:60]}...")
        print(f"   URL: {sample['url']}")
        print(f"   Cena: {sample.get('official_price', sample['price_raw'])}")
        print(f"   Opis (pierwsze 100 znaków): {sample.get('description', '')[:100]}...")
