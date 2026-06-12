# Changelog

Wszystkie istotne zmiany w projekcie SONAR-POKOJOWY.
Format luźno oparty na [Keep a Changelog](https://keepachangelog.com/pl/).

> Automatyczne commity skanów (`🤖 Automatyczny scan: ...`) są pomijane.
> Pełne historyczne raporty z napraw: `docs/archive/`.
> Źródło prawdy o statusie skanów: `data/scan_history.json`.

## [Nieopublikowane]

### Porządki frontend/narzędzia (2026-06-12)
- **perf**: debounce filtrów — pola cen, wyszukiwarka (300 ms) i suwaki dat (250 ms) nie przebudowują markerów na każdy keystroke/tick; checkboxy bez zmian (dyskretne).
- **refactor**: blok nagłówka `.sp-header` (identyczny w 7 stronach) wydzielony do `docs/assets/header.css` (−352 linie); per-page overridy zostają w plikach.
- **chore**: wykonane migracje jednorazowe przeniesione do `scripts/archive/` (w `scripts/` zostaje `build_golden.py`).
- **fix**: `quick_scan`, `test_scan`, `cleanup_bogus_addresses`, `retry_none_cache` używają ścieżek z `shared_utils` — działają z dowolnego cwd, usunięte fallbacki zgadywania ścieżek.
- **chore**: usunięte debug `console.log` (15 szt.) z `script.js` (warn/error zostają) i martwe klasy `.header`/`.subtitle` w `style.css`.

### Audyt i naprawy (2026-06-11)
- **security**: XSS — dane z OLX (adresy, opisy, URL-e, historia adresów) są escapowane przed wstawieniem do HTML (`escapeHtml()`/`safeOfferUrl()` w `script.js`, `ostatnie.html`, `market_analysis.html`); inline `onclick` z interpolacją ID ofert zastąpione `data-oid`.
- **fix**: workflow scannera — `concurrency` (runy kolejkowane zamiast wyścigu o push) + `git pull --rebase` z 3 próbami przed pushem; nieudany push to teraz twardy błąd, nie cichy warning.
- **feat**: `src/shared_utils.py` — atomowy zapis JSON (`write_json_atomic`, temp + rename) we wszystkich miejscach zapisu (`offers.json`, `geocoding_cache`, `scan_history`, `docs/*.json`); crash nie utnie już pliku. Wspólny `format_datetime()` zamiast kopii w `map_generator`/`profile_generator`.
- **fix**: golden test parsera adresów jest hermetyczny — czyta zamrożony `test_fixtures/geocoding_cache_golden.json` zamiast żywego cache'a (który mutuje przy każdym scanie i powodował fałszywe regresje); golden przebudowany (1506 tekstów). `tests.yml` odpala się też na push do `main` (z filtrem ścieżek — commity scanów pomijane).
- **fix**: retry geokodowania po transient-failu Nominatim z backoffem 5/10/20 s (wcześniej jedna próba po 5 s → oferty spadały do `no_coords`).
- **fix**: scraper alarmuje gdy >10% ogłoszeń na stronie pada na wyjątku parsowania (wczesny sygnał zmiany struktury HTML OLX); wyjątki w weryfikacji inactive logowane zamiast połykane.
- **chore**: usunięty martwy zdublowany blok return w `geocoder.py`; usunięte sekcje Roadmap z `README.md`, `BLUEPRINT.md` i `docs/api/README.md` (sekcje BLUEPRINT przenumerowane 12–14 → 11–13).

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
