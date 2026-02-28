"""
Map Data Generator - generuje data.json dla mapy
Konwertuje offers.json → docs/data.json (format dla Leaflet)
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List
from collections import defaultdict

class MapDataGenerator:
    PRICE_RANGES = {
        'under_600': {'label': '< 600 zł', 'color': '#90EE90', 'min': 0, 'max': 599},
        'range_600_799': {'label': '600-799 zł', 'color': '#FFD700', 'min': 600, 'max': 799},
        'range_800_999': {'label': '800-999 zł', 'color': '#FFA500', 'min': 800, 'max': 999},
        'range_1000_1199': {'label': '1000-1199 zł', 'color': '#FF6347', 'min': 1000, 'max': 1199},
        'over_1200': {'label': '1200+ zł', 'color': '#8B0000', 'min': 1200, 'max': 999999}
    }
    
    def __init__(self, input_file: str = "../data/offers.json", output_file: str = "../docs/data.json"):
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
    
    def _get_price_range_key(self, price: int) -> str:
        """Zwraca klucz zakresu cenowego dla danej ceny."""
        for key, data in self.PRICE_RANGES.items():
            if data['min'] <= price <= data['max']:
                return key
        return 'over_1200'  # Fallback
    
    def _group_by_address(self, offers: List[Dict]) -> Dict[str, List[Dict]]:
        """Grupuje oferty po adresie (współrzędnych)."""
        grouped = defaultdict(list)
        
        for offer in offers:
            coords = offer['address']['coords']
            key = f"{coords['lat']:.6f},{coords['lon']:.6f}"
            grouped[key].append(offer)
        
        return grouped
    
    def _format_date(self, iso_date: str) -> str:
        """Formatuje datę z ISO na czytelny format (dd.mm.yyyy)."""
        try:
            dt = datetime.fromisoformat(iso_date)
            return dt.strftime('%d.%m.%Y')
        except:
            return iso_date
    
    def _format_datetime(self, iso_datetime: str) -> str:
        """Formatuje datetime z ISO na czytelny format (dd.mm.yyyy HH:MM)."""
        try:
            dt = datetime.fromisoformat(iso_datetime)
            return dt.strftime('%d.%m.%Y %H:%M')
        except:
            return iso_datetime
    
    def _create_marker_data(self, address: str, coords: Dict, offers: List[Dict]) -> Dict:
        """
        Tworzy dane dla jednego markera (może zawierać wiele ofert).
        """
        # Sortuj oferty: aktywne najpierw, potem po dacie
        offers.sort(key=lambda x: (not x['active'], x['last_seen']), reverse=True)
        
        # Limit 5 aktywnych ofert per adres
        active_offers = [o for o in offers if o['active']][:5]
        inactive_offers = [o for o in offers if not o['active']]
        
        # Łącz (max 5 aktywnych + wszystkie nieaktywne)
        limited_offers = active_offers + inactive_offers
        
        # Formatuj oferty do wyświetlenia
        formatted_offers = []
        for offer in limited_offers:
            formatted = {
                'id': offer['id'],
                'price': offer['price']['current'],
                'price_history': offer['price']['history'],
                'media_info': offer['price']['media_info'],
                'url': offer['url'],
                'description': offer['description'],  # Pełny opis bez ucinania
                'first_seen': self._format_date(offer['first_seen']),
                'last_seen': self._format_date(offer['last_seen']),
                'days_active': offer['days_active'],
                'active': offer['active']
            }
            formatted_offers.append(formatted)
        
        # Znajdź cenę reprezentatywną (pierwsza aktywna lub ostatnia)
        representative_price = active_offers[0]['price']['current'] if active_offers else offers[0]['price']['current']
        price_range_key = self._get_price_range_key(representative_price)
        
        return {
            'coords': {'lat': coords['lat'], 'lon': coords['lon']},  # Format obiektowy dla Leaflet
            'address': address,
            'offers': formatted_offers,
            'price_range': price_range_key,
            'has_active': len(active_offers) > 0
        }
    
    def _calculate_stats(self, offers: List[Dict]) -> Dict:
        """Oblicza statystyki dla aktywnych ofert."""
        active_offers = [o for o in offers if o['active']]
        
        if not active_offers:
            return {
                'active_count': 0,
                'avg_price': 0,
                'min_price': 0,
                'max_price': 0
            }
        
        prices = [o['price']['current'] for o in active_offers]
        
        return {
            'active_count': len(active_offers),
            'avg_price': int(sum(prices) / len(prices)),
            'min_price': min(prices),
            'max_price': max(prices)
        }
    
    def generate(self):
        """Główna metoda - generuje data.json dla mapy."""
        print("\n🗺️ Generowanie danych dla mapy...")
        
        # Wczytaj bazę danych
        if not self.input_file.exists():
            print(f"❌ Brak pliku bazy danych: {self.input_file}")
            return
        
        with open(self.input_file, 'r', encoding='utf-8') as f:
            database = json.load(f)
        
        offers = database.get('offers', [])
        
        if not offers:
            print("⚠️ Brak ofert w bazie danych")
            return
        
        # Grupuj po adresie
        grouped = self._group_by_address(offers)
        
        # Twórz markery
        markers = []
        for coords_key, address_offers in grouped.items():
            address = address_offers[0]['address']['full']
            coords = address_offers[0]['address']['coords']
            marker = self._create_marker_data(address, coords, address_offers)
            markers.append(marker)
        
        # Oblicz statystyki
        stats = self._calculate_stats(offers)
        
        # Informacje o skanach
        scan_info = {
            'last': self._format_datetime(database.get('last_scan', '')),
            'next': self._format_datetime(database.get('next_scan', ''))
        }
        
        # Finalna struktura danych
        map_data = {
            'scan_info': scan_info,
            'stats': stats,
            'markers': markers,
            'price_ranges': self.PRICE_RANGES
        }
        
        # Zapisz do pliku
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(map_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Wygenerowano dane dla mapy: {self.output_file}")
        print(f"   Markery: {len(markers)}")
        print(f"   Aktywne oferty: {stats['active_count']}")
        print(f"   Średnia cena: {stats['avg_price']} zł\n")


if __name__ == "__main__":
    generator = MapDataGenerator()
    generator.generate()
    
    # Wygeneruj także dane monitoringu
    print("\n📊 Generowanie danych monitoringu...")
    from monitoring_generator import generate_monitoring_data
    generate_monitoring_data()
