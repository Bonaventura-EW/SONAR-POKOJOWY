"""
Test regresyjny — propagacja z SONAR---DZIA-KOWY (2026-10-07, issue#164).

Tam refiner lokalizacji wywracał się IndexError-em na pustej nazwie ulicy
(`nominative_variants('')`), a wyjątek przerywał main.py PRZED zapisem bazy —
4 z 8 skanów przepadło po cichu (workflow zielony dzięki `|| echo`).

U nas konkretny trigger (`nominative_variants`) nie istnieje — `to_nominative`
(geocoder.py) ma już `if not address`, a `street.split()[...]` w address_parser.py
jest zawsze za `if street and ...`. Ale KSZTAŁT ryzyka był identyczny: pętla
przetwarzania w `run_scan` (main.py) wołała `_process_offer` bez żadnej izolacji
per-oferta, więc nieznany jeszcze edge case w parserze/geokoderze/duplicate_detectorze
ubiłby cały skan tak samo.

Fix: `_process_offer_safe` — wrapper łapiący wyjątek, logujący go (offer_id + URL)
i klasyfikujący ofertę jako `_skip_reason='processing_error'` (nowa kategoria w
skipped_offers_sample.json), zamiast pozwolić mu wylecieć do `run_scan`.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from main import SonarPokojowy  # noqa: E402


class StubScanLogger:
    """Stub bez dotykania pliku — zbiera błędy tak jak prawdziwy ScanLogger.errors."""
    def __init__(self):
        self.errors = []

    def log_error(self, message):
        self.errors.append(message)


def _make_proc(process_offer_impl):
    """Lekki stub SonarPokojowy (bez __init__) — tylko to, czego potrzebuje
    _process_offer_safe: scan_logger + zastąpiona _process_offer."""
    proc = SonarPokojowy.__new__(SonarPokojowy)
    proc.scan_logger = StubScanLogger()
    proc._process_offer = process_offer_impl
    return proc


def test_exception_is_caught_and_classified():
    """Wyjątek z _process_offer NIE wylatuje z _process_offer_safe."""
    def boom(raw_offer):
        raise IndexError("list index out of range")

    proc = _make_proc(boom)
    raw_offer = {'url': 'https://www.olx.pl/d/oferta/x-CID3-IDzzz1.html'}

    result = proc._process_offer_safe(raw_offer, offer_id='IDzzz1')

    assert result is None, "oferta z wyjątkiem musi dać None, nie propagować"
    assert proc._skip_reason == 'processing_error', proc._skip_reason
    assert 'list index out of range' in proc._skip_detail
    assert proc._geocode_transient is False


def test_exception_is_logged_with_offer_id_and_url():
    """Log błędu musi zawierać offer_id i URL — bez tego crash jest cichy."""
    def boom(raw_offer):
        raise ValueError("adres pusty")

    proc = _make_proc(boom)
    raw_offer = {'url': 'https://www.olx.pl/d/oferta/x-CID3-IDzzz2.html'}

    proc._process_offer_safe(raw_offer, offer_id='IDzzz2')

    assert len(proc.scan_logger.errors) == 1
    logged = proc.scan_logger.errors[0]
    assert 'IDzzz2' in logged
    assert raw_offer['url'] in logged
    assert 'adres pusty' in logged


def test_offer_id_derived_from_url_when_not_passed():
    """Gdy offer_id nie podany (ścieżka retry), wyprowadza go z URL-a tak jak pętla główna."""
    def boom(raw_offer):
        raise RuntimeError("fail")

    proc = _make_proc(boom)
    raw_offer = {'url': 'https://www.olx.pl/d/oferta/pokoj-CID3-IDabc9.html'}

    proc._process_offer_safe(raw_offer)

    assert 'IDabc9' in proc.scan_logger.errors[0]


def test_success_passes_through_unchanged():
    """Normalny przypadek (bez wyjątku) — wynik przechodzi bez zmian, zero logów błędu."""
    sentinel = {'address': {'full': 'Chodźki'}, 'price': {'current': 800}}

    def ok(raw_offer):
        return sentinel

    proc = _make_proc(ok)
    raw_offer = {'url': 'https://www.olx.pl/d/oferta/x-CID3-IDok1.html'}

    result = proc._process_offer_safe(raw_offer, offer_id='IDok1')

    assert result is sentinel
    assert proc.scan_logger.errors == []


def test_none_without_exception_passes_through():
    """_process_offer zwracający None zgodnie z własną logiką (np. no_address) —
    _process_offer_safe nie ma prawa tego zamienić na 'processing_error'."""
    def returns_none(raw_offer):
        return None

    proc = _make_proc(returns_none)
    proc._skip_reason = 'no_address'
    raw_offer = {'url': 'https://www.olx.pl/d/oferta/x-CID3-IDok2.html'}

    result = proc._process_offer_safe(raw_offer, offer_id='IDok2')

    assert result is None
    assert proc._skip_reason == 'no_address', "nie-wyjątkowy None nie może być nadpisany"
    assert proc.scan_logger.errors == []


def _run():
    tests = [
        test_exception_is_caught_and_classified,
        test_exception_is_logged_with_offer_id_and_url,
        test_offer_id_derived_from_url_when_not_passed,
        test_success_passes_through_unchanged,
        test_none_without_exception_passes_through,
    ]
    passed = 0
    failed = 0
    print("🧪 TEST: guard na nieobsłużony wyjątek w pętli przetwarzania ofert\n")
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
