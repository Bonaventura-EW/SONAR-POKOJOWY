#!/usr/bin/env python3
"""
Generator map_data.json dla SONAR POKOJOWY
Przekształca data.json → map_data.json z formatem wymaganym przez frontend
"""

import json
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# Definicja zakresów cenowych (zgodnie z frontend)
PRICE_RANGES = {
    'range_0_600': {
        'label': '0-600 zł',
        'min': 0,
        'max': 600,
        'color': '#28a745'  # Zielony
    },
    'range_601_800': {
        'label': '601-800 zł',
        'min': 601,
        'max': 800,
        'color': '#5cb85c'  # Jasnozielony
    },
    'range_801_1000': {
        'label': '801-1000 zł',
        'min': 801,
        'max': 1000,
        'color': '#ffc107'  # Żółty
    },
    'range_1001_1300': {
        'label': '1001-1300 zł',
        'min': 1001,
        'max': 1300,
        'color': '#ff9800'  # Pomarańczowy
    },
    'range_1301_plus': {
        'label': '1301+ zł',
        'min': 1301,
        'max': 999999,
        'color': '#dc3545'  # Czerwony
    }
}

def get_price_range(price):
    """Przypisz cenę do zakresu"""
    for key, range_info in PRICE_RANGES.items():
        if range_info['min'] <= price <= range_info['max']:
            return key
    return 'range_1301_plus'  # Fallback


def format_datetime(iso_string):
    """
    Konwertuj ISO datetime → format frontend 'DD.MM.RRRR HH:MM'
    Input: '2026-03-01T15:51:38.344630+01:00'
    Output: '01.03.2026 15:51'
    """
    try:
        # Parse ISO format (obsługa timezone)
        if '+' in iso_string:
            dt_str = iso_string.split('+')[0]  # Usuń timezone
        elif 'Z' in iso_string:
            dt_str = iso_string.replace('Z', '')
        else:
            dt_str = iso_string
        
        # Parse datetime
        if '.' in dt_str:
            dt = datetime.fromisoformat(dt_str)
        else:
            dt = datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%S')
        
        # Format do DD.MM.YYYY HH:MM
        return dt.strftime('%d.%m.%Y %H:%M')
    except Exception as e:
        print(f"⚠️  Błąd parsowania daty '{iso_string}': {e}")
        return iso_string


def format_scan_datetime(iso_string):
    """
    Format dla scan info (z sekundami)
    Output: 'DD.MM.YYYY HH:MM:SS'
    """
    try:
        if '+' in iso_string:
            dt_str = iso_string.split('+')[0]
        elif 'Z' in iso_string:
            dt_str = iso_string.replace('Z', '')
        else:
            dt_str = iso_string
        
        if '.' in dt_str:
            dt = datetime.fromisoformat(dt_str)
        else:
            dt = datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%S')
        
        return dt.strftime('%d.%m.%Y %H:%M:%S')
    except Exception as e:
        print(f"⚠️  Błąd parsowania daty skanu '{iso_string}': {e}")
        return iso_string


def generate_map_data(input_file, output_file):
    """Główna funkcja generująca map_data.json"""
    
    print("🔄 Generowanie map_data.json...")
    
    # 1. Wczytaj data.json
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    offers = data.get('offers', [])
    print(f"📥 Wczytano {len(offers)} ofert z data.json")
    
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
        key = address_full
        
        # Przygotuj ofertę do frontendu
        offer_data = {
            'id': offer.get('id'),
            'url': offer.get('url'),
            'price': offer.get('price', {}).get('current', 0),
            'first_seen': format_datetime(offer.get('first_seen', '')),
            'last_seen': format_datetime(offer.get('last_seen', '')),
            'active': offer.get('active', True),
            'is_new': offer.get('days_active', 0) == 0,  # Nowa jeśli days_active = 0
            'description': offer.get('description', '')[:200]  # Skróć opis
        }
        
        markers_dict[key].append({
            'coords': coords,
            'address': address_full,
            'offer': offer_data
        })
    
    print(f"📍 Pogrupowano na {len(markers_dict)} unikalnych adresów")
    
    # 3. Stwórz listę markerów
    markers = []
    
    for address, items in markers_dict.items():
        # Weź współrzędne z pierwszej oferty
        coords = items[0]['coords']
        
        # Zbierz wszystkie oferty dla tego adresu
        offers_list = [item['offer'] for item in items]
        
        # Oblicz cenę średnią dla aktywnych ofert
        active_offers = [o for o in offers_list if o['active']]
        if active_offers:
            avg_price = sum(o['price'] for o in active_offers) / len(active_offers)
            price_range = get_price_range(avg_price)
            has_active = True
        else:
            # Jeśli brak aktywnych, użyj pierwszej nieaktywnej
            avg_price = offers_list[0]['price']
            price_range = get_price_range(avg_price)
            has_active = False
        
        markers.append({
            'coords': coords,
            'address': address,
            'offers': offers_list,
            'price_range': price_range,
            'has_active': has_active
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
        'price_ranges': PRICE_RANGES
    }
    
    # 7. Zapisz do pliku
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(map_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Zapisano map_data.json ({len(markers)} markerów, {stats['active_count']} aktywnych ofert)")
    print(f"   Ostatni scan: {scan_info['last']}")
    print(f"   Następny scan: {scan_info['next']}")


if __name__ == '__main__':
    # Ścieżki plików
    base_dir = Path(__file__).parent.parent
    input_file = base_dir / 'data' / 'offers.json'
    output_file = base_dir / 'docs' / 'data.json'
    
    # Sprawdź czy plik wejściowy istnieje
    if not input_file.exists():
        print(f"❌ Plik {input_file} nie istnieje!")
        exit(1)
    
    # Generuj
    generate_map_data(input_file, output_file)
    
    # Wygeneruj także dane monitoringu
    print("\n📊 Generowanie danych monitoringu...")
    from monitoring_generator import generate_monitoring_data
    generate_monitoring_data()
