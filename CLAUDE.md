# SONAR-POKOJOWY — Onboarding dla Claude Code

> **Co to za repo:** Automatyczny monitoring ofert najmu pokoi z OLX w Lublinie. Scraper → geokodowanie → mapa Leaflet hostowana na GitHub Pages. Brak backendu, brak bazy — wszystko statyczne, w JSON-ach commitowanych do repo.

> **Pełna dokumentacja:** `BLUEPRINT.md` (44 KB, kompletny opis architektury). Czytaj go, gdy potrzebujesz głębi. Ten plik to skrót do natychmiastowego startu.

> **Historia zmian:** `CHANGELOG.md` (kanoniczne, zwięzłe). **Czytaj go na początku każdej sesji** — zawiera kontekst ostatnich zmian niezbędny do zrozumienia stanu projektu. Stare raporty z napraw (`RAPORT_*`, `PODSUMOWANIE_*`, `WIZUALIZACJA_*`) → `docs/archive/`. Luźne backupy danych → `data/backups/`.

---

## 👔 PODZIAŁ RÓL

- **Mateusz**: koncepcja, decyzje wizualne/produktowe, wybór wariantów, kierunek.
- **Claude**: **pełna egzekucja od A do Z** — implementacja, commit, push, **otwarcie PR-a, merge do `main`**, weryfikacja czy GitHub Pages się zaktualizowały. Mateusz NIE robi mergów ani PR-ów. Po akceptacji wizualnej Claude doprowadza zmianę do produkcji bez dopytywania o każdy krok.
- Wyjątki gdy Claude PYTA przed wykonaniem: rzeczy destrukcyjne (force push, reset --hard, kasowanie branchy z cudzymi commitami), zmiana w `main` bez PR-a, edycja workflowów GitHub Actions, zmiany w `data/offers.json` ręcznie, **merge PR-a do `main`** (zawsze zapytaj przed mergem).

---

## ⚡ KOMENDY-SKRÓTY MATEUSZA (rozumiej dosłownie)

- **"scan" / "uruchom scan" / "odpal scan" / "zrób scan"** → **ZAWSZE** znaczy: triggeruj GitHub Actions workflow `238181145` przez `curl -X POST` z `$GITHUB_TOKEN` na endpoint `https://api.github.com/repos/Bonaventura-EW/SONAR-POKOJOWY/actions/workflows/238181145/dispatches` z body `{"ref":"main"}`. Spodziewany kod: `204`. **Nigdy** nie odpalaj `python src/main.py` lokalnie, chyba że Mateusz wyraźnie napisze "lokalnie".
- Po triggerze: zwróć tylko kod HTTP i link do https://github.com/Bonaventura-EW/SONAR-POKOJOWY/actions. Nie pollu statusu, nie czekaj na koniec.

---

## 🚨 ZASADY WSPÓŁPRACY Z UŻYTKOWNIKIEM (Mateusz)

Czytaj uważnie — to nie są sugestie, to są twarde reguły wypracowane przez wiele iteracji.

1. **Komunikuj się po polsku**, terse. Mateusz odpowiada krótko: `tak` / `nie` / `inaczej` / konkretny URL OLX z bugiem.
2. **Visual-first dla UI**: zanim zmienisz cokolwiek wizualnego, pokaż artifact before/after w HTML do akceptacji. Bez `tak` od użytkownika — nie implementuj.
3. **Backend fixes preferred**: jeśli problem widać na froncie, ale źródło jest w pipeline — naprawiaj u źródła (`src/`), nie patchuj w `docs/`.
4. **Direct deletion over flagging**: złe/bogus rekordy usuwaj z bazy całkowicie, nie flaguj jako "disabled".
5. **One feature at a time**: kończ i weryfikuj jedną zmianę przed startem kolejnej.
6. **Diagnoza przed fixem**: zidentyfikuj root cause, nie zgaduj. Pokaż użytkownikowi diagnozę, dopiero potem proponuj poprawkę.
7. **Proposals A/B/C dla nietrywialnych feature'ów**: gdy decyzja ma więcej niż jeden wymiar, przedstaw 2–3 opcje, niech wybierze.
8. **Bez przeprosin i bez auto-flagellation**: gdy się mylisz, uznaj, popraw, jedź dalej.

---

## 📁 STRUKTURA REPO — ŚCIĄGAWKA

```
src/                      ← cały backend Python (uruchamiane z poziomu `src/`)
├── main.py               ← orkiestrator skanu (entrypoint)
├── scraper.py            ← OLX listing + detail pages, BASE_URL tu
├── address_parser.py     ← regex extractor adresów z opisów (LOGIKA)
├── address_parser_data.py ← DANE parsera: EXCLUDED_WORDS, LUBLIN_DISTRICTS, PREFIX_MAP, HARDCODED_LUBLIN_STREETS (edytuj blocklisty/dzielnice TUTAJ)
├── price_parser.py       ← JSON-LD → desc parser → HTML fallback
├── geocoder.py           ← Nominatim (OpenStreetMap)
├── duplicate_detector.py ← Levenshtein 95%
├── map_generator.py      ← data/offers.json → docs/data.json
├── monitoring_generator.py
├── api_generator.py      ← statyczne endpointy mobilne
├── top5_generator.py
├── profile_generator.py
├── offer_tagger.py
├── scan_logger.py
└── (pomocnicze: quick_scan, retry_none_cache, cleanup_*, skipped_*)

data/                     ← źródło prawdy
├── offers.json           ← główna baza ofert (NIGDY nie edytuj ręcznie bez backupu)
├── scan_history.json     ← historia skanów (źródło prawdy o statusie scanów,
│                            NIE polegaj na GitHub Actions API conclusion)
├── geocoding_cache.json  ← cache adres→lat/lon (czyść TANDEM z offers.json!)
└── *.backup_*            ← punkty kontrolne (zostawiaj, nie kasuj)

docs/                     ← frontend GitHub Pages (NIE edytuj ręcznie data.json!)
├── index.html            ← główna mapa Leaflet (markery na canvas — assets/script.js)
├── assets/script.js      ← logika mapy: filtry, warstwy, popupy + render canvas (L.canvas)
├── analytics.html        ← Chart.js
├── monitoring.html       ← status skanów
├── market_analysis.html
├── data.json             ← REGENEROWANY przez map_generator.py
├── monitoring_data.json  ← REGENEROWANY
├── api/                  ← statyczne endpointy mobilki (SZPERACZ)
│   ├── status.json
│   ├── history.json
│   └── health.json
└── ...

.github/workflows/scanner.yml  ← cron 9:00 / 15:00 / 21:00 CEST + workflow_dispatch
```

---

## 🔥 PUŁAPKI, KTÓRE JUŻ NAS UGRYZŁY — NIE POWTARZAJ

Te błędy są naprawione. Jeśli edytujesz odpowiedni kod, **zachowaj zabezpieczenia**:

### Backend / pipeline

- **Empty-scrape guard** (`main.py` → `_mark_inactive_offers`): jeśli scraper zwróci 0 ofert albo <30% aktywnego stanu, BLOKUJ masowe deaktywowanie. Bez tego jeden zepsuty scrape kasuje pół bazy.
- **`skipped_offer_ids`**: inteligentne skanowanie pomija oferty z niezmienioną ceną. Ich ID **MUSZĄ** trafić do `_mark_inactive_offers()` jako `skipped_ids`, inaczej zostaną fałszywie zdeaktywowane.
- **Inactive URL verification**: przed deaktywacją odpytaj URL OLX-a — HTTP 410 = na pewno usunięte, 404 czasem wraca, `availability: InStock` w JSON-LD = oferta nadal żywa (reaktywuj).
- **Address parser — false addresses**: regex łapie "X minut", "Y metrów" jako ulice. Sprawdzaj `non_street_names` set i excluded words. Litera `O` vs cyfra `0` w nazwach — odrzucaj.
- **Adres: TYTUŁ ma pierwszeństwo nad opisem** (`main.py` → `_process_offer`): opisy firm wymieniają wszystkie swoje lokalizacje ("Dostępność innych lokalizacji: ul. X, ul. Y..."), więc adres z opisu może dotyczyć innego mieszkania tego samego wynajmującego. Kolejność parsowania: tytuł → tytuł+opis → sam opis. W `extract_address` przy remisie prefiksu wygrywa WCZEŚNIEJSZA pozycja w tekście (nie dłuższa nazwa!).
- **Genitive case streets**: polski dopełniacz ("ul. Lubelskiej" → "Lubelska") — wzorce w `address_parser.py`.
- **`extract_street_only` — ulica ZNANA bije NIEZNANĄ bez względu na pozycję**: `priority_class=2` (ulica w whiteliście/cache) wygrywa z `priority_class=1` (nieznana) niezależnie od kolejności w tekście. Pułapka: orientacyjny punkt ("10 min od biurowców przy **ul. Zana**") bije faktyczny adres ("mieści się przy **ul. Magdaleny Brzeskiej**"), gdy realna ulica NIE jest w whiteliście (a jest tylko krótsza forma w cache). Fix: dodaj realną ulicę do `HARDCODED_LUBLIN_STREETS` (`address_parser_data.py`) — także formy dwuczłonowe ("magdaleny brzeskiej"), bo `extract_street_only` wyciąga oba wyrazy po "ul.". Po zmianie: `python test_address_parser_golden.py`. (2026-07-17, ID1buaHj)
- **Price pipeline**: JSON-LD = źródło prawdy. HTML fallback wyciąga koszty mediów albo numer ulicy jako cenę — używaj tylko gdy JSON-LD nie ma.
- **Price range per-offer**: ceny przypisuj per-oferta, nigdy averagowane na markerze.
- **Geocoding cache**: usuwając wpisy z `offers.json`, **usuń też** odpowiadające wpisy z `geocoding_cache.json`. Inaczej stare/błędne współrzędne wrócą.

### Frontend

- **LayerGroup MUSI mieć `.addTo(map)`**: dodanie markerów do grupy to nie to samo co dodanie grupy do mapy. Klasyczny bug "warstwa nie widać".
- **Markery na canvasie (NIE divIcon)**: pinezki/kwadraty rysowane są na JEDNYM `<canvas>` (`L.canvas`) przez własne klasy `PinMarker`/`SquareMarker` (rozszerzenia `L.CircleMarker`) w `assets/script.js` — wydajność przy ~1000 ofert. **Nie cofaj do `L.divIcon`/SVG.** Kształt + badge (`N`/`↓↑`/`×`) rysują metody `_updatePath`; klikalność (popup) zależy od `_containsPoint` — edytując kształt zaktualizuj OBA. Kolejność rysowania (kwadraty pod pinezkami, firmy na wierzchu) ustawia `restackCanvasOrder()`. (Stary wariant `mapa2.html`/`script2.js` był prototypem tego rozwiązania i został scalony/usunięty.)
- **Format daty PL**: `"DD.MM.YYYY HH:MM"` — `new Date()` JS-a tego nie sparsuje. Używaj custom `parseDateString()`.
- **Struktura `docs/data.json`**: zagnieżdżona `markers[].offers[]`, **nie** flat array. Po regeneracji przez `map_generator.py` — wymuś hard reload (Ctrl+F5).

### Workflow / Actions

- **Workflow ID**: `238181145`. Trigger: `POST /repos/.../actions/workflows/238181145/dispatches` z body `{"ref":"main"}` → status `204` = OK.
- **`conclusion=success` w API jest niewiarygodne**: zawsze sprawdzaj logi bezpośrednio. Prawda o skanach jest w `data/scan_history.json`.
- **Logi Actions → Azure blob**: `GET` na endpoint logów zwraca `Location` header z URL-em Azure blob, pobierz przez `curl`.
- **Golden test pokazuje regresje → NAJPIERW sprawdź zależności, nie golden**: `test_address_parser_golden.py` w świeżej web-sesji BEZ zainstalowanego `requirements.txt` (brak `geopy`/`pytz`) daje **fałszywe** regresje. `from geocoder import to_nominative` pada po cichu (`except ImportError`), krok "mianownik" w parserze umiera, więc formy dopełniaczowe (Czeremchowej, Smyczkowej, Szewskiej…) nie trafiają w mianownikowy fixture → `whitelist→None`. To **NIE** jest przestarzały golden. Setup odpala się automatycznie przez SessionStart hook (`.claude/settings.json` → `.claude/hooks/session-start.sh` → `.claude/setup.sh`); jeśli i tak widzisz te regresje, ręcznie `pip install -r requirements.txt --break-system-packages` i sprawdź ponownie. Golden zdrowy = 2255/2255. (2026-07-17)

---

## 🛠️ ŚRODOWISKO I KOMENDY

### Setup zależności
```bash
pip install -r requirements.txt --break-system-packages
# requirements.txt: requests, beautifulsoup4, lxml, python-Levenshtein, pytz, geopy
```

### Uruchomienie skanu lokalnie
```bash
cd src/
python main.py                # pełny skan
python map_generator.py       # regenerate docs/data.json
python api_generator.py       # regenerate docs/api/*
python top5_generator.py
python monitoring_generator.py
```

### Testy (w root, nie w `tests/`)
> Zależności instaluje SessionStart hook (`.claude/hooks/session-start.sh`). Bez nich golden daje FAŁSZYWE regresje — patrz pułapka wyżej.
```bash
python test_integration.py
python test_analytics.py
python test_monitoring.py
python test_price_fix.py
python test_address_parser_golden.py   # regresja parsera na 2255 realnych tekstach (zdrowy = 0 rozbieżności)
```

### Trigger scanu przez API (gdy nie chcesz czekać na cron)
```bash
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/Bonaventura-EW/SONAR-POKOJOWY/actions/workflows/238181145/dispatches \
  -d '{"ref":"main"}'
# spodziewany kod: 204
```

### Rozwiązywanie konfliktów git (sprawdzony pattern)
```bash
git pull --rebase
git checkout --theirs <plik_pochodny_np_docs/data.json>
python src/map_generator.py   # regenerate
git add <plik>
GIT_EDITOR=true git rebase --continue
git push
```

---

## 🧭 DECISION TREE — DOKĄD IŚĆ Z PROBLEMEM

| Problem zgłoszony przez Mateusza | Pierwsze miejsce do sprawdzenia |
|---|---|
| "marker w złym miejscu" / "zły adres" | `src/address_parser.py` + `data/geocoding_cache.json` |
| "cena jest dziwna" / "X zł zamiast Y zł" | `src/price_parser.py` (JSON-LD priorytet!) |
| "oferta zniknęła a powinna być" | `src/main.py` → `_mark_inactive_offers`, sprawdź `skipped_offer_ids` i empty-scrape guard |
| "warstwa się nie wyświetla" | `docs/index.html` → szukaj `LayerGroup` bez `.addTo(map)` |
| "data wygląda jak NaN/Invalid" | `parseDateString()` w `docs/*.html` — PL format |
| "scan się nie odpalił" | `data/scan_history.json` (truth), potem logi Actions |
| "duplikaty na mapie" | `src/duplicate_detector.py` — threshold Levenshtein 95% |
| "OCR / parser łapie bzdury" | `src/address_parser_data.py` → `EXCLUDED_WORDS` (blocklista). Po zmianie: `python test_address_parser_golden.py` (regresja na 2255 realnych tekstach). Zmiana zamierzona → `python scripts/build_golden.py`. |
| "marker na złej ulicy obok prawdziwej" (punkt orientacyjny wygrał) | `extract_street_only` — ulica ZNANA bije NIEZNANĄ bez względu na pozycję. Dodaj realną ulicę (też dwuczłonową) do `HARDCODED_LUBLIN_STREETS`. Patrz pułapka Backend/pipeline. |
| "golden test nagle pokazuje regresje" | NAJPIERW `pip install -r requirements.txt` (brak `geopy`/`pytz` → fałszywe regresje), dopiero potem podejrzewaj golden. Zdrowy = 2255/2255. |

---

## ✅ CHECKLIST PRZED ZAKOŃCZENIEM ZADANIA

Przed commitowaniem zawsze sprawdź:

- [ ] Czy edytowałem plik źródłowy (`src/`) zamiast pochodny (`docs/data.json`)?
- [ ] Jeśli zmieniłem dane (`data/offers.json`), czy zregenerowałem `docs/data.json` przez `python src/map_generator.py`?
- [ ] Jeśli usunąłem oferty, czy wyczyściłem `geocoding_cache.json`?
- [ ] Czy odpaliłem `python test_integration.py` i przeszło?
- [ ] Czy commit message jest sensowny po polsku? (przykład: `"fix: warstwa nieaktywne nie renderuje sie na mapie"`)
- [ ] Czy nie zostawiłem `print()` debug-owych w kodzie?
- [ ] Czy zaktualizowałem `CHANGELOG.md` o opis zmiany? (zawsze, bez wyjątku)

---

## 🤝 STYL ODPOWIEDZI

**Dobre:**
- "Diagnoza: `_mark_inactive_offers` nie dostaje `skipped_ids` z linii 142. Poprawiam, sekundę."
- "Przed zmianą — pokażę Ci before/after w HTML. Daj `tak` jak OK."
- "Mam 3 opcje jak to ugryźć: A) szybko ale brzydko, B) refactor `address_parser`, C) zmiana w geocoderze. Co wybierasz?"

**Złe:**
- "Świetne pytanie! Z radością pomogę! Oto co możemy zrobić..."
- Zaimplementowanie zmiany w UI bez pokazania artifactu before/after.
- Patchowanie objawu w `docs/` zamiast naprawy w `src/`.
- Generowanie wielkich raportów Markdown po każdej zmianie (mamy już 40 plików RAPORT_*.md).

---

**Powodzenia. Mateusz delegował Ci pełną egzekucję — nie pytaj o rzeczy, które możesz sam sprawdzić w repo. Działaj.**
