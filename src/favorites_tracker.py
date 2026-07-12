#!/usr/bin/env python3
"""
Favorites Tracker — śledzenie pojedynczych ofert dodanych do ulubionych.

Lista ulubionych: data/favorites.json (dopisywana ręcznie/przez Claude'a).
Każdy przebieg dokłada snapshot per oferta do data/favorites_tracking.json:
cena, status, last_refresh_time (z OLX API v1, anonimowo — 1 request/oferta)
oraz licznik wyświetleń (opcjonalnie, headless Chromium przez Playwright —
licznik "Wyświetlenia: N" jest doładowywany przez JS za tokenem, więc
zwykły request go nie widzi). Brak Playwrighta / błąd przeglądarki NIE
przerywa trackera — snapshot zapisuje się z views=None.

Po snapshotach odpala favorites_generator (docs/favorites_data.json).

Uruchamianie: python favorites_tracker.py (z src/ lub roota).
"""

import json
import re
import sys
from datetime import datetime

import requests

from shared_utils import DATA_DIR, TZ, write_json_atomic

FAVORITES_FILE = DATA_DIR / 'favorites.json'
TRACKING_FILE = DATA_DIR / 'favorites_tracking.json'

API_URL = 'https://www.olx.pl/api/v1/offers/{numeric_id}/'
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'),
    'Accept': 'application/json',
}
REQUEST_TIMEOUT = 20
VIEWS_PATTERN = re.compile(r'Wyświetlenia:\s*([\d\s ]+)')


def load_favorites() -> list:
    if not FAVORITES_FILE.exists():
        return []
    with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f).get('favorites', [])


def load_tracking() -> dict:
    if not TRACKING_FILE.exists():
        return {}
    with open(TRACKING_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def resolve_numeric_id(url: str) -> int | None:
    """Numeryczne ID oferty z window.__PRERENDERED_STATE__ strony OLX.
    Potrzebne raz — wynik zapisywany z powrotem do favorites.json."""
    try:
        resp = requests.get(url, headers={'User-Agent': HEADERS['User-Agent']},
                            timeout=REQUEST_TIMEOUT)
        m = re.search(r'"sku":\s*"?(\d{6,})', resp.text)
        if m:
            return int(m.group(1))
        m = re.search(r'\\"id\\":(\d{6,}),\\"title\\"', resp.text)
        if m:
            return int(m.group(1))
    except requests.RequestException as e:
        print(f"   ⚠️ Nie udało się pobrać strony {url}: {e}")
    return None


def fetch_api_snapshot(numeric_id: int) -> dict | None:
    """Snapshot z OLX API v1 (anonimowe). None = błąd sieci (nie zapisuj),
    {'status': 'removed'} = oferta usunięta z OLX (404)."""
    try:
        resp = requests.get(API_URL.format(numeric_id=numeric_id),
                            headers=HEADERS, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        print(f"   ⚠️ Błąd API dla {numeric_id}: {e}")
        return None

    if resp.status_code == 404:
        return {'status': 'removed'}
    if resp.status_code != 200:
        print(f"   ⚠️ API {numeric_id}: HTTP {resp.status_code}")
        return None

    d = resp.json().get('data', {})
    price = None
    for p in d.get('params', []):
        if p.get('key') == 'price':
            price = (p.get('value') or {}).get('value')
            break

    return {
        'status': d.get('status', ''),
        'price': price,
        'title': d.get('title', ''),
        'last_refresh': d.get('last_refresh_time') or '',
        'pushup': d.get('pushup_time') or '',
        'created': d.get('created_time') or '',
        'valid_to': d.get('valid_to_time') or '',
    }


def fetch_views(favorites: list) -> dict:
    """Licznik wyświetleń per short_id przez headless Chromium.
    Zwraca {} gdy Playwright niedostępny albo przeglądarka padnie."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("   ℹ️ Playwright niedostępny — pomijam wyświetlenia.")
        return {}

    views = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            context = browser.new_context(user_agent=HEADERS['User-Agent'])
            page = context.new_page()
            for fav in favorites:
                try:
                    page.goto(fav['url'], wait_until='domcontentloaded',
                              timeout=45000)
                    page.wait_for_timeout(2500)
                    # licznik jest lazy-loaded na dole strony
                    page.mouse.wheel(0, 30000)
                    page.wait_for_timeout(4000)
                    body = page.evaluate('document.body.innerText')
                    m = VIEWS_PATTERN.search(body)
                    if m:
                        views[fav['short_id']] = int(
                            re.sub(r'\D', '', m.group(1)))
                        print(f"   👁️ {fav['short_id']}: "
                              f"{views[fav['short_id']]} wyświetleń")
                    else:
                        print(f"   ⚠️ {fav['short_id']}: licznik wyświetleń "
                              f"nie pojawił się na stronie")
                except Exception as e:
                    print(f"   ⚠️ Wyświetlenia {fav['short_id']}: {e}")
            browser.close()
    except Exception as e:
        print(f"   ⚠️ Chromium niedostępny ({e}) — pomijam wyświetlenia.")
    return views


def track_favorites() -> bool:
    favorites = load_favorites()
    if not favorites:
        print("ℹ️ Brak ulubionych ofert (data/favorites.json pusty).")
        return False

    print(f"⭐ Śledzenie {len(favorites)} ulubionych ofert...")
    tracking = load_tracking()
    now_iso = datetime.now(TZ).isoformat()

    # Uzupełnij brakujące numeric_id (nowe wpisy dodane samym URL-em)
    favorites_changed = False
    for fav in favorites:
        if not fav.get('short_id'):
            m = re.search(r'-ID(\w+)\.html', fav.get('url', ''))
            if m:
                fav['short_id'] = m.group(1)
                favorites_changed = True
        if not fav.get('numeric_id'):
            fav['numeric_id'] = resolve_numeric_id(fav['url'])
            if fav['numeric_id']:
                favorites_changed = True
                print(f"   🔎 {fav['short_id']}: numeric_id = {fav['numeric_id']}")
    if favorites_changed:
        write_json_atomic(FAVORITES_FILE, {'favorites': favorites})

    views_map = fetch_views([f for f in favorites if f.get('numeric_id')])

    for fav in favorites:
        short_id = fav.get('short_id', '')
        numeric_id = fav.get('numeric_id')
        if not short_id or not numeric_id:
            print(f"   ⚠️ Pomijam wpis bez ID: {fav.get('url', '(brak URL)')}")
            continue

        snap = fetch_api_snapshot(numeric_id)
        if snap is None:
            continue  # błąd sieci — nie fałszuj historii pustym snapshotem

        entry = tracking.setdefault(short_id, {
            'url': fav['url'].split('?')[0],
            'numeric_id': numeric_id,
            'added': fav.get('added', now_iso[:10]),
            'title': '',
            'snapshots': [],
        })
        if snap.get('title'):
            entry['title'] = snap['title']

        entry['snapshots'].append({
            'ts': now_iso,
            'status': snap.get('status', ''),
            'price': snap.get('price'),
            'last_refresh': snap.get('last_refresh', ''),
            'pushup': snap.get('pushup', ''),
            'valid_to': snap.get('valid_to', ''),
            'created': snap.get('created', ''),
            'views': views_map.get(short_id),
        })
        label = snap.get('status', '?')
        price = snap.get('price')
        print(f"   ✅ {short_id}: {label}, cena {price if price is not None else '—'}")

    write_json_atomic(TRACKING_FILE, tracking)
    print(f"💾 Zapisano {TRACKING_FILE}")
    return True


if __name__ == '__main__':
    ok = track_favorites()
    from favorites_generator import generate_favorites_data
    generate_favorites_data()
    sys.exit(0 if ok else 0)
