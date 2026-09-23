---
id: 2026-09-23-apexcharts-month-bands
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonary
date: 2026-09-23
category: feature
what: Naprzemienne, subtelne pasy tła co drugi miesiąc na wykresie liniowym ApexCharts (Saldo zmian cen na stronie Indeks), żeby granice miesięcy było widać bez czytania osi X.
why: Na długich (100+ dni) szeregach czasowych trudno ocenić "w którym to było miesiącu" tylko z podpisów osi. Użytkownik dostał 20 wariantów wizualnych do wyboru (mockup jako Artifact, real dane z produkcji) i wybrał najbardziej stonowany: kolor marki przy 7% opacity, bez separatorów i etykiet miesięcy.
how: Funkcja `_monthBandsXaxis(daily)` liczy granice kalendarzowych miesięcy z zakresu dat pierwszej i ostatniej próbki serii (`daily[0][0]` … `daily[last][0]`), zwraca tablicę adnotacji ApexCharts `{x, x2, fillColor, opacity}` tylko dla co drugiego miesiąca (parzyste zostają bez pasa), z granicami przyciętymi (`Math.max`/`Math.min`) do faktycznego zakresu danych. Podpięte przez `opts.annotations.xaxis = (opts.annotations.xaxis || []).concat(...)` — WAŻNE: istniejący kod w kilku miejscach robił `opts.annotations = {...}` (przypisanie, nie merge), co nadpisywało wcześniej ustawioną adnotację linii zera. Włączone selektywnie flagą `extra.monthBands: true` tylko na jednym wywołaniu współdzielonego renderera, żeby nie zmieniać wyglądu pozostałych wykresów bez osobnej zgody.
surface: docs/trend.html
generality: family
propagate: maybe
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

Technika jest generyczna dla ApexCharts (nie ma nic specyficznego dla rynku
najmu) — jeśli używacie tej samej biblioteki do wykresów liniowych/czasowych,
`_monthBandsXaxis()` kopiuje się praktycznie 1:1, zmienia się tylko kolor i
opacity pod Wasz motyw.

Jedna pułapka, na którą warto zwrócić uwagę PRZED kopiowaniem, nie po: jeśli
Wasz kod (tak jak nasz) w kilku miejscach warunkowo PRZYPISUJE
`opts.annotations = {...}` zamiast scalać pola (`yaxis`/`xaxis` osobno), dwie
adnotacje na tym samym wykresie potrafią się wzajemnie skasować po cichu —
bez błędu w konsoli, po prostu jedna z nich nie narysuje się nigdy. U nas to
akurat nie ujawniło się jako bug (linia zera i pasy miesięcy nie kolidowały
z żadną z pozostałych gałęzi warunkowych na tym wykresie), ale przy kopiowaniu
wzorca na inny wykres współdzielonego renderera warto to sprawdzić.

Wybór wariantu (7% opacity, bez etykiet) był subiektywną decyzją użytkownika
z 20 pokazanych opcji — nie traktujcie konkretnych wartości kolorów jako
rekomendacji, tylko sam mechanizm liczenia granic miesięcy i mergowania
adnotacji.
