---
id: 2026-09-12-window-balance-symmetry
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-09-12
category: bugfix
what: KPI „Bilans netto" (nowe − zniknięte w oknie czasowym) przestał być strukturalnie ujemny — wejścia i wyjścia liczymy teraz tym samym filtrem, więc bilans równa się dosłownie zmianie wielkości rynku.
why: Wejścia były filtrowane warunkiem „i nadal żyje", wyjścia warunkiem „już nie żyje". Rekord urodzony i zamknięty w tym samym oknie wchodził więc WYŁĄCZNIE na minus, a asymetria rosła z długością okna: przy oknie „cały czas" wzór degenerował się do `aktywne − nieaktywne` (u nas 836 − 1925 = −1089). Metryka nie mogła wyjść na plus, choćby rynek rósł — czytający widział stały spadek zamiast odczytu rynku.
how: (1) „Nowe" = wszystko, co urodziło się w oknie, także rekordy już zamknięte; wyjścia bez zmian. Po tym zachodzi tożsamość `nowe(okno) − zniknięte(okno) == żywe dziś − żywe na starcie okna`, którą da się sprawdzić niezależnie na samych danych i która jest najtańszym testem tej klasy błędu. (2) Rekordy-efemerydy (urodzone i zamknięte w oknie) trzeba pokazać, nie tylko doliczyć: osobny wariant karty w kolumnie „Nowe" (wyszarzona, dwukolorowy pasek, plakietka „już zniknęła", w stopce obie daty + czas życia), licznik „w tym N już zniknęło" pod KPI wejść i podpis bilansu zmieniony na „zmiana liczby ofert na rynku". Bez tego liczba wejść rośnie, a użytkownik nie widzi, skąd. (3) Akcje na karcie muszą patrzeć na STAN rekordu, nie na kolumnę, w której stoi — guzik „Mapa" otwiera efemerydę na warstwie nieaktywnych.
surface: docs/ostatnie.html
generality: universal
propagate: yes
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

**Przenośna jest reguła, nie kod.** Jednym zdaniem: *jeśli w metryce okna liczysz
wejścia filtrem „i nadal istnieje", a wyjścia filtrem „już nie istnieje", to bilans
ma wbudowany minus rosnący z długością okna* — i to nie jest szum, tylko stała
stronniczość. Wykryjesz to bez czytania kodu: weź najdłuższe okno. Jeśli bilans
zbiega do `żywe − martwe` zamiast do `żywe`, masz ten sam błąd.

Test, który warto przenieść razem ze zmianą: równość `bilans(okno) == żywe dziś −
żywe na starcie okna`, z prawą stroną liczoną NIEZALEŻNIE od kodu KPI (u nas wprost
z `docs/data.json`, po wszystkich oknach). Spięcie tych dwóch liczb ze sobą jest
tańsze niż fixture'y i łapie regresję od razu.

Czego świadomie NIE zrobiliśmy: reaktywacje zostają nieliczone po obu stronach
(rekord, który wrócił, nie jest ani „nowy", ani „zniknięty") — tak samo jak w naszym
`src/trend_generator.py`. Liczenie powrotów jako wejść byłoby tą samą asymetrią od
drugiej strony: odpowiadających im wyjść nie ma w danych.

U nas zmiana jest czysto frontowa (jeden plik, zero backendu i zero migracji danych),
bo KPI liczy się w przeglądarce z gotowego JSON-a. U brata, który liczy podobny bilans
po stronie generatora, ta sama reguła wejdzie w kod generatora — adaptacja dotyczy
miejsca, nie treści.
