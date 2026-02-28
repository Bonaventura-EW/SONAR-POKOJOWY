"""
Geocoder - zamiana adresów na współrzędne GPS
Używa Nominatim API (OpenStreetMap) + cache w JSON
+ walidacja czy adres jest w Lublinie (bounding box)
"""

import json
import time
from pathlib import Path
from typing import Optional, Dict
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# Bounding box Lublina (~20x25 km z marginesem)
# Pokrywa centrum + wszystkie dzielnice + przedmieścia
LUBLIN_BBOX = {
    'min_lat': 51.18,   # Południowa granica (~3km od skraju)
    'max_lat': 51.30,   # Północna granica (~3km zapasu)
    'min_lon': 22.42,   # Zachodnia granica
    'max_lon': 22.68    # Wschodnia granica
}

class Geocoder:
    def __init__(self, cache_file: str = "data/geocoding_cache.json"):
        self.cache_file = Path(cache_file)
        self.cache = self._load_cache()
        self.geolocator = Nominatim(user_agent="sonar-pokojowy-lublin/1.0")
        
    def _load_cache(self) -> Dict:
        """Ładuje cache z pliku JSON."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def _save_cache(self):
        """Zapisuje cache do pliku JSON."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)
    
    def is_in_lublin(self, coords: Dict[str, float]) -> bool:
        """
        Sprawdza czy współrzędne są w granicach Lublina (bounding box).
        
        Args:
            coords: Dict z kluczami 'lat' i 'lon'
            
        Returns:
            True jeśli w Lublinie, False jeśli poza
        """
        if not coords:
            return False
        
        return (
            LUBLIN_BBOX['min_lat'] <= coords['lat'] <= LUBLIN_BBOX['max_lat'] and
            LUBLIN_BBOX['min_lon'] <= coords['lon'] <= LUBLIN_BBOX['max_lon']
        )
    
    def geocode_address(self, address: str, max_retries: int = 3) -> Optional[Dict[str, float]]:
        """
        Geokoduje adres na współrzędne GPS.
        
        Args:
            address: Adres do geokodowania (np. "Narutowicza 5")
            max_retries: Maksymalna liczba prób
            
        Returns:
            Dict z lat, lon lub None jeśli nie znaleziono
        """
        if not address:
            return None
        
        # Sprawdzamy cache
        if address in self.cache:
            return self.cache[address]
        
        # Pełny adres z miastem
        full_address = f"{address}, Lublin, Poland"
        
        # Próbujemy geokodować
        for attempt in range(max_retries):
            try:
                location = self.geolocator.geocode(
                    full_address,
                    timeout=10,
                    language='pl'
                )
                
                if location:
                    coords = {
                        'lat': location.latitude,
                        'lon': location.longitude
                    }
                    
                    # WALIDACJA: Sprawdź czy adres jest w Lublinie
                    if not self.is_in_lublin(coords):
                        print(f"⚠️ Odrzucono {address} - poza Lublinem (lat={coords['lat']:.4f}, lon={coords['lon']:.4f})")
                        # Zapisujemy do cache jako None (nie próbujemy ponownie)
                        self.cache[address] = None
                        self._save_cache()
                        return None
                    
                    # Zapisujemy do cache
                    self.cache[address] = coords
                    self._save_cache()
                    
                    return coords
                else:
                    # Nie znaleziono - zapisujemy jako None
                    self.cache[address] = None
                    self._save_cache()
                    return None
                    
            except GeocoderTimedOut:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    return None
                    
            except GeocoderServiceError:
                return None
        
        return None
    
    def batch_geocode(self, addresses: list, delay: float = 1.0) -> Dict[str, Optional[Dict]]:
        """
        Geokoduje wiele adresów z opóźnieniem (Nominatim wymaga max 1 req/s).
        
        Args:
            addresses: Lista adresów
            delay: Opóźnienie między requestami (sekundy)
            
        Returns:
            Dict {adres: {lat, lon}}
        """
        results = {}
        
        for i, address in enumerate(addresses):
            coords = self.geocode_address(address)
            results[address] = coords
            
            # Opóźnienie między requestami (polityka Nominatim)
            if i < len(addresses) - 1:
                time.sleep(delay)
        
        return results


# Testy jednostkowe
if __name__ == "__main__":
    geocoder = Geocoder(cache_file="test_geocoding_cache.json")
    
    test_addresses = [
        "Narutowicza 5",
        "Racławickie 14",
        "Plac Litewski 1",
        "Nieistniejąca Ulica 999"  # Test błędnego adresu
    ]
    
    print("🧪 Testy Geocoder:\n")
    for address in test_addresses:
        coords = geocoder.geocode_address(address)
        if coords:
            print(f"✅ {address} → {coords['lat']:.4f}, {coords['lon']:.4f}")
        else:
            print(f"❌ {address} → Nie znaleziono")
    
    print("\n📦 Cache zapisany w: test_geocoding_cache.json")
