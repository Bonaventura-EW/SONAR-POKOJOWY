---
id: 2026-10-26-velocity-history-chart
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonary
date: 2026-10-26
category: feature
what: Wykres historii Market Velocity (rolling 7 dni, dzień po dniu) na tle stref aktywności, pod "Rozkładem dziennym" w sekcji Wskaźnik Rotacji Rynku, z przełącznikiem 6 miesięcy / cała historia.
why: Pasek Market Velocity pokazywał tylko dzisiejszą wartość, bez kontekstu, czy rynek przyspiesza, czy zwalnia. Przy okazji wyszło, że formuła ucinała wynik na 100, a rynek przekraczał 100 przez 79 z 90 dni, więc historia z limitem byłaby płaską linią. Użytkownik wybrał wariant A (linia na tle stref) i skalę bez limitu z 5 mockupów na prawdziwych danych.
how: `processData()` liczy `rotation.history`: dla każdego dnia od pierwszego dnia danych okno 7 dni z tych samych liczników `dailyNew`/`dailyRemoved` co pasek, więc ostatni punkt = wartość paska. Velocity bez `Math.min(100, ...)`; pasek ma szerokość obciętą do 100%, a tekst "/100" tylko do 100. Wykres Chart.js (line) z dwoma inline pluginami: pasy stref (0-30/31-60/61-80/81+) rysowane w `beforeDatasetsDraw` przez `y.getPixelForValue` z podpisami, oraz podpis wartości przy ostatnim punkcie. Dzisiejsza doba jest niepełna (usunięcia liczone po `last_seen`), więc ostatni punkt jest pusty, ostatni odcinek przerywany (`segment.borderDash`), a statystyki min/max/średnia pomijają dzisiejszą dobę.
surface: docs/market_analysis.html
generality: family
propagate: maybe
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

Przenośne, jeśli brat ma podobny wskaźnik liczony z oknem kroczącym: wzorzec
"historia wskaźnika = ta sama formuła liczona dla każdego dnia, ostatni punkt =
bieżąca wartość" plus pasy stref jako plugin Chart.js kopiuje się prawie 1:1.

Pułapki:
- Sprawdź, czy wskaźnik nie jest ucinany (`Math.min(100, ...)`). U nas limit
  sprawiał, że historia przez większość czasu leżała na 100.
- Jeśli "usunięte" liczone są po dacie ostatniego widzenia, dzisiejszy dzień jest
  zawsze niepełny i wykres opada na końcu. Oznacz go wizualnie i wyłącz ze statystyk.
- Odrzucone warianty: obszar w gradiencie paska, pasek ciepła (kafelki), słupki
  w kolorze strefy, rozbicie nowe/usunięte jako stos.
