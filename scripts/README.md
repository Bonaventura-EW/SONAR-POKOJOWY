# scripts/ — narzędzia i archiwum migracji

Aktywne narzędzia leżą w tym katalogu. Jednorazowe migracje/naprawy danych, odpalone historycznie, leżą w `archive/` — **nie są częścią pipeline'u** (`src/`) ani workflow, nic ich nie importuje. Trzymane jako wzorzec/referencja na wypadek podobnej migracji w przyszłości.

| Skrypt | Co robił |
|---|---|
| `archive/migrate_history_full.py` | migracja `data/offers.json` do pełnej historii cen (tworzył backup `offers.backup_before_history_full.json`) |
| `archive/fix_price_history.py` | jednorazowa naprawa struktury historii cen |
| `archive/fix_reversed_prices.py` | naprawa odwróconych cen (min/max zamienione miejscami) |
| `archive/fix_days_active.py` | przeliczenie pola `days_active` w ofertach |

> Nie uruchamiaj ich na ślepo — operują bezpośrednio na `data/offers.json`. Najpierw backup.

## Narzędzia (aktywne)

| Skrypt | Do czego |
|---|---|
| `build_golden.py` | regeneruje golden set regresyjny parsera adresów (`test_address_golden.json`). Uruchom **tylko** po świadomej, zamierzonej zmianie zachowania `AddressParser` — golden to „prawda" dla `test_address_parser_golden.py`. Wymusza `PYTHONHASHSEED=0` dla determinizmu. |
