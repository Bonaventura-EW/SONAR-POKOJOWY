#!/usr/bin/env python3
"""
Generator map_data.json dla SONAR POKOJOWY
Przekształca data.json → map_data.json z formatem wymaganym przez frontend
"""

import json
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# Import taggera ofert (B1)
from offer_tagger import tag_offer, TAGS as OFFER_TAGS
from shared_utils import write_json_atomic, format_datetime
from profiles_config import TRACKED_PROFILES, FIRM_BORDER_COLOR, FIRM_BORDER_WIDTH

# Definicja zakresów cenowych - 22 przedziały.
# Gradient zielony → ciemny fiolet rozciągnięty na 0-3000 zł (interpolacja RGB
# z 12 historycznych anchorów), powyżej 3000 zł jeden kolor: czarny.
# Kroki: 0-500, potem co 100 zł do 2000, potem co 200 zł do 3000.
PRICE_RANGES = {
    'range_0_500': {
        'label': '0-500 zł',
        'min': 0,
        'max': 500,
        'color': '#00c853'  # Zielony
    },
    'range_501_600': {
        'label': '501-600 zł',
        'min': 501,
        'max': 600,
        'color': '#37d432'
    },
    'range_601_700': {
        'label': '601-700 zł',
        'min': 601,
        'max': 700,
        'color': '#6bde15'
    },
    'range_701_800': {
        'label': '701-800 zł',
        'min': 701,
        'max': 800,
        'color': '#94e508'
    },
    'range_801_900': {
        'label': '801-900 zł',
        'min': 801,
        'max': 900,
        'color': '#bee600'
    },
    'range_901_1000': {
        'label': '901-1000 zł',
        'min': 901,
        'max': 1000,
        'color': '#ebdb00'  # Żółty
    },
    'range_1001_1100': {
        'label': '1001-1100 zł',
        'min': 1001,
        'max': 1100,
        'color': '#ffc900'
    },
    'range_1101_1200': {
        'label': '1101-1200 zł',
        'min': 1101,
        'max': 1200,
        'color': '#ffb100'
    },
    'range_1201_1300': {
        'label': '1201-1300 zł',
        'min': 1201,
        'max': 1300,
        'color': '#ff9300'
    },
    'range_1301_1400': {
        'label': '1301-1400 zł',
        'min': 1301,
        'max': 1400,
        'color': '#ff7200'  # Pomarańczowy
    },
    'range_1401_1500': {
        'label': '1401-1500 zł',
        'min': 1401,
        'max': 1500,
        'color': '#ff5600'
    },
    'range_1501_1600': {
        'label': '1501-1600 zł',
        'min': 1501,
        'max': 1600,
        'color': '#fd3a00'
    },
    'range_1601_1700': {
        'label': '1601-1700 zł',
        'min': 1601,
        'max': 1700,
        'color': '#e61800'  # Czerwony
    },
    'range_1701_1800': {
        'label': '1701-1800 zł',
        'min': 1701,
        'max': 1800,
        'color': '#d3030f'
    },
    'range_1801_1900': {
        'label': '1801-1900 zł',
        'min': 1801,
        'max': 1900,
        'color': '#ca0c45'
    },
    'range_1901_2000': {
        'label': '1901-2000 zł',
        'min': 1901,
        'max': 2000,
        'color': '#be0d89'  # Różowy
    },
    'range_2001_2200': {
        'label': '2001-2200 zł',
        'min': 2001,
        'max': 2200,
        'color': '#af03e0'
    },
    'range_2201_2400': {
        'label': '2201-2400 zł',
        'min': 2201,
        'max': 2400,
        'color': '#9a1bff'  # Fioletowy
    },
    'range_2401_2600': {
        'label': '2401-2600 zł',
        'min': 2401,
        'max': 2600,
        'color': '#8145ff'
    },
    'range_2601_2800': {
        'label': '2601-2800 zł',
        'min': 2601,
        'max': 2800,
        'color': '#702af6'
    },
    'range_2801_3000': {
        'label': '2801-3000 zł',
        'min': 2801,
        'max': 3000,
        'color': '#6200ea'  # Fioletowy ciemny
    },
    'range_3001_plus': {
        'label': '3001+ zł',
        'min': 3001,
        'max': 999999,
        'color': '#000000'  # Czarny
    }
}

def get_price_range(price):
    """Przypisz cenę do zakresu"""
    for key, range_info in PRICE_RANGES.items():
        if range_info['min'] <= price <= range_info['max']:
            return key
    return 'range_3001_plus'  # Fallback (musi być ostatnim kluczem PRICE_RANGES)


def format_scan_datetime(iso_string):
    """Format dla scan info (z sekundami): 'DD.MM.YYYY HH:MM:SS'"""
    return format_datetime(iso_string, '%d.%m.%Y %H:%M:%S')

def _build_addr_versions(offer):
    """Wersje adresu do popupu/pinów głównej mapy (najnowsza/bieżąca pierwsza).
    Każda wersja: adres, współrzędne, zakres dat, ceny, odświeżenia, reaktywacje."""
    past = offer.get('versions', [])
    if not past:
        return []
    addr = offer.get('address', {}) or {}
    c = addr.get('coords', {}) or {}
    price = offer.get('price', {}) or {}
    cur_prices = [h.get('price') for h in (price.get('history_full') or [])] or price.get('history', [])
    out = [{
        'address': addr.get('full', ''),
        'lat': c.get('lat'), 'lon': c.get('lon'),
        'current': True,
        'active': offer.get('active', False),
        'first_seen': format_datetime(offer.get('version_first_seen') or offer.get('first_seen', '')),
        'last_seen': format_datetime(offer.get('last_seen', '')),
        'prices': cur_prices,
        'refresh_count': offer.get('refresh_count', 0),
        'reactivation_count': offer.get('reactivation_count', 0),
    }]
    for v in reversed(past):
        vc = (v.get('address', {}) or {}).get('coords', {}) or {}
        out.append({
            'address': (v.get('address', {}) or {}).get('full', ''),
            'lat': vc.get('lat'), 'lon': vc.get('lon'),
            'current': False,
            'active': False,
            'first_seen': format_datetime(v.get('first_seen', '')),
            'last_seen': format_datetime(v.get('last_seen', '')),
            'prices': [h.get('price') for h in (v.get('price_history') or [])],
            'refresh_count': v.get('refresh_count', 0),
            'reactivation_count': v.get('reactivation_count', 0),
        })
    return out


def generate_map_data(input_file, output_file):
    """Główna funkcja generująca map_data.json"""
    
    print("🔄 Generowanie map_data.json...")
    
    # 1. Wczytaj data.json
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    offers = data.get('offers', [])
    print(f"📥 Wczytano {len(offers)} ofert z data.json")
    
    # Pobierz aktualną datę w strefie czasowej polskiej
    from datetime import datetime
    import pytz
    tz = pytz.timezone('Europe/Warsaw')
    now = datetime.now(tz)
    today_date = now.date()  # Tylko data (bez godziny)
    
    # 2. Grupuj oferty według adresów
    markers_dict = defaultdict(list)
    
    for offer in offers:
        address_full = offer.get('address', {}).get('full', 'Nieznany adres')
        coords = offer.get('address', {}).get('coords', {})
        
        # Sprawdź czy są współrzędne
        if not coords.get('lat') or not coords.get('lon'):
            print(f"⚠️  Brak współrzędnych dla oferty {offer.get('id')}, pomijam")
            continue
        
        # Klucz grupowania: pełen adres
        # Klucz grupowania: WSPÓŁRZĘDNE (zaokrąglone do 6 miejsc) + adres jako fallback
        # Używamy coords jako primary key żeby uniknąć problemów z fleksją (Organowa vs Organowej)
        # 6 miejsc po przecinku ≈ precyzja 0.1m - bezpieczne dla tego samego budynku
        lat_r = round(coords['lat'], 6)
        lon_r = round(coords['lon'], 6)
        key = (lat_r, lon_r)
        
        # Przygotuj ofertę do frontendu
        price_data = offer.get('price', {})
        
        # Oblicz czy oferta jest nowa (first_seen dzisiaj)
        first_seen_str = offer.get('first_seen', '')
        is_new = False
        if first_seen_str:
            try:
                # Parse ISO datetime
                first_seen_dt = datetime.fromisoformat(first_seen_str.replace('Z', '+00:00'))
                # Konwertuj na polską strefę czasową
                if first_seen_dt.tzinfo is None:
                    first_seen_dt = tz.localize(first_seen_dt)
                else:
                    first_seen_dt = first_seen_dt.astimezone(tz)
                
                first_seen_date = first_seen_dt.date()
                is_new = (first_seen_date == today_date)  # Porównaj tylko daty
            except (ValueError, AttributeError) as e:
                print(f"⚠️  Błąd parsowania first_seen dla {offer.get('id')}: {e}")
                is_new = False
        
        # Pobierz cenę i oblicz price_range dla tej konkretnej oferty
        current_price = price_data.get('current', 0)
        offer_price_range = get_price_range(current_price)
        
        # B1: Tagowanie oferty (kawalerka/pokój/mieszkanie)
        description_text = offer.get('description', '')
        # Wyciągnij tytuł z URL (pierwsza część przed CID)
        url = offer.get('url', '')
        title_from_url = url.split('/')[-1].split('.')[0].replace('-', ' ') if url else ''
        
        tag_result = tag_offer(title_from_url, description_text)
        
        offer_data = {
            'id': offer.get('id'),
            'url': offer.get('url'),
            'price': current_price,
            'price_range': offer_price_range,  # ✅ Zakres cenowy dla tej konkretnej oferty
            'price_history': price_data.get('history', []),  # Historia cen
            'previous_price': price_data.get('previous_price'),  # Poprzednia cena (jeśli się zmieniła)
            'price_trend': price_data.get('price_trend'),  # 'up' lub 'down'
            'price_changed_at': format_datetime(price_data.get('price_changed_at', '')) if price_data.get('price_changed_at') else None,
            'media_info': price_data.get('media_info', 'brak informacji'),  # Info o mediach
            'first_seen': format_datetime(offer.get('first_seen', '')),
            'last_seen': format_datetime(offer.get('last_seen', '')),
            'days_active': offer.get('days_active', 0),  # Dni aktywności
            'active': offer.get('active', True),
            'is_new': is_new,  # ✅ Obliczone na podstawie daty
            'description': offer.get('description', ''),  # Pełny opis (frontend się sam obcina)
            'reactivated': offer.get('reactivated_at') is not None,  # Czy była reaktywowana
            'reactivated_at': format_datetime(offer.get('reactivated_at', '')) if offer.get('reactivated_at') else None,
            # Precyzja adresu: 'exact' (z numerem) lub 'street_only' (środek ulicy)
            'precision': offer.get('address', {}).get('precision', 'exact'),
            # B1: Tagi oferty
            'tags': {
                'primary': tag_result['primary'],
                'secondary': tag_result['secondary'],
                'all': tag_result['all_tags'],
                'confidence': tag_result['confidence']
            },
            # Profil firmowy
            'profile_name': offer.get('profile_name'),
            'is_firm_offer': bool(offer.get('profile_name')),
            'offer_type': offer.get('offer_type'),  # 'pokoj'/'mieszkanie'/'inne'/None
            'city': offer.get('city', ''),
            # Wersje adresu (zmiany adresu tego samego listingu OLX)
            'address_change_count': offer.get('address_change_count', 0),
            'address_changed_at': format_datetime(offer.get('address_changed_at', '')) if offer.get('address_changed_at') else None,
            'address_versions': _build_addr_versions(offer),
        }
        
        markers_dict[key].append({
            'coords': coords,
            'address': address_full,
            'offer': offer_data
        })
    
    print(f"📍 Pogrupowano na {len(markers_dict)} unikalnych adresów")
    
    # 3. Stwórz listę markerów
    markers = []
    
    for key, items in markers_dict.items():
        # Weź współrzędne z pierwszej oferty
        coords = items[0]['coords']
        # Wybierz adres z mianowniku (unikamy fleksji: Organowa vs Organowej)
        all_addresses = [item['address'] for item in items if item.get('address')]
        address = min(all_addresses, key=len) if all_addresses else 'Nieznany adres'

        # Zbierz wszystkie oferty dla tego adresu
        offers_list = [item['offer'] for item in items]

        # Sprawdź czy są aktywne oferty
        has_active = any(o['active'] for o in offers_list)

        # Flagi dla nowych warstw przybliżonych (precision == 'street_only' lub 'district')
        # FIX 2026-05-26 (A): precision='district' (centroidy dzielnic) też trafia
        # do warstwy "przybliżone" — markery są w środku dzielnicy zamiast pomijać oferty.
        APPROX_PRECISIONS = ('street_only', 'district')
        has_active_approx = any(
            o['active'] and o.get('precision') in APPROX_PRECISIONS for o in offers_list
        )
        has_inactive_approx = any(
            (not o['active']) and o.get('precision') in APPROX_PRECISIONS for o in offers_list
        )

        LUBLIN_VARIANTS = {'lublin', 'Lublin'}
        has_firm_offers = any(
            o.get('is_firm_offer') and o['active']
            and o.get('offer_type') in ('pokoj', 'mieszkanie')
            and (not o.get('city') or o.get('city') in LUBLIN_VARIANTS)
            for o in offers_list
        )

        markers.append({
            'coords': coords,
            'address': address,
            'offers': offers_list,
            'has_active': has_active,
            'has_active_approx': has_active_approx,
            'has_inactive_approx': has_inactive_approx,
            'has_firm_offers': has_firm_offers
        })
    
    # 4. Oblicz statystyki (tylko dla aktywnych ofert)
    active_offers_all = [o for marker in markers for o in marker['offers'] if o['active']]
    
    if active_offers_all:
        prices = [o['price'] for o in active_offers_all]
        stats = {
            'active_count': len(active_offers_all),
            'avg_price': round(sum(prices) / len(prices)),
            'min_price': min(prices),
            'max_price': max(prices)
        }
    else:
        stats = {
            'active_count': 0,
            'avg_price': 0,
            'min_price': 0,
            'max_price': 0
        }
    
    print(f"📊 Statystyki: {stats['active_count']} aktywnych, średnia {stats['avg_price']} zł")
    
    # 5. Formatuj informacje o skanach
    scan_info = {
        'last': format_scan_datetime(data.get('last_scan', '')),
        'next': format_scan_datetime(data.get('next_scan', ''))
    }
    
    # 6. Stwórz finalny plik map_data.json
    map_data = {
        'markers': markers,
        'stats': stats,
        'scan_info': scan_info,
        'price_ranges': PRICE_RANGES,
        'offer_tags': OFFER_TAGS,  # B1: Definicje tagów dla frontendu
        'tracked_profiles': {k: {'name': v['name'], 'url': v['url']}
                             for k, v in TRACKED_PROFILES.items()},
        'firm_style': {
            'border_color': FIRM_BORDER_COLOR,
            'border_width': FIRM_BORDER_WIDTH
        }
    }
    
    # 7. Zapisz do pliku (atomowo)
    write_json_atomic(output_file, map_data)
    
    print(f"✅ Zapisano map_data.json ({len(markers)} markerów, {stats['active_count']} aktywnych ofert)")
    print(f"   Ostatni scan: {scan_info['last']}")
    print(f"   Następny scan: {scan_info['next']}")


def regenerate_all_derived(base_dir: Path = None) -> bool:
    """
    Regeneruje WSZYSTKIE pliki pochodne z data/offers.json:
    - docs/data.json (mapa)
    - docs/monitoring_data.json (monitoring)
    - docs/profile_data.json (profile firmowe)
    - docs/skipped_debug.html (debug pominiętych)
    
    Wywoływana z __main__ tego skryptu (workflow GitHub Actions),
    a także dostępna dla importerów którzy chcą regenerować pełen
    zestaw derived po zmianie offers.json (np. skrypty czyszczące,
    migracje, narzędzia diagnostyczne).
    
    Returns:
        True jeśli wszystkie podstawowe generatory się udały
        (monitoring/profile/skipped są opcjonalne - błędy nie failują)
    """
    if base_dir is None:
        base_dir = Path(__file__).parent.parent
    
    input_file = base_dir / 'data' / 'offers.json'
    output_file = base_dir / 'docs' / 'data.json'
    
    if not input_file.exists():
        print(f"❌ Plik {input_file} nie istnieje!")
        return False
    
    # 1. Główna mapa (krytyczne - musi się udać)
    generate_map_data(input_file, output_file)
    
    # 2. Monitoring (krytyczne dla strony monitoring.html)
    print("\n📊 Generowanie danych monitoringu...")
    try:
        from monitoring_generator import generate_monitoring_data
        generate_monitoring_data()
    except Exception as e:
        print(f"⚠️  monitoring_generator nie powiódł się: {e}")
    
    # 3. Profile firmowe (opcjonalne - strona profile_tracker)
    print("\n🏢 Generowanie danych profili firmowych...")
    try:
        from profile_generator import generate_profile_data
        generate_profile_data(
            input_file=str(base_dir / 'data' / 'offers.json'),
            output_file=str(base_dir / 'docs' / 'profile_data.json')
        )
    except Exception as e:
        print(f"⚠️  profile_generator nie powiódł się: {e}")
    
    # 4. Debug skipped (opcjonalne)
    print("\n🐛 Generowanie strony debug pominiętych ofert...")
    try:
        from skipped_debug_generator import generate_skipped_debug_page
        generate_skipped_debug_page()
    except Exception as e:
        print(f"⚠️  skipped_debug_generator nie powiódł się: {e}")
    
    return True


if __name__ == '__main__':
    # Workflow GitHub Actions wywołuje: python map_generator.py
    # Funkcjonalność identyczna jak wcześniej - regeneracja wszystkich derived
    regenerate_all_derived()
