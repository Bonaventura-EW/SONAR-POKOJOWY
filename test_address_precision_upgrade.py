#!/usr/bin/env python3
"""
Testy DOPRECYZOWANIA MARKERA — dopisany numer budynku trafia na mapę.

Zgłoszenie Mateusza (07.09.2026, ID1bxU2z): "tutaj jest adres a na mapie jest
nieprecyzyjna pinezka". Wynajmujący dopisał numer do opisu ("w bloku przy
ul. P. Wołodyjowskiego" → "przy ul. Pana Wołodyjowskiego 7"), ale zmiana nie
docierała do bazy przez trzy niezależne blokady:

  1. opis istniejącej oferty NIGDY nie był nadpisywany (zamrożony na pierwszym
     skanie), więc parser czytał tekst sprzed tygodni,
  2. `_addr_changed` czyta 'Wołodyjowskiego' → 'Pana Wołodyjowskiego 7' jako TEN
     SAM adres (porównanie numerów wypada, gdy baza numeru nie ma; nazwa ulicy to
     podzbiór nowej), więc nawet świeży odczyt niczego nie zmieniał,
  3. inteligentne skanowanie pomijało ofertę bez zmiany ceny i tytułu, więc
     szczegółów w ogóle nie pobieraliśmy.

Ten plik pilnuje wszystkich trzech napraw plus zabezpieczeń wokół nich:
doprecyzowanie NIE jest przeprowadzką (nie kasuje historii cen), marker nigdy
nie schodzi w dół precyzji, a opis z cache nie może wrócić do bazy z doklejonym
tytułem.
"""

import sys
from datetime import datetime, timedelta

sys.path.insert(0, 'src')

import pytz

from main import SonarPokojowy
from scraper import OLXScraper, PL_TZ

NOW = datetime.now(PL_TZ)


def _existing(full, street, number, precision, coords, description, title):
    """Rekord z bazy — minimum pól, których dotyka _update_existing_offer."""
    return {
        'id': 'pokoje-testowe-CID3-ID1bxU2z',
        'address': {'full': full, 'street': street, 'number': number,
                    'coords': coords, 'precision': precision},
        'price': {'current': 800, 'history': [700, 800],
                  'history_full': [{'price': 700, 'date': '2026-07-22T09:07:36+02:00',
                                    'approximated': False},
                                   {'price': 800, 'date': '2026-09-06T23:05:56+02:00',
                                    'approximated': False}],
                  'media_info': 'sprawdź w opisie', 'source': 'JSON-LD (OLX)'},
        'description': description,
        'title': title,
        'first_seen': '2026-07-22T09:07:36+02:00',
        'last_seen': '2026-09-07T20:08:17+02:00',
        'active': True,
    }


def _new_data(full, street, number, precision, coords, description, title,
              price=800, details_fetched=True):
    """Świeżo przetworzona oferta — kształt zwracany przez _process_offer."""
    return {
        'id': 'pokoje-testowe-CID3-ID1bxU2z',
        'url': 'https://www.olx.pl/d/oferta/pokoje-testowe-CID3-ID1bxU2z.html',
        'address': {'full': full, 'street': street, 'number': number,
                    'coords': coords, 'precision': precision},
        'price': {'current': price, 'history': [price], 'media_info': 'sprawdź w opisie',
                  'source': 'JSON-LD (OLX)'},
        'description': description,
        'details_fetched_at': NOW.isoformat() if details_fetched else None,
        'title': title,
    }


# Wołodyjowskiego (LSM) i Nadbystrzycka — realne punkty z geocoding_cache
W_STREET = {'lat': 51.2375418, 'lon': 22.5176492}
W_NUMBER = {'lat': 51.2382327, 'lon': 22.5126237}
NADBYSTRZYCKA = {'lat': 51.2321, 'lon': 22.5470}
SLAWINEK = {'lat': 51.2590, 'lon': 22.5090}
FAR_AWAY = {'lat': 51.1650, 'lon': 22.6100}   # ~12 km od Sławinka


def test_precision_upgrade_predicate():
    print("\n📝 Test 1: co jest doprecyzowaniem, a co przeprowadzką")

    m = SonarPokojowy()
    street = {'full': 'Wołodyjowskiego', 'street': 'Wołodyjowskiego', 'number': None,
              'precision': 'street_only', 'coords': W_STREET}
    numbered = {'full': 'Pana Wołodyjowskiego 7', 'street': 'Pana Wołodyjowskiego',
                'number': '7', 'precision': 'exact', 'coords': W_NUMBER}

    assert m._precision_upgrade(street, numbered) is True
    print('   ✅ ta sama ulica + dopisany numer = doprecyzowanie')

    # Odwrotny kierunek: opis okrojony do samej ulicy NIE może zjeść numeru
    assert m._precision_upgrade(numbered, street) is False
    print('   ✅ marker nie schodzi w dół precyzji')

    other = {'full': 'Nadbystrzycka 12', 'street': 'Nadbystrzycka', 'number': '12',
             'precision': 'exact', 'coords': NADBYSTRZYCKA}
    assert m._precision_upgrade(street, other) is False
    print('   ✅ inna ulica z numerem = zwykła ścieżka (zmiana adresu/korekta)')

    district = {'full': 'Sławinek', 'street': None, 'number': None,
                'precision': 'district', 'coords': SLAWINEK}
    near = {'full': 'Kurantowa 6', 'street': 'Kurantowa', 'number': '6',
            'precision': 'exact', 'coords': {'lat': 51.2620, 'lon': 22.5150}}
    far = {'full': 'Gdzieś Daleko 1', 'street': 'Gdzieś Daleko', 'number': '1',
           'precision': 'exact', 'coords': FAR_AWAY}
    assert m._precision_upgrade(district, near) is True
    assert m._precision_upgrade(district, far) is False
    print('   ✅ dzielnica → ulica: tylko w promieniu 3 km od centroidu')

    # Ta sama ranga (street_only → street_only) to nie awans
    assert m._precision_upgrade(street, dict(street, full='Zana', street='Zana')) is False
    print('   ✅ równa precyzja = brak awansu')


def test_upgrade_keeps_history():
    print("\n📝 Test 2: doprecyzowanie nie kasuje historii cen (ID1bxU2z)")

    m = SonarPokojowy()
    existing = _existing('Wołodyjowskiego', 'Wołodyjowskiego', None, 'street_only',
                         W_STREET,
                         'Pokoje do wynajęcia Pokoje w bloku przy ul. P. Wołodyjowskiego.',
                         'Pokoje do wynajęcia')
    new = _new_data('Pana Wołodyjowskiego 7', 'Pana Wołodyjowskiego', '7', 'exact',
                    W_NUMBER,
                    'Pokoje do wynajęcia Pokoje w bloku przy ul. Pana Wołodyjowskiego 7.',
                    'Pokoje do wynajęcia')

    m._update_existing_offer(existing, new)

    assert existing['address']['full'] == 'Pana Wołodyjowskiego 7', existing['address']
    assert existing['address']['number'] == '7'
    assert existing['address']['precision'] == 'exact'
    assert existing['address']['coords'] == W_NUMBER, 'marker musi przeskoczyć na numer'
    print('   ✅ adres, numer, precyzja i współrzędne podmienione')

    assert 'versions' not in existing, 'doprecyzowanie to NIE przeprowadzka'
    assert existing.get('address_change_count') is None
    assert existing['price']['history'] == [700, 800], existing['price']['history']
    assert len(existing['price']['history_full']) == 2
    print('   ✅ historia cen i versions[] nietknięte')

    last = existing['address_corrections'][-1]
    assert last['reason'] == 'precision_upgrade', last
    assert last['from'] == 'Wołodyjowskiego' and last['to'] == 'Pana Wołodyjowskiego 7'
    assert m._addr_upgrades_count == 1
    print('   ✅ ślad w address_corrections[] z reason=precision_upgrade')


def test_real_move_still_resets():
    print("\n📝 Test 3: realna przeprowadzka dalej zrzuca wersję do versions[]")

    m = SonarPokojowy()
    existing = _existing('Wołodyjowskiego 7', 'Wołodyjowskiego', '7', 'exact',
                         W_NUMBER,
                         'Pokój Pokój przy ul. Wołodyjowskiego 7, LSM.',
                         'Pokój')
    new = _new_data('Nadbystrzycka 12', 'Nadbystrzycka', '12', 'exact', NADBYSTRZYCKA,
                    'Pokój Zupełnie inne mieszkanie, ul. Nadbystrzycka 12 obok politechniki.',
                    'Pokój', price=900)

    m._update_existing_offer(existing, new)

    assert existing['address']['full'] == 'Nadbystrzycka 12'
    assert len(existing.get('versions', [])) == 1, existing.get('versions')
    assert existing['versions'][0]['address']['full'] == 'Wołodyjowskiego 7'
    assert existing['price']['history'] == [900], existing['price']['history']
    assert m._addr_upgrades_count == 0
    print('   ✅ inna ulica + przepisany opis = versions[] + świeża historia cen')


def test_description_refresh():
    print("\n📝 Test 4: opis odświeżany tylko po realnym pobraniu strony")

    m = SonarPokojowy()
    frozen = 'Stary tytuł Stary tytuł Pokój przy ul. P. Wołodyjowskiego.'
    existing = _existing('Wołodyjowskiego', 'Wołodyjowskiego', None, 'street_only',
                         W_STREET, frozen, 'Stary tytuł')
    fresh_text = 'Stary tytuł Pokój przy ul. Pana Wołodyjowskiego 7.'
    m._update_existing_offer(existing, _new_data(
        'Pana Wołodyjowskiego 7', 'Pana Wołodyjowskiego', '7', 'exact', W_NUMBER,
        fresh_text, 'Stary tytuł'))
    assert existing['description'] == fresh_text, existing['description']
    assert existing['details_fetched_at'], 'brak znacznika odczytu szczegółów'
    print('   ✅ pobrana strona nadpisuje zamrożony opis')

    # Oferta POMINIĘTA: opis pochodzi z bazy i jest sklejony z tytułem jeszcze raz.
    # Zapis takiego tekstu doklejałby tytuł przy każdym skanie.
    m2 = SonarPokojowy()
    existing2 = _existing('Wołodyjowskiego 7', 'Wołodyjowskiego', '7', 'exact', W_NUMBER,
                          fresh_text, 'Stary tytuł')
    m2._update_existing_offer(existing2, _new_data(
        'Wołodyjowskiego 7', 'Wołodyjowskiego', '7', 'exact', W_NUMBER,
        'Stary tytuł ' + fresh_text, 'Stary tytuł', details_fetched=False))
    assert existing2['description'] == fresh_text, existing2['description']
    assert 'details_fetched_at' not in existing2
    print('   ✅ oferta pominięta nie dokleja tytułu do opisu')


def test_stale_title_prefix_is_not_a_rewrite():
    print("\n📝 Test 5: stary tytuł w sklejce to nie 'przepisane ogłoszenie'")

    m = SonarPokojowy()
    existing = {
        'title': 'Nowy tytuł',
        'title_versions': [{'title': 'Stary tytuł'}, {'title': 'Nowy tytuł'}],
        'description': 'Stary tytuł Pokój przy ul. Wołodyjowskiego, LSM.',
    }
    same_body = {'title': 'Nowy tytuł',
                 'description': 'Nowy tytuł Pokój przy ul. Wołodyjowskiego, LSM.'}
    assert m._source_text_changed(existing, same_body) is False
    print('   ✅ zmiana samego prefiksu tytułu nie liczy się jako edycja opisu')

    rewritten = {'title': 'Nowy tytuł',
                 'description': 'Nowy tytuł Zupełnie inny opis, inne mieszkanie.'}
    assert m._source_text_changed(existing, rewritten) is True
    print('   ✅ przepisany opis dalej wykrywany')


def test_stale_rotation_picks_oldest_imprecise():
    print("\n📝 Test 6: rotacja dociąga najstarsze oferty z nieprecyzyjnym markerem")

    scraper = OLXScraper(existing_offers={})
    scraper.STALE_REFRESH_BUDGET = 2

    def item(oid, precision, age_days):
        ts = (NOW - timedelta(days=age_days)).isoformat() if age_days is not None else None
        return {'offer': {'url': f'https://www.olx.pl/d/oferta/{oid}.html'},
                'existing': {'address': {'full': 'Wołodyjowskiego', 'precision': precision,
                                         'coords': W_STREET},
                             'details_fetched_at': ts},
                'reason': 'same_price'}

    to_skip = [
        item('swiezy', 'street_only', 1),        # młodszy niż próg → zostaje
        item('stary', 'street_only', 30),        # najstarszy → awans
        item('sredni', 'district', 10),          # drugi w kolejce → awans
        item('dokladny', 'exact', 40),           # ma numer → nie ma czego zyskać
        item('mlody-district', 'district', 2),   # poniżej progu wieku
    ]
    scraper.stats['skipped_same_price'] = len(to_skip)
    to_fetch = []
    left = scraper._promote_stale_imprecise(to_skip, to_fetch)

    promoted = [it['offer']['url'] for it in to_fetch]
    assert len(promoted) == 2, promoted
    assert 'stary' in promoted[0] and 'sredni' in promoted[1], promoted
    assert all(it['reason'] == 'stale_address' for it in to_fetch)
    # Adres z bazy jedzie jako siatka bezpieczeństwa: usunięty z opisu adres nie
    # może zrzucić żywej oferty do 'no_address' i zgasić markera.
    assert all(it['offer']['cached_address']['full'] == 'Wołodyjowskiego' for it in to_fetch)
    assert all(it['offer']['cached_coordinates'] == W_STREET for it in to_fetch)
    assert len(left) == 3
    assert scraper.stats['fetched_stale_address'] == 2
    assert scraper.stats['skipped_same_price'] == 3, scraper.stats
    print('   ✅ budżet, próg wieku i kolejność od najstarszego')

    # Rekord bez znacznika (sprzed wprowadzenia pola) = najstarszy z możliwych
    scraper2 = OLXScraper(existing_offers={})
    scraper2.STALE_REFRESH_BUDGET = 1
    to_fetch2 = []
    scraper2._promote_stale_imprecise(
        [item('ma-znacznik', 'street_only', 30), item('bez-znacznika', 'street_only', None)],
        to_fetch2)
    assert 'bez-znacznika' in to_fetch2[0]['offer']['url'], to_fetch2
    print('   ✅ brak znacznika traktowany jako najstarszy odczyt')

    # Same oferty z dokładnym adresem → nic nie awansuje, zero dodatkowych requestów
    scraper3 = OLXScraper(existing_offers={})
    to_fetch3 = []
    left3 = scraper3._promote_stale_imprecise([item('a', 'exact', 90)], to_fetch3)
    assert to_fetch3 == [] and len(left3) == 1
    print('   ✅ oferty z numerem nie generują ruchu')


if __name__ == '__main__':
    print('🧪 TESTY DOPRECYZOWANIA MARKERA (dopisany numer budynku)')
    print('=' * 70)
    test_precision_upgrade_predicate()
    test_upgrade_keeps_history()
    test_real_move_still_resets()
    test_description_refresh()
    test_stale_title_prefix_is_not_a_rewrite()
    test_stale_rotation_picks_oldest_imprecise()
    print('\n' + '=' * 70)
    print('✅ Wszystkie testy doprecyzowania markera przeszły')
