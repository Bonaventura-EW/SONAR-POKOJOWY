# Changelog

Wszystkie istotne zmiany w projekcie SONAR-POKOJOWY.
Format luźno oparty na [Keep a Changelog](https://keepachangelog.com/pl/).

> Automatyczne commity skanów (`🤖 Automatyczny scan: ...`) są pomijane.
> Pełne historyczne raporty z napraw: `docs/archive/`.
> Źródło prawdy o statusie skanów: `data/scan_history.json`.

## [Nieopublikowane]

### Mapa: kompresja popupów + tytuł ogłoszenia w 2. wierszu (2026-07-21)
- **feat (po akceptacji before/after)**: popup oferty na mapie głównej ~40% niższy i węższy (380→350 px, margines wewn. 20→10 px, padding karty 16→9 px). Te same informacje i ikony 1:1: mniejsze fonty/odstępy, „▼ Pokaż całość" jako link w linii opisu zamiast przycisku w ramce, daty zawijane obok siebie zamiast 3 osobnych wierszy, fioletowa linia nagłówka schodzi pod tytuł.
- **feat**: **tytuł ogłoszenia w 2. wierszu** nagłówka popupu (`.popup-title`; przy kilku ofertach pod adresem — `.offer-item-title` per karta). Fix u źródła: scraper nie zapisuje tytułu osobno (skleja z opisem — stąd „…Czechowie! OpisPokój do wynajęcia…"), więc `map_generator.py` odzyskuje go z prefiksu opisu walidowanego **slugiem URL-a** (zamrożony tytuł z chwili publikacji) + 2 fallbacki: marker „Opis" i zdublowany tytuł na początku treści (sprzedawca zmienił tytuł po publikacji → slug nieaktualny). Pokrycie: **1529/1532 (99,8%)**; bez tytułu → wiersz się nie renderuje. Nowe pole `title` w `docs/data.json`, `description` czyszczone z powtórzonego tytułu i sklejki „Opis".
- Zweryfikowane headless (Chromium, lokalny Leaflet): popup aktywnej i nieaktywnej oferty (Paganiniego 12: tytuł „Wolny pokój od zaraz na Czechowie!", czysty opis), rozwijanie opisu, 374×330 px, 0 błędów JS; `test_integration.py` OK.

### Firmy: archiwalne ogłoszenia sortowane po dacie zniknięcia (2026-07-21)
- **fix (zgłoszenie Mateusza)**: w zakładce Firmy sekcja „ogłoszenia archiwalne" sortowała nieaktywne oferty po `first_seen` (data pojawienia się) malejąco — na górze była oferta, która *pojawiła się* najpóźniej, a nie ta, która *zniknęła* jako ostatnia. Oczekiwane: ostatnio zniknięte na górze.
- **root cause**: `profile_generator.py` — `inactive_sorted` używał klucza `first_seen_iso`. Front (`profile_tracker.html`) tylko filtruje `prof.offers` w kolejności z JSON-a, więc porządek pochodzi z backendu.
- **fix**: `offer_entry` dostaje pole `last_seen_iso` (surowy ISO), a nieaktywne oferty sortowane są po nim malejąco (`last_seen` nieaktywnej oferty = ostatni raz widziana = kiedy zniknęła). Aktywne bez zmian (po `first_seen` malejąco). Zregenerowane `docs/profile_data.json`.
- Zweryfikowane na realnych danych: profil „Poqui" (ze screenshotu) → Pogodnej 36 (20.07) → Obrońców Pokoju 21 (19.07) → Hetmańskiej 5 (01.07) → Pogodnej 36 (29.05) → Przytulna 6A / Granata 13 (24.05). `test_integration.py` PASS.

### Ulubione: kafelek „Śr. przyrost/dzień" pokazywał absurdy (+1158/dzień) (2026-07-20)
- **fix (zgłoszenie Mateusza)**: kafelek na karcie ulubionej oferty (`docs/ulubione.html`) potrafił pokazać **+1158,1/dzień** — oferta Faraona 6 miała 2 pomiary oddalone o ~7 min (53 → 59 wyświetleń) tego samego dnia.
- **root cause**: metryka liczyła `(ostatnie − pierwsze) / dni_między_pomiarami` z `date_iso`. Przy pod-dobowym oknie (7 min ≈ 0,005 dnia) dzielenie +6 przez ułamek doby ekstrapolowało tempo na całą dobę → absurd. Matematycznie „poprawne", ale z 7 minut nie da się oszacować dziennego tempa.
- **fix**: kafelek liczy teraz tak samo jak sąsiedni wykres słupkowy „📈 Przyrost dzienny" — porównuje **stany na koniec dnia kalendarzowego**: `(ostatni_pomiar_ostatniego_dnia − ostatni_pomiar_pierwszego_dnia) / (liczba_dni − 1)` (grupowanie po `date_iso`, reuse istniejących `dayLast`/`dayKeys`). Gdy wszystkie pomiary są z jednego dnia → „—" (za mało danych; bieżące tempo pokazuje „przyrost/pomiar"). Model wg Mateusza: wczoraj 100 → dziś 130 = +30/dzień.
- Zweryfikowane headless (Node, replika logiki): przykład Mateusza (100→130 przez dobę) = **+30,0**; Faraona 6 (2 pomiary, ten sam dzień) = **„—"** (było +1158,1); 3 świeże ulubione (dni=1) = „—" (było +25,6/+39,4/+17,7); oferty z ≥2 dniami (LSM, Organowa, Czechów, Głęboka, Centrum) = wartości spójne, bez ekstrapolacji (+12,5/+18,0/+26,3/+63,0/+7,8). `test_integration.py` PASS.

### Adres: oferta ID1buaHj (Magdaleny Brzeskiej) na mapie stała na Zana (2026-07-20)
- **fix (zgłoszenie Mateusza)**: `politechnika-m-brzeskiej-z-balkonem-…-ID1buaHj` — realny adres „ul. Magdaleny Brzeskiej", a marker stał na „Zana" (punkt orientacyjny z opisu: „10 min od biurowców przy ul. Zana").
- **root cause**: to była zastana, nieświeża DANA, nie regresja kodu. Fix parsera (dodanie `magdaleny brzeskiej` do `HARDCODED_LUBLIN_STREETS`) był już w kodzie od 2026-07-17 i `extract_street_only` na tym opisie zwraca poprawnie „Magdaleny Brzeskiej". Ale rekord w `data/offers.json` miał scache'owany stary wynik „Zana" sprzed fixu, a smart-scan pomija tę ofertę (cena bez zmian), więc nigdy się nie przeparsowała. „Zana" to realna ulica → nie łapie jej ścieżka re-parse bogus-adresów.
- **fix (dane)**: skorygowany JEDEN rekord przez faktyczny pipeline (parser `extract_street_only` → geocoder), nie ręcznie: `address` = `Magdaleny Brzeskiej`, coords `(51.2332228, 22.5364355)` (rejon LSM/Rury, obok „Brzeskiej 8" z cache). `geocoding_cache.json` dostał wpis `Magdaleny Brzeskiej`. Zregenerowane `docs/data.json` + `docs/profile_data.json`. Backup: `data/backups/offers.backup_fix_brzeskiej_*`.
- Zweryfikowane: golden 2255/2255 (bez zmian kodu parsera), `test_integration.py` PASS, marker w `docs/data.json` na poprawnych koordynatach.

### Mapa: liczniki zakresów cenowych i grup zmian nie liczyły ofert firmowych (2026-07-20)
- **fix (zgłoszenie Mateusza)**: gdy na mapie odznaczone były warstwy „Aktywne/Nieaktywne oferty" i zostawiona tylko warstwa „Firmy / Agencje", liczniki przy „Zakresy cenowe" oraz „Grupy zmian" (Cena spadła/wzrosła, Nowa oferta, Bez zmian) pokazywały wszędzie `(0)` — mimo że markery firmowe były widoczne na mapie.
- **root cause**: `updatePriceRangeCounts()` i `updateBadgeCounts()` (`docs/assets/script.js`) miały własną, uproszczoną logikę filtra warstw — sprawdzały tylko `layer-active`/`layer-inactive`/`*-approx`, **ignorując** warstwę Firmy (`isFirmOffer`/`layer-firm`/profile). Aktywna oferta firmowa wpadała do gałęzi zwykłych aktywnych i była zerowana, gdy `layer-active` był odznaczony. `filterMarkers()` (rzeczywiste wyświetlanie) miał poprawną, firmo-świadomą logikę — liczniki się z nią rozjeżdżały.
- **fix**: wyodrębniony wspólny helper `getLayerFilterState()` + `itemPassesLayerFilter(item, state)` — jedno źródło prawdy dla filtra warstw (aktywne/nieaktywne/przybliżone/firmy + wybór profili firmowych). Używany teraz w `filterMarkers()`, `updatePriceRangeCounts()` i `updateBadgeCounts()`, więc oferty firmowe **liczą się tak samo, jak są wyświetlane**. Bump `script.js?v=23` → `v=24` (wymuszenie reloadu).
- Zweryfikowane headless (Node VM na realnym `script.js`, mock DOM): scenariusz „tylko Firmy zaznaczone" → zakresy `901-1000=2`, `1201-1300=1`, `0-500=0` (oferta prywatna niewidoczna), grupy zmian `Nowa=1`, `Cena spadła=1`, `Bez zmian=1`, `Cena wzrosła=0`; odznaczenie profilu MyRent → jego oferta znika z liczników. Wszystkie asercje PASS.

### Ulubione: dodana oferta — Faraona 6 (MyRent) (2026-07-20)
- **feat (zgłoszenie Mateusza)**: do `data/favorites.json` dopisana oferta „Pokoje do wynajęcia od września — ul. Faraona 6, 3 wolne pokoje, bez prowizji, blisko uczelni" (short_id `1bv4ph`, numeric_id `1086315967`; profil MyRent). Tracker zacznie zbierać snapshoty przy najbliższym scanie.

### Firmy: dodana firma MyRent do śledzonych profili (2026-07-20)
- **feat (zgłoszenie Mateusza)**: nowy profil `myrent` w `src/profiles_config.py` — MyRent, `https://www.olx.pl/oferty/uzytkownik/56DT9/`, `user_id=75464983` (rozwiązany ze slugu `56DT9` z HTML profilu: `"seller":{"data":{"id":75464983}}`; zweryfikowany przez OLX API v1 — 11 ofert, pokoje w Lublinie). Tab pojawia się od razu (pusty), oferty zbiorą się przy najbliższym scanie.

### Firmy: daty reaktywacji zamiast samego licznika ×N (2026-07-20)
- **feat (zgłoszenie Mateusza)**: badge „♻ reaktywacja ×N" w `docs/profile_tracker.html` mówił *ile razy*, ale nie *kiedy*. Pod wierszem meta dochodzi linijka „♻ daty: [data] …" (wariant C, jak sub-line adresu) z datami reaktywacji (`DD.MM.YYYY`). Badge z licznikiem zostaje.
- **backend (`main.py`)**: nowe pole `reactivation_dates` — lista dat reaktywacji. Dopisywane we wszystkich 3 ścieżkach reaktywacji (`_update_existing_offer`, skipped w `_mark_inactive_offers`, weryfikacja URL w `_verify_inactive_offers`), inicjalizowane w szablonie nowej oferty i w snapshocie wersji, resetowane przy zmianie adresu (jak pozostałe liczniki wersji).
- **dane**: backfill (`scripts/archive/backfill_reactivation_dates.py`, idempotentny) — 661 ofert dostało `reactivation_dates=[reactivated_at]` (jedyna znana data), 8 ofert z `count>0` bez daty → pusta lista. Historii **wielokrotnych** reaktywacji nie da się odtworzyć (nigdy nie zapisywana, patrz 2026-07-13), więc gdy `reactivation_count > len(reactivation_dates)` front pokazuje brakujące jako „+N wcześniej"; przyszłe reaktywacje zapiszą pełne daty. Backup: `data/backups/offers.backup_reactivation_dates_*`.
- **frontend (`profile_generator.py`)**: `profile_data.json` dostaje `reactivation_dates` (sformatowane `DD.MM.YYYY`).
- Zweryfikowane headless (Chromium + lokalny Leaflet): profil „Dawny Patron" — Niecała 4 `×2` → „♻ daty: 19.07.2026 +1 wcześniej", Ogrodowa 8 `×1` → „♻ daty: 21.05.2026" bez „+N", oferty bez reaktywacji bez linijki, 0 błędów JS.

### Ulubione: dodane 3 oferty — Przy Stawie, Langiewicza, Nowowiejskiego (2026-07-20)
- **feat** (zgłoszenie Mateusza): do `data/favorites.json` dopisane trzy oferty: „Pokój w mieszkaniu 2-pokojowym, blisko UMCS/KUL/UP — ul. Przy Stawie" (short_id `1biza2`, numeric_id `1083097594`), „Przytulny pokój po remoncie, 5 min od UMCS/KUL/UP — ul. Langiewicza" (short_id `1biJym`, numeric_id `1083137542`) oraz „Przestronny pokój po remoncie, blisko centrum — ul. Feliksa Nowowiejskiego" (short_id `1bnkW7`, numeric_id `1084234493`). Tracker zacznie zbierać snapshoty przy najbliższym scanie.

### Ulubione: wykres „Przyrost dzienny" (2026-07-20)
- **feat (zgłoszenie Mateusza)**: pod wykresem wyświetleń nowy wykres słupkowy **📈 Przyrost dzienny** — słupek na dzień kalendarzowy, wartość = ostatni pomiar dnia − ostatni pomiar dnia poprzedniego (grupowanie po `date_iso`). Pierwszy dzień śledzenia nie ma poprzednika — liczony od pierwszego pomiaru, oznaczony jaśniejszym słupkiem + dopiskiem w tooltipie „(dzień częściowy)". Kolor jak wykres wyświetleń (`#667eea`, ta sama encja). Pokazywany gdy ≥ 2 dni pomiarów.
- Zweryfikowane headless (Chromium, lokalny Chart.js): 5 wykresów słupkowych, suma słupków każdej karty = różnica wyświetleń od pierwszego pomiaru, 0 błędów JS.

### Ulubione: kafelek „Śr. przyrost/dzień" (2026-07-20)
- **feat (zgłoszenie Mateusza)**: karta ulubionej oferty (`docs/ulubione.html`) dostaje 6. kafelek **Śr. przyrost/dzień** — średni dzienny wzrost wyświetleń `(ostatnie − pierwsze) / dni między pierwszym a ostatnim pomiarem` (z `date_iso`, ISO 8601 — parsowane natywnie przez `new Date()`, bez pułapki formatu PL). Format `+N,N` jak w sąsiednim kafelku, wyszarzony `—` gdy < 2 pomiary lub zerowy odstęp czasu. To inna wartość niż przyrost między pomiarami: przy 3 scanach dziennie ~3× wyższa.
- **ui**: dotychczasowa etykieta „Śr. przyrost" → **„Śr. przyrost/pomiar"**, żeby oba kafelki się nie myliły.

### Ulubione: przycisk profilu/firmy na karcie (2026-07-19)
- **feat (zgłoszenie Mateusza)**: karta ulubionej oferty (`docs/ulubione.html`) pokazuje w wierszu tytułu, obok badge'a statusu, przycisk z profilem źródłowym ogłoszenia. Śledzona firma → klikalny bursztynowy przycisk „🏢 Nazwa →" prowadzący do zakładki Firmy z otwartą podzakładką tej firmy (istniejący deep-link `profile_tracker.html#klucz`); firma spoza śledzonych → sam badge z nazwą (bez linku); oferta bez profilu → szary badge „👤 Prywatne".
- **feat**: fix u źródła — `favorites_generator.py` dokłada do `docs/favorites_data.json` pola `profile_name` (z `offers.json`) i `profile_key` (mapowanie nazwa→klucz przez `TRACKED_PROFILES` z `profiles_config.py`).
- Zweryfikowane headless (Chromium, lokalny Chart.js/Leaflet): 4 przyciski firmowe (MAT×2, stylowe pokoje-ania, Artymiuk) z poprawnymi hashami, 1 badge „Prywatne", klik `#mat` otwiera zakładkę MAT w Firmach, 0 błędów JS, wykresy bez regresji.

### Ulubione: dodane 2 oferty — LSM (studenckie) i Organowa 5 (2026-07-18)
- **feat** (zgłoszenie Mateusza): do `data/favorites.json` dopisane dwie oferty: „Pokój jednoosobowy na LSM, idealny dla studentów PL/UMCS/UP/KUL" (short_id `1bw9sZ`, numeric_id `1086097089`) oraz „Pokój jednoosobowy ul. Organowa 5, blisko UM" (short_id `1bwa88`, numeric_id `1086099640`). Tracker zacznie zbierać snapshoty przy najbliższym scanie.

### Ulubione: kafelek „Śr. przyrost" + wykres ceny w czasie (2026-07-18)
- **feat (po akceptacji before/after)**: karta ulubionej oferty (`docs/ulubione.html`) dostaje 5. kafelek **Śr. przyrost** — średni wzrost wyświetleń między pomiarami `(ostatnie − pierwsze) / (pomiary − 1)`, format `+N,N` (znak, 1 miejsce po przecinku), wyszarzony `—` gdy < 2 pomiary. Liczony w JS z `views_history`.
- **feat**: nowy wykres **💰 Cena w czasie** — Chart.js `stepped: 'before'` (cena trzyma poziom aż do zmiany), kolor morski (`#0d9488`), ostatni schodek dociągnięty do „teraz" (bieżąca cena). Pokazywany **tylko gdy cena się zmieniła** (`price_history.length ≥ 2`); gdy stała — jak dotąd, sam kafelek Cena. Czysty frontend z istniejącego `price_history` + `current_price`, bez zmian w generatorze.
- **feat**: wiersz „📊 Historia cen" dostaje **strzałki kierunku** — ↓ zielona (spadek) / ↑ czerwona (wzrost, perspektywa najemcy) między cenami + sumaryczna zmiana „(+N zł od dodania)". Dotyczy każdej śledzonej oferty.
- Zweryfikowane headless (Chromium + Chart.js, wstrzyknięta zmiana 950→900→1000): 5 kafelków, wykres schodkowy w poprawnych pozycjach, strzałki, wykres wyświetleń bez regresji, 0 błędów JS.

### Docs: pułapki tej sesji dopisane do CLAUDE.md (2026-07-17)
- **docs**: do CLAUDE.md dopisane 3 lekcje z tej sesji, żeby nie wracały: (1) `extract_street_only` — ulica ZNANA bije NIEZNANĄ bez względu na pozycję (punkt orientacyjny wygrywa z faktycznym adresem); (2) golden test pokazujący regresje → NAJPIERW sprawdź zależności (`geopy`/`pytz`), nie golden; (3) `test_address_parser_golden.py` dopisany do listy testów + note o SessionStart hooku. Plus 2 nowe wiersze w decision tree.

### Ulubione: dodana oferta Głęboka/Miasteczko (2026-07-17)
- **feat** (zgłoszenie Mateusza): do `data/favorites.json` dopisana „Politechnika, Miasteczko, Głęboka z balkonem" (short_id `1bubFQ`, numeric_id `1085867246`). Tracker zacznie zbierać snapshoty przy najbliższym scanie.

### Infra: SessionStart hook auto-instaluje zależności w web-sesji (2026-07-17)
- **fix (zgłoszenie Mateusza „ogarnij to")**: `.claude/setup.sh` (instalacja `requirements.txt`) istniał, ale NIC go nie uruchamiało — brakowało `.claude/settings.json` z hookiem. Świeży kontener web-sesji startował bez `geopy`/`pytz`, więc `from geocoder import to_nominative` padał po cichu, krok „mianownik" w `address_parser` przestawał działać i `test_address_parser_golden.py` pokazywał 13 **fałszywych** regresji (whitelist→None dla Czeremchowej/Smyczkowej/Szewskiej… — form dopełniaczowych, które bez mianownika nie trafiały w fixture). To NIE był przestarzały golden — po instalacji zależności golden = 2255/2255, 0 regresji.
- **fix**: dodany `.claude/settings.json` z hookiem `SessionStart` → `.claude/hooks/session-start.sh` (web-only guard `CLAUDE_CODE_REMOTE`, deleguje do `setup.sh`). Każda przyszła web-sesja dostaje zależności przed startem, pułapka fałszywych regresji znika. Zwalidowane: hook exit 0 („Wszystkie zależności OK"), golden 2255/2255, `test_integration.py` OK. Zadziała globalnie po merge do `main`.

### Parser: ul. Magdaleny Brzeskiej lądowała na Zana (2026-07-17)
- **fix (zgłoszenie Mateusza — ID1buaHj „Politechnika, M. Brzeskiej z balkonem" na mapie jako Zana)**: oferta z opisem „mieści się na 3 piętrze przy ul. Magdaleny Brzeskiej … 10 min od biurowców przy ul. Zana" geokodowała się na **Zana** (orientacyjny punkt), nie na faktyczny adres. Root cause: `extract_address` wymaga numeru domu, którego w treści nie ma → `None`; fallback `extract_street_only` wybierał `Zana` bo była **znaną** ulicą (`priority_class=2`), a dwuczłonowa „Magdaleny Brzeskiej" była **nieznana** (`priority_class=1`) — a klasa „znana" bije „nieznaną" bezwarunkowo, ignorując pozycję w tekście (mimo że Brzeskiej jest wcześniej i to ona jest adresem). W cache była tylko krótsza forma „Brzeskiej"; `extract_from_whitelist` znajdował ją, ale to niższy fallback niż `street_only`.
- **fix**: dodane `magdaleny brzeskiej` do `HARDCODED_LUBLIN_STREETS` (`address_parser_data.py`). Teraz forma dwuczłonowa jest znana (class=2), przy remisie wygrywa wcześniejszą pozycją → `extract_street_only` zwraca „Magdaleny Brzeskiej"; Nominatim zna pełną nazwę (`51.2332, 22.5364`, LSM/Rury). Zweryfikowane na parserze (Zana→Magdaleny Brzeskiej) i golden (2255/2255, 0 regresji). Oferta ustawi się poprawnie przy najbliższym scanie (nie ma jej jeszcze w bazie).

### Ulubione: dni odświeżeń na wykresie wyświetleń (2026-07-17)
- **feat (po akceptacji before/after)**: wykres „👁️ Wyświetlenia w czasie" (`docs/ulubione.html`) dostaje pionowe, bursztynowe (`#f59e0b`) przerywane linie w momentach odświeżenia/podbicia oferty na OLX, z etykietą dnia (🔄 DD.MM) nad linią. Pozycja X interpolowana po czasie między pomiarami (dokładny moment odświeżenia, nie zaokrąglany do najbliższego punktu). Własny plugin Chart.js `refreshMarkerPlugin` (`afterDatasetsDraw`), dane per oferta z `f.refresh_events` + `viewsIso`; bez nowych zależności. Legenda pod nagłówkiem gdy oferta ma odświeżenia; `layout.padding.top` na etykiety. Dotyczy **każdej** śledzonej oferty (obecnej i przyszłej) — zmiana w pętli renderującej karty. Zweryfikowane headless (Chromium + lokalny Chart.js): 2 linie w poprawnych pozycjach, etykiety, legenda, 0 błędów JS.

### Ulubione: dodana oferta Paganiniego 11 (2026-07-17)
- **feat** (zgłoszenie Mateusza): do `data/favorites.json` dopisana oferta „2 pokoje jednoosobowe do wynajęcia, Czechów Dolny, ul. Paganiniego 11" (short_id `1bomFK`, numeric_id `1084479556`). `favorites_tracker.py` zacznie zbierać snapshoty (cena/status/odświeżenia/wyświetlenia) przy najbliższym scanie; karta pojawi się w zakładce Ulubione po pierwszym pomiarze.

### Nowy profil firmowy: MAT (2026-07-17)
- **feat** (zgłoszenie Mateusza): dodany 8. śledzony profil OLX do `TRACKED_PROFILES` (`profiles_config.py`): „MAT" (user_id 67948084, konto firmowe, https://www.olx.pl/oferty/uzytkownik/4B6oQ/). W chwili dodania profil ma 0 aktywnych ofert (`total_elements=0` w API v1) — konfiguracja jest wyprzedzająca: oferty dostaną tag firmowy i trafią do warstwy/zakładki przy najbliższym scanie, gdy się pojawią. Propagacja automatyczna: zakładka Firmy (`profile_data.json` — profil renderuje się jako pusta karta, licznik 0), warstwa firmy/agencje na mapie głównej (`tracked_profiles` w `data.json`, drzewo profili w `script.js` — checkbox z licznikiem 0). Zregenerowane `docs/data.json` + `docs/profile_data.json` (7→8 profili).

### Firmy: słupki odświeżeń (14 dni) w bieżącej wersji adresu (2026-07-15)
- **feat (wariant A, wybór Mateusza po before/after)**: karty z historią wersji adresu (`profile_tracker.html`) pokazywały dla każdej wersji tylko liczniki („odświeżenia: N"), bez paska 14 dni jak w kartach bez zmiany adresu. Teraz bieżąca (zielona) wersja dostaje pasek `buildRefreshBars` pod statami — top-level `refresh_dates` opisują właśnie ją, bo liczniki i daty odświeżeń resetują się przy zmianie adresu. Stare wersje bez zmian (liczniki). Pasek nadal znika przy `refresh_count=0`.
- Zweryfikowane headless (Chromium + lokalny Leaflet): karta Batalionów Chłopskich 16 — 14 słupków, hit 15.07, „ostatnie: 15.07 14:09" w nowym formacie; karta Romanowskiego 58 — 3 hity; stare wersje 0 słupków; karty bez wersji (Paganiniego 12) bez zmian.

### Ceny ofert firmowych: JSON-LD bez progu 50% + dzielnice-"miejscowości" OLX + cena przy reaktywacji (2026-07-15)
- **fix (P1 — zgłoszenie Mateusza — Paganiniego 12 ID195dLc: baza 600 zł, OLX 920 zł)**: bezpiecznik w `_update_existing_offer` odrzucał zmianę ceny ≥50% jako błąd parsera, a podwyżka 600→920 to +53% — baza trzymała starą cenę, więc każdy scan liczył tę samą różnicę i blokada była WIECZNA (log: „PODEJRZANA zmiana ceny: 600 → 920 zł (53.3%) - IGNORUJĘ"). Fix: cena z JSON-LD świeżo pobranej strony (źródło prawdy) aktualizuje bez limitu %; próg 50% zostaje dla słabszych źródeł (HTML fallback, parser tekstowy).
- **fix (P2 — Batalionów Chłopskich 16 ID16ZeYm: baza 780 zł, OLX 900 zł)**: OLX lokalizuje to ogłoszenie w `city="Szerokie"` (dzielnica Lublina jako osobna „miejscowość"), więc filtr `city == "Lublin"` w `_fetch_profile_offers_api` wycinał je z API profilu, a w listingu wyszukiwarki też go nie ma. Efekt: każdy scan dezaktywował ofertę, po czym weryfikacja URL reaktywowała ją BEZ aktualizacji ceny (ping-pong `reactivation_count=7`, cena zamrożona od 03.06). Fix: filtr przepuszcza `LUBLIN_CITY_NAMES` = Lublin + dzielnice z `LUBLIN_DISTRICTS`.
- **fix (P2 — systemowy)**: reaktywacja przez `_verify_inactive_offers` aktualizuje teraz też cenę z JSON-LD już pobranej strony (zakres sanity 200–5000 zł jak w scraperze) — to była jedyna ścieżka dotykająca ofert niewidocznych w listingu/API i nie ruszała ceny. Logika zapisu zmiany ceny (previous_price/trend/history/history_full) wydzielona do `_apply_price_change`, wspólna dla obu ścieżek.
- **fix (UI, zgłoszenie Mateusza)**: `profile_tracker.html` — „ostatnie:" przy odświeżeniach pokazywało surowy ogon ISO w kolejności miesiąc.dzień („07.14T14:48:33+02:00"); teraz „14.07 14:48" (dzień.miesiąc). Zweryfikowane node'em (ISO z czasem, sama data, pusty string).
- Ceny obu zgłoszonych ofert wyrównają się przy najbliższym scanie (Paganiniego przez zdjęty limit, Batalionów wróci do scanu profilu przez filtr dzielnic).

### Mapa: retry z backoffem przy wczytywaniu data.json (2026-07-15)
- **fix** (zgłoszenie Mateusza — alert „Nie udało się wczytać danych mapy. Błąd: Failed to fetch" na live): `"Failed to fetch"` to `TypeError` z `fetch()` PRZED odpowiedzią HTTP (nie 404 — plik był, live zwracał 200), czyli przejściowy blip sieci/CDN. Root cause środowiskowy: GitHub Pages redeployuje się 3×/dobę na commitach scanu i w oknie deploya na kilka sekund zrzuca requesty. Stary `loadData()` przy pierwszym błędzie od razu walił alertem (retry był tylko na `!response.ok`, nie na `TypeError`).
- **fix**: nowy helper `fetchDataWithRetry()` w `assets/script.js` — 3 ponowienia z backoffem 0.5s / 1.5s / 3s, obejmuje też błędy sieci; alert dopiero po wyczerpaniu prób. Okno deploya przechodzi niezauważone. Bump `?v=22`→`?v=23` w `index.html`. Zweryfikowane node-mockiem (2 blipy→sukces po ~2s, zawsze-pada→rzuca prawdziwy błąd, sukces-od-razu→0ms). Dotyczy tylko głównej mapy (stamtąd był alert); pozostałe zakładki bez zmian.

### Parser: mianownik ulic (Bataliony Chłopskie→Batalionów Chłopskich) + "Spokojna okolica" (2026-07-14)
- **fix (P1 — zgłoszenie Mateusza — ID1brMAd „ul. Bataliony Chłopskie 16" na mapie jako Spokojna)**: tytuł-first ZADZIAŁAŁ — `extract_address` wyciągnął z tytułu „Bataliony Chłopskie 16", ale adres zginął na GEOKODOWANIU. Prawdziwa ulica to „Batalionów Chłopskich" (dopełniacz); wynajmujący napisał mianownik „Bataliony Chłopskie", którego Nominatim nie zna → geokoder zwrócił None → `_geocode_with_fallbacks` zszedł niżej i whitelist złapał fałszywą „Spokojna". Fix: `STREET_ALIASES` (address_parser_data.py) mapuje mianownik→dopełniacz, `_canonicalize_street()` stosowane w `extract_address`/`extract_street_only` PRZED geokodowaniem. Dodane „batalionów chłopskich" do `HARDCODED_LUBLIN_STREETS`.
- **fix (P2 — systemowy)**: „Spokojna okolica" (wielka S na początku zdania po „OKOLICA -") przechodziła filtr rzeczownika własnego z fixa 13.07 i whitelist stawiał ofertę na ul. Spokojna. Guard `_OKOLICA_AFTER` w `_find_in_text`: jednowyrazowa ulica tuż przed „okolic…" (okolica/okolicy/okolicę) i BEZ prefiksu ulicy = przymiotnik opisujący dzielnicę, nie adres. Realne „ul. Spokojna 5" (z prefiksem/numerem) bez zmian. Golden bez regresji (2255 tekstów, 0 diffów — w golden „spokojna okolica" zawsze współwystępuje z inną realną ulicą, która i tak wygrywała).
- **dane**: 17 ofert z adresem „Spokojna" → 1 poprawiona (ID1brMAd → Batalionów Chłopskich 16, coords 51.2538/22.5169), 4 odzyskane do znanych ulic z opisu (Pogodna, Zana×2, Cicha), 1 legit zostawiona (ul. Spokojna 10), 11 bez wiarygodnego adresu USUNIĘTYCH (live wrócą przy następnym scanie już z poprawnym parserem; reparse z samego opisu bez tytułu bywa zawodny — dawał śmieć „Możliwość wynajmu 4"). Usunięte 4 martwe wpisy mianownika z `geocoding_cache.json`. Zregenerowane `data.json` + `profile_data.json` (1424→1417 ofert). Backupy w `data/backups/`.

### Fix liczników reaktywacji i odświeżeń ofert firmowych (2026-07-13)
- **fix (reaktywacje)** (zgłoszenie Mateusza — Batalionów Chłopskich 16 miało badge „NOWE" mimo „reaktywacje: 0"): licznik `reactivation_count` rósł tylko w jednej z trzech ścieżek reaktywacji. Ścieżka skipped (`_mark_inactive_offers`) i weryfikacja URL (`_verify_inactive_offers`) ustawiały `reactivated_at`, ale NIE inkrementowały licznika → 40 ofert miało `reactivated_at` ustawione przy `reactivation_count=0`. Obie ścieżki teraz inkrementują licznik.
- **fix (odświeżenia)**: licznik `refresh_count` był martwy w całej bazie (0 ofert z count>0 mimo realnych dat pushup). Root cause: niezgodność nazw kluczy — `_process_offer` zapisuje świeże `api_last_refresh` pod kluczem `last_refresh_date`, a `_update_existing_offer` czytał nieistniejący `new_data['api_last_refresh']`, więc guard był zawsze fałszywy. Poprawiony klucz + logika wydzielona do `_track_refresh()`.
- **feat (wariant B)**: śledzenie odświeżeń również dla ofert pominiętych przez inteligentne skanowanie — bump bez zmiany ceny nie wchodził w `_update_existing_offer`, więc umykał. `_mark_inactive_offers` dostaje `skipped_refresh_map` (id → api_last_refresh) i woła `_track_refresh` dla skipped. Przy merge ofert profilowych do regular scanu propagowane jest `api_last_refresh` (regular HTML scrape go nie zna).
- **dane**: backfill 40 ofert — `reactivation_count=1` tam, gdzie `reactivated_at` było ustawione a licznik 0 (minimalna prawdziwa wartość; historii wielokrotnych reaktywacji nie da się odtworzyć). Zregenerowane `docs/data.json` + `profile_data.json`. Backup: `data/backups/offers.backup_reactivation_backfill_*`.

### Parser: „N-pokojowa" jako numer, „boczna ul. X" i przymiotniki-ulice w whitelist (2026-07-13)
- **fix** (zgłoszenie Mateusza — „Przytulna 2-pokojowa Stancja" ID1bpu4N błędnie na mapie): tytuł dawał adres „Przytulna 2", bo „Przytulna" to realna ulica Lublina (celowo NIE na blockliście), a „2" z „2-pokojowa" wpadało we wzorzec numeru domu. Guard `_NUM_ROOMCOUNT` w `extract_address` (główny wzorzec + fallback nazwisk): cyfra tuż przed „-pokojowa/-osobowy/-piętrowe/-poziomowe/-izbowe" to liczba pokoi, nie numer. Łapie też przyszłe przypadki (Słoneczna/Zielona/Kameralna N-pokojowa).
- **fix**: „boczna ul. X" = przecznica ulicy X (mieszkanie stoi przy bocznej uliczce, nie przy X) — nazwa po „boczna ul./ulica/al." usuwana w `_normalize_text` (jeden chokepoint dla wszystkich czterech parserów), więc żadna ścieżka nie stawia oferty na X. Decyzja Mateusza: takie opisy → „Brak adresu".
- **fix (systemowy)**: `extract_from_whitelist` wybierał NAJDŁUŻSZEGO kandydata, więc przymiotniki-które-są-ulicami wygrywały użyte opisowo — „płyta **elektryczna**" → ul. Elektryczna (~19 tekstów w golden!), „w **spokojnej** okolicy" → ul. Spokojna, „pomieszczenie **gospodarcze**" → ul. Gospodarcza. Teraz jednowyrazowe dopasowanie ulicy wymaga rzeczownika własnego: WIELKA litera w oryginale („na Spokojnej") LUB prefiks ulicy przed nazwą („ul zana", „ul.żarnowiecka"). Guard `_ADJ_ROOMCOUNT` dodatkowo odrzuca „Przytulna 2-pokojowa" (słowo-przymiotnik przed złożeniem).
- **dane**: usunięte 2 oferty (ID1bpu4N „Przytulna 2" oraz ID12PKxH „Zbożowej" — obie tylko „boczna ul. …") + wpisy w `geocoding_cache.json` („Przytulna 2" miało zresztą śmieciowe coords Nominatim ~5 km od realnej ul. Przytulna). Zregenerowany `docs/data.json` (1403→1401 ofert). Golden przebudowany (`build_golden.py`, 2255 tekstów, 0 regresji): 29 zmian to poprawki przymiotnik→realna ulica, 28 to przymiotniki/fragmenty → None. Znany koszt: ulice pisane z małej BEZ prefiksu (np. „nadbystrzycka") wymagają teraz prefiksu lub wielkiej litery; istniejące markery bez zmian (skip-scan trzyma coords).

### Fix zbierania wyświetleń ulubionych (2026-07-13)
- **fix**: pierwsze 3 snapshoty miały `views=None` — licznik „Wyświetlenia: N" na OLX montuje się przez IntersectionObserver dopiero, gdy stopka wejdzie w viewport, a `fetch_views` teleportował scrollem od razu na dół, omijając trigger. Teraz: stopniowy scroll (kroki ~900px), klik w banner cookies (OneTrust), `wait_for_function` na liczbę w DOM + nasłuch odpowiedzi sieciowej `page-views` jako drugie źródło, diagnostyka w logach Actions gdy licznik nieobecny.
- Zweryfikowane runem workflow na branchu (dispatch z ref=branch): snapshot 22:15 ma `views: 64`. Zakładka pokazuje ostatni znany pomiar w kafelku Wyświetlenia.
- **fix (`scanner.yml`)**: pętla retry pushu gubiła wyniki scanu przy wyścigu z równoległym runem — po nieudanym rebase kolejne `git pull` padało na „Pulling is not possible because you have unmerged files" (run 22:05 stracił scan). Teraz: `git rebase --abort` przed każdą próbą (sprząta stan) + `git pull --rebase -X theirs` (przy konflikcie na plikach danych wygrywa świeży scan).

### Mapa: warstwa „Przeniesione (poprzednie adresy)" domyślnie wyłączona (2026-07-12)
- **feat** (decyzja Mateusza): checkbox warstwy startuje odznaczony (`index.html`), a `markerLayers.addrArchival` nie jest dodawana do mapy przy inicjalizacji (`script.js`, bump `?v=22`). Piny archiwalne dalej się renderują do grupy (licznik działa), a „pokaż" w historii adresu popupu automatycznie włącza warstwę + checkbox. Zweryfikowane headless: start off → toggle on działa.

### Zakładka ⭐ Ulubione: śledzenie pojedynczych ofert + wykres wyświetleń (2026-07-12)
- **feat**: nowy moduł ulubionych (wariant B z fallbackiem przez Claude'a, wybór Mateusza). Lista: `data/favorites.json` (dopisywana na wiadomość „dodaj do ulubionych: <link>"). `src/favorites_tracker.py` robi per oferta 1 anonimowy request do OLX API v1 (`/api/v1/offers/{id}/`) i dokłada snapshot (cena, status, last_refresh) do `data/favorites_tracking.json`; wyświetlenia zbiera opcjonalnie headless Chromium (Playwright) — licznik „Wyświetlenia: N" jest doładowywany JS-em za tokenem, zwykły request go nie widzi. Brak Playwrighta ≠ błąd: snapshot zapisuje się z `views=None`.
- **feat**: `src/favorites_generator.py` → `docs/favorites_data.json` (historia cen = zmiany, odświeżenia = zmiany last_refresh/pushup, pełna seria wyświetleń; adres/coords dołączane z `offers.json` po short_id).
- **feat**: `docs/ulubione.html` — karty ofert ze statami jak w Firmach + wykres liniowy wyświetleń w czasie (Chart.js, kolor #667eea zwalidowany na jasnym tle) i tabela pomiarów. Sekcja „Gwiazdki z mapy": ulubione zapisane lokalnie (localStorage), z przyciskiem kopiującym gotową wiadomość dla Claude'a.
- **feat**: gwiazdka ⭐/☆ w popupach mapy (`script.js`, blok helperów NA GÓRZE pliku — funkcje używają top-level const, więc muszą stać przed kodem inicjalizacji mapy; bump `?v=21`) + link ⭐ Ulubione w nawigacji wszystkich stron.
- **fix**: wspólny nagłówek (`header.css?v=3`): próg ciasnego wariantu nawigacji przesunięty 1200→1400px, bo po 10. zakładce luźny wariant nachodził na tytuł przy ~1280px.
- Pierwsza śledzona oferta: „Pokój Najem Lublin, Centrum" (Bernardyńska 24, ID1be1cg).
- **workflow** (za zgodą Mateusza): krok `Track favorites` w `scanner.yml` po generacji mapy — instaluje Playwrighta + Chromium (~2 min/run) i odpala `favorites_tracker.py`; `docs/favorites_data.json` dodany do commitowanych ścieżek. Krok jest `continue-on-error` — awaria trackera nie psuje scanu.

### Zakładka Pominięte: usunięty banner debug + ujednolicony nagłówek (2026-07-12)
- **fix**: usunięty żółty banner „⚠️ Strona tymczasowa do analizy błędów parsera..." ze strony `skipped_debug.html` (u źródła: `src/skipped_debug_generator.py`).
- **fix**: belka nagłówka zakładki Pominięte używa teraz wspólnego `assets/header.css` (klasa `sp-header`) zamiast własnego, większego inline CSS — identyczny rozmiar jak w pozostałych zakładkach. Przy okazji dodany brakujący link 📉 Indeks w nawigacji.

### Parser: priorytet pozycyjny zamiast długości nazwy ulicy (2026-07-09)
- **feat**: TYTUŁ ma pierwszeństwo nad opisem (`main.py` → `_process_offer`, decyzja Mateusza): kolejność parsowania adresu to tytuł → tytuł+opis → sam opis, we wszystkich trzech stopniach (`extract_address`/`extract_street_only`/`extract_from_whitelist`) oraz w re-parsingu bogus cache. Adres z tytułu to adres oferty; adres z opisu może dotyczyć innej lokalizacji tego samego wynajmującego.
- **fix**: prawie wszystkie oferty profilu „stylowe pokoje-ania" dostawały adres „Chęcińskiego 1", bo każdy opis wynajmującej wymienia wszystkie jej lokalizacje („Dostępność innych lokalizacji: ul. Kurantowa 8, ul. Skołuby 10, ul. Chęcińskiego 1..."), a `extract_address` wybierał kandydata po długości nazwy — „Chęcińskiego" (12 liter) wygrywało z właściwym adresem z tytułu/leadu. Nowy wybór: prefiks ul./al./pl., potem **najwcześniejsza pozycja w tekście** (właściwy adres oferty jest na początku, listy „innych lokalizacji" na końcu).
- **dane**: przeparsowane oferty profilu — 7 poprawionych (Paganiniego 4/11, Jutrzenki 12, Skołuby 10, Pogodna 34), 3 bez zmian (Chęcińskiego 1 ×2, Kurantowa 8); zregenerowane `docs/data.json` + `profile_data.json`.
- **audyt bazy**: dry-run re-parse'u 591 aktywnych ofert — 75% identycznych; masowy re-parse ODRZUCONY, bo baza nie przechowuje tytułów (masowe parsowanie działałoby bez tytuł-first i pogorszyłoby ~60+ rekordów, a 59 straciłoby adres). Z audytu wyszła blocklista śmieciowych drugich członów: `szukasz/odstąpię/podnajmę/zarówno/koszt(y)` („Nadbystrzycka Szukasz", „Kleeberga Koszt"). UWAGA: `przytulna/przytulny` celowo NIE — ul. Przytulna to realna ulica Lublina.
- **blocklista**: `całość/całości/samsung/smart/orange/światłowodowy` — szum („(całość 72m²)", „TV SAMSUNG SMART 32"), który po zmianie priorytetu wygrywałby pozycją. Golden przebudowany (2177 tekstów); efekt uboczny: adresy częściej w mianowniku z tytułu („Muzyczna 7" zamiast „Muzycznej 7"), geokoder normalizuje oba tak samo.

### Fix CI: golden zbudowany bez geopy kodował zdegradowany parser (2026-07-09)
- **fix**: workflow Testy czerwony od PR #51 — golden był przebudowany w środowisku bez `geopy`, a `extract_from_whitelist` przy ImportError geocodera cicho wyłącza dopasowania mianownikowe (`to_nominative` → identyczność). Golden zakodował None dla 7 tekstów typu „Jagiellońskiej 33", które pełny parser (CI) rozwiązuje do „Jagiellońska". Golden przebudowany w pełnym środowisku (2171 tekstów); to samo wyjaśnia poranny pozorny „dryf cache" przy Garbarskiej.
- **guard**: `scripts/build_golden.py` robi twardy `from geocoder import to_nominative` — budowa golden na zdegradowanym parserze pada od razu zamiast produkować fałszywą prawdę.

### Nowy profil firmowy: stylowe pokoje-ania (2026-07-09)
- **feat**: dodany 7. śledzony profil OLX do `TRACKED_PROFILES` (`profiles_config.py`): „stylowe pokoje-ania" (user_id 28543245, https://www.olx.pl/oferty/uzytkownik/1WLoW/, 8 ofert w Lublinie). Propagacja automatyczna: zakładka Firmy (`profile_data.json`), warstwa firmy/agencje na mapie głównej (`tracked_profiles` w `data.json`, drzewo profili w `script.js`). Oferty profilu dostaną tag firmowy przy najbliższym scanie.

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
