#!/usr/bin/env python3
"""
Testy sygnałów „od Twojej ostatniej wizyty" na zakładkach firm (profile_tracker).

Regresja z 08.09.2026 (zgłoszenie Mateusza): trzy oferty MAT zostały podbite
o 08:21, lista pokazywała przy nich „↻ odświeżona", ale zakładka MAT nie
dostała plakietki 🔄. Powód: sygnały czytały `refresh_dates`, czyli same DNI
('YYYY-MM-DD'), które parsują się na PÓŁNOC — 08.09 00:00 wypada przed wizytą
o 08.09 08:18, więc podbicie z dnia wizyty było niewidzialne. I to na zawsze:
wpis w liście dni nigdy nie dostanie godziny wstecz.

Test odpala PRAWDZIWY kod z `docs/profile_tracker.html` (wycięte funkcje
uruchamiane w node), a nie jego pythonową imitację — inaczej pilnowałby
własnej kopii logiki, nie tej, która trafia do przeglądarki.

Pilnowane pułapki:
  · podbicie z dnia wizyty, ale PO niej → sygnał musi się zapalić,
  · podbicie z dnia wizyty PRZED nią → sygnał NIE może się zapalić,
  · `last_refresh_date` przy PUSTEJ liście dni (znacznik z pierwszego widzenia,
    sprzed śledzenia bumpów) nie może udawać zdarzenia,
  · reaktywacja z dnia wizyty — to samo, przez `reactivation_dates_iso`,
  · niezmienny warunek fixu: ostatni dzień w `refresh_dates` = dzień
    `last_refresh_date` (inaczej dokładna godzina trafiłaby w zły dzień).
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

import pytz

REPO = os.path.dirname(os.path.abspath(__file__))
TRACKER = os.path.join(REPO, 'docs', 'profile_tracker.html')
PROFILE_DATA = os.path.join(REPO, 'docs', 'profile_data.json')

# Funkcje wycinane z HTML-a i uruchamiane w node. computeSignals woła tylko
# parseAnyDate + shortDate + helpery czasu, więc ten zestaw jest zamknięty.
NEEDED = ['parseAnyDate', 'refreshTimes', 'reactivationTimes', 'shortDate', 'computeSignals']


def extract_js(source, name):
    """Wycina `function name(...) { ... }` — domknięcie to `}` w kolumnie 0.

    Styl pliku: wszystkie funkcje najwyższego poziomu są niewcięte, więc
    pierwsza samotna klamra na początku linii kończy ciało.
    """
    start = source.find('function %s(' % name)
    assert start != -1, 'nie znaleziono function %s() w profile_tracker.html' % name
    end = source.find('\n}\n', start)
    assert end != -1, 'nie znaleziono domknięcia function %s()' % name
    return source[start:end + 3]


def run_js(scenarios):
    """Uruchamia wycięty kod w node i zwraca wynik computeSignals per scenariusz."""
    if not shutil.which('node'):
        print('❌ Brak `node` w PATH — ten test uruchamia prawdziwy kod frontu.')
        print('   Zainstaluj node (w CI jest domyślnie na ubuntu-latest).')
        sys.exit(1)

    html = open(TRACKER, encoding='utf-8').read()
    js = '\n'.join(extract_js(html, n) for n in NEEDED)
    js += """
const IN = %s;
const OUT = IN.map(sc => {
    const S = computeSignals({ offers: sc.offers }, sc.since);
    return { podbicia: S.podbiciaN, podbiciaOfert: S.podbicia.length, powroty: S.powrot.length };
});
console.log(JSON.stringify(OUT));
""" % json.dumps(scenarios, ensure_ascii=False)

    env = dict(os.environ, TZ='Europe/Warsaw')   # znaczniki liczone lokalnie
    res = subprocess.run(['node', '-e', js], capture_output=True, text=True, env=env)
    assert res.returncode == 0, 'node padł:\n%s' % res.stderr
    return json.loads(res.stdout)


# Wizyta z ekranu Mateusza: 08.09.2026 08:18, skan podbił oferty o 08:21.
# Liczone przez pytz, nie wklepane jako stała — pomyłka o rok w epochu dałaby
# test, który przechodzi z zupełnie innego powodu, niż myślisz.
PL_TZ = pytz.timezone('Europe/Warsaw')
VISIT = int(PL_TZ.localize(datetime(2026, 9, 8, 8, 18)).timestamp() * 1000)


def offer(**kw):
    base = {'address': 'Testowa 1', 'active': True, 'first_seen': '01.07.2026 10:00',
            'last_seen': '08.09.2026 12:00', 'price_history': [], 'refresh_dates': [],
            'reactivation_dates': [], 'reactivation_dates_iso': []}
    base.update(kw)
    return base


def test_bump_z_dnia_wizyty():
    print('\n📝 Test 1: podbicie z dnia wizyty, ale PO niej (regresja MAT 08.09)')

    since = VISIT   # 08.09.2026 08:18 Europe/Warsaw
    scenarios = [
        # 1. dokładnie przypadek MAT: ostatni dzień = dzień wizyty, godzina 08:21 > 08:18
        {'since': since, 'offers': [offer(
            refresh_dates=['2026-08-28', '2026-09-08'],
            last_refresh_date='2026-09-08T08:21:35+02:00')]},
        # 2. to samo podbicie, ale o 07:00 — PRZED wizytą, sygnał ma milczeć
        {'since': since, 'offers': [offer(
            refresh_dates=['2026-08-28', '2026-09-08'],
            last_refresh_date='2026-09-08T07:00:00+02:00')]},
        # 3. znacznik z pierwszego widzenia przy PUSTEJ liście dni — to nie zdarzenie
        {'since': since, 'offers': [offer(
            refresh_dates=[],
            last_refresh_date='2026-09-08T09:00:00+02:00')]},
        # 4. dni sprzed wizyty nie zapalają nic, mimo że parsują się na północ
        {'since': since, 'offers': [offer(
            refresh_dates=['2026-09-05', '2026-09-06'],
            last_refresh_date='2026-09-06T21:30:00+02:00')]},
    ]
    out = run_js(scenarios)

    assert out[0]['podbicia'] == 1, 'podbicie z dnia wizyty zgubione: %s' % out[0]
    print('   ✅ podbicie 08:21 po wizycie 08:18 → sygnał 🔄 zapala się')

    assert out[1]['podbicia'] == 0, 'podbicie sprzed wizyty policzone: %s' % out[1]
    print('   ✅ podbicie 07:00 przed wizytą 08:18 → cisza (brak fałszywki)')

    assert out[2]['podbicia'] == 0, 'last_refresh_date bez dnia w liście udało zdarzenie: %s' % out[2]
    print('   ✅ `last_refresh_date` przy pustej liście dni nie jest zdarzeniem')

    assert out[3]['podbicia'] == 0, 'stare dni policzone: %s' % out[3]
    print('   ✅ dni sprzed wizyty nie zapalają sygnału')


def test_bump_liczony_w_zdarzeniach():
    print('\n📝 Test 2: licznik to ZDARZENIA, nie oferty (i dni po wizycie)')

    since = VISIT
    out = run_js([{'since': since, 'offers': [
        offer(address='A', refresh_dates=['2026-09-08'],
              last_refresh_date='2026-09-08T08:21:35+02:00'),
        offer(address='B', refresh_dates=['2026-09-08'],
              last_refresh_date='2026-09-08T08:21:34+02:00'),
        offer(address='C', refresh_dates=['2026-09-08', '2026-09-09'],
              last_refresh_date='2026-09-09T09:10:00+02:00'),
    ]}])[0]

    # C: dzień wizyty (08.09 północ < wizyta, bez dokładnego znacznika — ten ma
    # tylko ostatni dzień) nie wchodzi, 09.09 wchodzi. Razem A+B+C = 3.
    assert out['podbicia'] == 3, out
    assert out['podbiciaOfert'] == 3, out
    print('   ✅ 3 oferty × po jednym podbiciu po wizycie → 3 zdarzenia')


def test_reaktywacja_z_dnia_wizyty():
    print('\n📝 Test 3: reaktywacja z dnia wizyty (♻) — godzina z ISO')

    since = VISIT
    out = run_js([
        # ISO z godziną PO wizycie → sygnał
        {'since': since, 'offers': [offer(
            reactivation_dates=['08.09.2026'],
            reactivation_dates_iso=['2026-09-08T18:01:16.565787+02:00'])]},
        # ISO z godziną PRZED wizytą → cisza
        {'since': since, 'offers': [offer(
            reactivation_dates=['08.09.2026'],
            reactivation_dates_iso=['2026-09-08T06:01:16.565787+02:00'])]},
        # stary payload bez pola ISO → fallback na 'DD.MM.YYYY' (dzień po wizycie)
        {'since': since, 'offers': [offer(
            reactivation_dates=['09.09.2026'], reactivation_dates_iso=[])]},
    ])

    assert out[0]['powroty'] == 1, 'reaktywacja z dnia wizyty zgubiona: %s' % out[0]
    print('   ✅ reaktywacja 18:01 po wizycie 08:18 → sygnał ♻')
    assert out[1]['powroty'] == 0, 'reaktywacja sprzed wizyty policzona: %s' % out[1]
    print('   ✅ reaktywacja 06:01 przed wizytą → cisza')
    assert out[2]['powroty'] == 1, 'fallback na stary payload nie działa: %s' % out[2]
    print('   ✅ payload bez `reactivation_dates_iso` dalej działa (fallback)')


def test_generator_daje_iso():
    print('\n📝 Test 4: generator wystawia `reactivation_dates_iso`')

    data = json.load(open(PROFILE_DATA, encoding='utf-8'))
    seen = 0
    for key in data['profile_keys']:
        for o in data['profiles'][key].get('offers', []):
            iso = o.get('reactivation_dates_iso')
            assert iso is not None, 'brak pola reactivation_dates_iso w %s' % o['id']
            disp = o.get('reactivation_dates') or []
            assert len(iso) == len(disp), 'rozjazd długości list w %s' % o['id']
            for i, d in zip(iso, disp):
                assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', i), 'ISO bez godziny: %r' % i
                # ten sam dzień w obu formatach
                assert i[:10] == '%s-%s-%s' % (d[6:10], d[3:5], d[0:2]), '%r vs %r' % (i, d)
                seen += 1
    print('   ✅ %d dat reaktywacji ma surowe ISO z godziną' % seen)


def test_invariant_ostatniego_dnia():
    print('\n📝 Test 5: ostatni dzień w `refresh_dates` = dzień `last_refresh_date`')

    # Na tym stoi cały fix: dokładny znacznik podstawiamy pod OSTATNI dzień listy.
    # Gdyby `_track_refresh` przestał aktualizować oba pola razem, godzina
    # trafiłaby w zły dzień i sygnał kłamałby zamiast milczeć.
    data = json.load(open(PROFILE_DATA, encoding='utf-8'))
    checked = 0
    for key in data['profile_keys']:
        for o in data['profiles'][key].get('offers', []):
            dates = o.get('refresh_dates') or []
            if not dates:
                continue
            raw = o.get('last_refresh_date') or ''
            assert raw, 'oferta %s ma dni podbić, ale brak last_refresh_date' % o['id']
            assert dates[-1] == raw[:10], \
                '%s: ostatni dzień %s ≠ %s' % (o['id'], dates[-1], raw[:10])
            assert dates == sorted(dates), 'niesortowane refresh_dates w %s' % o['id']
            checked += 1
    print('   ✅ %d ofert z podbiciami — lista dni spójna z dokładnym znacznikiem' % checked)


if __name__ == '__main__':
    print('=' * 64)
    print('SYGNAŁY ODŚWIEŻEŃ NA ZAKŁADKACH FIRM')
    print('=' * 64)
    test_bump_z_dnia_wizyty()
    test_bump_liczony_w_zdarzeniach()
    test_reaktywacja_z_dnia_wizyty()
    test_generator_daje_iso()
    test_invariant_ostatniego_dnia()
    print('\n' + '=' * 64)
    print('✅ WSZYSTKIE TESTY PRZESZŁY')
    print('=' * 64)
