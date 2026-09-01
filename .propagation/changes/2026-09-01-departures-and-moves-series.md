---
id: 2026-09-01-departures-and-moves-series
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-09-01
category: feature
what: Wykres ruchu profilu dostał dwie kolejne serie — trwałe zejścia ogłoszeń z serwisu i zmiany adresu — wyprowadzone z danych, które już były, bez nowych pól w pipeline.
why: Widać było, jak firma podbija i przywraca ogłoszenia, ale nie było widać ubytku ani przeprowadzek — a to one mówią, czy oferta faktycznie zeszła z rynku, czy tylko zmieniła lokalizację.
how: Zejście liczone jako „rekord jest dziś nieaktywny, w dniu ostatniego widzenia" — nie mamy osobnej daty dezaktywacji, a taka definicja sama realizuje regułę „nie licz tych, co wróciły": rekord, który wrócił, jest dziś aktywny i wypada z serii, a jeśli po powrocie zszedł drugi raz, liczy się to ostatnie zejście. Zmiany adresu biorą się z listy wersji adresu: każda wersja poza najstarszą to jedno zdarzenie w dniu jej pierwszego widzenia. Panele wykresu budują się z deklaratywnej listy serii, która zasila też podsumowanie w nagłówku — dołożenie kolejnej serii to jeden wpis, nie kolejna gałąź w kodzie rysującym.
surface: docs/profile_tracker.html
generality: family
propagate: maybe
commit: dd04000
---

# Kontekst

Warta uwagi jest sama **definicja zdarzenia wyprowadzona ze stanu**, nie z logu:
baza trzyma tylko „aktywny / nieaktywny" plus datę ostatniego widzenia, a mimo to
da się z tego zrobić uczciwą serię czasową zejść — pod warunkiem, że przyjmie się,
iż liczymy zejścia TRWAŁE. Każdy brat, który śledzi ogłoszenia znikające i wracające,
ma ten sam problem i to samo obejście bez dokładania pola do pipeline'u.

Drugi element: lista serii jako dane (`{key, color, label}`), z której generuje się
i panele wykresu, i podsumowanie w nagłówku. Rozrost z dwóch serii do czterech nie
dotknął kodu rysującego.

Ograniczenie do zapisania u siebie: jeśli dezaktywujecie rekordy również z powodów
wewnętrznych (czyszczenie śmieciowych danych), te zejścia wpadają do serii razem
z prawdziwymi i front ich nie odróżni.
