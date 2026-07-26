#!/usr/bin/env python3
"""Test: korekta parsera vs realna zmiana adresu (2026-07-26).

Pilnuje kontraktu wprowadzonego przy odmrożeniu re-parsingu istniejących ofert:

  1. ten sam tekst + inny adres  → korekta in-place, BEZ wpisu do versions[]
  2. zmieniony tytuł + inny adres → realna zmiana adresu, wpis do versions[]
  3. powrót do adresu, z którego już korygowaliśmy → pominięte (anty-migotanie)
  4. opis pominiętej oferty (wraca z doklejonym tytułem) NIE liczy się jako
     zmiana tekstu — inaczej każda korekta lądowałaby w historii adresu

Uruchamianie: python3 test_address_correction.py  (z katalogu głównego repo)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from main import SonarPokojowy  # noqa: E402

OPIS = ('Pokój 1 osobowy, ul. Kaprysowa, Czechów Pokój 1 osobowy, ul. Kaprysowa, Czechów '
        'Lublin Ciche osiedle, tuż obok pasaż handlowy przy ul. Braci Wieniawskich.')


def _offer(**over):
    o = {
        'id': 'pokoj-1-osobowy-CID3-IDTEST01',
        'url': 'https://www.olx.pl/d/oferta/pokoj-1-osobowy-CID3-IDTEST01.html',
        'title': 'Pokój 1 osobowy, ul. Kaprysowa, Czechów',
        'description': OPIS,
        'address': {'full': 'Braci Wieniawskich', 'street': 'Braci Wieniawskich',
                    'number': None, 'coords': {'lat': 51.26, 'lon': 22.54},
                    'precision': 'street_only'},
        'price': {'current': 1200, 'history': [1200], 'history_full': [],
                  'media_info': '+ media', 'source': 'JSON-LD (OLX)'},
        'first_seen': '2026-07-01T10:00:00+02:00',
        'last_seen': '2026-07-25T22:00:00+02:00',
        'active': True,
    }
    o.update(over)
    return o


def _processed(addr_full, street, title=None, description=None, number=None):
    return {
        'id': 'pokoj-1-osobowy-CID3-IDTEST01',
        'title': title if title is not None else 'Pokój 1 osobowy, ul. Kaprysowa, Czechów',
        # _process_offer zapisuje pod 'description' sklejkę TYTUŁ + ' ' + opis
        'description': description if description is not None else (
            'Pokój 1 osobowy, ul. Kaprysowa, Czechów ' + OPIS),
        'address': {'full': addr_full, 'street': street, 'number': number,
                    'coords': {'lat': 51.263, 'lon': 22.546}, 'precision': 'street_only'},
        'price': {'current': 1200, 'media_info': '+ media', 'source': 'JSON-LD (OLX)'},
    }


def main():
    m = SonarPokojowy()
    failed = []

    def check(name, cond, detail=''):
        print(f"   {'✅' if cond else '❌'} {name}{'' if cond else '  → ' + detail}")
        if not cond:
            failed.append(name)

    print("\n1️⃣  Ten sam tekst, lepszy adres → korekta parsera")
    o = _offer()
    m._update_existing_offer(o, _processed('Kaprysowa', 'Kaprysowa'))
    check('adres podmieniony', o['address']['full'] == 'Kaprysowa', o['address']['full'])
    check('BRAK wpisu w versions[]', not o.get('versions'), str(o.get('versions')))
    check('address_change_count nietknięty', not o.get('address_change_count'))
    check('ślad w address_corrections', len(o.get('address_corrections', [])) == 1)

    print("\n2️⃣  Zmieniony tytuł + inny adres → realna zmiana adresu")
    o = _offer()
    m._update_existing_offer(o, _processed(
        'Husarska', 'Husarska',
        title='Pokój 1 osobowy, ul. Husarska, Czuby',
        description='Pokój 1 osobowy, ul. Husarska, Czuby Lublin zupełnie inny opis oferty.'))
    check('adres podmieniony', o['address']['full'] == 'Husarska', o['address']['full'])
    check('wpis w versions[]', len(o.get('versions', [])) == 1, str(o.get('versions')))
    check('address_change_count == 1', o.get('address_change_count') == 1)
    check('BRAK wpisu w address_corrections', not o.get('address_corrections'))

    print("\n3️⃣  Powrót do poprzedniego adresu → pominięte (anty-migotanie)")
    o = _offer()
    m._update_existing_offer(o, _processed('Kaprysowa', 'Kaprysowa'))
    m._update_existing_offer(o, _processed('Braci Wieniawskich', 'Braci Wieniawskich'))
    check('adres NIE wrócił', o['address']['full'] == 'Kaprysowa', o['address']['full'])
    check('tylko jedna korekta', len(o.get('address_corrections', [])) == 1)

    print("\n4️⃣  Opis pominiętej oferty (doklejony tytuł) to NIE zmiana tekstu")
    o = _offer()
    check('_source_text_changed == False',
          not m._source_text_changed(o, _processed('Kaprysowa', 'Kaprysowa')))
    check('_source_text_changed == True dla realnej edycji opisu',
          m._source_text_changed(o, _processed(
              'Kaprysowa', 'Kaprysowa',
              description='Pokój 1 osobowy Lublin wynajmę od zaraz, przeprowadzka na ul. Nową 5.')))

    print("\n" + "=" * 60)
    if failed:
        print(f"❌ Niezaliczone: {len(failed)} → {', '.join(failed)}")
        return 1
    print("✅ Korekty adresu zachowują się zgodnie z kontraktem.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
