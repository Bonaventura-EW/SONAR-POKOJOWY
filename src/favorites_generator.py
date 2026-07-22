#!/usr/bin/env python3
"""
Favorites Generator — data/favorites_tracking.json → docs/favorites_data.json
dla zakładki Ulubione (docs/ulubione.html).

Z surowych snapshotów wyprowadza per oferta:
- price_history (tylko zmiany ceny),
- refresh_events (zmiany last_refresh/pushup = odświeżenia/podbicia na OLX),
- views_history (pełna seria do wykresu wyświetleń),
- bieżący status + adres/współrzędne z data/offers.json (jeśli oferta jest w bazie).
"""

import json
from datetime import datetime

from profiles_config import TRACKED_PROFILES
from shared_utils import (DATA_DIR, DOCS_DIR, OFFERS_FILE, TZ,
                          format_datetime, write_json_atomic)

TRACKING_FILE = DATA_DIR / 'favorites_tracking.json'
OUTPUT_FILE = DOCS_DIR / 'favorites_data.json'

# nazwa profilu (jak w offers.json 'profile_name') → klucz zakładki w profile_tracker.html
PROFILE_KEY_BY_NAME = {cfg['name'].lower(): key for key, cfg in TRACKED_PROFILES.items()}


def _load_json(path, default):
    if not path.exists():
        return default
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _offers_by_short_id() -> dict:
    """Indeks ofert z bazy po krótkim ID ('...-ID1be1cg' → '1be1cg')."""
    data = _load_json(OFFERS_FILE, {})
    index = {}
    for offer in data.get('offers', []):
        oid = offer.get('id', '')
        if '-ID' in oid:
            index[oid.rsplit('-ID', 1)[-1]] = offer
    return index


def _build_favorite(short_id: str, entry: dict, base_offer: dict | None) -> dict:
    snapshots = entry.get('snapshots', [])

    price_history = []
    refresh_events = []
    views_history = []
    last_price = object()
    last_refresh_seen = None

    for snap in snapshots:
        ts = snap.get('ts', '')

        price = snap.get('price')
        if price is not None and price != last_price:
            price_history.append({'date': format_datetime(ts, '%d.%m.%Y'),
                                  'date_iso': ts, 'price': price})
            last_price = price

        refresh = snap.get('pushup') or snap.get('last_refresh') or ''
        if refresh and refresh != last_refresh_seen:
            if last_refresh_seen is not None:  # pierwsza wartość to stan startowy
                refresh_events.append({'date': format_datetime(refresh, '%d.%m.%Y %H:%M'),
                                       'date_iso': refresh})
            last_refresh_seen = refresh

        views = snap.get('views')
        if views is not None:
            views_history.append({'date': format_datetime(ts, '%d.%m %H:%M'),
                                  'date_iso': ts, 'views': views,
                                  'page': snap.get('page')})

    last = snapshots[-1] if snapshots else {}
    address = None
    coords = None
    profile_name = None
    if base_offer:
        addr = base_offer.get('address', {}) or {}
        address = addr.get('full') or None
        coords = addr.get('coords') or None
        profile_name = base_offer.get('profile_name') or None
    profile_key = PROFILE_KEY_BY_NAME.get(profile_name.lower()) if profile_name else None

    return {
        'short_id': short_id,
        'url': entry.get('url', ''),
        'title': entry.get('title', '') or (base_offer or {}).get('id', short_id),
        'added': entry.get('added', ''),
        'status': last.get('status', 'unknown'),
        'current_price': last.get('price'),
        'price_history': price_history,
        'refresh_count': len(refresh_events),
        'refresh_events': refresh_events,
        'views_history': views_history,
        'current_views': views_history[-1]['views'] if views_history else None,
        'current_page': next((s.get('page') for s in reversed(snapshots)
                              if s.get('page') is not None), None),
        'created': format_datetime(last.get('created', '')),
        'valid_to': format_datetime(last.get('valid_to', '')),
        'last_checked': format_datetime(last.get('ts', '')),
        'address': address,
        'coords': coords,
        'profile_name': profile_name,
        'profile_key': profile_key,
        'in_database': base_offer is not None,
        'snapshots_count': len(snapshots),
    }


def generate_favorites_data() -> bool:
    tracking = _load_json(TRACKING_FILE, {})
    offers_index = _offers_by_short_id()

    favorites = [
        _build_favorite(short_id, entry, offers_index.get(short_id))
        for short_id, entry in tracking.items()
    ]
    # najnowsze na górze
    favorites.sort(key=lambda f: f.get('added', ''), reverse=True)

    payload = {
        'generated': datetime.now(TZ).strftime('%d.%m.%Y %H:%M'),
        'count': len(favorites),
        'favorites': favorites,
    }
    write_json_atomic(OUTPUT_FILE, payload)
    print(f"✅ favorites_data.json wygenerowany: {OUTPUT_FILE} ({len(favorites)} ofert)")
    return True


if __name__ == '__main__':
    generate_favorites_data()
