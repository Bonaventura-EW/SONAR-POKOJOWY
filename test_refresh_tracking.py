#!/usr/bin/env python3
"""
Testy śledzenia odświeżeń (bump/podbicie na OLX) dla CAŁEJ bazy.

Do 07.09.2026 datę podbicia znały tylko oferty firmowe (API v1 przy skanie
profili). Teraz źródłem jest też karta listingu — strona, którą i tak
pobieramy — więc odświeżenia ma każde ogłoszenie, także prywatne.

Pilnowane tu pułapki:
  · karta BEZ słowa "Odświeżono" (sama data wystawienia) nie może udawać bumpu,
  · przybliżenie 23:59 z karty oglądanej nazajutrz nie może nadpisać dokładnej
    godziny zapisanej tego samego dnia,
  · `_track_refresh` nie może wracać na warunek `profile_name` (regresja: 109
    ofert zamiast 802).
"""

import sys
from datetime import datetime, timedelta

sys.path.insert(0, 'src')

import pytz
from bs4 import BeautifulSoup

from scraper import OLXScraper, parse_listing_refresh, PL_TZ
from main import SonarPokojowy

NOW = PL_TZ.localize(datetime(2026, 9, 7, 8, 0))


def test_parse_listing_refresh():
    print("\n📝 Test 1: parsowanie daty z karty listingu")

    cases = [
        ('Lublin - Odświeżono dzisiaj o 07:23', '2026-09-07T07:23:00+02:00'),
        ('Lublin - Odświeżono dnia 06 września 2026', '2026-09-06T23:59:00+02:00'),
        ('Lublin - Odświeżono wczoraj o 22:10', '2026-09-06T22:10:00+02:00'),
        # Karta bez podbicia — sama data wystawienia. NIE wolno jej zamienić na bump.
        ('Lublin - 05 września 2026', ''),
        ('Lublin - Dzisiaj o 07:23', ''),
        # Śmieci nie mogą wywalić scrapera ani wyprodukować daty
        ('Lublin - Odświeżono dnia 06 nieistniejaca 2026', ''),
        ('Lublin - Odświeżono dnia 32 września 2026', ''),
        ('Lublin - Odświeżono dzisiaj o 33:99', ''),
        ('', ''),
        (None, ''),
    ]
    for text, expected in cases:
        got = parse_listing_refresh(text, NOW)
        assert got == expected, f'{text!r} → {got!r}, oczekiwano {expected!r}'
        print(f'   ✅ {str(text)[:46]:46s} → {got or "(brak)"}')

    # Zimowa data — strefa musi zejść na +01:00, inaczej ISO kłamie o godzinie
    winter = parse_listing_refresh('Odświeżono dnia 31 grudnia 2025', NOW)
    assert winter == '2025-12-31T23:59:00+01:00', winter
    print(f'   ✅ zmiana czasu (grudzień)                       → {winter}')


def test_card_extraction():
    print("\n📝 Test 2: wyciąganie oferty z karty listingu")

    html = """
    <div data-cy="l-card">
      <a href="/d/oferta/pokoj-testowy-CID3-ID1abcde.html">
        <h6>Pokój testowy w centrum</h6>
      </a>
      <p data-testid="ad-price">1200 zł</p>
      <p data-testid="location-date">Lublin - Odświeżono dzisiaj o 07:23</p>
    </div>
    <div data-cy="l-card">
      <a href="/d/oferta/pokoj-bez-bumpa-CID3-ID1fghij.html">
        <h6>Pokój bez podbicia</h6>
      </a>
      <p data-testid="ad-price">900 zł</p>
      <p data-testid="location-date">Lublin - 05 września 2026</p>
    </div>
    """
    scraper = OLXScraper(delay_range=(0, 0), max_workers=1)
    offers = scraper._extract_offers_from_page(BeautifulSoup(html, 'lxml'))

    assert len(offers) == 2, f'oczekiwano 2 ofert, jest {len(offers)}'
    bumped = next(o for o in offers if 'ID1abcde' in o['url'])
    plain = next(o for o in offers if 'ID1fghij' in o['url'])

    assert bumped['api_last_refresh'].startswith('20'), bumped['api_last_refresh']
    assert bumped['api_last_refresh'].endswith('T07:23:00+02:00'), bumped['api_last_refresh']
    assert plain['api_last_refresh'] == '', plain['api_last_refresh']
    print(f'   ✅ karta z podbiciem  → {bumped["api_last_refresh"]}')
    print(f'   ✅ karta bez podbicia → (brak)')


def test_track_refresh_all_offers():
    print("\n📝 Test 3: _track_refresh dla ofert prywatnych i firmowych")

    monitor = SonarPokojowy()

    # REGRESJA: przed 07.09.2026 metoda wychodziła tu na braku profile_name
    private = {'id': 'ID1abcde', 'refresh_dates': [], 'refresh_count': 0,
               'last_refresh_date': ''}
    assert monitor._track_refresh(private, '2026-09-07T07:23:00+02:00') is True
    assert private['refresh_dates'] == ['2026-09-07'], private['refresh_dates']
    assert private['refresh_count'] == 1
    print('   ✅ oferta prywatna (bez profile_name) zapisuje odświeżenie')

    firm = {'id': 'ID1zzzzz', 'profile_name': 'Poqui', 'refresh_dates': [],
            'refresh_count': 0, 'last_refresh_date': ''}
    assert monitor._track_refresh(firm, '2026-09-07T10:05:00+02:00') is True
    assert firm['refresh_count'] == 1
    print('   ✅ oferta firmowa działa jak wcześniej')


def test_same_day_not_overwritten():
    print("\n📝 Test 4: przybliżenie 23:59 nie nadpisuje dokładnej godziny")

    monitor = SonarPokojowy()
    offer = {'id': 'ID1abcde', 'refresh_dates': [], 'refresh_count': 0,
             'last_refresh_date': ''}

    # Skan o 15:00: karta mówi "Odświeżono dzisiaj o 09:00" → dokładny znacznik
    monitor._track_refresh(offer, '2026-09-06T09:00:00+02:00')
    assert offer['last_refresh_date'] == '2026-09-06T09:00:00+02:00'

    # Nazajutrz karta pokazuje już samą datę → parser daje 23:59 TEJ SAMEJ doby.
    # Nadpisanie przesunęłoby oznaczenie „ostatnie 24h" o ~15 godzin w przód.
    added = monitor._track_refresh(offer, '2026-09-06T23:59:00+02:00')
    assert added is False, 'ta sama doba nie może dodać drugiego odświeżenia'
    assert offer['last_refresh_date'] == '2026-09-06T09:00:00+02:00', offer['last_refresh_date']
    assert offer['refresh_count'] == 1
    print('   ✅ dokładna godzina wygrywa z przybliżeniem tej samej doby')

    # Kolejna doba = nowe odświeżenie
    assert monitor._track_refresh(offer, '2026-09-07T08:10:00+02:00') is True
    assert offer['refresh_dates'] == ['2026-09-06', '2026-09-07']
    assert offer['refresh_count'] == 2
    print('   ✅ nowa doba dopisuje kolejne odświeżenie')

    # Pusta wartość niczego nie psuje
    assert monitor._track_refresh(offer, '') is False
    assert offer['refresh_count'] == 2
    print('   ✅ brak daty = brak zmian')


def test_map_export_field():
    print("\n📝 Test 5: pole last_refresh trafia do docs/data.json")

    import json
    from pathlib import Path

    data_path = Path('docs/data.json')
    if not data_path.exists():
        print('   ⏭️  brak docs/data.json — pominięte')
        return

    data = json.loads(data_path.read_text(encoding='utf-8'))
    offers = [o for m in data.get('markers', []) for o in m.get('offers', [])]
    assert offers, 'data.json bez ofert'
    with_field = [o for o in offers if o.get('last_refresh')]
    assert all('refresh_count' in o for o in offers), 'brak refresh_count w części ofert'
    assert with_field, 'żadna oferta nie ma last_refresh — generator nie eksportuje pola'

    # Format PL "DD.MM.YYYY HH:MM" — front parsuje go przez parsePolishDate()
    sample = with_field[0]['last_refresh']
    assert len(sample) == 16 and sample[2] == '.' and sample[10] == ' ', sample
    print(f'   ✅ {len(with_field)}/{len(offers)} ofert z last_refresh, format: {sample}')


if __name__ == '__main__':
    print('🧪 TESTY ODŚWIEŻEŃ (bump z karty listingu)')
    print('=' * 70)
    test_parse_listing_refresh()
    test_card_extraction()
    test_track_refresh_all_offers()
    test_same_day_not_overwritten()
    test_map_export_field()
    print('\n' + '=' * 70)
    print('✅ Wszystkie testy odświeżeń przeszły')
