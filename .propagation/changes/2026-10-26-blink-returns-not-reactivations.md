---
id: 2026-10-26-blink-returns-not-reactivations
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonary
date: 2026-10-26
category: bugfix
what: Powrót oferty po mignięciu (zniknięcie i powrót w ciągu 24 h) nie liczy się jako reaktywacja na wykresach, w pasmach recyklingu ani we fladze "reaktywowana" na mapie.
why: Po odfiltrowaniu mignięć z odpływu (manifest 2026-10-26-outflow-without-blinks) ich powroty dalej liczyły się jako reaktywacje, więc bilans napływ − odpływ od 03.09 wychodził +169 przy spadku Indeksu o 289. Po poprawce −304, czyli zgodnie z Indeksem co do 15 ofert. 56 aktywnych ofert było oznaczonych jako reaktywowane wyłącznie przez mignięcia.
how: Jedna funkcja `_blinks(offer)` paruje każdą deaktywację z najbliższą reaktywacją i oznacza parę jako mignięcie, gdy dzieli je najwyżej `BLINK_MAX_HOURS`. Z niej korzystają `exit_days` (odpływ), `real_reactivations` (szereg reaktywacji, napływ całkowity, pierwsza reaktywacja w pasmach) i `is_reactivated` (flaga w data.json). Oferty z `reactivated_at`, ale bez zapisanych dat reaktywacji, zachowują flagę.
surface: src/trend_generator.py, src/map_generator.py, docs/trend.html, test_trend_index.py
generality: family
propagate: maybe
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

Wdrażaj razem z filtrem mignięć w odpływie albo wcale: połowiczny filtr psuje
bilans przepływów (napływ zawiera powroty, których zniknięć odpływ nie zna).

Kontrola po wdrożeniu: suma (napływ − odpływ) za okres powinna być bliska zmianie
liczby aktywnych ofert w tym samym okresie.
