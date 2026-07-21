#!/usr/bin/env python3
"""
Generator profile_data.json dla SONAR POKOJOWY
Generuje dane dla strony profile_tracker.html:
- per-profil lista ofert, historia cen, timeline pojawienia się
"""

import json
from datetime import datetime
from pathlib import Path
import pytz

from profiles_config import TRACKED_PROFILES
from shared_utils import write_json_atomic, format_datetime
from map_generator import PRICE_RANGES


def format_date_only(iso_string: str) -> str:
    """ISO datetime → 'DD.MM.YYYY'"""
    return format_datetime(iso_string, '%d.%m.%Y')


def _within_days(iso_string: str, now, tz, days: int = 2) -> bool:
    """Czy timestamp ISO mieści się w ostatnich `days` dniach względem now."""
    if not iso_string:
        return False
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = tz.localize(dt)
        else:
            dt = dt.astimezone(tz)
        seconds = (now - dt).total_seconds()
        # -3600 toleruje drobny skew zegara dla świeżych wpisów
        return -3600 <= seconds <= days * 86400
    except (ValueError, AttributeError):
        return False



KNOWN_NON_LUBLIN = [
    'warszawa', 'gdańsk', 'gdansk', 'kraków', 'krakow', 'wrocław', 'wroclaw',
    'poznań', 'poznan', 'szczecin', 'bydgoszcz', 'łódź', 'lodz', 'katowice',
    'gdynia', 'białystok', 'bialystok', 'rzeszów', 'rzeszow', 'toruń', 'torun',
    'olsztyn', 'pogórze', 'pogorze', 'trojmiasto', 'trójmiasto',
]

# Granice geograficzne Lublina
LUBLIN_LAT = (51.14, 51.32)
LUBLIN_LON = (22.40, 22.72)


def _resolve_city(offer: dict) -> str:
    """Zwraca miasto oferty — z pola city, adresu lub współrzędnych."""
    city = offer.get('city', '').strip()
    if city:
        return city

    # Próba z adresu (address to dict ze schematem {full, street, ...})
    addr_obj = offer.get('address', {}) or {}
    if isinstance(addr_obj, dict):
        addr_str = (addr_obj.get('full', '') or '').lower()
    else:
        addr_str = str(addr_obj).lower()
    for non_lublin in KNOWN_NON_LUBLIN:
        if non_lublin in addr_str:
            return addr_str.split(',')[-1].strip().title() or 'inne'

    # Próba ze współrzędnych (schemat: address.coords.lat/lon LUB lat/lon bezpośrednio)
    coords = addr_obj.get('coords', {}) or {}
    lat = coords.get('lat') or offer.get('lat')
    lon = coords.get('lon') or offer.get('lon')
    # Sprawdź też adres pełny jeśli coords nie pomoże
    full_addr = (addr_obj.get('full', '') or '').lower()
    for non_lublin in KNOWN_NON_LUBLIN:
        if non_lublin in full_addr:
            return full_addr.split(',')[-1].strip().title() or 'inne'
    if lat and lon:
        try:
            lat_f, lon_f = float(lat), float(lon)
            if LUBLIN_LAT[0] <= lat_f <= LUBLIN_LAT[1] and LUBLIN_LON[0] <= lon_f <= LUBLIN_LON[1]:
                return 'Lublin'
            else:
                return 'inne'
        except (ValueError, TypeError):
            pass

    return ''  # nieznane

def _format_price_history(history_full):
    """Lista {price,date,date_iso,approximated} z surowego history_full."""
    out = []
    for h in history_full or []:
        out.append({
            'price': h.get('price', 0),
            'date': format_datetime(h.get('date', '')),
            'date_iso': h.get('date', ''),
            'approximated': h.get('approximated', False),
        })
    return out


def _build_address_versions(offer, current_price_history):
    """Buduje listę wersji adresu do wyświetlenia (najnowsza/bieżąca pierwsza).
    Każda wersja ma własną historię cen, odświeżenia i reaktywacje."""
    past = offer.get('versions', [])
    if not past:
        return []  # brak zmian adresu — front nie pokazuje sekcji wersji

    address = offer.get('address', {}) or {}
    cur_coords = address.get('coords', {}) or {}
    versions = [{
        'address': address.get('full', ''),
        'lat': cur_coords.get('lat'),
        'lon': cur_coords.get('lon'),
        'current': True,
        'active': offer.get('active', False),
        'first_seen': format_datetime(offer.get('version_first_seen') or offer.get('first_seen', '')),
        'first_seen_iso': offer.get('version_first_seen') or offer.get('first_seen', ''),
        'last_seen': format_datetime(offer.get('last_seen', '')),
        'price_history': current_price_history,
        'refresh_count': offer.get('refresh_count', 0),
        'reactivation_count': offer.get('reactivation_count', 0),
    }]
    for v in reversed(past):  # najnowsze najpierw
        v_coords = (v.get('address', {}) or {}).get('coords', {}) or {}
        versions.append({
            'address': (v.get('address', {}) or {}).get('full', ''),
            'lat': v_coords.get('lat'),
            'lon': v_coords.get('lon'),
            'current': False,
            'active': False,
            'first_seen': format_datetime(v.get('first_seen', '')),
            'first_seen_iso': v.get('first_seen', ''),
            'last_seen': format_datetime(v.get('last_seen', '')),
            'price_history': _format_price_history(v.get('price_history', [])),
            'refresh_count': v.get('refresh_count', 0),
            'reactivation_count': v.get('reactivation_count', 0),
        })
    return versions


def generate_profile_data(input_file: str, output_file: str):
    """Główna funkcja generująca profile_data.json"""
    print("🔄 Generowanie profile_data.json...")

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    offers = data.get('offers', [])
    print(f"📥 Wczytano {len(offers)} ofert z offers.json")

    tz = pytz.timezone('Europe/Warsaw')
    now = datetime.now(tz)

    # Inicjalizuj struktury per-profil
    # Mapa: nazwa wyświetlana -> klucz profilu
    name_to_key = {cfg['name']: key for key, cfg in TRACKED_PROFILES.items()}

    profile_data = {}
    for key, cfg in TRACKED_PROFILES.items():
        profile_data[key] = {
            'key': key,
            'name': cfg['name'],
            'url': cfg['url'],
            'offers': [],
            'stats': {
                'total': 0,
                'active': 0,
                'inactive': 0,
                'avg_price': 0,
                'min_price': None,
                'max_price': None,
                'newest_date': None,
                'oldest_date': None,
                'recent_change': False,       # czy zmiana w ostatnich 2 dniach
                'recent_change_count': 0,     # ile ofert ze świeżą zmianą
            }
        }

    # Przydziel oferty do profili
    unassigned = 0
    for offer in offers:
        raw_profile = offer.get('profile_name')
        if not raw_profile:
            unassigned += 1
            continue
        # profile_name może być kluczem lub nazwą wyświetlaną
        if raw_profile in profile_data:
            profile_key = raw_profile
        elif raw_profile in name_to_key:
            profile_key = name_to_key[raw_profile]
        else:
            unassigned += 1
            continue

        price_data = offer.get('price', {})
        current_price = price_data.get('current', 0)
        address = offer.get('address', {})
        is_active = offer.get('active', False)

        # Pełna historia cen z datami
        history_full = price_data.get('history_full', [])
        if not history_full and price_data.get('history'):
            # Backfill: tylko pierwsze i ostatnie
            prices = price_data['history']
            history_full = [{'price': p, 'date': offer.get('first_seen', ''), 'approximated': False}
                            for p in prices[:1]]
            if len(prices) > 1:
                history_full.append({
                    'price': prices[-1],
                    'date': offer.get('last_seen', ''),
                    'approximated': False
                })

        # Formatuj historię cen
        price_history_formatted = []
        for h in history_full:
            price_history_formatted.append({
                'price': h.get('price', 0),
                'date': format_datetime(h.get('date', '')),
                'date_iso': h.get('date', ''),
                'approximated': h.get('approximated', False)
            })

        offer_entry = {
            'id': offer.get('id'),
            'url': offer.get('url'),
            'address': address.get('full', ''),
            'lat': address.get('coords', {}).get('lat'),
            'lon': address.get('coords', {}).get('lon'),
            'precision': address.get('precision', 'exact'),
            'price': current_price,
            'price_history': price_history_formatted,
            'previous_price': price_data.get('previous_price'),
            'price_trend': price_data.get('price_trend'),
            'media_info': price_data.get('media_info', ''),
            'first_seen': format_datetime(offer.get('first_seen', '')),
            'first_seen_iso': offer.get('first_seen', ''),
            'last_seen': format_datetime(offer.get('last_seen', '')),
            'last_seen_iso': offer.get('last_seen', ''),
            'days_active': offer.get('days_active', 0),
            'active': is_active,
            'is_new': False,  # obliczone poniżej
            'reactivated': offer.get('reactivated_at') is not None,
            'offer_type': offer.get('offer_type'),   # 'pokoj'/'mieszkanie'/'inne'
            'city': _resolve_city(offer),                # miasto ogłoszenia
            'refresh_count': offer.get('refresh_count', 0),
            'refresh_dates': offer.get('refresh_dates', []),
            'last_refresh_date': offer.get('last_refresh_date', ''),
            'reactivation_count': offer.get('reactivation_count', 0),
            # Daty reaktywacji (DD.MM.YYYY). Historycznie znamy tylko ostatnią,
            # więc len(dates) może być < reactivation_count → front pokazuje "+N wcześniej".
            'reactivation_dates': [
                format_datetime(d, fmt='%d.%m.%Y')
                for d in offer.get('reactivation_dates', [])
            ],
            # Wersje adresu (Faza 1): zmiany adresu tego samego listingu OLX
            'address_change_count': offer.get('address_change_count', 0),
            'address_changed_at': format_datetime(offer.get('address_changed_at', '')),
            'address_versions': _build_address_versions(offer, price_history_formatted),
        }

        # Czy nowa (first_seen dzisiaj)
        first_seen_str = offer.get('first_seen', '')
        if first_seen_str:
            try:
                first_dt = datetime.fromisoformat(first_seen_str.replace('Z', '+00:00'))
                if first_dt.tzinfo is None:
                    first_dt = tz.localize(first_dt)
                else:
                    first_dt = first_dt.astimezone(tz)
                offer_entry['is_new'] = (first_dt.date() == now.date())
            except (ValueError, AttributeError):
                pass

        profile_data[profile_key]['offers'].append(offer_entry)

        # Świeża zmiana (≤2 dni): nowa oferta / zmiana ceny / reaktywacja / dezaktywacja
        recent_change = False
        if _within_days(offer.get('first_seen', ''), now, tz):
            recent_change = True
        if not is_active and _within_days(offer.get('last_seen', ''), now, tz):
            recent_change = True
        if offer.get('reactivated_at') and _within_days(offer.get('reactivated_at'), now, tz):
            recent_change = True
        if not recent_change:
            for h in history_full[1:]:  # pomiń wpis startowy = sama cena początkowa
                if _within_days(h.get('date', ''), now, tz):
                    recent_change = True
                    break
        # Per-ofertę: ta flaga steruje badge'em "NOWE" przy konkretnym ogłoszeniu
        offer_entry['recent_change'] = recent_change
        if recent_change:
            profile_data[profile_key]['stats']['recent_change_count'] += 1

    # Oblicz statystyki per-profil
    for key, pdata in profile_data.items():
        poffers = pdata['offers']
        active_offers = [o for o in poffers if o['active']]
        inactive_offers = [o for o in poffers if not o['active']]

        prices = [o['price'] for o in active_offers if o['price']]

        pdata['stats']['total'] = len(poffers)
        pdata['stats']['active'] = len(active_offers)
        pdata['stats']['inactive'] = len(inactive_offers)
        pdata['stats']['recent_change'] = pdata['stats']['recent_change_count'] > 0

        if prices:
            pdata['stats']['avg_price'] = round(sum(prices) / len(prices))
            pdata['stats']['min_price'] = min(prices)
            pdata['stats']['max_price'] = max(prices)

        # Daty pojawienia się ofert
        dates = [o['first_seen_iso'] for o in poffers if o['first_seen_iso']]
        if dates:
            pdata['stats']['newest_date'] = format_date_only(max(dates))
            pdata['stats']['oldest_date'] = format_date_only(min(dates))

        # Aktywne najpierw (najnowsze wg first_seen), potem archiwalne.
        # Archiwalne sortujemy po last_seen malejąco: ta, która zniknęła
        # jako ostatnia, jest na górze (zgłoszenie Mateusza).
        active_sorted = sorted([o for o in poffers if o['active']],
                               key=lambda o: o.get('first_seen_iso', ''), reverse=True)
        inactive_sorted = sorted([o for o in poffers if not o['active']],
                                 key=lambda o: o.get('last_seen_iso', '') or '', reverse=True)
        pdata['offers'] = active_sorted + inactive_sorted

    total_firm = sum(p['stats']['total'] for p in profile_data.values())
    total_active = sum(p['stats']['active'] for p in profile_data.values())
    print(f"📊 Profili: {len(profile_data)}, ofert firmowych: {total_firm} "
          f"({total_active} aktywnych)")
    print(f"   Bez profilu: {unassigned} ofert")

    # Timeline: zebranie dat pojawienia się wszystkich ofert firmowych
    # Używane do wykresu aktywności na stronie
    timeline_map: dict = {}  # date_str → {profile_key: count}
    for key, pdata in profile_data.items():
        for o in pdata['offers']:
            date_str = format_date_only(o.get('first_seen_iso', ''))
            if not date_str:
                continue
            if date_str not in timeline_map:
                timeline_map[date_str] = {}
            timeline_map[date_str][key] = timeline_map[date_str].get(key, 0) + 1

    timeline = [
        {'date': d, 'counts': counts}
        for d, counts in sorted(timeline_map.items())
    ]

    output = {
        'generated_at': now.isoformat(),
        'profiles': profile_data,
        'timeline': timeline,
        'profile_keys': list(TRACKED_PROFILES.keys()),
        'price_ranges': PRICE_RANGES,
        'scan_info': {
            'last': data.get('last_scan', ''),
            'next': data.get('next_scan', '')
        }
    }

    out_path = Path(output_file)
    write_json_atomic(out_path, output)

    print(f"✅ Zapisano profile_data.json ({out_path})")


if __name__ == '__main__':
    generate_profile_data(
        input_file='../data/offers.json',
        output_file='../docs/profile_data.json'
    )
