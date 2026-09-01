---
id: 2026-09-01-rolling-window-activity-pills
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-09-01
category: feature
what: Belka statystyk profilu dostała trzy pigułki z liczbą zdarzeń (odświeżenia, reaktywacje) w oknach 30/60/90 dni, liczonych na froncie z dat, które już były w danych.
why: Belka pokazywała wyłącznie STAN (ile aktywnych, jakie ceny) — nie było widać, jak bardzo firma pracuje ogłoszeniami: podbija je, przywraca zdjęte. Dane na to leżały w JSON-ie nieużywane.
how: Funkcja countActivity() przechodzi po ofertach profilu i zlicza ZDARZENIA z list dat (jedna oferta podbita 8× daje 8), w trzech oknach naraz. Granica okna liczona od północy, nie od „teraz minus N×24h", bo daty mają dokładność dnia i ruchoma granica ucinałaby najstarszy dzień zależnie od pory dnia. Ponieważ metryka wystartowała później, niż sięga najdłuższe okno, refreshCoverageNote() dokleja do dymka „mierzone od DD.MM.RRRR" — ale tylko dopóki zebrana historia jest krótsza niż okno, więc adnotacja znika sama; początek pomiaru wyznacza najstarsza data w danych, nie stała w kodzie. Bez zmian w pipeline — liczenie na froncie, jak istniejąca śr. cena/min/max.
surface: docs/profile_tracker.html
generality: family
propagate: maybe
commit: (uzupełniony przy commicie)
---

# Kontekst

Warta przeniesienia jest przede wszystkim **para wzorców**, nie same pigułki:

1. **Okno liczone od północy.** Wszędzie, gdzie zliczamy zdarzenia o dokładności dnia
   w oknie „ostatnie N dni", ruchoma granica (`Date.now() - N*86400000`) po cichu gubi
   część najstarszego dnia — ta sama strona pokazuje inne liczby rano i wieczorem.

2. **Adnotacja o pokryciu danych, która wygasa sama.** Metryka włączona w połowie życia
   projektu ma okno dłuższe niż historia — „90 dni ≈ 60 dni" wygląda wtedy jak zastój
   rynku, a nie jak brak pomiaru. Zamiast hardkodować datę startu, bierzemy najstarszy
   wpis z danych i pokazujemy dopisek tylko dla okien dłuższych od zebranej historii.

Odrzucone warianty (Mateusz wybierał z trzech): pigułka na metrykę z liczbami
`307 · 430 · 444` (najciaśniej, ale które okno to które mówi dopiero podpis) i macierz
2×3 (najczytelniej, ale podnosi belkę z 34 na ~46 px kosztem wysokości mapy).
