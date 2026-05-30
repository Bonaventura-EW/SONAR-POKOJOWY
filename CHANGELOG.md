# Changelog

Wszystkie istotne zmiany w projekcie SONAR-POKOJOWY.
Format luźno oparty na [Keep a Changelog](https://keepachangelog.com/pl/).

> Automatyczne commity skanów (`🤖 Automatyczny scan: ...`) są pomijane.
> Pełne historyczne raporty z napraw: `docs/archive/`.
> Źródło prawdy o statusie skanów: `data/scan_history.json`.

## [Nieopublikowane]

### Porządki / utrzymanie (2026-05-30)
- **chore**: wyczyszczono `geocoding_cache.json` z 494 martwych wpisów (adresy nieużywane przez żadną ofertę). Cache 1082 → 588 wpisów, backup w `data/backups/`.
- **docs**: archiwizacja 33 historycznych raportów/wizualizacji do `docs/archive/` (root: 45 → 8 plików dokumentacji).
- **chore**: backupy `*.backup_*` i `*.old` przeniesione do `data/backups/`; `.gitignore` blokuje dorzucanie nowych luźnych backupów.
- **fix**: testy `test_analytics.py` i `test_monitoring.py` nie są już zależne od ścieżki `/tmp/SONAR-POKOJOWY` — używają `REPO_ROOT` z `__file__`.

> Ustalenie z audytu 2026-05-30: geokodowanie aktywnej bazy ma **100% pokrycia** (368/368 ofert z współrzędnymi). Wcześniejsza metryka "~49% success rate" liczyła martwe wpisy cache i była myląca — realnie nie ma problemu z pokryciem. Przestrzeń na poprawę: 32 oferty z precyzją `district` (środek dzielnicy zamiast ulicy).

## Wcześniej (wybrane, z historii git)

### Funkcje
- Warstwa „Firmy/Agencje (nieaktywne)" w panelu warstw (#11)
- Przycisk „📍 Mapa" w liście ofert profilu → przenosi na główną mapę (#10)
- Filtr okresu (30/60/90/180 dni / wszystkie) w Analizie Rynku (#9)
- Filtr statusu ofert (aktywne/nieaktywne/wszystkie) w Analizie Rynku (#8)
- Data zniknięcia oferty w zakładce firm (#7)
- Parser adresów: 3 naprawy zwiększające pokrycie ofert

### Naprawy
- Oferty `precision='district'` trafiają do warstwy „przybliżone aktywne" (#4)
- `skipped_debug_generator` generuje nagłówek sunset (#6)
- Parser adresu: „Wymagana 1-miesięczna kaucja" błędnie łapane jako adres
- `verification` nie reaktywuje już ofert na podstawie `InStock`
- `deactivated_count = None` gdy scan failed
- Pinezki firmowe widoczne mimo odznaczonych warstw
- ETAP 1: naprawa formatu współrzędnych `{lat,lon}` → `[lat,lon]` dla Leaflet (pełny opis: `docs/archive/CHANGELOG_ETAP1.md`)

### Refaktory
- `map_generator`: wydzielono `regenerate_all_derived()` z bloku `__main__`
- Migracja legacy `coordinates` → `address.coords`
- `script.js`: usunięto duplikat parsowania daty
