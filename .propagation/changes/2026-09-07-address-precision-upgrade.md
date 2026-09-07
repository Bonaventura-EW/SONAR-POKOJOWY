---
id: 2026-09-07-address-precision-upgrade
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-09-07
category: bugfix
what: Treść rekordu przestała być zamrożona na pierwszym pobraniu — świeży odczyt nadpisuje opis, doprecyzowanie adresu (dopisany numer) wchodzi in-place bez kasowania historii, a rotacja dociąga najstarsze rekordy mimo braku sygnału zmiany.
why: Ogłoszeniodawca dopisał numer budynku do opisu tydzień po wystawieniu. Zmiana nie ruszyła ani ceny, ani tytułu — czyli żadnego z pól, po których inteligentne skanowanie decyduje o pobraniu szczegółów — więc marker do końca życia oferty stał na środku ulicy zamiast na budynku. Trzy niezależne blokady w łańcuchu, każda wystarczająca samodzielnie.
how: (1) Pole z treścią jest nadpisywane tylko wtedy, gdy rekord pochodzi z realnego pobrania — znacznik `details_fetched_at` odróżnia to od danych z cache, których zapis doklejałby tytuł przy każdym przebiegu. (2) Nowa klasa zmiany „doprecyzowanie": ta sama ulica + dopisany numer albo centroid dzielnicy → ulica w promieniu 3 km. Wchodzi in-place, bez wersjonowania i resetu historii cen, które są zarezerwowane dla realnej przeprowadzki; ranga precyzji pilnuje, żeby zmiana nigdy nie szła w dół. (3) Rotacja: stały budżet rekordów na przebieg (40), wybierane po najdawniejszym odczycie, ograniczone do rekordów, które mają co zyskać (nieprecyzyjny marker). (4) Porównanie „czy tekst źródłowy się zmienił" obcina z obu stron prefiks tytułu — bez tego rotacja czytałaby nietknięty opis ze starym tytułem jako przepisane ogłoszenie.
surface: src/main.py, src/scraper.py, test_address_precision_upgrade.py
generality: family
propagate: maybe
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

**Przenośny jest wzorzec, nie kod.** Sedno w jednym zdaniu: *jeśli pomijasz pobranie
na podstawie sygnału (cena, tytuł, ETag, hash listingu), to zmiany NIEWIDOCZNE w tym
sygnale są dla Ciebie niewidzialne na zawsze — potrzebujesz rotacji, nie tylko
detekcji.* Drugi wzorzec: dane w rekordzie, których nigdy nie nadpisujesz, cicho
starzeją się względem źródła; u nas opis był zamrożony na pierwszym skanie dla
**wszystkich** aktywnych ofert (mediana 19 dni, maks. 119) i nikt tego nie zauważył,
bo front pokazuje głównie cenę i adres.

**Trzecia część jest tu najciekawsza.** „Dokładniejszy wariant tej samej wartości" to
osobna klasa zmiany od „inna wartość". Bez niej porównywarka adresów odpowiadała
*„bez zmian"* (nazwa ulicy to podzbiór nowej, a numeru nie było z czego porównać),
a przy dzielnicy → ulicy odpowiadała *„przeprowadzka"* i kasowała historię cen.
Każdy brat, który wersjonuje rekord po zmianie pola, powinien sprawdzić, co robi,
gdy nowa wartość jest po prostu **precyzyjniejsza**.

**Czego NIE kopiować:** budżet 40/przebieg i próg 3 dni są wyliczone z naszych
liczb (505 nieprecyzyjnych rekordów, 3 przebiegi dziennie, ~4 s kosztu przy 95 s
całego skanu, pełny obieg w ~4 dni). Promień 3 km bierze się z rozmiarów dzielnic
Lublina. Progi trzeba przeliczyć u siebie, nie przepisać.
