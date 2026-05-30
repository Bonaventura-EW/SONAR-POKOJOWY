#!/usr/bin/env python3
"""
Generator golden setu dla AddressParser.
Przepuszcza realne opisy ofert (z offers.json + backupow) przez OBECNY parser
i zapisuje wyniki jako 'prawde' do test_address_golden.json.

Po refaktorze test_address_parser_golden.py porownuje nowy parser z ta prawda.

Uruchom TYLKO po swiadomej zmianie zachowania parsera.
"""
import json, os, sys

# Determinizm: patrz komentarz w test_address_parser_golden.py. Golden MUSI byc
# generowany z tym samym PYTHONHASHSEED co test, inaczej pole 'whitelist' bedzie flaky.
if os.environ.get('PYTHONHASHSEED') != '0':
    os.environ['PYTHONHASHSEED'] = '0'
    os.execv(sys.executable, [sys.executable] + sys.argv)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'src'))

from address_parser import AddressParser

CACHE = os.path.join(REPO_ROOT, 'data', 'geocoding_cache.json')


def collect_texts():
    """Zbiera unikalne teksty: opisy + tytuly + adresy.full z offers.json i backupow."""
    texts = []
    seen = set()
    sources = [os.path.join(REPO_ROOT, 'data', 'offers.json')]
    bdir = os.path.join(REPO_ROOT, 'data', 'backups')
    if os.path.isdir(bdir):
        for f in sorted(os.listdir(bdir)):
            if f.startswith('offers') and f.endswith('.json'):
                sources.append(os.path.join(bdir, f))

    for src in sources:
        try:
            data = json.load(open(src, encoding='utf-8'))
        except Exception:
            continue
        offers = data.get('offers', data) if isinstance(data, dict) else data
        if isinstance(offers, dict):
            offers = list(offers.values())
        for o in offers:
            if not isinstance(o, dict):
                continue
            for key in ('description', 'title'):
                t = o.get(key)
                if isinstance(t, str) and t.strip():
                    h = t.strip()
                    if h not in seen:
                        seen.add(h)
                        texts.append(h)
            a = o.get('address')
            if isinstance(a, dict) and a.get('full'):
                h = a['full'].strip()
                if h and h not in seen:
                    seen.add(h)
                    texts.append(h)
    return texts


def run_parser(parser, text):
    """Odwzorowuje pipeline z main.py: extract_address -> street_only -> whitelist -> district."""
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
    parser = AddressParser(geocoding_cache_path=CACHE)
    texts = collect_texts()
    golden = {t: run_parser(parser, t) for t in texts}

    out = os.path.join(REPO_ROOT, 'test_address_golden.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(golden, f, ensure_ascii=False, indent=1, sort_keys=True)

    print(f"✅ Golden zapisany: {out}")
    print(f"   Tekstow: {len(texts)}")


if __name__ == '__main__':
    main()
