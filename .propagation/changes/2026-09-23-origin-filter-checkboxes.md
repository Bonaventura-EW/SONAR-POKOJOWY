---
id: 2026-09-23-origin-filter-checkboxes
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonary
date: 2026-09-23
category: feature
what: Dwa niezależne checkboxy "Nowe" / "Reaktywowane" na głównej mapie, które filtrują aktywne oferty wg pola offer.reactivated (kiedykolwiek wróciła po zniknięciu z listingu).
why: Wiedzieliśmy od dawna które oferty są reaktywowane (pole `reactivated`/`reactivated_at` liczy `map_generator.py` od miesięcy i trafia do `docs/data.json`), ale ta informacja była widoczna wyłącznie w trybie suwaka "Zniknięcia" — nie dało się na głównej mapie samodzielnie zobaczyć "tylko nowe" albo "tylko recykling". Użytkownik chciał dokładnie tego, nie nowej ikony/badge'a na pinezce.
how: Dwa checkboxy w sidebarze, domyślnie oba zaznaczone (odpowiednik "brak filtra"). `filterMarkers()` traktuje je jako filtr AND (nie OR jak reszta legendy pinezek) — podział jest rozłączny, więc odznaczenie jednego pokazuje wyłącznie drugą grupę. Liczniki dostają własną funkcję (`updateOriginCounts()`) skopiowaną wzorcowo z istniejącej `updateBadgeCounts()` — respektuje wszystkie POZOSTAŁE filtry, żeby liczba przy checkboxie odpowiadała na "ile ofert pojawi się, gdy go włączę". Zero zmian backendowych — dane już były w pipeline.
surface: docs/index.html, docs/assets/script.js
generality: family
propagate: maybe
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

Przenośne jest samo pole: jeśli Wasz scraper też wykrywa "oferta zniknęła z
listingu i wróciła" (u nas `deactivation_dates` / `reactivation_dates` per
oferta, patrz `src/map_generator.py::_gone_days`), dodanie tych dwóch
checkboxów to czysto frontendowa zmiana — nie trzeba nic ruszać w pipeline.

Rzecz, na której warto się zatrzymać przed kopiowaniem: zdecydowaliśmy się na
**AND, nie OR**. Reszta naszej "Legendy pinezek" (cena spadła/wzrosła/nowa/
odświeżona) to filtr OR — oferta bez żadnego zaznaczonego oznaczenia wpada do
"Bez zmian". Tu inaczej: KAŻDA aktywna oferta jest albo nowa, albo
reaktywowana (rozłączny podział), więc odznaczenie obu checkboxów świadomie
pokazuje zero ofert, a nie "wszystko z automatu". Jeśli u Was ten sam pattern
(rozłączny podział na dwie grupy) się powtarza gdzie indziej, ten sam kawałek
kodu (dwa checkboxy + AND) nadaje się do przeniesienia 1:1.

Użytkownik jawnie odrzucił wariant z nowym badge'em/ikoną na pinezce (był
pierwszą propozycją) na rzecz czystego filtrowania widoczności — warto to
rozstrzygnąć u siebie PRZED implementacją, nie zakładać automatycznie.
