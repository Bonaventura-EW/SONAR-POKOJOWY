# Changelog

Wszystkie istotne zmiany w projekcie SONAR-POKOJOWY.
Format luźno oparty na [Keep a Changelog](https://keepachangelog.com/pl/).

> Automatyczne commity skanów (`🤖 Automatyczny scan: ...`) są pomijane.
> Pełne historyczne raporty z napraw: `docs/archive/`.
> Źródło prawdy o statusie skanów: `data/scan_history.json`.

## [Nieopublikowane]

### Parser: znane ulice Lublina ze słowem z blocklisty ("Obrońców Pokoju") (2026-07-09)
- **fix**: `extract_address()` odrzucał każdą nazwę ulicy zawierającą słowo z `EXCLUDED_WORDS` — bez wyjątku dla znanych ulic. "Obrońców Pokoju 6" przepadało, bo "pokoju" jest (słusznie) na blockliście; fallback ucinał nazwę do "Obrońców", a Nominatim geokodował to ~5,5 km od celu. Catch-22: whitelist znanych ulic (`_load_known_streets`) też filtruje excluded words, więc ulica nigdy na nią nie trafiała. Fix: (1) wyjątek `is_known_full` w ścieżce adresu z numerem (`address_parser.py`, analogiczny do istniejącego w `extract_street_only`), (2) `'obrońców pokoju'` dodane do `HARDCODED_LUBLIN_STREETS` (`address_parser_data.py`).
- Efekt uboczny (pozytywny): "Przy Stawie 4" i podobne znane ulice z przyimkiem parsują się teraz z numerem, nie tylko street_only.
- **dane**: usunięty błędny wpis `"Obrońców"` z `geocoding_cache.json`; poprawione 2 oferty (ID1biAIE → "Obrońców Pokoju 6" exact, ID1bcDEs → "Obrońców Pokoju" street_only), zregenerowany `docs/data.json`. Golden przebudowany (`build_golden.py`) — 3 diffy to zamierzone poprawy, czwarty (Łęczyńska→None przy Garbarskiej) to wcześniejszy dryf cache, niezwiązany z fixem.

### Oferty firmowe: czarna obwódka zamiast aureoli i piktogramu (2026-07-08)
- **feat**: po feedbacku Mateusza wycofany wariant C (złota aureola + piktogram budynku, wdrożony wcześniej tego dnia). Oferty firmowe oznaczane prościej: **czarna obwódka 4px** (kropla i kwadrat) zamiast białej; nowe oferty nadal czerwona. Środek wraca do białego kółka. Bump cache `script.js?v=20`.
- Znane ograniczenie: firmowe pinezki z przedziału 3001+ (czarne wypełnienie) zlewają się obwódką z wypełnieniem — kształt pozostaje czytelny dzięki białemu kółku w środku.

### Wyróżnienie pinezek firmowych na mapie (2026-07-08)
- **feat**: oferty firmowe (`is_firm_offer`) dostają na canvasie złotą świetlistą aureolę pod kształtem (gradient + pierścień, `_drawFirmHalo`) oraz — dla aktywnych — piktogram budynku w złotym kółku zamiast białego środka (`_drawFirmGlyph`). Wariant C wybrany przez Mateusza z propozycji A/B/C. Nieaktywne firmowe zachowują krzyżyk ×, dostają aureolę.
- **fix**: firmowe oferty z przybliżonym adresem (kwadraty) traciły złotą obwódkę — kolor ramki był nadpisywany na biały. Teraz złota, spójnie z kroplami.
- `_updateBounds` obu klas rozszerzone dla firm o zasięg aureoli (poprawne odświeżanie regionów canvasu). Bump cache `script.js?v=19`.

### Pinezki firm niewidoczne na świeżym wejściu (2026-07-08)
- **fix**: `loadData()` (`script.js`) wywoływał `filterMarkers()` przed `buildFirmProfilesTree()` — `getEnabledProfiles()` nie znajdował jeszcze checkboxów profili w DOM, traktował wszystkie profile jako odznaczone (pusty Set) i wszystkie pinezki firm wypadały z warstwy na starcie strony. Pierwsza interakcja z filtrami je przywracała, więc bug był widoczny tylko na świeżym wejściu. Fix: drzewo profili budowane przed pierwszym `filterMarkers()` + `getEnabledProfiles()` traktuje brakujący checkbox jako zaznaczony (checkboxy startują jako checked). Bump cache `script.js?v=18`.
- Weryfikacja headless (Chromium): przed fixem 0/44 pinezek firm na warstwie przy świeżym wejściu, po fixie 44/44.

### Rozszerzona skala kolorów cen 0–3000 zł (2026-07-08)
- **feat**: `PRICE_RANGES` (`map_generator.py`) rozszerzone z 12 do 22 przedziałów. Gradient zielony → ciemny fiolet rozciągnięty na całą skalę 0–3000 zł (kolory interpolowane RGB z dotychczasowych 12 anchorów), **powyżej 3000 zł jeden kolor: czarny**. Kroki: 0–500, co 100 zł do 2000, co 200 zł do 3000. Fallback `get_price_range()` zmieniony na `range_3001_plus`.
- Efekt: fiolet zaczyna się od ~2000 zł zamiast dominować od 1501+ (dotąd 47 aktywnych ofert >1500 zł zlewało się w jeden fioletowy kubełek), czerwień od ~1500, typowy pokój ~950 zł jest żółty. Frontend bez zmian — legenda, popupy i liczniki czytają zakresy dynamicznie z `data.json`.
- Wariant (kroki 100/200 zł + gradient na całość) wybrany przez Mateusza z propozycji before/after.
- **fix**: ujednolicenie skali na wszystkich podstronach — `profile_tracker.html` (pinezki firm) i `ostatnie.html` (chipy cen) miały własne, zahardkodowane i rozjechane palety (ostatnie.html w ogóle inną, czerwono-zieloną). Teraz obie czytają skalę dynamicznie: `profile_generator.py` dokłada `price_ranges` do `profile_data.json`, `ostatnie.html` bierze je z `data.json` (kolor tekstu chipa liczony z luminancji tła). Jedno źródło prawdy: `map_generator.PRICE_RANGES`.

### Weryfikacja nieaktywnych ofert ze śledzonych profili firmowych (2026-07-02)
- **fix**: `_verify_inactive_offers` (`main.py`) reaktywuje ofertę na podstawie bezpośredniej weryfikacji URL (HTTP 200 + `availability: InStock`, bez markera "nieaktywne"), gdy oferta ma ustawiony `profile_name` (pochodzi ze śledzonego profilu firmowego). Wcześniej (fix 2026-05-23) weryfikacja ignorowała InStock dla wszystkich ofert, żeby uniknąć pętli reaktywacja/dezaktywacja dla anonimowych ofert wypadających z listingu — ale to samo zabezpieczenie fałszywie oznaczało jako nieaktywne żywe oferty znanych firm, które spadły w rankingu profilu (brak odświeżenia), np. `Poqui — ul. Hetmańska 5` (ID1be0ER), mimo że strona OLX nadal serwowała pełną, aktywną ofertę.
- Uzasadnienie zawężenia do profili: ryzyko "zombie" strony (OLX trzyma InStock dla dawno zarchiwizowanych ofert) jest dużo niższe dla konkretnej, znanej firmy niż dla anonimowego listingu kategorii.

### Filtr cen-outlierów (2026-07-01)
- **feat**: `_process_offer` odrzuca oferty z ceną >= 10x średnia cena aktywnych ofert w bazie (próg liczony raz na scan, z bazy sprzed scanu, `main.py::_compute_price_outlier_threshold`). Chroni przed literówkami/błędami parsera cen (np. "9500" zamiast "950") i ofertami nie-pokojowymi z absurdalną ceną. Nowy `_skip_reason='price_outlier'`, liczony i próbkowany osobno w `skipped_offers_sample.json` i `scan_history.json`. Filtr wyłączony gdy baza ma <10 aktywnych ofert z ceną (świeży start).
- Audyt bazy 2026-07-01: 0 ofert w aktualnej bazie (518 aktywnych, średnia ~969 zł, próg ~9685 zł, max cena w bazie 4799 zł) spełnia to kryterium — filtr zabezpiecza na przyszłość, nie było czego czyścić.

### Wykrywanie blokady OLX w skanach (2026-06-26)
- **fix**: gdy scraper zwróci 0 ofert (lub <30% liczby aktywnych w bazie), scan kończy się statusem `warning` zamiast `completed`, a `scan_history.json` dostaje wpis w `errors[]` z komunikatem `SCRAPE_BLOCKED`/`SCRAPE_PARTIAL`.
- **fix**: `api/status.json` pokazuje `degraded` zamiast `operational` po takim scanie; `api/scan_status.json` wypełnia `failureReason` treścią błędu.
- **fix**: `monitoring.html` — nowy żółty badge „Ostrzeżenie" dla skanów z `status: warning` (wcześniej błędnie wyświetlał „Sukces").

### Mapa fix scalona w mapę główną — wariant canvas (2026-06-24)
- **perf**: renderowanie pinezek na canvasie (`L.canvas`) zostało **scalone do mapy głównej** (`index.html` + `assets/script.js`). Wszystkie pinezki rysowane są na JEDNYM `<canvas>` przez warstwę wektorową Leaflet zamiast ~1000 węzłów DOM (`divIcon`) — płynny pan/zoom i filtrowanie przy dużej liczbie ofert, **bez klastrowania** (każda oferta to nadal osobny punkt).
- Kształty zachowane 1:1: kropla = dokładny adres, kwadrat z przerywaną ramką = adres przybliżony. Własne klasy `PinMarker`/`SquareMarker` (rozszerzenia `L.CircleMarker`) rysują kształt + badge `N`/`↓↑`/`×` na canvasie.
- Wszystkie filtry, warstwy, legenda, liczniki, popupy i suwaki dat działają identycznie jak wcześniej — backend i `docs/data.json` bez zmian.
- **cleanup**: usunięto tymczasową zakładkę `docs/mapa2.html` + `docs/assets/script2.js` oraz link „🗺️ Mapa fix" z nawigacji wszystkich podstron (canvas jest teraz domyślny). Bump cache `script.js?v=17`.

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
