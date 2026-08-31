---
id: 2026-08-31-coincident-marker-stacks
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-08-31
category: bugfix
what: Markery o identycznych współrzędnych (kilka ofert pod jednym adresem) są grupowane w jedną pinezkę z liczbą, a popup listuje wszystkie oferty spod tego adresu.
why: Pinezki leżały jedna na drugiej, więc klikalna była tylko wierzchnia — w naszej bazie 39 takich punktów i 69 ofert nie do otwarcia, rekordowo 12 ofert w jednym miejscu.
how: Przed rysowaniem markerów grupujemy rekordy po zaokrąglonych współrzędnych (`lat.toFixed(6),lon.toFixed(6)`). Grupa jednoelementowa idzie starą ścieżką; grupa większa dostaje jedną pinezkę tego samego kształtu, ale z liczbą w środku i kolorem najtańszej pozycji, oraz popup z płaską listą (klik w wiersz woła istniejącą funkcję podświetlania karty w panelu). Kluczowy detal: w rejestrze markerów KAŻDE id z grupy wskazuje na ten sam obiekt markera, a przełączanie ikony idzie przez jedną funkcję, która wie, czy to stos, czy pojedynczy rekord — inaczej podświetlenie z listy podmieniłoby ikonę stosu na zwykłą i zgubiło liczbę.
surface: docs/profile_tracker.html
generality: family
propagate: maybe
commit: PENDING
---

# Kontekst

**Kiedy to jest problem u brata.** Wszędzie tam, gdzie punkty na mapie biorą się z geokodowania
adresu, a nie z GPS-u: kilka rekordów pod tym samym adresem dostaje identyczne `lat/lon` co do
ostatniego miejsca po przecinku. Warto najpierw zmierzyć skalę u siebie — u nas dotknęło to 9 z 10
profili, ale w zbiorze bez powtarzalnych adresów problem może w ogóle nie istnieć.

**Dlaczego nie rozbicie geometryczne.** Rozważaliśmy jitter, rozetę, spiralę, spiderfy i klastrowanie.
Odpadły, bo w tym projekcie pozycja pinezki ma być prawdziwa (mapa służy do oceny lokalizacji), a przy
stosie 12 rozeta rozjeżdża się na dziesiątki metrów i zaczyna kolidować z sąsiednimi adresami.
Jeśli u brata dokładność pozycji jest mniej istotna niż liczba klików, tańszym wyborem jest rozeta
liczona w pikselach ekranu.

**Pułapki przy adaptacji.**
- Rejestr markerów zwykle mapuje `id rekordu → marker`; przy grupowaniu kilka id wskazuje na jeden
  marker. Każde miejsce, które ustawia ikonę „podświetloną", musi wiedzieć, którego typu to marker.
- Nie przeładowuj otwartego popupu przy kliknięciu wiersza — przewinięta lista wraca wtedy na górę.
- Popupy Leafletu powstają dopiero przy otwarciu, więc obsługa kliknięć wierszy musi iść przez
  delegację na dokumencie, a nie przez `addEventListener` na elementach w chwili budowania treści.
- Treść wiersza pochodzi z zewnętrznego serwisu: escapuj tekst i przepuszczaj `href` przez filtr
  schematu (`http(s)` only).
