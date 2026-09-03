---
id: 2026-09-03-measured-index-history
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-09-03
category: bugfix
what: Wykres indeksu podaży czyta zapisany dzienny stan bazy zamiast rekonstruować go wstecz z rekordów ofert.
why: Rekonstrukcja "ile ofert żyło dnia D" z pól first_seen/last_seen zawyżała przeszłość o 27%, malejąco do 4% dla dnia dzisiejszego, bo oferta z przerwą w życiu ma jeden ciągły przedział. Ponieważ błąd malał z wiekiem punktu, prawy koniec wykresu zawsze sztucznie opadał — wykres pokazywał 10% spadku rynku w okresie, w którym rynek urósł o 2%, a nagłówkowa zmiana 1M miała zły znak.
how: Nowy magazyn data/index_history.json — każdy przebieg pipeline'u dopisuje swój wynik (liczba aktywnych rekordów po przebiegu); wartość dnia to maksimum z odczytów, więc przebieg częściowy nie obniża historii, a dzień bez przebiegu zostaje luką zamiast zerem. Historię sprzed wdrożenia odtworzono ze starszych rewizji commitowanego pliku z historią przebiegów (trzyma tylko ostatnie ~100 wpisów, ale jest commitowany po każdym) — pięć rewizji dało 112 dni bez luk. Dodatkowo pipeline zapisuje odtąd daty deaktywacji rekordów, więc przedziały życia rozpoznają przerwy i szeregi pochodne (odpływ, podział na pasma) domykają się same w miarę napływu danych.
surface: src/index_history.py, src/trend_generator.py, src/main.py, scripts/backfill_index_history.py, docs/trend.html, test_trend_index.py
generality: family
propagate: maybe
commit: HEAD
---

# Kontekst dla brata-ewaluatora

**Kiedy to Cię dotyczy.** Masz wykres szeregu czasowego, którego punkty liczysz
wstecz z bieżącego stanu bazy („ile rekordów było wtedy aktywnych"), zamiast
zapisywać stan przy każdym przebiegu. Taki wykres ma dwie wady naraz:

1. **Zmienia się wstecz.** Ten sam dzień pokazuje inną wartość co tydzień, bo
   dochodzą nowe zdarzenia zmieniające interpretację starych rekordów.
2. **Ostatnie punkty są systematycznie inne niż starsze** — nie dlatego, że
   rzeczywistość się zmieniła, tylko dlatego, że nie zdążyły jeszcze zebrać
   „przyszłości". To odwraca kierunek trendu na prawym końcu, czyli dokładnie
   tam, gdzie ludzie patrzą.

**Test, który to wykrywa.** Porównaj rekonstrukcję z niezależnie zapisanym
pomiarem tej samej wielkości (u nas: licznik w historii przebiegów). Jeśli
różnica maleje monotonicznie w stronę dnia dzisiejszego — masz ten sam błąd.
Płaski szum wokół zera oznacza, że rekonstrukcja jest zdrowa.

**Tanie, jeśli commitujesz dane.** Historię dało się odtworzyć bez żadnej
zewnętrznej bazy: plik z historią przebiegów trzyma krótkie okno, ale każdy
commit to snapshot, więc kilka rewizji rozstawionych co ~30 dni skleja pełny
zakres. Skrypt backfillu przyjmuje ścieżki albo URL-e do rewizji.

**Czego świadomie NIE zrobiliśmy.** Nie mieszamy dwóch metod w jednej linii —
seria zaczyna się tam, gdzie zaczyna się pomiar, a nie tam, gdzie kończy się
rekonstrukcja. Krok na złączeniu (u nas ~27%) czytałby się jak zdarzenie
rynkowe. Tam, gdzie podział serii na składowe wciąż musi opierać się na
rekonstrukcji, bierzemy z niej wyłącznie UDZIAŁ i nakładamy go na zmierzoną
sumę, żeby składowe dalej sumowały się do linii głównej.

**Lokalne dla nas:** nazwy pól rekordu i konkretne progi. Przenośne: sam wzorzec
(mierz i zapisuj zamiast odtwarzać), backfill z historii gita i test na
monotoniczny dryf błędu.
