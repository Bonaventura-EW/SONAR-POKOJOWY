#!/usr/bin/env python3
"""
Test regresyjny AddressParser (golden set).
Przepuszcza realne teksty przez AKTUALNY parser i porownuje z zapisana
'prawda' (test_address_golden.json). Jakakolwiek roznica = regresja.

Golden generuje sie: python scripts/build_golden.py
Uruchom test:        python test_address_parser_golden.py
"""
import json, os, sys, io, contextlib

# Determinizm: extract_from_whitelist wybiera ulice iterujac po set (_known_streets),
# a kolejnosc iteracji po zbiorze stringow zalezy od PYTHONHASHSEED (rozna miedzy procesami).
# Wymuszamy staly seed, by golden byl powtarzalny. Re-exec jesli seed nieustawiony.
if os.environ.get('PYTHONHASHSEED') != '0':
    os.environ['PYTHONHASHSEED'] = '0'
    os.execv(sys.executable, [sys.executable] + sys.argv)

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(REPO_ROOT, 'src'))

from address_parser import AddressParser

CACHE = os.path.join(REPO_ROOT, 'data', 'geocoding_cache.json')
GOLDEN = os.path.join(REPO_ROOT, 'test_address_golden.json')


def run_parser(parser, text):
    def safe(fn, *a):
        try:
            return fn(*a)
        except Exception as e:
            return {'__error__': f'{type(e).__name__}: {e}'}
    return {
        'address': safe(parser.extract_address, text),
        'street_only': safe(parser.extract_street_only, text),
        'district': safe(parser.extract_district, text),
        'whitelist': safe(parser.extract_from_whitelist, text),
        'valid': safe(parser.validate_lublin_address, text),
    }


def main():
    if not os.path.exists(GOLDEN):
        print(f"❌ Brak golden setu: {GOLDEN}")
        print("   Wygeneruj: python scripts/build_golden.py")
        return 1

    golden = json.load(open(GOLDEN, encoding='utf-8'))
    parser = AddressParser(geocoding_cache_path=CACHE)

    diffs = []
    # parser drukuje warningi na stdout — tlumimy, zeby wynik testu byl czytelny
    with contextlib.redirect_stdout(io.StringIO()):
        for text, expected in golden.items():
            actual = run_parser(parser, text)
            if actual != expected:
                changed = [k for k in expected if actual.get(k) != expected.get(k)]
                diffs.append((text, changed, expected, actual))

    total = len(golden)
    print("=" * 70)
    print("🧪 TEST REGRESYJNY AddressParser (golden set)")
    print(f"   Tekstow w golden: {total}")
    print(f"   Zgodnych:         {total - len(diffs)}")
    print(f"   Rozbieznych:      {len(diffs)}")
    print("=" * 70)

    if diffs:
        print(f"\n❌ REGRESJA — {len(diffs)} tekstow zmienilo wynik:\n")
        for text, changed, exp, act in diffs[:15]:
            print(f"  TEXT: {text[:70]!r}")
            for k in changed:
                print(f"    [{k}] PRZED: {exp.get(k)}")
                print(f"    [{k}] PO:    {act.get(k)}")
            print()
        if len(diffs) > 15:
            print(f"  ... i {len(diffs) - 15} wiecej")
        return 1

    print("\n✅ Brak regresji — parser zachowuje sie identycznie jak golden.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
