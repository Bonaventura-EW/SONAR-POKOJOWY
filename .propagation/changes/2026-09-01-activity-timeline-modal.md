---
id: 2026-09-01-activity-timeline-modal
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-09-01
category: feature
what: Okno z osią czasu zdarzeń profilu (odświeżenia i reaktywacje) otwierane z belki statystyk — dwa panele ze wspólną osią dat, zakresy 30/60/90 dni i „wszystko".
why: Liczby zbiorcze w belce mówią ILE, ale nie KIEDY — nie widać, czy firma podbija ogłoszenia równo co drugi dzień, czy raz na miesiąc hurtem. Dane na to leżały w JSON-ie, brakowało tylko widoku.
how: Wykres to inline SVG budowane w JS, bez żadnej biblioteki — ten sam wzorzec co istniejące sparkline'y w kartach. Dwa panele (po jednej metryce) mają wspólną oś dat, ale osobne skale, bo proporcje bywają skrajne: 25 zdarzeń jednej metryki dziennie kontra jedno zdarzenie drugiej na tydzień; wspólna skala zgniotłaby rzadszą serię do niewidocznej kreski. Podziałki liczy funkcja dobierająca krok 1/2/5/10/…, żeby na osi stały liczby całkowite. Okno to dialog z aria-modal, zamykany ✕ / Escape / kliknięciem w tło, z powrotem focusu na element otwierający; zmiana kontekstu (zakładki) zamyka je, żeby nie pokazywało danych poprzedniego bytu.
surface: docs/profile_tracker.html
generality: family
propagate: maybe
commit: 1bb93e4
---

# Kontekst

Trzy rzeczy warte przeniesienia niezależnie od samej funkcji:

1. **Uczciwe tło dla metryki młodszej niż zakres.** Obszar sprzed startu pomiaru
   jest zakreskowany i podpisany kreską. Bez tego pusty lewy brzeg wykresu czyta
   się jak „nic się nie działo", a nie „jeszcze nie mierzyliśmy". Granicę wyznacza
   najstarszy wpis w danych, nie stała w kodzie, więc zakreskowany pas kurczy się
   sam w miarę zbierania historii.

2. **Panel bez zdarzeń mówi to słowami** („brak w tym zakresie") zamiast zostawiać
   pusty prostokąt, który wygląda jak wykres, który się nie doczytał.

3. **Wykres bez biblioteki.** Dwie serie dzienne przez ~180 dni to kilkanaście
   linijek generowania SVG — taniej niż 400 KB zależności na stronie, która poza
   tym ciągnie tylko mapę.

Odrzucone warianty (wybór po obejrzeniu trzech na prawdziwych danych): pary
słupków dziennych obok siebie (na długim zakresie zlewają się w jedno pasmo)
i lustro — jedna metryka w górę, druga w dół (ciasne, ale przy skrajnych
proporcjach trudniej porównywać wysokości po dwóch stronach osi).
