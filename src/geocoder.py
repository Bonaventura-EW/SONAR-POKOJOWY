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

from shared_utils import write_json_atomic

# Nazwy dzielnic Lublina — dla nich NIE forsujemy dopasowania do ulicy o tej samej
# nazwie (marker dzielnicowy ma stać na centroidzie dzielnicy). FIX 2026-08-18.
try:
    from address_parser_data import LUBLIN_DISTRICTS as _LUBLIN_DISTRICTS
except ImportError:  # pragma: no cover — geocoder bywa importowany samodzielnie
    _LUBLIN_DISTRICTS = set()
_DISTRICT_NAMES_LOWER = {str(d).strip().lower() for d in _LUBLIN_DISTRICTS}

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

# === FIX 2026-05-14 (P2b - fix B): drugorzędne warianty dla liczby mnogiej → pojedynczej ===
# Niektóre ulice Lublina mają formę kanoniczną w liczbie POJEDYNCZEJ żeńskiej:
#   - Kraśnicka (nie Kraśnickie)
#   - Nadbystrzycka (nie Nadbystrzyckie)  
#   - Nałkowska (nie Nałkowskie)
# Ale parser czasem wyciąga formę z opisu "okolice Kraśnickich/Nadbystrzyckich" (l.mn. dop.).
# Standardowy to_nominative transformuje to do l. mnogiej mianownika (Kraśnickie), które
# Nominatim nie zna. Te reguły dają DRUGI wariant - liczba pojedyncza żeńska.
# 
# UWAGA: są ulice z prawdziwą l. mnogą (Aleje Racławickie). Geocoder próbuje OBA warianty.
NOMINATIVE_VARIANT_RULES = [
    # Forma z -ckich → -cka (Kraśnickich → Kraśnicka, Nadbystrzyckich → Nadbystrzycka)
    (re.compile(r'ckich$', re.IGNORECASE), 'cka'),
    # Forma z -skich → -ska (Nałkowskich → Nałkowska, Lubomelskich → Lubomelska)
    (re.compile(r'skich$', re.IGNORECASE), 'ska'),
    # Forma z -ckie → -cka (Nadbystrzyckie → Nadbystrzycka)
    (re.compile(r'ckie$', re.IGNORECASE), 'cka'),
    # Forma z -skie → -ska (Wieniawskie → Wieniawska)
    (re.compile(r'skie$', re.IGNORECASE), 'ska'),
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


def to_nominative_singular_feminine(address: str) -> str:
    """
    Alternatywny mianownik dla nazw ulic w liczbie POJEDYNCZEJ ŻEŃSKIEJ.
    
    Stosuje NOMINATIVE_VARIANT_RULES per-word. Zwraca pusty string jeśli żadna
    reguła nie zadziałała (czyli adres nie ma formy zmieniającej się).
    
    Przykłady:
        "Kraśnickich"      → "Kraśnicka"
        "Aleja Kraśnickich" → "Aleja Kraśnicka"
        "Nadbystrzyckie"   → "Nadbystrzycka"
        "Racławickie"      → "Racławicka"   (UWAGA: ta forma NIE istnieje w Lublinie,
                                              ale Nominatim odrzuci ją i geocoder
                                              przejdzie do innych wariantów)
        "Lipowa"           → ""              (reguła nie zadziałała = brak alt. wariantu)
    
    Used by Geocoder jako dodatkowy wariant fallbacku (KROK 3.5).
    """
    if not address:
        return ''
    
    tokens = address.split()
    result = []
    any_change = False
    for token in tokens:
        if re.match(r'^\d+[a-zA-Z]?(/\d+)?$', token):
            result.append(token)
            continue
        
        new_token = token
        for pattern, replacement in NOMINATIVE_VARIANT_RULES:
            if pattern.search(token):
                new_token = pattern.sub(replacement, token)
                if new_token != token:
                    any_change = True
                break
        result.append(new_token)
    
    if not any_change:
        return ''  # Brak transformacji = brak alt. wariantu
    return ' '.join(result)


class Geocoder:
    def __init__(self, cache_file: str = "data/geocoding_cache.json"):
        self.cache_file = Path(cache_file)
        self.cache = self._load_cache()
        self.geolocator = Nominatim(user_agent="sonar-pokojowy-lublin/1.0")
        # Stats dla Fix #3
        self._stats_nominative_hits = 0
        # Stats dla Fix 2026-05-14: ile razy fallback "sama ulica bez numeru" zadziałał
        self._stats_number_fallback_hits = 0
        
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
        """Zapisuje cache do pliku JSON (atomowo)."""
        write_json_atomic(self.cache_file, self.cache)
    
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
    
    def geocode_address(self, address: str, max_retries: int = 3, return_meta: bool = False):
        """
        Geokoduje adres na współrzędne GPS.
        
        Strategia:
        1. Sprawdź cache pod oryginalnym kluczem
        2. Spróbuj Nominatim z oryginalnym adresem
        3. Jeśli fail, przekształć do mianownika ("Puławskiej" → "Puławska") i ponów
        4. Jeśli fail, retry z liczbą mnogą/poj. (Aleja ↔ Aleje)
        5. Fix 2026-05-14: jeśli adres ma numer i dotąd brak wyniku, spróbuj samej ulicy
           bez numeru. Zwraca koordynaty samej ulicy + flagę fallback w meta.
        6. Cache zapisuje wynik pod ORYGINALNYM kluczem (żeby był idempotentny).
        
        Args:
            address: Adres do geokodowania (np. "Narutowicza 5" lub "Puławskiej")
            max_retries: Maksymalna liczba prób per query
            return_meta: Jeśli True, zwraca tupla (coords, meta_dict). Domyślnie zachowuje
                wsteczną kompatybilność i zwraca sam coords (lub None).
        
        Returns:
            Jeśli return_meta=False (domyślnie): Dict z lat, lon lub None.
            Jeśli return_meta=True: tupla (coords, meta) gdzie meta to dict:
                - 'number_fallback': bool — True jeśli zwrócono koordynaty samej ulicy
                  zamiast adresu z numerem (caller powinien obniżyć precision do street_only)
                - 'cache_hit': bool — True jeśli wynik pochodzi z cache (bez Nominatim)
        """
        coords, meta = self._geocode_with_meta(address, max_retries)
        if return_meta:
            return coords, meta
        return coords

    def _geocode_with_meta(self, address: str, max_retries: int = 3):
        """Implementacja geokodowania, zawsze zwraca (coords, meta)."""
        meta = {'number_fallback': False, 'cache_hit': False, 'transient_error': False}
        
        if not address:
            return None, meta
        
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
                        meta['cache_hit'] = True
                        return coords, meta
                    # Nie ma w cache - kontynuuj normalny flow (KROK 2 niżej spróbuje Nominatim)
                    # Usuwamy zatruty wpis żeby logika niżej mogła zapisać świeży wynik
                else:
                    # Brak transformacji - cache None oznacza "Nominatim już próbował i nie znalazł".
                    # Ale jeśli adres ma numer, spróbujemy fallbacku "sama ulica" (KROK 4 niżej).
                    # Nie zwracamy tutaj — kontynuujemy do fallbacku.
                    pass
            else:
                # Cache ma koordynaty - zwróć je
                meta['cache_hit'] = True
                return cached_value, meta
        
        # === FIX 2026-08-18 (audyt markerów): tryb zapytania ===
        # Adres z numerem → akceptujemy TYLKO wynik z numerem domu (inaczej dostajemy
        # punkt ulicy z etykietą "dokładny adres" — 11 takich markerów w audycie).
        # Adres bez numeru → wolimy wynik będący ULICĄ, a nie osiedlem/parkiem/sklepem
        # o tej samej nazwie (9 markerów: 'Chopina' → osiedle Chopina zamiast ulicy).
        wants_house = self._has_house_number(address)
        prefer_road = (
            not wants_house
            and not self._ESTATE_PREFIX.match(address)
            and address.strip().lower() not in _DISTRICT_NAMES_LOWER
        )
        # Wyniki "gorszego sortu" znalezione po drodze — używamy ich dopiero, gdy
        # żaden wariant nie da lepszego:
        #  - street_level: adres z numerem trafił tylko w ulicę (→ number_fallback),
        #  - weak: adres bez numeru trafił w osiedle/park/sklep zamiast w ulicę.
        street_level_coords = None
        weak_coords = None

        def _lookup(query, max_retries=max_retries):
            """Zwraca (coords, info) albo podnosi wyjątek sieciowy."""
            return self._nominatim_lookup(query, max_retries=max_retries,
                                          require_house=wants_house, prefer_road=prefer_road)

        def _accept(coords, info):
            """Wynik "mocny" → zwraca coords. Słaby → chowa go i zwraca None,
            żeby dalsze warianty (mianownik, l. mnoga, ucięty numer mieszkania)
            miały szansę trafić lepiej."""
            nonlocal street_level_coords, weak_coords
            if coords is None:
                return None
            if info.get('street_level'):
                if street_level_coords is None:
                    street_level_coords = coords
                return None
            if info.get('weak'):
                if weak_coords is None:
                    weak_coords = coords
                return None
            return coords

        # === KROK 1: Próba z oryginalnym adresem ===
        # Pomijamy Nominatim jeśli cache już dał None (jest tam właśnie z tego powodu).
        coords = None
        skip_full_lookup = (address in self.cache and self.cache[address] is None
                           and to_nominative(address) == address)

        if not skip_full_lookup:
            try:
                coords, info = _lookup(address)
            except (GeocoderTimedOut, GeocoderServiceError) as e:
                # Tymczasowy błąd (rate-limit, timeout, 5xx) - NIE zapisuj None do cache
                print(f"      ⏸️  Tymczasowy błąd Nominatim dla '{address}': {type(e).__name__}")
                meta['transient_error'] = True
                return None, meta

            # Wynik słaby (punkt ulicy zamiast numeru albo osiedle zamiast ulicy)
            # NIE trafia do cache pod tym kluczem — kolejny scan wziąłby go za
            # dokładny adres. Chowamy go i próbujemy dalszych wariantów.
            if coords is not None and (info['street_level'] or info['weak']):
                print(f"      📍 '{address}': słaby wynik Nominatim "
                      f"({'brak numeru' if info['street_level'] else 'nie ulica'}), szukam dalej")
            coords = _accept(coords, info)

            if coords is not None:
                self.cache[address] = coords
                self._save_cache()
                return coords, meta
        
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
                return coords, meta
            
            try:
                coords, info = _lookup(nominative)
            except (GeocoderTimedOut, GeocoderServiceError) as e:
                # Tymczasowy błąd przy mianowniku - NIE zapisuj None do cache
                print(f"      ⏸️  Tymczasowy błąd Nominatim dla mianownika '{nominative}': {type(e).__name__}")
                meta['transient_error'] = True
                return None, meta

            coords = _accept(coords, info)

            if coords is not None:
                print(f"      ✅ Mianownik znaleziony: {nominative}")
                # Cache pod OBA klucze
                self.cache[address] = coords
                self.cache[nominative] = coords
                self._save_cache()
                self._stats_nominative_hits += 1
                return coords, meta
        
        # === KROK 3 (Fix 2026-05-14): retry z liczbą mnogą Aleja ↔ Aleje ===
        # W Lublinie są ulice w liczbie mnogiej: "Aleje Racławickie", "Aleje 1000-lecia",
        # "Aleje Solidarności" itd. Parser standardowo robi "Aleja" (liczba poj.), więc
        # Nominatim nie znajduje. Próbujemy z "Aleje".
        # Analogicznie odwrotnie - jeśli ktoś napisał "Aleje X" a to jest "Aleja X".
        plural_variants = []
        # Wybierz mianownik (jeśli istnieje) albo oryginał
        candidate = nominative if nominative != address else address
        if candidate.startswith('Aleja '):
            plural_variants.append('Aleje ' + candidate[len('Aleja '):])
        elif candidate.startswith('Aleje '):
            plural_variants.append('Aleja ' + candidate[len('Aleje '):])
        
        for variant in plural_variants:
            print(f"      🔄 Retry liczba mnoga/poj.: '{address}' → '{variant}'")
            
            # Cache hit?
            if variant in self.cache and self.cache[variant] is not None:
                coords = self.cache[variant]
                print(f"      ✅ Trafiony cache wariantu: {variant}")
                self.cache[address] = coords
                self._save_cache()
                return coords, meta
            
            try:
                coords, info = _lookup(variant)
            except (GeocoderTimedOut, GeocoderServiceError) as e:
                print(f"      ⏸️  Tymczasowy błąd Nominatim dla '{variant}': {type(e).__name__}")
                meta['transient_error'] = True
                return None, meta

            coords = _accept(coords, info)

            if coords is not None:
                print(f"      ✅ Wariant znaleziony: {variant}")
                self.cache[address] = coords
                self.cache[variant] = coords
                self._save_cache()
                return coords, meta
        
        # === KROK 3.5 (Fix 2026-05-14, P2b): wariant liczba pojedyncza żeńska ===
        # Niektóre ulice Lublina mają formę kanoniczną w liczbie POJEDYNCZEJ żeńskiej:
        # Kraśnicka, Nadbystrzycka, Nałkowska. Parser z opisów typu "okolice Kraśnickich"
        # daje "Kraśnickich" (l.mn. dop.), standardowy to_nominative robi "Kraśnickie",
        # ale Nominatim zna tylko "Kraśnicka". Próbujemy obu form.
        # Działa też dla "Nadbystrzyckie" → "Nadbystrzycka" (gdy parser wyciągnął już l.mn.
        # mianownik z opisu typu "ul. Nadbystrzyckie").
        # 
        # WAŻNE: jeśli oryginał i nominative już wyczerpały te warianty, pomijamy.
        singular_fem_variants = []
        for source in [address, nominative]:
            variant = to_nominative_singular_feminine(source)
            if variant and variant not in singular_fem_variants and variant != address and variant != nominative:
                singular_fem_variants.append(variant)
        
        for variant in singular_fem_variants:
            print(f"      🔄 Retry l. poj. żeńska: '{address}' → '{variant}'")
            
            if variant in self.cache and self.cache[variant] is not None:
                coords = self.cache[variant]
                print(f"      ✅ Trafiony cache wariantu: {variant}")
                self.cache[address] = coords
                self._save_cache()
                return coords, meta
            
            if variant in self.cache and self.cache[variant] is None:
                continue  # Już wiemy że Nominatim go nie zna
            
            try:
                coords, info = _lookup(variant)
            except (GeocoderTimedOut, GeocoderServiceError) as e:
                print(f"      ⏸️  Tymczasowy błąd Nominatim dla '{variant}': {type(e).__name__}")
                meta['transient_error'] = True
                return None, meta

            coords = _accept(coords, info)

            if coords is not None:
                print(f"      ✅ Wariant l. poj. ż. znaleziony: {variant}")
                self.cache[address] = coords
                self.cache[variant] = coords
                self._save_cache()
                return coords, meta
            else:
                # Cache None dla negatywnego wyniku — ale tylko pod kluczem wariantu
                self.cache[variant] = None
                self._save_cache()

        # === KROK 3.7 (FIX 2026-08-18, audyt markerów klasa C): numer mieszkania ===
        # "Głęboka 29/4", "Niecała 15/80", "Skrzetuskiego 2/22" — Nominatim nie zna
        # numeru z mieszkaniem i oddaje punkt ulicy (marker 160–540 m od budynku,
        # z etykietą "dokładny adres"). Sam numer domu ZNA: "Głęboka 29" → budynek.
        # Próbujemy po odcięciu części po "/" — najpierw oryginał, potem mianownik.
        if wants_house:
            apt_variants = []
            for source in [address, nominative]:
                stripped = self._strip_apartment(source)
                if stripped and stripped not in apt_variants:
                    apt_variants.append(stripped)

            for variant in apt_variants:
                if variant in self.cache and self.cache[variant] is not None:
                    coords = self.cache[variant]
                    print(f"      🏠 Numer bez mieszkania z cache: '{address}' → '{variant}'")
                    self.cache[address] = coords
                    self._save_cache()
                    return coords, meta
                if variant in self.cache and self.cache[variant] is None:
                    continue

                print(f"      🏠 Retry bez numeru mieszkania: '{address}' → '{variant}'")
                try:
                    coords, info = self._nominatim_lookup(variant, max_retries=max_retries,
                                                          require_house=True, prefer_road=False)
                except (GeocoderTimedOut, GeocoderServiceError) as e:
                    print(f"      ⏸️  Tymczasowy błąd Nominatim dla '{variant}': {type(e).__name__}")
                    meta['transient_error'] = True
                    return None, meta

                if coords is not None and not info['street_level']:
                    print(f"      ✅ Trafiony numer domu: {variant}")
                    self.cache[variant] = coords
                    self.cache[address] = coords
                    self._save_cache()
                    return coords, meta
                if coords is not None and street_level_coords is None:
                    street_level_coords = coords


        # === KROK 4 (Fix 2026-05-14): fallback "sama ulica bez numeru" ===
        # Jeśli adres ma numer i wszystkie powyższe podejścia zawiodły, spróbuj samej ulicy.
        # Nominatim często nie ma konkretnego numeru w bazie (np. "Narutowicza 38" — None,
        # ale "Narutowicza" — znajduje się ulica). Wracamy koordynaty samej ulicy i flagę
        # number_fallback=True, żeby caller obniżył precision do 'street_only'.
        # 
        # WAŻNE: NIE zapisujemy wyniku pod cache[address] - bez tego utracilibyśmy info
        # o fallbacku przy kolejnym wywołaniu (cache zwracałby koordynaty samej ulicy
        # bez flagi number_fallback, caller traktowałby je jako precision=exact).
        # Zamiast tego cache[street_only] zostaje uzupełnione (jeśli to świeży Nominatim),
        # więc kolejny call dla tej samej oferty (z numerem) i tak zrobi tylko 1 cache lookup
        # dla street_only — co jest bardzo szybkie.
        # 
        # Strategia: weź WSZYSTKIE warianty (oryginał, mianownik, liczba mnoga/poj.) i dla
        # każdego usuń ostatni token jeśli wygląda na numer domu. Próbuj każdy.
        # FIX P2b: dorzucamy też singular_fem_variants (np. "Nadbystrzycka 38")
        all_variant_sources = list(plural_variants) + list(singular_fem_variants)
        street_only_candidates = self._strip_number_variants(address, nominative, all_variant_sources)
        for street_only in street_only_candidates:
            # Cache hit (z koordynatami)?
            if street_only in self.cache and self.cache[street_only] is not None:
                coords = self.cache[street_only]
                print(f"      🎯 Fallback 'sama ulica': '{address}' → '{street_only}' (z cache)")
                self._stats_number_fallback_hits += 1
                meta['number_fallback'] = True
                return coords, meta
            
            # Cache None? Pomiń próbę Nominatim (już wiemy że nie znajdzie)
            if street_only in self.cache and self.cache[street_only] is None:
                continue
            
            # Spróbuj Nominatim z samą ulicą (wolimy trafienie w ULICĘ, nie w osiedle
            # czy sklep o tej nazwie — FIX 2026-08-18)
            print(f"      🎯 Fallback 'sama ulica': '{address}' → próbuję '{street_only}'")
            try:
                coords, _info = self._nominatim_lookup(
                    street_only, max_retries=max_retries,
                    require_house=False,
                    prefer_road=not self._ESTATE_PREFIX.match(street_only),
                )
            except (GeocoderTimedOut, GeocoderServiceError) as e:
                print(f"      ⏸️  Tymczasowy błąd Nominatim dla '{street_only}': {type(e).__name__}")
                meta['transient_error'] = True
                # Nie cache'ujemy None na tymczasowy błąd; idź do następnego wariantu
                continue
            
            if coords is not None:
                print(f"      ✅ Fallback znaleziony: {street_only}")
                # Cache POD KLUCZEM samej ulicy (żeby inne oferty z tej ulicy też trafiały).
                # NIE zapisujemy pod cache[address] - patrz komentarz wyżej.
                self.cache[street_only] = coords
                self._save_cache()
                self._stats_number_fallback_hits += 1
                meta['number_fallback'] = True
                return coords, meta
            else:
                # Cache None dla wariantu samej ulicy (np. literówka w nazwie)
                self.cache[street_only] = None
                self._save_cache()
        
        # FIX 2026-08-18: mamy punkt ULICY z któregoś wariantu, ale nie trafiliśmy
        # w numer domu — oddajemy go z number_fallback=True, żeby caller obniżył
        # precision do 'street_only' (kwadrat na mapie zamiast kropli "dokładny adres").
        # Świadomie NIE cache'ujemy pod kluczem z numerem — patrz komentarz przy KROKU 4.
        if street_level_coords is not None:
            print(f"      📌 '{address}': brak numeru w bazie OSM → punkt ulicy (street_only)")
            self._stats_number_fallback_hits += 1
            meta['number_fallback'] = True
            return street_level_coords, meta

        # Żaden wariant nie trafił w ulicę — bierzemy najlepsze, co było
        # (osiedle/park o tej nazwie). Zachowanie jak przed 2026-08-18.
        if weak_coords is not None:
            self.cache[address] = weak_coords
            self._save_cache()
            return weak_coords, meta

        # Wszystkie podejścia zawiodły (faktyczne None od Nominatim) - cache jako None
        self.cache[address] = None
        self._save_cache()
        return None, meta
    
    @staticmethod
    def _strip_number_variants(address: str, nominative: str, plural_variants: list) -> list:
        """
        Zwraca listę wariantów adresu BEZ numeru domu (dla fallbacku 'sama ulica').
        
        Filtruje:
        - duplikaty
        - warianty identyczne z oryginałem (numer nie był usuwany — brak fallbacku do zrobienia)
        - puste wyniki (gdy adres był jednowyrazowy)
        
        Args:
            address: oryginalny adres
            nominative: po transformacji do mianownika
            plural_variants: lista wariantów Aleja↔Aleje
        
        Returns:
            Lista unikalnych wariantów adresu bez numeru, np. ["Narutowicza", "Aleja Racławickie"]
        """
        all_variants = [address, nominative] + list(plural_variants)
        # Usuń duplikaty zachowując kolejność
        seen = set()
        unique_variants = []
        for v in all_variants:
            if v and v not in seen:
                seen.add(v)
                unique_variants.append(v)
        
        result = []
        # Wzorzec numeru domu: cyfry opcjonalnie + litera + opcjonalnie /N
        # Przykłady: "5", "10A", "80a", "12/5", "5A/11"
        number_pattern = re.compile(r'^\d+[a-zA-Z]?(?:/\d+)?$')
        
        for variant in unique_variants:
            tokens = variant.split()
            # Adres musi mieć min 2 tokeny żeby było co odciąć
            if len(tokens) < 2:
                continue
            # Ostatni token musi wyglądać na numer domu
            if not number_pattern.match(tokens[-1]):
                continue
            stripped = ' '.join(tokens[:-1])
            if stripped and stripped not in seen:
                seen.add(stripped)
                result.append(stripped)
        
        return result
    
    # === FIX 2026-08-18 (audyt markerów, klasy B i C) ===
    # Numer domu na końcu adresu ("Wileńska 15", "Głęboka 29/4", "Kraśnicka 73a").
    _HOUSE_NUMBER_TAIL = re.compile(r'\s\d+[a-zA-Z]?(?:/\d+[a-zA-Z]?)?$')
    # Numer z mieszkaniem — Nominatim nie zna takich numerów i oddaje punkt ulicy.
    _APARTMENT_PART = re.compile(r'(\s\d+[a-zA-Z]?)/\d+[a-zA-Z]?$')
    # Nazwy osiedli: dla nich wynik typu 'locality' jest POPRAWNY (osiedle Widok,
    # osiedle Chopina), więc nie forsujemy dopasowania do ulicy o tej samej nazwie.
    _ESTATE_PREFIX = re.compile(r'^\s*(?:osiedle|osiedlu|os\.|os\s)', re.IGNORECASE)

    @classmethod
    def _has_house_number(cls, address: str) -> bool:
        return bool(cls._HOUSE_NUMBER_TAIL.search((address or '').strip()))

    @classmethod
    def _strip_apartment(cls, address: str) -> Optional[str]:
        """'Głęboka 29/4' → 'Głęboka 29'. None gdy nie ma części mieszkaniowej."""
        stripped = cls._APARTMENT_PART.sub(r'\1', (address or '').strip())
        return stripped if stripped != (address or '').strip() else None

    @classmethod
    def _requested_number(cls, address: str) -> Optional[str]:
        """Numer domu z końca adresu, znormalizowany do porównania z OSM."""
        m = cls._HOUSE_NUMBER_TAIL.search((address or '').strip())
        return m.group(0).strip().lower().replace(' ', '') if m else None

    def _nominatim_lookup(self, address: str, max_retries: int = 3,
                          require_house: bool = False, prefer_road: bool = False):
        """
        Zapytanie do Nominatim ze świadomością TYPU wyniku.

        Nominatim odpowiada na każde zapytanie "coś sensownego", nawet gdy nie zna
        numeru domu ani ulicy — i to jest źródłem dwóch klas błędnych markerów
        wykrytych w audycie 2026-08-18:
          - "Wileńskiej 15" → 'Targ przy Wileńskiej' (landuse), a marker szedł na
            mapę jako precision=exact,
          - "Chopina" → 'Osiedle Chopina' (locality na Czechowie) zamiast
            ul. Fryderyka Chopina w centrum (2,5 km błędu).

        Args:
            require_house: adres MA numer domu — akceptuj tylko wynik z numerem
                (address.house_number). Wynik uliczny wraca jako 'street_level'.
            prefer_road: adres BEZ numeru — spośród wyników wybierz ulicę
                (class=highway), a nie osiedle/park/sklep o tej nazwie.

        Returns:
            (coords, info), gdzie info:
              - 'house': bool — wynik ma numer domu
              - 'street_level': bool — mamy koordynaty, ale bez żądanego numeru
                (caller powinien obniżyć precision do street_only)
              - 'road': bool — wynik to ulica (class=highway)
        """
        info = {'house': False, 'street_level': False, 'road': False, 'weak': False}
        results = self._nominatim_search(address, max_retries)
        if not results:
            return None, info

        wanted_number = self._requested_number(address) if require_house else None
        fallback = None  # pierwszy sensowny wynik, gdyby nie było lepszego
        for raw, coords in results:
            addr = raw.get('address') or {}
            house = (addr.get('house_number') or '').strip().lower().replace(' ', '')
            is_road = raw.get('class') == 'highway' or raw.get('addresstype') == 'road'
            # Numer musi się ZGADZAĆ. Nominatim na "Krańcowej 106" potrafi oddać
            # aptekę pod numerem 103 — z numerem domu, ale nie tym żądanym (219 m błędu).
            is_house = bool(house) and (wanted_number is None or house == wanted_number)

            if require_house and is_house:
                return coords, {'house': True, 'street_level': False, 'road': is_road, 'weak': False}
            if prefer_road and is_road and not require_house:
                return coords, {'house': False, 'street_level': False, 'road': True, 'weak': False}
            if fallback is None:
                fallback = (coords, is_house, is_road)

        if fallback is None:
            return None, info
        coords, is_house, is_road = fallback
        return coords, {
            'house': is_house,
            'street_level': bool(require_house and not is_house),
            # 'weak': chcieliśmy ULICĘ, a dostaliśmy osiedle/park/sklep o tej nazwie.
            # Caller zapamiętuje taki wynik, ale najpierw próbuje innych wariantów
            # ('Konopnickiej' → osiedle, ale mianownik 'Konopnicka' → prawdziwa ulica).
            'weak': bool(prefer_road and not is_road),
            'road': is_road,
        }

    def _nominatim_search(self, address: str, max_retries: int = 3):
        """Surowe wyniki z Nominatim (do 5), przefiltrowane po bbox Lublina.
        Zwraca listę (raw_dict, coords). Wyjątki jak w _try_nominatim."""
        full_address = f"{address}, Lublin, Poland"

        for attempt in range(max_retries):
            try:
                locations = self.geolocator.geocode(
                    full_address,
                    timeout=10,
                    language='pl',
                    addressdetails=True,
                    exactly_one=False,
                    limit=5,
                )
                out = []
                for loc in (locations or []):
                    coords = {'lat': loc.latitude, 'lon': loc.longitude}
                    if not self.is_in_lublin(coords):
                        continue
                    out.append((loc.raw, coords))
                if locations and not out:
                    print(f"      ⚠️ Odrzucono {address} - wszystkie wyniki poza Lublinem")
                return out

            except GeocoderTimedOut:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise

            except GeocoderServiceError as e:
                err_str = str(e).lower()
                is_rate_limit = (
                    '429' in err_str
                    or 'rate' in err_str
                    or 'quota' in err_str
                    or (GeocoderRateLimited is not None and isinstance(e, GeocoderRateLimited))
                )
                if is_rate_limit:
                    print(f"      ⏸️  Rate limit Nominatim dla '{address}' - nie cachuję None")
                raise
        return []

    def _try_nominatim(self, address: str, max_retries: int = 3) -> Optional[Dict[str, float]]:
        """
        Pojedyncza próba zapytania do Nominatim (bez logiki retry mianownikiem).
        Zwraca coords lub None. Cienka nakładka na _nominatim_lookup — dla wywołań,
        którym typ wyniku (ulica / budynek z numerem) jest obojętny.

        Raises:
            GeocoderRateLimited / GeocoderServiceError (429): tymczasowy błąd serwera,
                NIE zapisuj wyniku do cache - propagujemy żeby caller obsłużył.
        """
        coords, _info = self._nominatim_lookup(address, max_retries=max_retries)
        return coords

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
    # ===== FIX 2026-05-14: Testy _strip_number_variants =====
    print("🧪 FIX 2026-05-14 — _strip_number_variants:\n")
    strip_cases = [
        # (address, nominative, plural_variants, expected_result)
        ("Narutowicza 38", "Narutowicza 38", [], ["Narutowicza"]),
        ("Lipowej 10", "Lipowa 10", [], ["Lipowej", "Lipowa"]),
        ("Aleja Racławickie 6", "Aleja Racławickie 6", ["Aleje Racławickie 6"],
         ["Aleja Racławickie", "Aleje Racławickie"]),
        # Bez numeru — nic do odciąć
        ("Narutowicza", "Narutowicza", [], []),
        # Tylko jeden token + numer — zwróci ulicę (2 tokeny więc len(tokens)>=2)
        ("Centrum 5", "Centrum 5", [], ["Centrum"]),
        # Numer z literą
        ("Wojciechowska 5A", "Wojciechowska 5A", [], ["Wojciechowska"]),
        # Numer z lokalem
        ("Lipowa 14/2", "Lipowa 14/2", [], ["Lipowa"]),
        # Duplikaty
        ("Lipowa 10", "Lipowa 10", ["Lipowa 10"], ["Lipowa"]),
        # Pusty
        ("", "", [], []),
    ]
    strip_pass = 0
    strip_fail = 0
    for addr, nom, plurals, expected in strip_cases:
        actual = Geocoder._strip_number_variants(addr, nom, plurals)
        ok = actual == expected
        status = "✅" if ok else "❌"
        if ok:
            strip_pass += 1
        else:
            strip_fail += 1
        print(f"{status} ({addr!r}, {nom!r}, {plurals}) → {actual}")
        if not ok:
            print(f"   Oczekiwano: {expected}")
    print(f"\n📊 _strip_number_variants: {strip_pass} OK / {strip_fail} FAIL")

    # ===== FIX 2026-05-14: Testy fallbacku przez cache =====
    print("\n🧪 FIX 2026-05-14 — geocode_address z return_meta i fallback przez cache:\n")
    import tempfile, json as _json, os as _os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
        cache_data = {
            "Narutowicza": {"lat": 51.2458251, "lon": 22.5604385},  # ma koordy
            "Narutowicza 38": None,  # zatruty - tu fallback powinien zadziałać
            "Lipowa 14": {"lat": 51.2342, "lon": 22.5601},  # ma koordy, exact
        }
        _json.dump(cache_data, tf)
        cache_path = tf.name

    test_geo = Geocoder(cache_file=cache_path)
    
    fallback_test_cases = [
        # (address, expected_coords_obtained, expected_meta_subset)
        ("Lipowa 14", True, {"cache_hit": True, "number_fallback": False}),
        ("Narutowicza 38", True, {"cache_hit": False, "number_fallback": True}),
        ("Narutowicza", True, {"cache_hit": True, "number_fallback": False}),
    ]
    
    fb_pass = 0
    fb_fail = 0
    for addr, expected_has_coords, expected_meta in fallback_test_cases:
        coords, meta = test_geo.geocode_address(addr, return_meta=True)
        ok_coords = (coords is not None) == expected_has_coords
        ok_meta = all(meta.get(k) == v for k, v in expected_meta.items())
        ok = ok_coords and ok_meta
        status = "✅" if ok else "❌"
        if ok: fb_pass += 1
        else: fb_fail += 1
        print(f"{status} {addr!r} → coords_present={coords is not None}, meta={meta}")
        if not ok:
            print(f"   Oczekiwano: has_coords={expected_has_coords}, meta zawiera {expected_meta}")
    print(f"\n📊 Fallback meta: {fb_pass} OK / {fb_fail} FAIL")
    
    # Sprawdź czy fallback NIE zatruł cache pod kluczem oryginału
    print("\n🧪 Test: fallback NIE zapisuje koord pod oryginalnym kluczem:")
    if test_geo.cache.get('Narutowicza 38') is None:
        print("✅ cache[Narutowicza 38] = None (poprawnie - fallback nie zatruwa)")
        fb_pass += 1
    else:
        print(f"❌ cache[Narutowicza 38] = {test_geo.cache.get('Narutowicza 38')} (powinno być None)")
        fb_fail += 1
    
    # Sprawdź licznik fallbacków
    print("\n🧪 Test: licznik _stats_number_fallback_hits działa:")
    if test_geo._stats_number_fallback_hits >= 1:
        print(f"✅ _stats_number_fallback_hits = {test_geo._stats_number_fallback_hits}")
        fb_pass += 1
    else:
        print(f"❌ _stats_number_fallback_hits = {test_geo._stats_number_fallback_hits} (powinno być >= 1)")
        fb_fail += 1
    
    # Wsteczna kompatybilność: bez return_meta zachowuje stary kontrakt
    print("\n🧪 Test: wsteczna kompatybilność (bez return_meta):")
    coords_legacy = test_geo.geocode_address("Lipowa 14")
    if isinstance(coords_legacy, dict) and 'lat' in coords_legacy:
        print(f"✅ Bez return_meta zwraca samo coords dict: {coords_legacy}")
        fb_pass += 1
    else:
        print(f"❌ Bez return_meta zwraca: {coords_legacy}")
        fb_fail += 1
    
    _os.unlink(cache_path)

    # ===== FIX 2026-05-14 (P2b): Testy to_nominative_singular_feminine =====
    print("\n🧪 FIX 2026-05-14 (P2b) — to_nominative_singular_feminine:\n")
    fem_cases = [
        # Liczba mnoga dop. → liczba pojedyncza ż.
        ('Kraśnickich', 'Kraśnicka'),
        ('Aleja Kraśnickich', 'Aleja Kraśnicka'),
        ('Nadbystrzyckich', 'Nadbystrzycka'),
        ('Nałkowskich', 'Nałkowska'),
        ('Osiedle Nałkowskich', 'Osiedle Nałkowska'),
        # Liczba mnoga mianownik → liczba pojedyncza ż.
        ('Nadbystrzyckie', 'Nadbystrzycka'),
        ('Racławickie', 'Racławicka'),  # forma nie istniejąca, ale funkcja zwraca, Nominatim odrzuci
        # Brak transformacji = pusty string
        ('Lipowa', ''),
        ('Narutowicza', ''),
        ('Plac Litewski', ''),
        ('', ''),
        # Z numerem (numer powinien zostać)
        ('Kraśnickich 5', 'Kraśnicka 5'),
        ('Nadbystrzyckie 10A', 'Nadbystrzycka 10A'),
    ]
    fem_pass = 0
    fem_fail = 0
    for inp, expected in fem_cases:
        actual = to_nominative_singular_feminine(inp)
        ok = "✅" if actual == expected else "❌"
        if actual == expected: fem_pass += 1
        else: fem_fail += 1
        print(f"{ok} {inp!r} → {actual!r}")
        if actual != expected:
            print(f"   Oczekiwano: {expected!r}")
    print(f"\n📊 to_nominative_singular_feminine: {fem_pass} OK / {fem_fail} FAIL")

    # Test flow: cache-based fallback w geocode_address (bez Nominatim live)
    print("\n🧪 FIX 2026-05-14 (P2b) — fallback KROK 3.5 przez cache:\n")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
        cache_data_p2b = {
            "Kraśnicka": {"lat": 51.2426, "lon": 22.5068},
            "Nadbystrzycka": {"lat": 51.2331, "lon": 22.5397},
            "Aleja Kraśnickich": None,
            "Aleja Kraśnickie": None,
            "Aleje Kraśnickie": None,
            "Nadbystrzyckie": None,
        }
        _json.dump(cache_data_p2b, tf)
        cache_path_p2b = tf.name

    test_geo_p2b = Geocoder(cache_file=cache_path_p2b)
    
    p2b_cases = [
        # (address, expected_has_coords)
        ('Aleja Kraśnickich', True),   # przez Aleja Kraśnicka
        ('Nadbystrzyckie', True),       # przez Nadbystrzycka
    ]
    p2b_pass = 0
    p2b_fail = 0
    for addr, expected_has_coords in p2b_cases:
        coords = test_geo_p2b.geocode_address(addr)
        ok = (coords is not None) == expected_has_coords
        status = "✅" if ok else "❌"
        if ok: p2b_pass += 1
        else: p2b_fail += 1
        print(f"{status} {addr!r} → coords={coords}")
    print(f"\n📊 KROK 3.5 flow: {p2b_pass} OK / {p2b_fail} FAIL")
    
    _os.unlink(cache_path_p2b)

    print(f"\n{'='*60}")
    total_pass = strip_pass + fb_pass + fem_pass + p2b_pass
    total_fail = strip_fail + fb_fail + fem_fail + p2b_fail
    print(f"📊 ŁĄCZNIE Fix 2026-05-14 (geocoder): {total_pass} OK / {total_fail} FAIL")
    print(f"{'='*60}")

    # ===== Oryginalne testy (zakomentowane - wymagają Nominatim API live) =====
    # Te testy wykonują prawdziwe zapytania do Nominatim i tworzą test_geocoding_cache.json.
    # Uruchamiaj manualnie tylko przy potrzebie testów end-to-end.
    # 
    # geocoder = Geocoder(cache_file="test_geocoding_cache.json")
    # test_addresses = ["Narutowicza 5", "Racławickie 14", "Plac Litewski 1"]
    # for address in test_addresses:
    #     coords = geocoder.geocode_address(address)
    #     print(f"  {address} → {coords}")
