---
id: 2026-11-03-daily-price-distribution
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-11-03
category: feature
what: Karta „Rozkład cen” na stronie Indeksu — histogram cen aktywnych ofert dla dnia wybranego suwakiem (krok 20 zł, bez ofert powyżej 1500 zł, wygładzona linia trendu, kafelki dnia), zasilana nowym dziennym magazynem rozkładu cen.
why: Rekordy ofert znają tylko bieżącą cenę i flagę aktywności, więc rozkładu cen z dowolnego dnia w przeszłości nie da się uczciwie odtworzyć — rekonstrukcja z dat życia rekordu zawyża przeszłość. Bez zapisanego stanu suwak dni nie miałby czego pokazywać.
how: Nowy magazyn data/price_history.json — każdy przebieg pipeline'u zapisuje {cena: liczba aktywnych rekordów}, a dzień opisuje przebieg z największą liczbą aktywnych (ta sama konwencja co magazyn Indeksu, więc obie liczby dnia pochodzą z jednego odczytu). Zapisujemy pełne ceny bez kubełków i progu — szerokość słupka i próg to decyzja prezentacji w generatorze, więc ich zmiana nie wymaga nowego backfillu. Historię odtworzono z rewizji commitowanego pliku bazy w gicie (każda rewizja to dokładny stan po przebiegu). Generator liczy kubełki, statystyki z dokładnych kwot i kafelki dnia; front rysuje słupki, linię trendu (średnia ważona jądrem Gaussa w oknie ±50 zł, w skali słupków) i suwak.
surface: src/price_history.py, src/trend_generator.py, src/main.py, scripts/backfill_price_history.py, docs/trend.html, test_trend_index.py
generality: family
propagate: maybe
commit: HEAD
---

# Kontekst dla brata-ewaluatora

**Kiedy to Cię dotyczy.** Commitujesz plik bazy po każdym przebiegu i chcesz
pokazać, jak wyglądał rozkład jakiejś wartości (cena, metraż) w dowolnym dniu
wstecz. Historia gita to wtedy gotowy, dokładny zapis stanu — nie trzeba go
rekonstruować z dat życia rekordów.

**Na co uważać.**
- Konwencja dnia musi być ta sama co w Twoim głównym szeregu (u nas: przebieg
  z największą liczbą aktywnych). Inaczej suma słupków nie zgadza się z liczbą
  na wykresie obok.
- Przypisuj rewizję do dnia po znaczniku przebiegu zapisanym w samym pliku,
  nie po dacie commita — przebieg tuż przed północą commituje się już
  następnego dnia.
- Przy zapisie JSON z wcięciem lista par [od, liczba] zajmuje 4 linie na
  kubełek; słownik {od: liczba} jest ~3 razy mniejszy (u nas 747 → 477 KB).
- Ceny są zwykle okrągłe (u nas 377 z 453 to wielokrotność 50 zł), więc mały
  krok daje „grzebień” z pustymi przedziałami — linia trendu pokazuje kształt.

**Celowo lokalne:** próg 1500 zł i krok 20 zł to decyzja dla rynku pokoi
(drogie mieszkania rozciągały oś); u brata z innym rynkiem dobierz je do
własnego rozkładu.
