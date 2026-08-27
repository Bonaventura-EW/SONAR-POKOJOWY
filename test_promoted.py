#!/usr/bin/env python3
"""
Test detekcji PROMOWANYCH ogłoszeń (płatne wyróżnienia na listingu OLX).

Pokrywa całą ścieżkę bez ruszania sieci:
  scraper._is_promoted_href / _extract_offers_from_page  → flaga z HTML listingu
  main._track_promoted                                   → historia dni (max 1/dzień)
  trend_generator.build_promoted                         → dzienny szereg + udział

Uruchomienie: python test_promoted.py   (z katalogu głównego repo)
"""

import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, 'src')

from bs4 import BeautifulSoup

import trend_generator as tg
from scraper import OLXScraper

FAILURES = []


def check(name, condition, detail=''):
    if condition:
        print(f"   ✅ {name}")
    else:
        print(f"   ❌ {name} {detail}")
        FAILURES.append(name)


def _card(slug, reason, price='800 zł', featured=False):
    """Kafelek listingu OLX w formie, jaką widzi scraper (link + h6 + cena)."""
    href = f"/d/oferta/{slug}.html"
    if reason:
        href += f"?search_reason=search%7C{reason}"
    badge = '<span data-testid="adCard-featured">Wyróżnione</span>' if featured else ''
    return f'''
      <div class="card">
        {badge}
        <a href="{href}"><h6>Pokój do wynajęcia {slug}</h6></a>
        <p data-testid="ad-price">{price}</p>
      </div>'''


def test_is_promoted_href():
    print("\n🧪 1/4 _is_promoted_href — parametr atrybucji OLX")
    f = OLXScraper._is_promoted_href
    check('promoted (URL-encoded |)',
          f('https://www.olx.pl/d/oferta/pokoj-CID3-ID1bQaas.html?search_reason=search%7Cpromoted'))
    check('promoted (surowy |)',
          f('https://www.olx.pl/d/oferta/pokoj-CID3-ID1bQaas.html?search_reason=search|promoted'))
    check('organic → False',
          not f('https://www.olx.pl/d/oferta/pokoj-CID3-ID1bQaas.html?search_reason=search%7Corganic'))
    check('brak query → False', not f('https://www.olx.pl/d/oferta/pokoj-CID3-ID1bQaas.html'))
    check('pusty URL → False', not f(''))
    check('inny parametr → False',
          not f('https://www.olx.pl/d/oferta/pokoj.html?promoted_looking=1'))


def test_extract_offers():
    print("\n🧪 2/4 _extract_offers_from_page — flaga na ofercie")
    html = '<html><body>' + ''.join([
        _card('pokoj-promo-CID3-ID1', 'promoted'),
        _card('pokoj-zwykly-CID3-ID2', 'organic'),
        _card('pokoj-badge-CID3-ID3', None, featured=True),   # brak atrybucji → plakietka
        _card('pokoj-promo-CID3-ID1', 'organic'),             # duplikat promowanej
        _card('pokoj-zwykly-CID3-ID2', 'promoted'),           # duplikat: organic → promoted
    ]) + '</body></html>'

    scraper = OLXScraper.__new__(OLXScraper)          # bez sesji HTTP
    scraper.promoted_stats = {'promoted': 0, 'attributed': 0, 'cards': 0}
    offers = scraper._extract_offers_from_page(BeautifulSoup(html, 'lxml'))
    by_slug = {o['url'].split('/')[-1].split('.')[0]: o for o in offers}

    check('deduplikacja po URL bez query', len(offers) == 3, f'(jest {len(offers)})')
    check('kafelek promoted → promoted=True', by_slug['pokoj-promo-CID3-ID1']['promoted'])
    check('plakietka bez atrybucji → promoted=True', by_slug['pokoj-badge-CID3-ID3']['promoted'])
    check('duplikat promowany podnosi flagę organicznej',
          by_slug['pokoj-zwykly-CID3-ID2']['promoted'])
    check('licznik atrybucji widzi search_reason', scraper.promoted_stats['attributed'] == 4,
          f"(jest {scraper.promoted_stats['attributed']})")

    # Listing bez ani jednego promowanego kafelka
    plain = '<html><body>' + _card('pokoj-a-CID3-ID9', 'organic') + '</body></html>'
    scraper.promoted_stats = {'promoted': 0, 'attributed': 0, 'cards': 0}
    plain_offers = scraper._extract_offers_from_page(BeautifulSoup(plain, 'lxml'))
    check('sam listing organiczny → promoted=False',
          plain_offers and not plain_offers[0]['promoted'])


def test_track_promoted():
    print("\n🧪 3/4 _track_promoted — historia dni, max 1/dzień")
    from main import SonarPokojowy

    tracker = SonarPokojowy.__new__(SonarPokojowy)
    tracker.tz = datetime.now().astimezone().tzinfo
    today = datetime.now(tracker.tz).strftime('%Y-%m-%d')

    offer = {'id': 'x', 'promoted': False, 'promoted_dates': [], 'promoted_count': 0}
    check('pierwszy raz → dopisuje dzień', tracker._track_promoted(offer, True))
    check('flaga bieżąca ustawiona', offer['promoted'] is True)
    check('dzisiejsza data w historii', offer['promoted_dates'] == [today])

    check('drugi skan tego samego dnia nic nie dopisuje',
          tracker._track_promoted(offer, True) is False)
    check('historia nadal 1 wpis', offer['promoted_count'] == 1)

    tracker._track_promoted(offer, False)
    check('koniec wyróżnienia → promoted=False', offer['promoted'] is False)
    check('historia dni zostaje', offer['promoted_dates'] == [today])

    fresh = {'id': 'y'}
    check('oferta bez pól nie wybucha', tracker._track_promoted(fresh, False) is False)
    check('brak wyróżnienia → brak historii', fresh.get('promoted_dates') is None)


def test_build_promoted():
    print("\n🧪 4/4 build_promoted — dzienny szereg + udział w rynku")
    today = date.today()

    def iso(d):
        return d.isoformat() + 'T12:00:00+02:00'

    offers = []
    for i in range(100):
        offers.append({
            'id': f'o{i}',
            'first_seen': iso(today - timedelta(days=30)),
            'last_seen': iso(today),
            'active': True,
        })

    d0, d1, d2 = today - timedelta(days=3), today - timedelta(days=2), today
    for o in offers[:10]:
        o['promoted_dates'] = [d0.isoformat()]
    for o in offers[10:16]:
        o['promoted_dates'] = [d1.isoformat()]
    for o in offers[16:24]:
        o['promoted_dates'] = [d2.isoformat()]

    series = tg.build_series(offers)
    scan_days = {d0, d1, d2}                       # wczoraj BEZ skanu → luka na wykresie
    pr = tg.build_promoted(offers, series, scan_days)

    check('metryka zbudowana', pr is not None)
    daily = dict(pr['daily'])
    check('start = pierwszy dzień z danymi', pr['start'] == d0.isoformat(), f"(jest {pr['start']})")
    check('liczba wyróżnień z dnia d0', daily[tg._day_ms(d0)] == 10)
    check('dzień bez skanu = luka (None)',
          daily[tg._day_ms(today - timedelta(days=1))] is None)
    check('current = ostatni zeskanowany dzień', pr['current'] == 8, f"(jest {pr['current']})")
    check('udział w rynku liczony na aktywnych', pr['current_share'] == 8.0,
          f"(jest {pr['current_share']})")
    check('rekord to najwyższy dzień', pr['max_day'] == 10)
    check('total wycięty (metryka stanu, nie przepływu)', 'total' not in pr)

    empty = [{'id': 'z', 'first_seen': iso(today), 'last_seen': iso(today), 'active': True}]
    check('brak danych → None', tg.build_promoted(empty, series, scan_days) is None)


if __name__ == '__main__':
    print("=" * 66)
    print("🧪 TEST DETEKCJI PROMOWANYCH OGŁOSZEŃ")
    print("=" * 66)

    test_is_promoted_href()
    test_extract_offers()
    test_track_promoted()
    test_build_promoted()

    print("\n" + "=" * 66)
    if FAILURES:
        print(f"❌ NIEPOWODZENIA ({len(FAILURES)}): " + ', '.join(FAILURES))
        sys.exit(1)
    print("✅ WSZYSTKO PRZESZŁO")
