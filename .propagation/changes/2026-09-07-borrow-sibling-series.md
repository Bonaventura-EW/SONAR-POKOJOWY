---
id: 2026-09-07-borrow-sibling-series
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-09-07
category: feature
what: Wykres pożycza historię od repo-brata mierzącego to samo źródło — jako druga, podpisana linia, po wcześniejszym zmierzeniu zgodności obu pomiarów.
why: Nasza nowa metryka miała jeden punkt (start w dniu wdrożenia), a brat mierzy to samo od czterech miesięcy. Wyrzucanie tej historii to strata, a doklejenie jej po cichu do własnego szeregu byłoby fałszem — dwa pipeline'y o różnej kadencji nie dają jednej serii.
how: Najpierw walidacja na częsci wspólnej: oba projekty śledzą ten sam podzbiór obiektów, więc dzienne liczby zdarzeń da się porównać wprost — mediana stosunku 1,05 na 49 dniach. Dopiero to uprawnia do pokazania ich danych obok naszych. Dane wchodzą jako SNAPSHOT w naszym repo (skrypt importujący z lokalnego klona brata), nie jako odczyt cudzego repo przy każdym przebiegu; snapshot niesie commit źródła i wynik walidacji, żeby przy kolejnym imporcie było widać rozjazd. Front rysuje je osobną linią z nazwą źródła i kadencją w legendzie, a odcinek gorszej jakości (rekonstrukcja z żywych rekordów, więc zaniżona o skasowane) jest zakreskowany. Druga metryka z tego samego źródła została ODRZUCONA, bo tam stosunek wyniósł 2,55 — zdarzenie chwilowe jest niewidoczne przy rzadszym próbkowaniu, więc to inna wielkość, nie ta sama zmierzona inaczej.
surface: scripts/import_szperacz_refresh.py, data/szperacz_refresh_backfill.json, src/trend_generator.py, docs/trend.html, test_trend_index.py
generality: universal
propagate: yes
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

**Przenośna jest procedura, nie dane.** Kolejność, która się broni:

1. **Znajdź część wspólną.** Nie porównuj sum ani średnich globalnych — znajdź podzbiór
   obiektów, który oba projekty śledzą, i porównaj szeregi dzienne. Bez tego „nasze dane
   wyglądają podobnie" jest opinią.
2. **Policz stosunek per dzień, weź medianę i kwartyle.** Średnia ukryje wyrwę; mediana
   z rozstępem pokaże i poziom, i stabilność.
3. **Obejrzyj rozjazdy, zanim je uśrednisz.** U nas 13 dni odstawało od reszty — to była
   awaria po stronie brata, nie różnica metod. Bez wycięcia jej stosunek wychodził 1,12
   zamiast 1,05, czyli ich awaria wyglądałaby jak nasza systematyczna nadwyżka.
4. **Dopiero wtedy decyduj — osobno dla każdej metryki.** Ta sama para pipeline'ów dała
   1,05 na jednej metryce i 2,55 na drugiej. Różnica bierze się z natury zdarzenia:
   stan trwający dobę widać przy każdej kadencji, zdarzenie chwilowe tylko przy gęstej.
   Zgodność na jednej metryce NIE upoważnia do pożyczenia drugiej.

**Dwie zasady wdrożeniowe, które warto skopiować:**

- **Snapshot, nie zależność.** Cudze repo może się przemeblować, zniknąć albo mieć awarię
  w środku twojego przebiegu. Import robi osobny skrypt uruchamiany ręcznie, a wynik —
  z commitem źródła i wynikiem walidacji w środku — leży u ciebie.
- **Obca seria zostaje obcą serią.** Własna nazwa w legendzie, informacja o kadencji,
  gorszy odcinek zakreskowany. Czytelnik ma widzieć, że patrzy na dwa pomiary, nawet
  jeśli pokrywają się co do 5%.
