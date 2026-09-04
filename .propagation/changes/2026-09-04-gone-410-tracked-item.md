---
id: 2026-09-04-gone-410-tracked-item
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-09-04
category: bugfix
what: Tracker śledzonych ofert rozpoznaje HTTP 410 Gone jako „zniknęła ze źródła" zamiast traktować je jak błąd sieci.
why: Kod znał tylko 404; każdy inny kod szedł ścieżką „błąd sieci → nie zapisuj snapshotu", więc wpis zamarzał na ostatnim pomiarze i w UI świecił „AKTYWNA" bez końca (13 z 27 śledzonych ofert, najstarsza zamrożona od 6 tygodni).
how: 410 dołożone do 404 jako sygnał usunięcia; 403/5xx dalej NIE zapisują snapshotu (WAF to nie dowód na zniknięcie). Zniknięcie zapisuje się jako jeden snapshot 'removed' — kolejne przebiegi pomijają wpis, żeby licznik pomiarów nie rósł bez pomiaru, ale tanie zapytanie leci dalej, więc chwilowe 410 samo by się odkręciło. Warstwa prezentacji czyta cenę i daty z ostatniego NIEPUSTEGO pomiaru, bo snapshot zniknięcia niesie sam status.
surface: src/favorites_tracker.py, src/favorites_generator.py, test_favorites.py
generality: family
propagate: maybe
commit: HEAD  # squash-merge do main nadaje ostateczny sha
---

# Kontekst

Rzecz, która się uogólnia, to nie sam kod, tylko trzy wnioski dla każdego
pollera zewnętrznego zasobu:

1. **Nie ma jednego kodu „nie ma zasobu".** OLX zwraca `410 Gone` na zdjętą
   ofertę, `404` dostaje raczej ID, którego nigdy nie było. Kod obsługiwał
   tylko drugi przypadek. Sonda po API na wszystkich 27 śledzonych wpisach dała
   korelację 1:1 (13× zamrożone = 13× 410, 14× świeże = 14× 200) — warto ją
   zrobić u siebie, zanim uznasz, że problem jest gdzie indziej.
2. **„Błąd sieci → pomiń" bez limitu to cicha awaria.** Wpis, który stale nie
   dostaje pomiaru, wygląda w UI dokładnie jak zdrowy — z nieaktualną datą, na
   którą nikt nie patrzy. Jeśli masz taką gałąź, warto mieć drugi sygnał: albo
   status z niezależnego źródła, albo widoczne „ostatni pomiar sprzed N dni".
3. **Fallback z innego źródła maskuje skalę buga.** U nas 11 z 13 zamrożonych
   ofert wyglądało poprawnie, bo status ratował się z głównej bazy skanu.
   Widać było tylko 2 karty spoza tej bazy — i tylko one zostały zgłoszone.

`generality: family` bo mechanika (OLX API v1, Playwright do licznika
wyświetleń) jest wspólna z rodzeństwem, ale konkretne kody i nazwy pól są nasze.
