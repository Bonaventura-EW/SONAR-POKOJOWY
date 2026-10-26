---
id: 2026-10-26-velocity-history-chart
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonary
date: 2026-10-26
category: feature
what: Sekcja "Wskaźnik Rotacji Rynku" (Market Velocity) przeniesiona z Analizy rynku na stronę Indeks, liczona w backendzie z tych samych szeregów co wykresy Odpływ i Nowe oferty, z historią velocity dzień po dniu na tle stref aktywności.
why: Pasek velocity pokazywał tylko dzisiejszą wartość bez kontekstu. Formuła ucinała wynik na 100, a rynek przekraczał 100 przez 79 z 90 dni, więc historia z limitem byłaby płaską linią. Stara sekcja liczyła też "usunięte" inną definicją (nieaktywne teraz, po last_seen) niż wykres Odpływu, więc po przeniesieniu pod niego pokazywałaby inne liczby dla tego samego dnia.
how: `trend_generator.build_velocity(outflow, inflow)` liczy dla każdego dnia (nowe + zejścia z rynku z 7 dni) ÷ 2 z gotowych dziennych szeregów `inflow.new.daily` i `outflow.daily`, zapisuje `velocity.daily/new7/out7` do `trend_data.json`. Okno musi mieć 7 zmierzonych dni (doba w toku i dzień bez skanu = luka). Front (ApexCharts, ciemny motyw) rysuje kafelki, pasek, rozkład 7 dni i linię historii; strefy to `annotations.yaxis` z `y`/`y2`, kreski miesięcy to `annotations.xaxis`, wartość końcowa to `annotations.points`. Bez limitu 100.
surface: src/trend_generator.py, docs/trend.html, docs/market_analysis.html, test_trend_index.py
generality: family
propagate: maybe
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

Przenośne, jeśli brat ma wskaźnik liczony z oknem kroczącym i stronę z dziennymi
szeregami przepływów: velocity liczone z tych samych szeregów co wykresy obok
gwarantuje, że liczby się zgadzają.

Pułapki:
- Sprawdź, czy wskaźnik nie jest ucinany (`Math.min(100, ...)`). U nas limit
  sprawiał, że historia przez większość czasu leżała na 100.
- Nie licz "usuniętych" po `last_seen` obecnie nieaktywnych ofert, jeśli obok jest
  wykres odpływu po dniu wykrycia: rozjazd o dobę i brak ofert, które wróciły.
- Odrzucone warianty wizualne: obszar w gradiencie, pasek ciepła (kafelki), słupki
  w kolorze strefy, rozbicie nowe/usunięte jako stos.
