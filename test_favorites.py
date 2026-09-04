#!/usr/bin/env python3
"""
Test trackera ulubionych (docs/ulubione.html) — wykrywanie ofert zdjętych z OLX.

Pilnuje tego, co w 09.2026 było zepsute: OLX odpowiada na zdjętą ofertę
410 Gone, a tracker uznawał wszystko poza 200/404 za błąd sieci i NIE zapisywał
snapshotu. Wpis zamarzał na ostatnim pomiarze i świecił "AKTYWNA" bez końca
(ID1bKFSC: ostatni pomiar 22.08, karta aktywna 04.09 — 13 z 27 ulubionych
miało ten sam objaw).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

import favorites_generator as fg
import favorites_tracker as ft

FAILED = []


def check(label, condition, detail=''):
    print(f"   {'✅' if condition else '❌'} {label}" + (f" — {detail}" if detail else ''))
    if not condition:
        FAILED.append(label)


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def with_status(status_code, payload=None):
    """Podmiana sesji HTTP trackera na atrapę o zadanym kodzie odpowiedzi."""
    class FakeSession:
        def get(self, *a, **kw):
            return FakeResponse(status_code, payload)
    ft._session = FakeSession()


def snapshot(ts, status='active', price=2500, views=None):
    return {'ts': ts, 'status': status, 'price': price,
            'last_refresh': '2026-08-06T22:19:04+02:00', 'pushup': '',
            'valid_to': '2026-09-05T22:16:45+02:00',
            'created': '2026-08-06T22:00:33+02:00', 'views': views, 'page': None}


def test_http_codes():
    print("\n🌐 Test 1: kody HTTP z API OLX")
    original = ft._session
    try:
        with_status(410)
        check("410 Gone = oferta zdjęta z OLX",
              ft.fetch_api_snapshot(1)['status'] == 'removed')
        with_status(404)
        check("404 = oferta zdjęta z OLX",
              ft.fetch_api_snapshot(1)['status'] == 'removed')
        with_status(403)
        check("403 (WAF) = brak snapshotu, nie fałszujemy historii",
              ft.fetch_api_snapshot(1) is None)
        with_status(500)
        check("500 = brak snapshotu", ft.fetch_api_snapshot(1) is None)
        with_status(200, {'data': {'status': 'active', 'title': 'Pokój',
                                   'params': [{'key': 'price', 'value': {'value': 1200}}]}})
        snap = ft.fetch_api_snapshot(1)
        check("200 = normalny snapshot z ceną",
              snap['status'] == 'active' and snap['price'] == 1200, str(snap))
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
        'ZDJETA': {'url': 'u', 'numeric_id': 1, 'added': '2026-08-06', 'title': 'zdjęta',
                   'snapshots': [snapshot('2026-08-22T08:39:33+02:00'),
                                 snapshot('2026-09-04T12:50:00+02:00', status='removed', price=None)]},
        'ZYWA': {'url': 'u', 'numeric_id': 2, 'added': '2026-08-06', 'title': 'żywa',
                 'snapshots': [snapshot('2026-09-04T12:50:00+02:00')]},
    }
    api = {1: {'status': 'removed'},
           2: {'status': 'active', 'price': 1300, 'title': 'żywa', 'last_refresh': '',
               'pushup': '', 'created': '', 'valid_to': ''}}
    views_seen = []
    saved = {}
    originals = (ft.load_favorites, ft.load_tracking, ft.load_listing_positions,
                 ft.fetch_views, ft.fetch_api_snapshot, ft.write_json_atomic)
    try:
        ft.load_favorites = lambda: [{'short_id': 'ZDJETA', 'numeric_id': 1, 'url': 'u'},
                                     {'short_id': 'ZYWA', 'numeric_id': 2, 'url': 'u'}]
        ft.load_tracking = lambda: tracking
        ft.load_listing_positions = lambda: {}
        ft.fetch_views = lambda favs: (views_seen.extend(f['short_id'] for f in favs), {})[1]
        ft.fetch_api_snapshot = lambda nid: api[nid]
        ft.write_json_atomic = lambda path, data: saved.update({'path': path, 'data': data})
        ft.track_favorites()
    finally:
        (ft.load_favorites, ft.load_tracking, ft.load_listing_positions,
         ft.fetch_views, ft.fetch_api_snapshot, ft.write_json_atomic) = originals

    check("zdjęta oferta pominięta w kosztownym pomiarze wyświetleń",
          views_seen == ['ZYWA'], str(views_seen))
    check("zdjęta oferta nie dostała drugiego snapshotu 'removed'",
          len(tracking['ZDJETA']['snapshots']) == 2, str(len(tracking['ZDJETA']['snapshots'])))
    check("żywa oferta dostała nowy pomiar",
          len(tracking['ZYWA']['snapshots']) == 2, str(len(tracking['ZYWA']['snapshots'])))
    check("wynik zapisany na dysk", saved.get('path') == ft.TRACKING_FILE)

    # oferta zdjęta PO RAZ PIERWSZY dostaje snapshot 'removed' (odmrożenie wpisu)
    first_removal = {'ZDJETA': dict(tracking['ZDJETA'],
                                    snapshots=[snapshot('2026-08-22T08:39:33+02:00')])}
    try:
        ft.load_favorites = lambda: [{'short_id': 'ZDJETA', 'numeric_id': 1, 'url': 'u'}]
        ft.load_tracking = lambda: first_removal
        ft.load_listing_positions = lambda: {}
        ft.fetch_views = lambda favs: {}
        ft.fetch_api_snapshot = lambda nid: {'status': 'removed'}
        ft.write_json_atomic = lambda path, data: None
        ft.track_favorites()
    finally:
        (ft.load_favorites, ft.load_tracking, ft.load_listing_positions,
         ft.fetch_views, ft.fetch_api_snapshot, ft.write_json_atomic) = originals
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


if __name__ == '__main__':
    print("🧪 TEST ULUBIONYCH\n" + "=" * 60)
    test_http_codes()
    test_no_duplicate_removed_snapshots()
    test_card_after_removal()
    print("\n" + "=" * 60)
    if FAILED:
        print(f"❌ Niezaliczone ({len(FAILED)}): " + ', '.join(FAILED))
        sys.exit(1)
    print("✅ Wszystkie testy ulubionych przeszły.")
