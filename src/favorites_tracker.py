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

from scraper import OLXScraper, NETWORK_EXCEPTIONS
from shared_utils import DATA_DIR, TZ, write_json_atomic

# Sesja z impersonacją TLS Safari — zwykły requests dostaje 403 od WAF
# CloudFront OLX (patrz scraper.py IMPERSONATE, 2026-08-11).
_session = OLXScraper.make_olx_session()

FAVORITES_FILE = DATA_DIR / 'favorites.json'
TRACKING_FILE = DATA_DIR / 'favorites_tracking.json'
# Meldunek z ostatniego przebiegu — czyta go api_generator i robi z niego
# alert `favorites_stale` (zakładka Ulubione zamarła na 6 dni, 06–11.11.2026,
# bo nikt nie zgłaszał, że pomiary nie wchodzą).
STATUS_FILE = DATA_DIR / 'favorites_status.json'
LISTING_POSITIONS_FILE = DATA_DIR / 'listing_positions.json'
# Mapa pozycji jest zapisywana przez main.py na starcie scanu. Tracker leci
# w tym samym runie kilka minut później, więc świeża. Powyżej tego progu
# (tracker odpalony solo, bez świeżego scanu) strony pomijamy — lepiej brak
# strony niż nieaktualna.
LISTING_MAX_AGE_H = 12

# UA spójny z impersonacją TLS (Safari) — patrz scraper.py HEADERS.
HEADERS = {
    'User-Agent': OLXScraper.HEADERS['User-Agent'],
}
REQUEST_TIMEOUT = 20

# Blok JSON-LD oferty — tu mieszka cena i tytuł (konwencja całego projektu:
# JSON-LD = źródło prawdy o cenie, patrz price_parser).
JSONLD_PATTERN = re.compile(
    r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S)
# Daty i status siedzą w window.__PRERENDERED_STATE__ — JSON zaescape'owany
# wewnątrz HTML-a (\"klucz\":\"wartość\"). Kotwiczymy okno na lastRefreshTime,
# bo samo "status" pada w HTML-u kilkanaście razy (tłumaczenia UI) i pierwsze
# trafienie bywa cudze.
STATE_ANCHOR = re.compile(r'\\"lastRefreshTime\\"')
STATE_WINDOW = 1500  # znaków w każdą stronę od kotwicy

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


def last_snapshot_status(entry: dict) -> str:
    """Status z ostatniego snapshotu wpisu (pusty string gdy brak pomiarów)."""
    snapshots = entry.get('snapshots') or []
    return snapshots[-1].get('status', '') if snapshots else ''


def resolve_numeric_id(url: str) -> int | None:
    """Numeryczne ID oferty z window.__PRERENDERED_STATE__ strony OLX.
    Potrzebne raz — wynik zapisywany z powrotem do favorites.json."""
    try:
        resp = _session.get(url, timeout=REQUEST_TIMEOUT)
        m = re.search(r'"sku":\s*"?(\d{6,})', resp.text)
        if m:
            return int(m.group(1))
        m = re.search(r'\\"id\\":(\d{6,}),\\"title\\"', resp.text)
        if m:
            return int(m.group(1))
    except NETWORK_EXCEPTIONS as e:
        print(f"   ⚠️ Nie udało się pobrać strony {url}: {e}")
    return None


def _state_field(window: str, key: str) -> str:
    """Wartość klucza z zaescape'owanego JSON-a __PRERENDERED_STATE__.
    `null` (np. pushupTime oferty, której nikt nie podbijał) → pusty string,
    dokładnie jak dawało API v1."""
    m = re.search(r'\\"' + key + r'\\":(?:\\"([^"\\]+)\\"|null)', window)
    return m.group(1) if m and m.group(1) else ''


def parse_offer_page(html: str) -> dict | None:
    """Snapshot z HTML-a strony oferty — te same pola, które dawało API v1.

    None = strona nie jest stroną oferty (interstitial WAF-a, zgoda na
    ciasteczka, przebudowa OLX-a). Lepiej brak pomiaru niż pusty snapshot,
    który na karcie wygląda jak prawdziwy."""
    anchor = STATE_ANCHOR.search(html)
    if not anchor:
        return None
    window = html[max(0, anchor.start() - STATE_WINDOW):anchor.start() + STATE_WINDOW]

    title, price = '', None
    ld = JSONLD_PATTERN.search(html)
    if ld:
        try:
            data = json.loads(ld.group(1))
            title = data.get('name', '') or ''
            raw_price = (data.get('offers') or {}).get('price')
            price = int(float(raw_price)) if raw_price is not None else None
        except (ValueError, TypeError, AttributeError):
            pass

    return {
        'status': _state_field(window, 'status'),
        'price': price,
        'title': title,
        'last_refresh': _state_field(window, 'lastRefreshTime'),
        'pushup': _state_field(window, 'pushupTime'),
        'created': _state_field(window, 'createdTime'),
        'valid_to': _state_field(window, 'validToTime'),
    }


def fetch_page_snapshot(url: str) -> dict | None:
    """Snapshot ze strony oferty. None = nie udało się zmierzyć (nie zapisuj),
    {'status': 'removed'} = oferty nie ma już na OLX (410/404).

    Dlaczego nie API v1 (`/api/v1/offers/<id>/`), które było tu do 11.11.2026:
    od 06.11.2026 CloudFront OLX-a oddaje na nie 403 "Request blocked" każdemu
    klientowi spoza przeglądarki — zmierzone na runnerze Actions i w kontenerze
    chmurowym, z nagłówkami przeglądarki, z Refererem i z impersonacją TLS.
    Strona oferty z tych samych maszyn odpowiada 200 i niesie komplet tych
    samych pól (status, cena, created/validTo/lastRefresh/pushup).

    HEAD przed GET: zdjęta oferta kosztuje 0 B zamiast 1,7 MB strony błędu —
    przy 28 ulubionych to różnica 49 MB → 10 MB na skan."""
    # OLX na zdjętą ofertę odpowiada 410 Gone (404 zdarza się dla ID, którego
    # nigdy nie było). Bez tych kodów każda zdjęta oferta wpadała w gałąź
    # "błąd sieci" → brak snapshotu → wpis zamarzał na ostatnim stanie
    # i świecił "AKTYWNA" w nieskończoność (zgłoszenie Mateusza,
    # ID1bKFSC: ostatni pomiar 22.08, karta aktywna 04.09).
    try:
        head = _session.head(url, timeout=REQUEST_TIMEOUT, allow_redirects=False)
        if head.status_code in (404, 410):
            return {'status': 'removed'}
    except NETWORK_EXCEPTIONS as e:
        print(f"   ⚠️ Błąd HEAD {url}: {e}")
        return None

    try:
        resp = _session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    except NETWORK_EXCEPTIONS as e:
        print(f"   ⚠️ Błąd strony {url}: {e}")
        return None

    if resp.status_code in (404, 410):
        return {'status': 'removed'}
    if resp.status_code != 200:
        print(f"   ⚠️ Strona {url}: HTTP {resp.status_code}")
        return None

    snap = parse_offer_page(resp.text)
    if snap is None:
        print(f"   ⚠️ {url}: strona bez danych oferty ({len(resp.text)} zn.)")
    return snap


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

    # Oferty zdjęte z OLX nie mają już strony — Playwright i tak wisiałby na
    # nich ~30 s (goto na 410 → scroll → timeout czekania na licznik), a licznik
    # wyświetleń dla nieistniejącej oferty nie istnieje. Pomijamy je w tym
    # przejściu; status i tak weryfikuje tańszy HEAD niżej.
    removed_ids = {sid for sid, entry in tracking.items()
                   if last_snapshot_status(entry) == 'removed'}
    if removed_ids:
        print(f"   ⏭️ Pomijam wyświetlenia dla {len(removed_ids)} zdjętych ofert.")
    views_map = fetch_views([f for f in favorites
                             if f.get('short_id') not in removed_ids])

    measured, failed = 0, []
    for fav in favorites:
        short_id = fav.get('short_id', '')
        url = (fav.get('url') or '').split('?')[0]
        if not short_id or not url:
            print(f"   ⚠️ Pomijam wpis bez ID: {fav.get('url', '(brak URL)')}")
            continue

        snap = fetch_page_snapshot(url)
        if snap is None:
            # Nie fałszuj historii pustym snapshotem, ale ZGŁOŚ to dalej —
            # cicha porażka tutaj zamroziła zakładkę na 6 dni (06–11.11.2026).
            failed.append(short_id)
            continue
        measured += 1

        entry = tracking.setdefault(short_id, {
            'url': url,
            'numeric_id': fav.get('numeric_id'),
            'added': fav.get('added', now_iso[:10]),
            'title': '',
            'snapshots': [],
        })
        if snap.get('title'):
            entry['title'] = snap['title']

        # Zdjęta oferta już się nie zmieni — jeden snapshot 'removed' wystarczy.
        # Bez tego licznik "Pomiary" na karcie rósłby 3×/dobę bez żadnego pomiaru.
        # Sprawdzamy ją dalej (sam HEAD, 0 B), więc gdyby 410 okazało się
        # chwilowe, kolejny snapshot 'active' sam odkręci status.
        if snap.get('status') == 'removed' and last_snapshot_status(entry) == 'removed':
            print(f"   ⏭️ {short_id}: zdjęta z OLX (bez zmian)")
            continue

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
    write_status(now_iso, tracking, measured, failed)
    return not failed


def newest_snapshot_ts(tracking: dict) -> str:
    """Najświeższy pomiar w całym pliku — wiek tej daty to wiek zakładki."""
    stamps = [e['snapshots'][-1]['ts'] for e in tracking.values()
              if e.get('snapshots') and e['snapshots'][-1].get('ts')]
    return max(stamps) if stamps else ''


def write_status(now_iso: str, tracking: dict, measured: int, failed: list) -> None:
    """Meldunek z przebiegu dla api_generator (alert `favorites_stale`).

    Osobny plik, bo tracker leci jako własny proces PO main.py — scan_logger
    pisze tylko do skanu trzymanego w pamięci, więc nie ma już czego dopisać
    do scan_history.json."""
    write_json_atomic(STATUS_FILE, {
        'checked_at': now_iso,
        'tracked': len(tracking),
        'measured': measured,
        'failed': len(failed),
        'failed_ids': failed[:20],
        'last_snapshot_at': newest_snapshot_ts(tracking),
    })
    if failed:
        print(f"   ⚠️ Bez pomiaru: {len(failed)} z {measured + len(failed)} ofert "
              f"({', '.join(failed[:5])}{'…' if len(failed) > 5 else ''})")
    print(f"💾 Zapisano {STATUS_FILE}")


if __name__ == '__main__':
    ok = track_favorites()
    from favorites_generator import generate_favorites_data
    generate_favorites_data()
    sys.exit(0 if ok else 0)
