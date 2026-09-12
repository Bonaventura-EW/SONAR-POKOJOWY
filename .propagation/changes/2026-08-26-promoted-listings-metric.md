---
id: 2026-08-26-promoted-listings-metric
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-08-26
category: feature
what: Scraper wykrywa płatnie wyróżnione ogłoszenia na listingu OLX, a zakładka Indeks pokazuje dzienny wykres ich liczby i udziału w rynku.
why: Nie zbieraliśmy w ogóle informacji o promowaniu — nie dało się odpowiedzieć, ile ofert jest płatnie wypychanych na górę listingu ani jak to się zmienia w czasie.
how: Wyróżnienie czytamy z parametru atrybucji, który serwer OLX doszywa do href-a kafelka (`search_reason=search|promoted` vs `search|organic`) — odporniejsze niż klasy CSS czy `data-testid`, z fallbackiem na plakietkę karty i alarmem w logach, gdy atrybucja zniknie. Stan zapisujemy per-oferta (`promoted`) plus historię dni (`promoted_dates`, max 1 wpis/dzień), bo tylko z dat da się zbudować szereg czasowy — wyróżnienia nie da się odtworzyć wstecz. Generator liczy z tego serię dzienną, średnią 7 dni i udział w liczbie aktywnych ofert; dni bez skanu są lukami, nie zerami.
surface: src/scraper.py, src/main.py, src/trend_generator.py, docs/trend.html, test_promoted.py
generality: family
propagate: maybe
commit: bab2ffb
---

# Kontekst

**Skąd pewność co do sygnału.** Parametr `search_reason` był już w naszej bazie, bo zapisujemy URL
oferty razem z query stringiem: 2086 rekordów miało `search|organic`, 198 `search|promoted`. Czyli
detektor został zweryfikowany na realnych danych, zanim powstał — bez ani jednego requestu do OLX.

**Czego świadomie nie zrobiliśmy.** API v1 profili firmowych zwraca własną sekcję `promotion`
(`top_ad`, `highlighted`). Kusi, żeby ją dokleić dla lepszego pokrycia, ale semantyka jest inna niż
na listingu i licznik zacząłby skakać zależnie od źródła. Metryka ma jedno źródło prawdy: listing.

**Pułapki przy adaptacji.**
- Oferty pomijane przez inteligentne skanowanie nie przechodzą ścieżki aktualizacji rekordu —
  flagę trzeba im dopisać osobno (u nas w `_mark_inactive_offers`), inaczej wyróżnienia znikają
  dla ofert bez zmiany ceny.
- Ten sam kafelek potrafi wystąpić dwa razy na stronie (blok promowanych nad listingiem +
  wystąpienie organiczne). Deduplikacja musi PODNOSIĆ flagę, a nie brać pierwszego wystąpienia.
- Wykres z dwiema osiami (liczba + %) przy `min: 0` na obu wychodzi płaski — Apex dopasowuje osie
  do siebie i rozciąga skalę daleko ponad dane. Zakresy liczymy z danych.
- Seria „udział w rynku" jest proporcjonalna do liczby wyróżnień, więc na jednym wykresie dubluje
  kształt tej pierwszej. Zostawiliśmy ją ukrytą do kliknięcia w legendę.
