---
id: 2026-09-12-partial-day-dashed
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonary
date: 2026-09-12
category: bugfix
what: Doba w toku (za nią część zaplanowanych skanów) przestała być liczona jak domknięta — jej wartość jest na wykresie, ale rysowana linią przerywaną i wyłączona z delt oraz przepływów.
why: Adaptacja audytu brata SONAR-MIESZKANIOWY (2026-09-04-trend-charts-audit), który trwającą dobę chował. Chowanie rozwiązuje fałszywy zjazd, ale zabiera dzisiejszy stan na ~12 h dziennie i rodzi drugi problem: wszystko, co czyta OSTATNI punkt serii (u nas udział promowanych, legenda pasm), dostaje null i po cichu gaśnie. Dobra odpowiedź rozdziela dwie rzeczy: co WIDAĆ (wartość prowizoryczna, oznaczona) od tego, co się LICZY (tylko doby domknięte).
how: (1) Generator trzyma niedomkniętą dobę jako `None` w serii — dzięki temu delty, odpływ, napływ i pasma same ją pomijają istniejącą maszynerią luk — i RÓWNOLEGLE wystawia ją w osobnym bloku `partial` (wartość, ile skanów z ilu, etykieta dnia). Front rysuje z tego drugą, przerywaną serię dociągniętą od ostatniej domkniętej doby. (2) Maskujemy WYŁĄCZNIE dobę na krawędzi wykresu: dzień niepełny w środku historii jest już zamknięty i zamaskowany zniknąłby z metryk na zawsze. (3) Przy ~120 dniach jeden dzień to ~15 px, więc sam przerywany odcinek jest niewidoczny — czytelność niesie pionowa kreska w miejscu dnia + pusty marker + podpis „1 z 3 skanów"; w nagłówku plakietka „doba w toku", przy deltach przypis, do której doby liczone jest porównanie. (4) Każde miejsce czytające „ostatni punkt serii" trzeba przejrzeć — u nas dwa (udział promowanych, legenda pasm) pokazywały null zamiast ostatniej domkniętej doby.
surface: src/index_history.py, src/trend_generator.py, docs/trend.html, test_trend_index.py
generality: family
propagate: maybe
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

To odpowiedź na Wasz manifest `2026-09-04-trend-charts-audit`, ale z inną decyzją
produktową na końcu: **nie chowamy trwającej doby, tylko ją oznaczamy**. Wybór
świadomy — Mateusz dostał oba warianty na zrzutach i wskazał kreskę. Jeśli u Was
wykres ma być czysty, chowanie dalej jest OK; przenośne jest to, co niżej.

**Reguła:** wartość niedomkniętego okresu może być na wykresie, ale nie może wchodzić
do niczego, co się z niej liczy. Jeśli oznaczysz ją tylko wizualnie, a zostawisz
w serii, delty i średnie dalej kłamią. Jeśli ją usuniesz z serii bez osobnego kanału
na wartość, tracisz dzisiejszy odczyt i gasną panele czytające ostatni punkt.
Rozdzielenie na `series` (z luką) + `partial` (wartość do narysowania) daje jedno
i drugie i nie wymaga dotykania metryk.

**Pułapka wykryta u nas przy okazji:** po wprowadzeniu luki na krawędzi przejrzyj
WSZYSTKIE miejsca czytające „ostatni element serii". U nas dwa robiły to wprost
(`current_share` w panelu promowanych i podpis legendy pasm) i zaczęły pokazywać
pustkę zamiast ostatniej domkniętej doby — nie wysypało się nic, po prostu znikały
liczby, co jest gorsze niż błąd.

**Pułapka wizualna:** przy ~120 punktach jedna doba to kilkanaście pikseli. Sama
kreska między przedostatnim a ostatnim punktem jest niewidoczna — bez pionowego
znacznika i podpisu zmiana wygląda, jakby jej nie było.

**Miara pokrycia u nas to LICZBA skanów doby wobec planu (3/dobę), nie godzina.**
Inteligentne pomijanie i błędy sieci przesuwają realny czas skanu, więc godzina
nie jest wiarygodna; liczba przebiegów jest. U Was, gdzie Indeks idzie z rekonstrukcji
`last_seen`, ten sygnał trzeba wziąć skądinąd — to główna rzecz do przemyślenia
przed portem.
