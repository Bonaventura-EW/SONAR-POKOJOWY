---
id: 2026-09-12-gone-day-definition-alignment
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-09-12
category: bugfix
what: Mapowy filtr "zniknęło danego dnia" przestawiony z last_seen na deactivation_dates, przez co pokrywa się z wykresem odpływu we wszystkich dniach historii.
why: Mapa i wykres odpływu liczyły ten sam dzień inaczej (ostatni dzień NA listingu vs dzień wykrycia braku przez skan), więc dla 10.09.2026 wykres pokazywał 31 ofert, a mapa 23 — systematyczne przesunięcie o dobę plus całkowicie pominięte oferty reaktywowane.
how: Generator mapy wystawia per-ofertę listę dni zniknięcia (gone_days) zbieraną z deactivation_dates, także z versions[], z fallbackiem na last_seen wyłącznie dla rekordów sprzed wdrożenia tego pola. Front filtruje po tej liście i stosuje ją do WSZYSTKICH ofert, także dziś aktywnych (reaktywowanych), więc tryb "zniknięcia" nie może już wyłączać warstw aktywnych. Metryka odpływu deduplikuje po (oferta, dzień), bo opisuje oferty, a na mapie jedna oferta to jeden marker.
surface: src/map_generator.py, src/trend_generator.py, docs/assets/script.js
generality: family
propagate: yes
commit: e6a6d18
---

# Kontekst

Pułapka jest ogólna dla każdego repo z rodziny, które ma naraz wykres przepływów
i mapę/listę filtrowaną po dniu: "zniknęło" ma dwie naturalne definicje i wystarczy,
że dwa moduły wybiorą różne, żeby liczby rozjechały się w KAŻDYM dniu. `last_seen`
jest dodatkowo stratny — trzyma tylko ostatnią śmierć oferty, więc oferta, która
umarła, wróciła i umarła znowu, gubi pierwsze zniknięcie.

Odrzucone alternatywy:
- przestawienie WYKRESU na `last_seen` — spójne, ale traci wielokrotne zniknięcia
  i reaktywacje; `deactivation_dates` jest źródłem prawdy, `last_seen` pochodną,
- zostawienie rozjazdu z przypisem w UI — użytkownik i tak porównuje liczby.

Reaktywowane oferty (aktywne dziś, zniknęły wybranego dnia) bez oznaczenia wyglądają
jak zwykłe aktywne, więc dostały własne: krzyżyk "nieaktywna" jak reszta zniknięć plus
plakietkę z symbolem powrotu w wolnym rogu markera, oraz licznik "ile wróciło" przy
liczbie zniknięć dnia. Oznaczenie zależy od trybu, nie od rekordu, więc musi być
czytane przy każdym rysowaniu kształtu (nie zapisane w opcjach markera przy tworzeniu)
i wymaga wymuszonego repaintu przy wejściu w tryb.
