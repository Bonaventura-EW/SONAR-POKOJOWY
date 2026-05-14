"""
Geocoder - zamiana adresów na współrzędne GPS
Używa Nominatim API (OpenStreetMap) + cache w JSON
+ walidacja czy adres jest w Lublinie (bounding box)
+ Fix #3 (2026-05-11): retry z transformacją do mianownika
"""

import json
import re
import time
from pathlib import Path
from typing import Optional, Dict
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
# GeocoderRateLimited istnieje w nowszych geopy; fallback gdyby ktoś używał starszej wersji
try:
    from geopy.exc import GeocoderRateLimited
except ImportError:
    GeocoderRateLimited = None  # type: ignore

# Bounding box Lublina (~20x25 km z marginesem)
# Pokrywa centrum + wszystkie dzielnice + przedmieścia
LUBLIN_BBOX = {
    'min_lat': 51.18,   # Południowa granica (~3km od skraju)
    'max_lat': 51.30,   # Północna granica (~3km zapasu)
    'min_lon': 22.42,   # Zachodnia granica
    'max_lon': 22.68    # Wschodnia granica
}

# === FIX #3 (2026-05-11): Transformacja dopełniacz → mianownik ===
# Polskie nazwy ulic w ogłoszeniach często są w dopełniaczu ("przy Puławskiej")
# Nominatim szuka mianowników ("Puławska") - bez tej transformacji geokoder odrzuca
# ~40% prawdziwych ulic. Kolejność reguł istotna: dłuższe wzorce PRZED krótszymi.
NOMINATIVE_RULES = [
    # Końcówki -skiej / -ckiej i pochodne (Puławskiej → Puławska)
    (re.compile(r'owskiej$', re.IGNORECASE), 'owska'),
    (re.compile(r'ińskiej$', re.IGNORECASE), 'ińska'),
    (re.compile(r'yńskiej$', re.IGNORECASE), 'yńska'),
    (re.compile(r'eńskiej$', re.IGNORECASE), 'eńska'),
    # Specjalny przypadek: -dniej → -dnia (Zachodniej → Zachodnia, NIE → Zachodna)
    (re.compile(r'dniej$', re.IGNORECASE), 'dnia'),
    (re.compile(r'skiej$', re.IGNORECASE), 'ska'),
    (re.compile(r'ckiej$', re.IGNORECASE), 'cka'),
    (re.compile(r'kiej$', re.IGNORECASE), 'ka'),
    # Końcówki -owej / -nej (Spadowej → Spadowa, Pogodnej → Pogodna)
    (re.compile(r'owej$', re.IGNORECASE), 'owa'),
    (re.compile(r'nej$', re.IGNORECASE), 'na'),
    # Nazwiska męskie -ego (Wołodyjowskiego → Wołodyjowski, Dubieckiego → Dubiecki)
    (re.compile(r'wskiego$', re.IGNORECASE), 'wski'),
    (re.compile(r'ńskiego$', re.IGNORECASE), 'ński'),
    (re.compile(r'skiego$', re.IGNORECASE), 'ski'),
    (re.compile(r'ckiego$', re.IGNORECASE), 'cki'),
    (re.compile(r'iego$', re.IGNORECASE), 'i'),
    (re.compile(r'ego$', re.IGNORECASE), 'i'),
    # Liczba mnoga (Aleja Racławickich → Aleja Racławickie)
    (re.compile(r'ckich$', re.IGNORECASE), 'ckie'),
    (re.compile(r'skich$', re.IGNORECASE), 'skie'),
    (re.compile(r'ich$', re.IGNORECASE), 'ie'),
    # Generic -ej (Sympatycznej → Sympatyczna, Liliowej już złapane wyżej)
    (re.compile(r'ej$', re.IGNORECASE), 'a'),
]

def to_nominative(address: str) -> str:
    """
    Transformuje polską nazwę ulicy z dopełniacza/innego przypadka do mianownika.
    Działa per-word - obsługuje też dwuczłonowe ("Aleja Racławickich" → "Aleja Racławickie")
    oraz adresy z numerem ("Puławskiej 10" → "Puławska 10").
    
    Każdy word jest transformowany niezależnie pierwszą pasującą regułą.
    """
    if not address:
        return address
    
    tokens = address.split()
    result = []
    for token in tokens:
        # Pomiń tokeny które są same cyframi/numerem domu (np. "10", "5a", "1/2")
        if re.match(r'^\d+[a-zA-Z]?(/\d+)?$', token):
            result.append(token)
            continue
        
        new_token = token
        for pattern, replacement in NOMINATIVE_RULES:
            if pattern.search(token):
                new_token = pattern.sub(replacement, token)
                break  # Pierwsza pasująca reguła wygrywa
        result.append(new_token)
    
    return ' '.join(result)


class Geocoder:
    def __init__(self, cache_file: str = "data/geocoding_cache.json"):
        self.cache_file = Path(cache_file)
        self.cache = self._load_cache()
        self.geolocator = Nominatim(user_agent="sonar-pokojowy-lublin/1.0")
        # Stats dla Fix #3
        self._stats_nominative_hits = 0
        
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
        
        Strategia (Fix #3):
        1. Sprawdź cache pod oryginalnym kluczem
        2. Spróbuj Nominatim z oryginalnym adresem
        3. Jeśli fail, przekształć do mianownika ("Puławskiej" → "Puławska") i ponów
        4. Cache zapisuje wynik pod ORYGINALNYM kluczem (żeby był idempotentny)
        
        Args:
            address: Adres do geokodowania (np. "Narutowicza 5" lub "Puławskiej")
            max_retries: Maksymalna liczba prób per query
            
        Returns:
            Dict z lat, lon lub None jeśli nie znaleziono
        """
        if not address:
            return None
        
        # Sprawdzamy cache - oryginalny klucz
        if address in self.cache:
            cached_value = self.cache[address]
            
            # === FIX #6 (2026-05-13): cache-poisoning bypass ===
            # Jeśli w cache mamy None ale transformacja mianownika daje inny string,
            # NIE zwracaj None z cache - spróbuj mianownik (może być w cache jako koordynaty,
            # albo Nominatim go znajdzie). Bez tego cache zatruty przed Fix #3 pozostaje
            # martwy mimo że mianownik działa.
            if cached_value is None:
                nominative_check = to_nominative(address)
                if nominative_check != address:
                    # Mianownik się różni - spróbuj go (może już w cache, może Nominatim)
                    if nominative_check in self.cache and self.cache[nominative_check] is not None:
                        coords = self.cache[nominative_check]
                        print(f"      ♻️  Bypass zatrutego cache '{address}' → mianownik '{nominative_check}' jest w cache")
                        # Zaktualizuj cache oryginału żeby następnym razem hit był natychmiastowy
                        self.cache[address] = coords
                        self._save_cache()
                        self._stats_nominative_hits += 1
                        return coords
                    # Nie ma w cache - kontynuuj normalny flow (KROK 2 niżej spróbuje Nominatim)
                    # Usuwamy zatruty wpis żeby logika niżej mogła zapisać świeży wynik
                else:
                    # Brak transformacji - zwróć None z cache (genuinie nieznany adres)
                    return cached_value
            else:
                # Cache ma koordynaty - zwróć je
                return cached_value
        
        # === KROK 1: Próba z oryginalnym adresem ===
        try:
            coords = self._try_nominatim(address, max_retries=max_retries)
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            # Tymczasowy błąd (rate-limit, timeout, 5xx) - NIE zapisuj None do cache
            print(f"      ⏸️  Tymczasowy błąd Nominatim dla '{address}': {type(e).__name__}")
            return None
        
        if coords is not None:
            self.cache[address] = coords
            self._save_cache()
            return coords
        
        # === KROK 2 (Fix #3): Retry z transformacją do mianownika ===
        nominative = to_nominative(address)
        if nominative != address:
            # Tylko jeśli transformacja faktycznie coś zmieniła
            print(f"      🔄 Retry z mianownikiem: '{address}' → '{nominative}'")
            
            # Sprawdź czy mianownik jest w cache (możliwe że już go geokodowaliśmy)
            if nominative in self.cache and self.cache[nominative] is not None:
                coords = self.cache[nominative]
                print(f"      ✅ Trafiony cache mianownika: {nominative}")
                self.cache[address] = coords  # Zapisz pod oryginalnym też
                self._save_cache()
                self._stats_nominative_hits += 1
                return coords
            
            try:
                coords = self._try_nominatim(nominative, max_retries=max_retries)
            except (GeocoderTimedOut, GeocoderServiceError) as e:
                # Tymczasowy błąd przy mianowniku - NIE zapisuj None do cache
                print(f"      ⏸️  Tymczasowy błąd Nominatim dla mianownika '{nominative}': {type(e).__name__}")
                return None
            
            if coords is not None:
                print(f"      ✅ Mianownik znaleziony: {nominative}")
                # Cache pod OBA klucze
                self.cache[address] = coords
                self.cache[nominative] = coords
                self._save_cache()
                self._stats_nominative_hits += 1
                return coords
        
        # Oba podejścia zawiodły (faktyczne None od Nominatim) - cache jako None
        self.cache[address] = None
        self._save_cache()
        return None
    
    def _try_nominatim(self, address: str, max_retries: int = 3) -> Optional[Dict[str, float]]:
        """
        Pojedyncza próba zapytania do Nominatim (bez logiki retry mianownikiem).
        Zwraca coords lub None.
        
        Raises:
            GeocoderRateLimited / GeocoderServiceError (429): tymczasowy błąd serwera,
                NIE zapisuj wyniku do cache - propagujemy żeby caller obsłużył.
        """
        # Pełny adres z miastem
        full_address = f"{address}, Lublin, Poland"
        
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
                        print(f"      ⚠️ Odrzucono {address} - poza Lublinem (lat={coords['lat']:.4f}, lon={coords['lon']:.4f})")
                        return None
                    
                    return coords
                else:
                    # Nie znaleziono - prawdziwy negatywny wynik
                    return None
                    
            except GeocoderTimedOut:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    # Timeout - traktuj jak tymczasowy błąd, NIE zapisuj None do cache
                    raise
                    
            except GeocoderServiceError as e:
                # FIX 2026-05-13: rozróżnij rate-limit (429) od innych błędów serwera
                # Rate-limit jest TYMCZASOWY - nie zapisuj wyniku do cache.
                # Innych błędów serwera też nie cachuj - mogą minąć przy następnym scanie.
                err_str = str(e).lower()
                is_rate_limit = (
                    '429' in err_str
                    or 'rate' in err_str
                    or 'quota' in err_str
                    or (GeocoderRateLimited is not None and isinstance(e, GeocoderRateLimited))
                )
                if is_rate_limit:
                    print(f"      ⏸️  Rate limit Nominatim dla '{address}' - nie cachuję None")
                    raise  # Propaguj, caller obsłuży
                # Inne błędy serwera też propaguj - lepiej None than cache-poisoning
                raise
        
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
