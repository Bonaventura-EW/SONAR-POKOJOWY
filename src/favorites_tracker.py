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
LISTING_POSITIONS_FILE = DATA_DIR / 'listing_positions.json'
# Mapa pozycji jest zapisywana przez main.py na starcie scanu. Tracker leci
# w tym samym runie kilka minut później, więc świeża. Powyżej tego progu
# (tracker odpalony solo, bez świeżego scanu) strony pomijamy — lepiej brak
# strony niż nieaktualna.
LISTING_MAX_AGE_H = 12

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


def load_listing_positions() -> dict:
    """Mapa short_id → numer strony listingu OLX z ostatniego scanu.
    Zwraca {} gdy pliku brak, jest niepoprawny lub przeterminowany
    (tracker bez świeżego scanu) — wtedy 'page' w snapshocie zostaje None."""
    if not LISTING_POSITIONS_FILE.exists():
        return {}
    try:
        with open(LISTING_POSITIONS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (ValueError, OSError):
        return {}
    try:
        scanned = datetime.fromisoformat(data.get('scanned_at', ''))
        age_h = (datetime.now(TZ) - scanned).total_seconds() / 3600
        if age_h > LISTING_MAX_AGE_H:
            print(f"   ℹ️ listing_positions.json sprzed {age_h:.1f}h — pomijam strony.")
            return {}
    except (ValueError, TypeError):
        return {}
    return data.get('positions', {})


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


def _views_from_network(payloads: list) -> int | None:
    """Wyciągnij licznik z przechwyconych odpowiedzi page-views (JSON)."""
    for payload in payloads:
        try:
            data = json.loads(payload)
        except (ValueError, TypeError):
            continue
        # szukaj rekurencyjnie klucza z 'view' w nazwie o wartości int
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for k, v in node.items():
                    if isinstance(v, int) and 'view' in str(k).lower():
                        return v
                    stack.append(v)
            elif isinstance(node, list):
                stack.extend(node)
    return None


def fetch_views(favorites: list) -> dict:
    """Licznik wyświetleń per short_id przez headless Chromium.

    Licznik "Wyświetlenia: N" jest lazy-loaded (montuje się dopiero gdy
    stopka wejdzie w viewport) i zasilany autoryzowanym requestem
    page-views, więc: stopniowy scroll (nie teleport na dół), klik w banner
    cookies, czekanie na doładowanie + nasłuch odpowiedzi sieciowej jako
    drugie źródło. Zwraca {} gdy Playwright/przeglądarka niedostępne."""
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
            context = browser.new_context(
                user_agent=HEADERS['User-Agent'],
                viewport={'width': 1280, 'height': 900},
                locale='pl-PL')
            page = context.new_page()

            # w handlerze eventu sync API nie wolno blokować (resp.text()
            # dopiero po ustabilizowaniu strony) — zbieramy same obiekty
            captured = []

            def on_response(resp):
                if 'page-views' in resp.url or 'pageview' in resp.url.lower():
                    captured.append(resp)

            page.on('response', on_response)

            for fav in favorites:
                sid = fav['short_id']
                try:
                    captured.clear()
                    page.goto(fav['url'], wait_until='domcontentloaded',
                              timeout=60000)
                    page.wait_for_timeout(2000)

                    # banner cookies (OneTrust) potrafi blokować stronę
                    try:
                        page.click('#onetrust-accept-btn-handler', timeout=3000)
                        page.wait_for_timeout(800)
                    except Exception:
                        pass

                    # stopniowy scroll na dół — lazy-load licznika triggeruje
                    # IntersectionObserver, teleport na dół go omija
                    page_height = page.evaluate('document.body.scrollHeight')
                    step = 900
                    pos = 0
                    while pos < page_height:
                        pos += step
                        page.evaluate(f'window.scrollTo(0, {pos})')
                        page.wait_for_timeout(400)
                        page_height = page.evaluate('document.body.scrollHeight')

                    # czekaj aż licznik dostanie liczbę (montuje się async)
                    try:
                        page.wait_for_function(
                            "() => /Wyświetlenia:\\s*[\\d\\s\\u00a0]+/.test(document.body.innerText)",
                            timeout=15000)
                    except Exception:
                        pass

                    body = page.evaluate('document.body.innerText')
                    m = VIEWS_PATTERN.search(body.replace(' ', ' '))
                    if m:
                        views[sid] = int(re.sub(r'\D', '', m.group(1)))
                        print(f"   👁️ {sid}: {views[sid]} wyświetleń (DOM)")
                        continue

                    # fallback: odpowiedź sieciowa page-views
                    payloads = []
                    for resp in captured:
                        try:
                            payloads.append(resp.text())
                        except Exception:
                            pass
                    net = _views_from_network(payloads)
                    if net is not None:
                        views[sid] = net
                        print(f"   👁️ {sid}: {views[sid]} wyświetleń (network)")
                        continue

                    # diagnostyka do logów Actions — co poszło nie tak
                    label_present = 'Wyświetlenia' in body
                    print(f"   ⚠️ {sid}: licznik wyświetleń nie pojawił się "
                          f"(label w DOM: {label_present}, "
                          f"odpowiedzi page-views: {len(captured)}, "
                          f"długość strony: {len(body)} zn.)")
                except Exception as e:
                    print(f"   ⚠️ Wyświetlenia {sid}: {e}")
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
    listing_positions = load_listing_positions()
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

        page = listing_positions.get(short_id)
        entry['snapshots'].append({
            'ts': now_iso,
            'status': snap.get('status', ''),
            'price': snap.get('price'),
            'last_refresh': snap.get('last_refresh', ''),
            'pushup': snap.get('pushup', ''),
            'valid_to': snap.get('valid_to', ''),
            'created': snap.get('created', ''),
            'views': views_map.get(short_id),
            'page': page,
        })
        label = snap.get('status', '?')
        price = snap.get('price')
        page_txt = f", strona {page}" if page is not None else ""
        print(f"   ✅ {short_id}: {label}, cena {price if price is not None else '—'}{page_txt}")

    write_json_atomic(TRACKING_FILE, tracking)
    print(f"💾 Zapisano {TRACKING_FILE}")
    return True


if __name__ == '__main__':
    ok = track_favorites()
    from favorites_generator import generate_favorites_data
    generate_favorites_data()
    sys.exit(0 if ok else 0)
