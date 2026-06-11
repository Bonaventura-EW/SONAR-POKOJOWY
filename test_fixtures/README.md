# Fixtures testowe

- `geocoding_cache_golden.json` — ZAMROŻONA kopia `data/geocoding_cache.json`
  używana przez `test_address_parser_golden.py` i `scripts/build_golden.py`.
  Parser (whitelist znanych ulic) zależy od cache'a; żywy cache mutuje przy
  każdym scanie, więc test na żywym pliku był niedeterministyczny.
  Aktualizuj TYLKO razem z przebudową golden setu:
  `cp data/geocoding_cache.json test_fixtures/geocoding_cache_golden.json && python scripts/build_golden.py`
