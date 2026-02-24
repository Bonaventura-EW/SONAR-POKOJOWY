"""
SONAR POKOJOWY - Główny agent
Koordynuje: scraping → parsowanie → geokodowanie → wykrywanie duplikatów → zapis
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz
from typing import List, Dict

# Import lokalnych modułów
from scraper import OLXScraper
from address_parser import AddressParser
from price_parser import PriceParser
from geocoder import Geocoder
from duplicate_detector import DuplicateDetector

class SonarPokojowy:
    def __init__(self, data_file: str = "../data/offers.json"):
        self.data_file = Path(data_file)
        self.scraper = OLXScraper(delay_range=(2, 4))
        self.address_parser = AddressParser()
        self.price_parser = PriceParser()
        self.geocoder = Geocoder(cache_file="../data/geocoding_cache.json")
        self.duplicate_detector = DuplicateDetector(similarity_threshold=0.95)
        
        # Strefa czasowa polska
        self.tz = pytz.timezone('Europe/Warsaw')
        
        # Wczytaj istniejącą bazę
        self.database = self._load_database()
    
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
    
    def _process_offer(self, raw_offer: Dict) -> Dict:
        """
        Przetwarza surowe ogłoszenie: parsuje adres, cenę, geokoduje.
        
        Returns:
            Dict z przetworzonymi danymi lub None jeśli oferta nieprawidłowa
        """
        # 1. Pobierz pełny opis (jeśli potrzebny)
        full_text = raw_offer['title'] + " " + raw_offer.get('description_snippet', '')
        
        # Opcjonalnie: pobierz pełną stronę dla pełnego opisu
        # details = self.scraper.fetch_offer_details(raw_offer['url'])
        # if details:
        #     full_text += " " + details['description']
        
        # 2. Parsuj adres
        address_data = self.address_parser.extract_address(full_text)
        if not address_data:
            return None  # Brak adresu → ignoruj
        
        # 3. Parsuj cenę
        price_data = self.price_parser.extract_price(full_text)
        if not price_data:
            return None  # Brak ceny → ignoruj
        
        # 4. Geokoduj adres
        coords = self.geocoder.geocode_address(address_data['full'])
        if not coords:
            print(f"⚠️ Nie można geokodować: {address_data['full']}")
            return None  # Nie znaleziono współrzędnych → ignoruj
        
        # 5. Stwórz ID z URL (unikalne)
        offer_id = raw_offer['url'].split('/')[-1].split('.')[0]
        
        return {
            'id': offer_id,
            'url': raw_offer['url'],
            'address': {
                'full': address_data['full'],
                'street': address_data['street'],
                'number': address_data['number'],
                'coords': coords
            },
            'price': {
                'current': price_data['price'],
                'history': [price_data['price']],
                'media_info': price_data['media_info']
            },
            'description': full_text,
            'first_seen': datetime.now(self.tz).isoformat(),
            'last_seen': datetime.now(self.tz).isoformat(),
            'active': True,
            'days_active': 0
        }
    
    def _find_existing_offer(self, offer_id: str) -> Dict:
        """Znajduje istniejące ogłoszenie po ID."""
        for offer in self.database['offers']:
            if offer['id'] == offer_id:
                return offer
        return None
    
    def _update_existing_offer(self, existing: Dict, new_data: Dict):
        """Aktualizuje istniejące ogłoszenie."""
        now = datetime.now(self.tz).isoformat()
        
        # Aktualizuj last_seen
        existing['last_seen'] = now
        
        # Sprawdź zmianę ceny
        if existing['price']['current'] != new_data['price']['current']:
            existing['price']['history'].append(new_data['price']['current'])
            existing['price']['current'] = new_data['price']['current']
        
        # Aktualizuj media_info (może się zmienić)
        existing['price']['media_info'] = new_data['price']['media_info']
        
        # Upewnij się że jest aktywne
        existing['active'] = True
    
    def _mark_inactive_offers(self, current_offer_ids: List[str]):
        """Oznacza ogłoszenia jako nieaktywne jeśli nie ma ich w bieżącym scanie."""
        now = datetime.now(self.tz)
        
        for offer in self.database['offers']:
            if offer['id'] not in current_offer_ids and offer['active']:
                offer['active'] = False
                
                # Oblicz dni aktywności
                first_seen = datetime.fromisoformat(offer['first_seen'])
                last_seen = datetime.fromisoformat(offer['last_seen'])
                offer['days_active'] = (last_seen - first_seen).days
    
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
        """Główny proces skanowania."""
        print("\n" + "="*60)
        print("🎯 SONAR POKOJOWY - Scan Started")
        print("="*60 + "\n")
        
        now = datetime.now(self.tz)
        print(f"⏰ Czas: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")
        
        # 1. Scraping OLX
        print("📡 Krok 1: Scraping OLX...")
        raw_offers = self.scraper.scrape_all_pages(max_pages=20)
        print(f"✅ Pobrano {len(raw_offers)} surowych ofert\n")
        
        # 2. Przetwarzanie ofert
        print("🔧 Krok 2: Przetwarzanie ofert...")
        processed_offers = []
        skipped_no_address = 0
        skipped_no_price = 0
        skipped_no_coords = 0
        skipped_duplicate = 0
        
        for i, raw_offer in enumerate(raw_offers, 1):
            print(f"   [{i}/{len(raw_offers)}] Przetwarzam: {raw_offer['title'][:50]}...")
            
            processed = self._process_offer(raw_offer)
            
            if not processed:
                # Zlicz powody odrzucenia
                full_text = raw_offer['title'] + " " + raw_offer.get('description_snippet', '')
                if not self.address_parser.extract_address(full_text):
                    skipped_no_address += 1
                elif not self.price_parser.extract_price(full_text):
                    skipped_no_price += 1
                else:
                    skipped_no_coords += 1
                continue
            
            # Sprawdź duplikaty
            if self.duplicate_detector.filter_duplicates(processed, processed_offers):
                skipped_duplicate += 1
                print(f"      ⚠️ Duplikat - ignoruję")
                continue
            
            processed_offers.append(processed)
            print(f"      ✅ {processed['address']['full']} - {processed['price']['current']} zł")
        
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
        
        for processed in processed_offers:
            current_offer_ids.append(processed['id'])
            
            existing = self._find_existing_offer(processed['id'])
            
            if existing:
                self._update_existing_offer(existing, processed)
                updated_offers_count += 1
            else:
                self.database['offers'].append(processed)
                new_offers_count += 1
        
        # Oznacz nieaktywne
        self._mark_inactive_offers(current_offer_ids)
        
        print(f"   Nowe oferty: {new_offers_count}")
        print(f"   Zaktualizowane: {updated_offers_count}")
        
        # 4. Czyszczenie starych ofert
        print("\n🗑️ Krok 4: Czyszczenie starych ofert...")
        self._cleanup_old_offers(max_age_days=548)
        
        # 5. Aktualizacja metadanych
        self.database['last_scan'] = now.isoformat()
        self.database['next_scan'] = self._calculate_next_scan_time()
        
        # 6. Zapisz bazę
        print("\n💾 Krok 5: Zapisywanie bazy danych...")
        self._save_database()
        
        # 7. Podsumowanie
        print("\n" + "="*60)
        print("📊 PODSUMOWANIE SCANU")
        print("="*60)
        active = sum(1 for o in self.database['offers'] if o['active'])
        inactive = len(self.database['offers']) - active
        print(f"✅ Oferty aktywne: {active}")
        print(f"📁 Oferty nieaktywne (historia): {inactive}")
        print(f"📦 Łącznie w bazie: {len(self.database['offers'])}")
        print(f"⏰ Następny scan: {datetime.fromisoformat(self.database['next_scan']).strftime('%Y-%m-%d %H:%M')}")
        print("="*60 + "\n")


if __name__ == "__main__":
    agent = SonarPokojowy(data_file="../data/offers.json")
    agent.run_scan()
