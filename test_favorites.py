#!/usr/bin/env python3
"""
Test trackera ulubionych (docs/ulubione.html) — wykrywanie ofert zdjętych z OLX.

Pilnuje tego, co w 09.2026 było zepsute: OLX odpowiada na zdjętą ofertę
410 Gone, a tracker uznawał wszystko poza 200/404 za błąd sieci i NIE zapisywał
snapshotu. Wpis zamarzał na ostatnim pomiarze i świecił "AKTYWNA" bez końca
(ID1bKFSC: ostatni pomiar 22.08, karta aktywna 04.09 — 13 z 27 ulubionych
miało ten sam objaw).
"""

import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

import api_generator as ag
import favorites_generator as fg
import favorites_tracker as ft

FAILED = []


def check(label, condition, detail=''):
    print(f"   {'✅' if condition else '❌'} {label}" + (f" — {detail}" if detail else ''))
    if not condition:
        FAILED.append(label)


class FakeResponse:
    def __init__(self, status_code, text=''):
        self.status_code = status_code
        self.text = text


def with_status(status_code, text=''):
    """Podmiana sesji HTTP trackera na atrapę o zadanym kodzie odpowiedzi."""
    class FakeSession:
        def head(self, *a, **kw):
            return FakeResponse(status_code)

        def get(self, *a, **kw):
            return FakeResponse(status_code, text)
    ft._session = FakeSession()


# Strona oferty w kształcie, w jakim oddaje ją OLX: cena i tytuł w JSON-LD,
# daty i status w zaescape'owanym __PRERENDERED_STATE__. Na początku DEKOY —
# "status" z tłumaczeń UI, którego parser NIE może złapać (w HTML-u OLX-a jest
# takich kilkanaście przed właściwym blokiem oferty).
PAGE_HTML = (
    '<html><head><title>Ładny pokój jednoosobowy Lublin • OLX.pl</title>'
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"Product",'
    '"name":"Ładny pokój jednoosobowy",'
    '"offers":{"@type":"Offer","availability":"https://schema.org/InStock",'
    '"priceCurrency":"PLN","price":825}}'
    '</script></head><body>'
    '<script>window.i18n = "\\"priceNegotiation.status\\":\\"ZAAKCEPTOWANO\\""</script>'
    + 'x' * 2000 +
    '<script>window.__PRERENDERED_STATE__ = "'
    '\\"createdTime\\":\\"2026-11-04T14:28:56+01:00\\",'
    '\\"lastRefreshTime\\":\\"2026-11-11T14:30:01+01:00\\",'
    '\\"pushupTime\\":null,'
    '\\"validToTime\\":\\"2026-12-04T14:29:56+01:00\\",'
    '\\"isActive\\":true,\\"status\\":\\"active\\""</script>'
    '</body></html>'
)


def snapshot(ts, status='active', price=2500, views=None):
    return {'ts': ts, 'status': status, 'price': price,
            'last_refresh': '2026-08-06T22:19:04+02:00', 'pushup': '',
            'valid_to': '2026-09-05T22:16:45+02:00',
            'created': '2026-08-06T22:00:33+02:00', 'views': views, 'page': None}


def test_http_codes():
    print("\n🌐 Test 1: snapshot ze strony oferty (po blokadzie API v1)")
    original = ft._session
    try:
        with_status(410)
        check("410 Gone = oferta zdjęta z OLX",
              ft.fetch_page_snapshot('u')['status'] == 'removed')
        with_status(404)
        check("404 = oferta zdjęta z OLX",
              ft.fetch_page_snapshot('u')['status'] == 'removed')
        with_status(403)
        check("403 (WAF) = brak snapshotu, nie fałszujemy historii",
              ft.fetch_page_snapshot('u') is None)
        with_status(500)
        check("500 = brak snapshotu", ft.fetch_page_snapshot('u') is None)

        with_status(200, PAGE_HTML)
        snap = ft.fetch_page_snapshot('u')
        check("200 = snapshot ze stanu strony", snap is not None)
        check("status z bloku oferty, nie z tłumaczeń UI",
              snap['status'] == 'active', snap['status'])
        check("cena z JSON-LD", snap['price'] == 825, str(snap['price']))
        check("tytuł z JSON-LD (bez ' • OLX.pl')",
              snap['title'] == 'Ładny pokój jednoosobowy', snap['title'])
        check("odświeżenie — to po nie tu przyszliśmy",
              snap['last_refresh'] == '2026-11-11T14:30:01+01:00', snap['last_refresh'])
        check("data wystawienia", snap['created'] == '2026-11-04T14:28:56+01:00')
        check("data ważności", snap['valid_to'] == '2026-12-04T14:29:56+01:00')
        check("pushupTime: null = pusty string (jak w API)",
              snap['pushup'] == '', repr(snap['pushup']))

        # Interstitial WAF-a / zgoda na ciasteczka: HTTP 200, ale bez oferty.
        with_status(200, '<html><body>Potwierdź, że jesteś człowiekiem</body></html>')
        check("200 bez danych oferty = brak snapshotu (nie pusta karta)",
              ft.fetch_page_snapshot('u') is None)
    finally:
        ft._session = original


def test_no_duplicate_removed_snapshots():
    print("\n🔁 Test 2: zdjęta oferta nie mnoży snapshotów")
    fresh = {'snapshots': []}
    already = {'snapshots': [snapshot('2026-08-22T08:39:33+02:00'),
                             snapshot('2026-09-04T12:50:00+02:00', status='removed', price=None)]}
    check("wpis bez pomiarów ma pusty status", ft.last_snapshot_status(fresh) == '')
    check("wpis zdjętej oferty raportuje 'removed'",
          ft.last_snapshot_status(already) == 'removed')
    check("wpis żywej oferty raportuje 'active'",
          ft.last_snapshot_status({'snapshots': [snapshot('2026-09-04T12:50:00+02:00')]}) == 'active')

    # pełny przebieg trackera na atrapach: zdjęta (410) + żywa (200)
    tracking = {
        'ZDJETA': {'url': 'u1', 'numeric_id': 1, 'added': '2026-08-06', 'title': 'zdjęta',
                   'snapshots': [snapshot('2026-08-22T08:39:33+02:00'),
                                 snapshot('2026-09-04T12:50:00+02:00', status='removed', price=None)]},
        'ZYWA': {'url': 'u2', 'numeric_id': 2, 'added': '2026-08-06', 'title': 'żywa',
                 'snapshots': [snapshot('2026-09-04T12:50:00+02:00')]},
    }
    pages = {'u1': {'status': 'removed'},
             'u2': {'status': 'active', 'price': 1300, 'title': 'żywa', 'last_refresh': '',
                    'pushup': '', 'created': '', 'valid_to': ''}}
    views_seen = []
    saved = {}
    originals = (ft.load_favorites, ft.load_tracking, ft.load_listing_positions,
                 ft.fetch_views, ft.fetch_page_snapshot, ft.write_json_atomic)
    try:
        ft.load_favorites = lambda: [{'short_id': 'ZDJETA', 'numeric_id': 1, 'url': 'u1'},
                                     {'short_id': 'ZYWA', 'numeric_id': 2, 'url': 'u2'}]
        ft.load_tracking = lambda: tracking
        ft.load_listing_positions = lambda: {}
        ft.fetch_views = lambda favs: (views_seen.extend(f['short_id'] for f in favs), {})[1]
        ft.fetch_page_snapshot = lambda url: pages[url]
        ft.write_json_atomic = lambda path, data: saved.update({str(path): data})
        ft.track_favorites()
    finally:
        (ft.load_favorites, ft.load_tracking, ft.load_listing_positions,
         ft.fetch_views, ft.fetch_page_snapshot, ft.write_json_atomic) = originals

    check("zdjęta oferta pominięta w kosztownym pomiarze wyświetleń",
          views_seen == ['ZYWA'], str(views_seen))
    check("zdjęta oferta nie dostała drugiego snapshotu 'removed'",
          len(tracking['ZDJETA']['snapshots']) == 2, str(len(tracking['ZDJETA']['snapshots'])))
    check("żywa oferta dostała nowy pomiar",
          len(tracking['ZYWA']['snapshots']) == 2, str(len(tracking['ZYWA']['snapshots'])))
    check("wynik zapisany na dysk", str(ft.TRACKING_FILE) in saved)
    status = saved.get(str(ft.STATUS_FILE), {})
    check("meldunek dla API: 2 wpisy, 2 zmierzone, 0 bez pomiaru",
          (status.get('tracked'), status.get('measured'), status.get('failed')) == (2, 2, 0),
          str(status))

    # oferta zdjęta PO RAZ PIERWSZY dostaje snapshot 'removed' (odmrożenie wpisu)
    first_removal = {'ZDJETA': dict(tracking['ZDJETA'],
                                    snapshots=[snapshot('2026-08-22T08:39:33+02:00')])}
    try:
        ft.load_favorites = lambda: [{'short_id': 'ZDJETA', 'numeric_id': 1, 'url': 'u1'}]
        ft.load_tracking = lambda: first_removal
        ft.load_listing_positions = lambda: {}
        ft.fetch_views = lambda favs: {}
        ft.fetch_page_snapshot = lambda url: {'status': 'removed'}
        ft.write_json_atomic = lambda path, data: None
        ft.track_favorites()
    finally:
        (ft.load_favorites, ft.load_tracking, ft.load_listing_positions,
         ft.fetch_views, ft.fetch_page_snapshot, ft.write_json_atomic) = originals
    snaps = first_removal['ZDJETA']['snapshots']
    check("pierwsze zniknięcie zapisane jako snapshot 'removed'",
          len(snaps) == 2 and snaps[-1]['status'] == 'removed', str(snaps[-1].get('status')))


def test_card_after_removal():
    print("\n🃏 Test 3: karta oferty zdjętej z OLX")
    entry = {
        'url': 'https://www.olx.pl/d/oferta/x-CID3-ID1bKFSC.html',
        'numeric_id': 1089796606, 'added': '2026-08-06',
        'title': 'Mieszkanie 2 pokoje, Lublin Centrum Najem',
        'snapshots': [snapshot('2026-08-21T21:27:28+02:00', views=439),
                      snapshot('2026-08-22T08:39:33+02:00', views=445),
                      {'ts': '2026-09-04T12:50:00+02:00', 'status': 'removed',
                       'price': None, 'last_refresh': '', 'pushup': '',
                       'valid_to': '', 'created': '', 'views': None, 'page': None}],
    }
    # oferta spoza bazy (mieszkanie — listing pokoi jej nie skanuje)
    card = fg._build_favorite('1bKFSC', entry, None)
    check("status = removed (badge 'Usunięta z OLX')", card['status'] == 'removed', card['status'])
    check("cena z ostatniego realnego pomiaru", card['current_price'] == 2500,
          str(card['current_price']))
    check("data wystawienia nie zniknęła", card['created'] == '06.08.2026 22:00', card['created'])
    check("data ważności nie zniknęła", card['valid_to'] == '05.09.2026 22:16', card['valid_to'])
    check("historia wyświetleń nietknięta", [v['views'] for v in card['views_history']] == [439, 445])
    check("sprawdzona = dzień wykrycia zniknięcia",
          card['last_checked'] == '04.09.2026 12:50', card['last_checked'])

    # 410 bije bazę, która nie zdążyła jeszcze zdeaktywować oferty
    card_db = fg._build_favorite('1bKFSC', entry, {'id': 'x-ID1bKFSC', 'active': True})
    check("410 wygrywa z active:True w offers.json", card_db['status'] == 'removed',
          card_db['status'])

    # oferta żywa dalej działa jak wcześniej
    alive = dict(entry, snapshots=entry['snapshots'][:2])
    check("żywa oferta spoza bazy zostaje aktywna",
          fg._build_favorite('1bKFSC', alive, None)['status'] == 'active')
    check("baza z active:False daje 'inactive'",
          fg._build_favorite('1bKFSC', alive, {'id': 'x', 'active': False})['status'] == 'inactive')


def test_api_alert():
    """Czego zabrakło 06–11.11.2026: przez 15 skanów nikt nie krzyknął, że
    pomiary ulubionych nie wchodzą (OLX zablokował API v1 → 403)."""
    print("\n🚨 Test 4: alert w API, gdy pomiar ulubionych nie wchodzi")
    original_data_dir = ag.DATA_DIR
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ag.DATA_DIR = tmp
        gen = ag.APIGenerator(output_dir=str(tmp / 'api'))
        now = __import__('datetime').datetime.now(gen.tz)

        def status(**kw):
            (tmp / 'favorites_status.json').write_text(
                json.dumps(kw, default=str), encoding='utf-8')

        try:
            # a) komplet pomiarów — cisza w eterze
            status(checked_at=now.isoformat(), tracked=28, measured=28,
                   failed=0, failed_ids=[], last_snapshot_at=now.isoformat())
            check("komplet pomiarów = brak alertu", gen._favorites_alert() is None)

            # b) część ofert bez pomiaru — ostrzeżenie JUŻ w tym skanie
            status(checked_at=now.isoformat(), tracked=28, measured=26, failed=2,
                   failed_ids=['1d6ZfZ', '1bw9sZ'], last_snapshot_at=now.isoformat())
            alert = gen._favorites_alert()
            check("2 z 28 bez pomiaru = warning",
                  alert and alert['severity'] == 'warning', str(alert and alert['severity']))
            check("alert nazywa po imieniu, czego brakuje",
                  alert and 'odświeżenia' in alert['message'], alert['message'])
            check("alert niesie ID-ki, które padły",
                  alert['details']['failedIds'] == ['1d6ZfZ', '1bw9sZ'])

            # c) scenariusz 06.11: 403 na wszystko — critical natychmiast,
            #    bez czekania aż dane się zestarzeją
            status(checked_at=now.isoformat(), tracked=28, measured=0, failed=28,
                   failed_ids=['1d6ZfZ'], last_snapshot_at=now.isoformat())
            alert = gen._favorites_alert()
            check("zero pomiarów = critical w tym samym skanie",
                  alert and alert['severity'] == 'critical', str(alert and alert['severity']))

            # d) tracker w ogóle nie zameldował, a karty stoją sprzed 6 dni
            (tmp / 'favorites_status.json').unlink()
            old = (now - timedelta(days=6)).isoformat()
            (tmp / 'favorites_tracking.json').write_text(json.dumps(
                {'1d6ZfZ': {'snapshots': [{'ts': old, 'status': 'active'}]}}),
                encoding='utf-8')
            alert = gen._favorites_alert()
            check("brak meldunku + pomiar sprzed 6 dni = critical",
                  alert and alert['severity'] == 'critical', str(alert and alert['severity']))
            check("alert podaje wiek danych",
                  alert and round(alert['details']['hoursSinceSnapshot']) == 144,
                  str(alert and alert['details']['hoursSinceSnapshot']))

            # e) świeży pomiar w pliku śledzenia = cisza
            (tmp / 'favorites_tracking.json').write_text(json.dumps(
                {'1d6ZfZ': {'snapshots': [{'ts': now.isoformat(), 'status': 'active'}]}}),
                encoding='utf-8')
            check("świeży pomiar = brak alertu", gen._favorites_alert() is None)

            # f) brak ulubionych w ogóle — nie ma o co bić na alarm
            (tmp / 'favorites_tracking.json').unlink()
            check("brak ulubionych = brak alertu", gen._favorites_alert() is None)
        finally:
            ag.DATA_DIR = original_data_dir


if __name__ == '__main__':
    print("🧪 TEST ULUBIONYCH\n" + "=" * 60)
    test_http_codes()
    test_no_duplicate_removed_snapshots()
    test_card_after_removal()
    test_api_alert()
    print("\n" + "=" * 60)
    if FAILED:
        print(f"❌ Niezaliczone ({len(FAILED)}): " + ', '.join(FAILED))
        sys.exit(1)
    print("✅ Wszystkie testy ulubionych przeszły.")
