#!/usr/bin/env python3
"""
SONDA (jednorazowa, do skasowania po decyzji): skąd wziąć datę odświeżenia
ogłoszenia dla CAŁEJ bazy, a nie tylko dla 10 profili firmowych.

Dziś `refresh_dates` powstaje wyłącznie ze skanu profili (OLX API v1,
`last_refresh_time`), bo `_track_refresh()` wymaga `profile_name`. Sonda
sprawdza trzy alternatywy i mierzy ich koszt czasowy:

  A. karta listingu HTML — czy niesie "Odświeżono dnia ..." (koszt: 0 requestów,
     te strony i tak pobieramy),
  B. API v1 z filtrem kategoria+miasto — sweep całego listingu stronami po 50,
  C. API v1 per oferta — pomiar latencji pojedynczego requestu.

Uruchamiana z GitHub Actions (z sesji web OLX odpowiada 403 z CloudFront,
bo proxy re-terminuje TLS i psuje impersonację curl_cffi).
"""

import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))

from scraper import OLXScraper  # noqa: E402
from profiles_config import TRACKED_PROFILES  # noqa: E402

API_BASE = 'https://www.olx.pl/api/v1/offers/'
LISTING_PAGES = 2          # ile stron listingu obejrzeć w teście A
CARD_SAMPLES = 12          # ile tekstów kart wypisać dosłownie
SWEEP_PROBE_PAGES = 3      # ile stron API zmierzyć w teście B (reszta = ekstrapolacja)


def hdr(title):
    print('\n' + '=' * 72)
    print(title)
    print('=' * 72)


# ── A. Karta listingu HTML ──────────────────────────────────────────────────

def probe_listing_cards(scraper):
    """Czy karta ogłoszenia w listingu niesie datę odświeżenia?"""
    hdr('A. KARTA LISTINGU — czy jest "Odświeżono dnia ..."?')
    total_cards = 0
    with_refresh = 0
    other_dates = 0
    no_date = 0
    samples = []

    for page in range(1, LISTING_PAGES + 1):
        url = scraper.BASE_URL if page == 1 else f'{scraper.BASE_URL}?page={page}'
        t0 = time.time()
        soup = scraper._fetch_page(url)
        print(f'   strona {page}: {time.time() - t0:.2f}s')
        if not soup:
            print('   ❌ nie udało się pobrać strony')
            continue

        # Karta = kontener z linkiem do /d/oferta/ (ta sama heurystyka co scraper)
        seen = set()
        for link in soup.find_all('a', href=lambda x: x and '/d/oferta/' in str(x)):
            clean = link.get('href', '').split('?')[0]
            if clean in seen:
                continue
            seen.add(clean)

            container = None
            current = link
            for _ in range(6):
                current = current.find_parent()
                if not current:
                    break
                if current.find('p', {'data-testid': 'ad-price'}):
                    container = current
                    break
            if container is None:
                continue

            total_cards += 1
            date_el = container.find(attrs={'data-testid': 'location-date'})
            text = date_el.get_text(' ', strip=True) if date_el else ''
            if not text:
                # fallback: dowolny węzeł z datą/odświeżeniem w karcie
                for cand in container.find_all(['p', 'span', 'div']):
                    t = cand.get_text(' ', strip=True)
                    if 'Odświeżono' in t or 'Dzisiaj o' in t:
                        text = t
                        break

            if not text:
                no_date += 1
            elif 'Odświeżono' in text:
                with_refresh += 1
            else:
                other_dates += 1

            if len(samples) < CARD_SAMPLES and text:
                samples.append(text)

        scraper._random_delay()

    print(f'\n   kart obejrzanych:        {total_cards}')
    print(f'   z "Odświeżono dnia ...": {with_refresh}')
    print(f'   z inną datą:             {other_dates}')
    print(f'   bez daty w karcie:       {no_date}')
    print('\n   próbki tekstu z kart:')
    for s in samples:
        print(f'     · {s!r}')

    ok = with_refresh > 0
    print(f'\n   WERDYKT A: {"✅ karta niesie datę odświeżenia" if ok else "❌ brak daty odświeżenia w karcie"}')
    return {'cards': total_cards, 'with_refresh': with_refresh,
            'other_dates': other_dates, 'no_date': no_date, 'ok': ok}


# ── B. API v1 — sweep po całym listingu ────────────────────────────────────

def _api_get(scraper, url):
    t0 = time.time()
    try:
        resp = scraper.session.get(url, timeout=20)
    except Exception as e:                                   # noqa: BLE001
        return None, time.time() - t0, f'{type(e).__name__}: {e}'
    dt = time.time() - t0
    if resp.status_code != 200:
        return None, dt, f'HTTP {resp.status_code}'
    try:
        return resp.json(), dt, None
    except ValueError:
        return None, dt, 'odpowiedź nie jest JSON-em'


def discover_lublin_city_id(scraper):
    """ID miasta bierzemy z oferty istniejącego profilu — bez zgadywania."""
    for key, cfg in TRACKED_PROFILES.items():
        url = f'{API_BASE}?offset=0&limit=25&user_id={cfg["user_id"]}'
        data, dt, err = _api_get(scraper, url)
        if err:
            print(f'   {key}: {err} ({dt:.2f}s)')
            continue
        for offer in data.get('data', []):
            city = ((offer.get('location') or {}).get('city') or {})
            if (city.get('name') or '').lower() == 'lublin' and city.get('id'):
                print(f'   city_id z profilu {key}: {city["id"]} ({city["name"]})')
                return city['id'], offer.get('category', {}).get('id')
        scraper._random_delay()
    return None, None


def probe_api_sweep(scraper):
    """Czy da się przelecieć cały listing przez API v1 (kategoria + miasto)?"""
    hdr('B. API v1 — sweep całego listingu (kategoria + miasto)')
    city_id, cat_id = discover_lublin_city_id(scraper)
    if not city_id:
        print('   ❌ nie udało się ustalić city_id — reszta testu B pominięta')
        return {'ok': False}

    cat_id = 11  # stancje-pokoje (kategoria listingu, którą skanujemy)
    variants = [
        ('kategoria+miasto', f'{API_BASE}?offset=0&limit=50&category_id={cat_id}&city_id={city_id}'),
        ('kategoria+miasto+sort', f'{API_BASE}?offset=0&limit=50&category_id={cat_id}&city_id={city_id}&sort_by=created_at%3Adesc'),
        ('sama kategoria', f'{API_BASE}?offset=0&limit=50&category_id={cat_id}'),
    ]

    working = None
    for name, url in variants:
        data, dt, err = _api_get(scraper, url)
        if err:
            print(f'   {name:22s} → {err} ({dt:.2f}s)')
        else:
            rows = data.get('data', [])
            total = (data.get('metadata') or {}).get('total_elements')
            cities = {((o.get('location') or {}).get('city') or {}).get('name') for o in rows}
            with_refresh = sum(1 for o in rows if o.get('last_refresh_time') or o.get('pushup_time'))
            print(f'   {name:22s} → 200, {len(rows)} ofert, total={total}, '
                  f'last_refresh_time w {with_refresh}/{len(rows)}, miasta={sorted(c for c in cities if c)[:4]} ({dt:.2f}s)')
            if working is None and rows:
                working = (name, url, total)
        scraper._random_delay()

    if not working:
        print('\n   WERDYKT B: ❌ żaden wariant filtrów nie zadziałał')
        return {'ok': False}

    name, url, total = working
    # Ile stron trzeba i czy API nie utnie offsetu na wysokich stronach
    times = []
    for i in range(SWEEP_PROBE_PAGES):
        offset = i * 50
        data, dt, err = _api_get(scraper, url.replace('offset=0', f'offset={offset}'))
        times.append(dt)
        n = len(data.get('data', [])) if data else 0
        print(f'   offset={offset:<5d} → {n} ofert, {dt:.2f}s{" | " + err if err else ""}')
        scraper._random_delay()

    for offset in (500, 950, 1000, 1500):
        data, dt, err = _api_get(scraper, url.replace('offset=0', f'offset={offset}'))
        n = len(data.get('data', [])) if data else 0
        print(f'   offset={offset:<5d} → {n} ofert{" | " + err if err else ""} ({dt:.2f}s)')
        scraper._random_delay()

    avg = statistics.mean(times) if times else 0
    pages = -(-(total or 0) // 50)
    print(f'\n   średni czas requestu: {avg:.2f}s')
    print(f'   stron do przejścia:   {pages} (total={total})')
    print(f'   ⏱️  szacowany koszt sweepu: {pages * avg:.0f}s sekwencyjnie')
    print(f'\n   WERDYKT B: ✅ wariant "{name}" działa')
    return {'ok': True, 'variant': name, 'total': total, 'pages': pages, 'avg': avg}


# ── C. API v1 — koszt pojedynczej oferty ───────────────────────────────────

def probe_api_per_offer(scraper):
    """Latencja pojedynczego requestu — do wyceny wariantu 'API per oferta'."""
    hdr('C. API v1 — koszt requestu per oferta')
    tracking_path = ROOT / 'data' / 'favorites_tracking.json'
    ids = []
    if tracking_path.exists():
        tracking = json.loads(tracking_path.read_text(encoding='utf-8'))
        ids = [v['numeric_id'] for v in tracking.values() if v.get('numeric_id')][:6]
    if not ids:
        print('   ⏭️  brak numerycznych ID w favorites_tracking.json — pominięte')
        return {}

    times = []
    for oid in ids:
        data, dt, err = _api_get(scraper, f'{API_BASE}{oid}/')
        times.append(dt)
        if err:
            print(f'   {oid} → {err} ({dt:.2f}s)')
        else:
            d = data.get('data', {})
            print(f'   {oid} → {d.get("status", "?"):8s} last_refresh_time='
                  f'{d.get("last_refresh_time") or "brak"} ({dt:.2f}s)')

    avg = statistics.mean(times)
    print(f'\n   średnia latencja: {avg:.2f}s')
    print(f'   ⏱️  802 oferty sekwencyjnie: {802 * avg:.0f}s')
    print(f'   ⏱️  802 oferty przy 10 wątkach i globalnym capie 20 QPS: '
          f'~{max(802 / 20, 802 * avg / 10):.0f}s')
    return {'avg': avg}


def main():
    print('SONDA: źródła daty odświeżenia dla całej bazy')
    print(f'BASE_URL: {OLXScraper.BASE_URL}')
    scraper = OLXScraper(delay_range=(0.3, 0.8), max_workers=1)

    a = probe_listing_cards(scraper)
    b = probe_api_sweep(scraper)
    c = probe_api_per_offer(scraper)

    hdr('PODSUMOWANIE')
    print(f'A. karta listingu niesie odświeżenie: {"TAK" if a.get("ok") else "NIE"} '
          f'({a.get("with_refresh", 0)}/{a.get("cards", 0)} kart)')
    if b.get('ok'):
        print(f'B. sweep API v1 działa: TAK ({b["pages"]} stron × {b["avg"]:.2f}s '
              f'≈ {b["pages"] * b["avg"]:.0f}s, total={b["total"]})')
    else:
        print('B. sweep API v1 działa: NIE')
    if c.get('avg'):
        print(f'C. API per oferta: {c["avg"]:.2f}s/request → 802 ofert ≈ '
              f'{max(802 / 20, 802 * c["avg"] / 10):.0f}s przy 10 wątkach')
    print('\nGotowe. Skrypt jest jednorazowy — po decyzji do usunięcia.')


if __name__ == '__main__':
    main()
