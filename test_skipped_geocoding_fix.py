"""
Test regresyjny — oferty z `skipped_debug` (no_coords) które miały adres w treści,
ale nie trafiały na mapę.

Geneza (2026-06-09): Mateusz zgłosił 5 ogłoszeń z `skipped_debug`, w których adres
był jawnie w treści, a mimo to były pomijane (kategoria no_coords):

  1. ul. Chmielewskiego           — parser OK, transient fail geokodera
  2. Paganiniego 4                — parser brał "Adres Paganiniego 4" (słowo "Adres"!)
  3. ul. Wilczej (Bronowice)      — dopełniacz, mianownik "Wilcza" działa
  4. ul. Narutowicza              — parser brał "Gabriela Narutowicza 50" → centroid poza Lublinem
  5. ul. Bursztynowa              — parser brał śmieci "Głęboka Samochód 9m"

Dwie naprawy:
  A) EXCLUDED_WORDS += {adres*, samochód*, auto*} — słowa nigdy nie będące ulicą,
     które parser wciągał jako (pierwszy/drugi) człon nazwy ulicy.
  B) _process_offer → _geocode_with_fallbacks: gdy główny (exact) adres nie geokoduje
     się, próbujemy KOLEJNYCH ekstraktorów (street_only / whitelist / district)
     zanim porzucimy ofertę.

Test jest OFFLINE — używa stub-geocodera (mapa adres→coords), więc działa w CI
bez sieci/Nominatim.
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from address_parser import AddressParser, _apd  # noqa: E402
from main import SonarPokojowy  # noqa: E402

CACHE_PATH = os.path.join(os.path.dirname(__file__), 'data', 'geocoding_cache.json')

# Współrzędne (przybliżone, w bbox Lublina) dla adresów które REALNIE geokodują się.
# Klucz = string przekazywany do geocoder.geocode_address (czyli address['full']).
GEOCODABLE = {
    'Chmielewskiego':  {'lat': 51.2382, 'lon': 22.5438},
    'Paganiniego 4':   {'lat': 51.2561, 'lon': 22.5509},
    'Paganiniego':     {'lat': 51.2572, 'lon': 22.5518},
    'Wilczej':         {'lat': 51.2241, 'lon': 22.5856},  # geocoder robi mianownik wewn.
    'Wilcza':          {'lat': 51.2241, 'lon': 22.5856},
    'Narutowicza':     {'lat': 51.2458, 'lon': 22.5604},
    'Narutowicza 50':  {'lat': 51.2425, 'lon': 22.5562},
    'Bursztynowa':     {'lat': 51.2230, 'lon': 22.5093},
    'Chodźki':         {'lat': 51.2618, 'lon': 22.5640},
}

# Adresy które NIE geokodują się do punktu w Lublinie (zwracają None).
# To właśnie błędne wyniki parsera, które wcześniej zabijały oferty.
NON_GEOCODABLE = {
    'Adres Paganiniego 4',
    'Adres Paganini 4',
    'Gabriela Narutowicza 50',
    'Gabriela Narutowicza',
    'Głęboka Samochód 9m',
    'Głęboka Samochód',
}


class StubGeocoder:
    """Geocoder offline: zwraca coords z GEOCODABLE, None dla reszty."""
    def geocode_address(self, address, max_retries=3, return_meta=False):
        coords = GEOCODABLE.get(address)
        meta = {'number_fallback': False, 'cache_hit': coords is not None}
        if return_meta:
            return coords, meta
        return coords


# Realne teksty ofert (tytuł + fragment opisu z skipped_offers_sample.json, 2026-06-09)
OFFERS = [
    {
        'name': 'Paganiniego 4 (slowo "Adres")',
        'title': 'Wynajmę Pokój Lublin Czechów',
        'description': ('Lublin Czechów 25 m2 Paganiniego dla 1 lub 2 studentek '
                        'Wynajmę duży pokój 25 m2 z dużym balkonem dla jednej lub dwóch '
                        'studentek Adres Paganiniego 4, bliski Czechów, w mieszkaniu 60m2, '
                        'na 1 piętrze. Cena 600 zł za osobę przy 2 osobach plus prąd i woda.'),
        'expected_street_substr': 'Paganiniego',
    },
    {
        'name': 'Chmielewskiego',
        'title': 'Pokój dwuosobowy przy UP , blisko UMCS ,KUL',
        'description': ('Lublin Do wynajęcia pokoje w domu ul. Chmielewskiego  Lublin, '
                        'w bezpośrednim sąsiedztwie UP, blisko Politechniki i UMCS. '
                        'Duży pokój 2 osobowy 1200zł/mc plus opłaty.'),
        'expected_street_substr': 'Chmielewskiego',
    },
    {
        'name': 'Wilczej / Bronowice (dopełniacz)',
        'title': 'Pokoje do wynajęcia, nowy dom, miejsca parkingowe',
        'description': ('Lublin Samodzielny (zamykany) pokój w nowo wybudowanym domku '
                        '(bez właściciela), na ul. Wilczej (Bronowice). Domek z parkingiem '
                        'na 3 samochody i ogródkiem.'),
        'expected_street_substr': 'Wilcz',  # Wilczej lub Wilcza
    },
    {
        'name': 'Narutowicza (imie "Gabriela")',
        'title': 'Pokój do wynajęcia  przy ul. Narutowicza',
        'description': ('Lublin Cześć, mam do wynajęcia pokój 1-osobowy w mieszkaniu '
                        '4 pokojowym przy ulicy Gabriela Narutowicza 50. Mieszkanie jest '
                        'położone w centrum Lublina. GDZIE: ul. Narutowicza.'),
        'expected_street_substr': 'Narutowicza',
    },
    {
        'name': 'Bursztynowa (smieci "Głęboka Samochód")',
        'title': 'Pokój dla studentki',
        'description': ('Lublin Wynajmę pokój jednoosobowy dla studentki. 650 za pokój '
                        'plus opłaty lublin ul. Bursztynowa niedaleko do biedronki, '
                        'stokrotka, pętli autobusów, osiedle Czuby. Dojazd samochodem '
                        'na uczelnie ok. Pokój ma ok 9m.'),
        'expected_street_substr': 'Bursztynowa',
    },
    {
        'name': 'Chodźki (prywatny akademik)',
        'title': 'Pokój w prywatnym akademiku przy ul. Chodźki',
        'description': ('Lublin Zapraszamy do zapoznania się z ofertą wynajmu pokoju '
                        'w prywatnym domu studenckim, zlokalizowanym przy ul. Chodźki. '
                        'Pokój jest jednoosobowy, przestronny z dostępem do łazienki '
                        'i kuchni. Opłata w wysokości 1680zł obejmuje miesięczny czynsz.'),
        'expected_street_substr': 'Chodźki',
    },
]


def _make_stub_processor():
    """Lekki stub SonarPokojowy: tylko address_parser + (stub) geocoder."""
    parser = AddressParser(geocoding_cache_path=CACHE_PATH)
    return SimpleNamespace(address_parser=parser, geocoder=StubGeocoder())


def test_excluded_words_hygiene():
    """'adres' i 'samochód' (oraz odmiany) muszą być na blackliście."""
    fails = []
    for w in ['adres', 'adresie', 'samochód', 'samochodem', 'auto']:
        if w not in _apd.EXCLUDED_WORDS:
            fails.append(w)
    assert not fails, f"Brak w EXCLUDED_WORDS: {fails}"


def test_parser_never_returns_garbage_street():
    """
    Parser nie może zwrócić ulicy zaczynającej się od 'Adres ' ani zawierającej
    'samochód' (naprawa A — EXCLUDED_WORDS).

    UWAGA: przypadek "Gabriela Narutowicza 50" NIE jest tu sprawdzany — parser nie
    odróżni imienia od nazwy ulicy bez wiedzy zewnętrznej. Ten przypadek pokrywa
    naprawa B (fallback geokodera) — patrz test_geocode_with_fallbacks_places_all_offers.
    """
    parser = AddressParser(geocoding_cache_path=CACHE_PATH)
    fails = []
    for o in OFFERS:
        txt = o['title'] + ' ' + o['description']
        ea = parser.extract_address(txt)
        if ea:
            full = ea['full']
            if full.lower().startswith('adres ') or 'samochód' in full.lower():
                fails.append((o['name'], full))
    assert not fails, f"Parser zwrócił śmieciowe adresy: {fails}"


def test_geocode_with_fallbacks_places_all_offers():
    """
    KLUCZOWY test: każda z 5 ofert MUSI dostać współrzędne przez
    _geocode_with_fallbacks (z poprawną ulicą), mimo że główny ekstraktor
    czasem daje błędny adres.
    """
    proc = _make_stub_processor()
    fails = []
    for o in OFFERS:
        full_text = o['title'] + ' ' + o['description']
        raw_offer = {'title': o['title'], 'description': o['description']}

        # Symuluj główny etap _process_offer: extract_address → precision='exact',
        # z fallbackiem do street_only / whitelist / district.
        address_data = proc.address_parser.extract_address(full_text)
        precision = 'exact'
        if not address_data:
            so = proc.address_parser.extract_street_only(full_text)
            if so:
                address_data, precision = so, 'street_only'
        if not address_data:
            wl = proc.address_parser.extract_from_whitelist(full_text)
            if wl:
                address_data, precision = wl, 'street_only'
        if not address_data:
            dd = proc.address_parser.extract_district(full_text)
            if dd:
                address_data, precision = dd, 'district'

        assert address_data, f"[{o['name']}] żaden ekstraktor nie znalazł adresu"

        coords, chosen, prec = SonarPokojowy._geocode_with_fallbacks(
            proc, address_data, precision, full_text, raw_offer
        )

        if not coords:
            fails.append((o['name'], 'BRAK COORDS', address_data['full']))
            continue
        if o['expected_street_substr'].lower() not in chosen['full'].lower():
            fails.append((o['name'], f"zła ulica: {chosen['full']}",
                          f"oczekiwano substr {o['expected_street_substr']}"))

    assert not fails, "Oferty nie trafiły na mapę / zła ulica:\n" + \
        "\n".join(f"  - {f}" for f in fails)


def test_fallback_only_triggers_on_geocode_failure():
    """
    Gdy główny adres geokoduje się — fallback NIE może go nadpisać innym ekstraktorem.
    """
    proc = _make_stub_processor()
    # Główny adres 'Narutowicza 50' geokoduje się → musi zostać użyty, nie street_only.
    address_data = {'full': 'Narutowicza 50', 'street': 'Narutowicza', 'number': '50'}
    full_text = 'Pokój przy ul. Narutowicza 50, blisko ul. Bursztynowa'
    raw_offer = {'title': 'Pokój', 'description': full_text}
    coords, chosen, prec = SonarPokojowy._geocode_with_fallbacks(
        proc, address_data, 'exact', full_text, raw_offer
    )
    assert coords is not None
    assert chosen['full'] == 'Narutowicza 50', f"nadpisano główny adres: {chosen['full']}"
    assert prec == 'exact'


class TransientGeocoder:
    """Geocoder który ZAWSZE zwraca transient_error (symulacja chwilowego błędu)."""
    def geocode_address(self, address, max_retries=3, return_meta=False):
        meta = {'number_fallback': False, 'cache_hit': False, 'transient_error': True}
        return (None, meta) if return_meta else None


def test_transient_error_sets_flag():
    """
    Gdy geokoder pada na TYMCZASOWY błąd (timeout/429), _geocode_with_fallbacks
    musi ustawić self._geocode_transient=True (run_scan użyje tego do kolejki retry),
    a NIE liczyć oferty od razu jako no_coords.
    """
    parser = AddressParser(geocoding_cache_path=CACHE_PATH)
    proc = SimpleNamespace(address_parser=parser, geocoder=TransientGeocoder(),
                           _geocode_transient=False)
    address_data = {'full': 'Chodźki', 'street': 'Chodźki', 'number': None}
    full_text = 'Pokój przy ul. Chodźki'
    raw_offer = {'title': 'Pokój', 'description': full_text}
    coords, chosen, prec = SonarPokojowy._geocode_with_fallbacks(
        proc, address_data, 'street_only', full_text, raw_offer
    )
    assert coords is None, "przy transient-failu nie powinno być coords"
    assert proc._geocode_transient is True, "flaga _geocode_transient nie ustawiona"


def test_no_transient_flag_on_genuine_miss():
    """
    Gdy geokoder zwraca None BEZ transient (adres realnie nieznany), flaga
    _geocode_transient zostaje False — oferta trafi do no_coords, nie do retry.
    """
    parser = AddressParser(geocoding_cache_path=CACHE_PATH)
    # Stub: None bez transient_error
    class MissGeo:
        def geocode_address(self, address, max_retries=3, return_meta=False):
            meta = {'number_fallback': False, 'cache_hit': False, 'transient_error': False}
            return (None, meta) if return_meta else None
    proc = SimpleNamespace(address_parser=parser, geocoder=MissGeo(),
                           _geocode_transient=False)
    address_data = {'full': 'Nieistniejąca 999', 'street': 'Nieistniejąca', 'number': '999'}
    full_text = 'Pokój'
    raw_offer = {'title': 'Pokój', 'description': ''}
    coords, _, _ = SonarPokojowy._geocode_with_fallbacks(
        proc, address_data, 'exact', full_text, raw_offer
    )
    assert coords is None
    assert proc._geocode_transient is False, "false-positive transient na realnym miss"


def _run():
    tests = [
        test_excluded_words_hygiene,
        test_parser_never_returns_garbage_street,
        test_geocode_with_fallbacks_places_all_offers,
        test_fallback_only_triggers_on_geocode_failure,
        test_transient_error_sets_flag,
        test_no_transient_flag_on_genuine_miss,
    ]
    passed = 0
    failed = 0
    print("🧪 TEST: skipped no_coords offers (adres w treści, brak na mapie)\n")
    for t in tests:
        try:
            t()
            print(f"✅ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"❌ {t.__name__}\n   {e}")
            failed += 1
    print(f"\n📊 {passed} OK / {failed} FAIL")
    return failed == 0


if __name__ == "__main__":
    ok = _run()
    sys.exit(0 if ok else 1)
