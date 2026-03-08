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
        'color': '#00c853'  # Jaskrawy zielony (świetna cena!)
    },
    'range_601_800': {
        'label': '601-800 zł',
        'min': 601,
        'max': 800,
        'color': '#76ff03'  # Limonkowy (dobra cena)
    },
    'range_801_1000': {
        'label': '801-1000 zł',
        'min': 801,
        'max': 1000,
        'color': '#ffc107'  # Żółty (średnia cena)
    },
    'range_1001_1300': {
        'label': '1001-1300 zł',
        'min': 1001,
        'max': 1300,
        'color': '#ff9800'  # Pomarańczowy (wysoka cena)
    },
    'range_1301_plus': {
        'label': '1301+ zł',
        'min': 1301,
        'max': 999999,
        'color': '#f44336'  # Jaskrawy czerwony (bardzo wysoka!)
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
    except (ValueError, AttributeError) as e:
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
    except (ValueError, AttributeError) as e:
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
        key = address_full
        
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
        
        offer_data = {
            'id': offer.get('id'),
            'url': offer.get('url'),
            'price': price_data.get('current', 0),
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
            'reactivated_at': format_datetime(offer.get('reactivated_at', '')) if offer.get('reactivated_at') else None
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
