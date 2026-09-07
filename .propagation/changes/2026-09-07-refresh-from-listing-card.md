---
id: 2026-09-07-refresh-from-listing-card
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-09-07
category: feature
what: Data „odświeżenia" (podbicia) ogłoszenia czytana z karty listingu, którą i tak pobieramy — dotąd znało ją tylko 13% bazy z osobnego API — plus oznaczenie „odświeżona w 24h" na mapie i w widoku firm.
why: Sygnał aktywności ogłoszeniodawcy pochodził wyłącznie z API profili firmowych (109 z 802 aktywnych ofert). Reszta bazy — ogłoszenia prywatne — nie miała go w ogóle, więc na mapie nie dało się odróżnić oferty podbitej dziś od stojącej od miesiąca.
how: Sonda na żywym źródle sprawdziła trzy drogi do pełnego pokrycia i zmierzyła koszt każdej: karta listingu (0 dodatkowych requestów), sweep API z filtrem kategoria+miasto (~17 requestów, ale węższy przekrój niż listing i twardy limit offsetu), API per oferta (802 requesty, ~+50% czasu skanu). Wygrała karta — element z datą siedzi na stronie, którą scraper już pobiera. Parser rozróżnia „Odświeżono dzisiaj o HH:MM" (dokładny znacznik) od „Odświeżono dnia D miesiąca RRRR" (bez godziny → przyjmowany koniec tamtej doby, bo taki wpis widać dopiero, gdy podbicie wypadło po ostatnim skanie dnia). Rejestrator odświeżeń stracił warunek „tylko oferty firmowe", ale zachował zasadę „max jedno na dobę" i nie nadpisuje daty w obrębie doby, więc dokładna godzina nigdy nie zostaje zastąpiona przybliżeniem. Front dostał znacznik ostatniego podbicia i zapala z niego badge w LEWYM górnym rogu pinezki — prawy zajmuje badge zmiany ceny, a 2/3 podbijanych ofert ma jednocześnie zmianę ceny, więc przy jednym rogu sygnał ginąłby dokładnie tam, gdzie dzieje się najwięcej.
surface: src/scraper.py, src/main.py, src/map_generator.py, docs/assets/script.js, docs/assets/style.css, docs/index.html, docs/profile_tracker.html, test_refresh_tracking.py
generality: family
propagate: maybe
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

**Przenośny jest wzorzec, nie regexy.** Sedno: zanim dołożysz źródło danych, sprawdź,
czy nie niesie ich strona, którą już pobierasz. Trzy warianty zostały zmierzone na
żywym źródle (jednorazowa sonda w CI, usunięta po decyzji), nie oszacowane na oko —
różnica między „0 s" a „+50% czasu skanu" wyszła dopiero z pomiaru. Polskie nazwy
miesięcy i selektor `data-testid` są lokalne dla OLX-a.

**Dwa rogi zamiast priorytetu.** Pierwszy szkic wkładał nowe oznaczenie w ten sam róg
co istniejące, z kolejnością priorytetów. Liczby to wywróciły: 63% podbijanych ofert
miało już badge zmiany ceny, więc „priorytet" znaczyłby „niewidoczne w większości
przypadków". Jeśli dokładasz drugi niezależny sygnał do tego samego obiektu, policz
najpierw współwystępowanie — dopiero ono mówi, czy potrzebujesz osobnego miejsca.
Przy okazji: kształt rysowany na canvasie ma własne `bounds`; badge w nowym rogu
wymaga poszerzenia ich w tę stronę, inaczej znika przy przewijaniu.

**Dokładność, której nie ma, nie może wygrać z tą, którą masz.** Źródło daje albo
dokładny znacznik (tego samego dnia), albo samą datę (nazajutrz). Reguła „w obrębie
doby nie nadpisujemy" pilnuje, żeby przybliżenie nie zjadło dokładnego pomiaru —
jest na to test, bo to najłatwiejsza regresja do przeoczenia.

**Efekt uboczny do sprawdzenia u siebie:** szeregi czasowe liczone z historii
odświeżeń dostają skok, bo od teraz mierzą całą bazę, a nie jej wycinek. Stare
punkty zostają wąskie — to nie jest zmiana rynku, tylko zasięgu pomiaru.
