---
id: 2026-08-31-vertical-label-rotation
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-08-31
category: feature
what: Zakładka Firmy dostała dwa pionowe paski na krawędzi mapy („↑ aktywne" / „↓ nieaktywne") skaczące po liście ogłoszeń, z wyśrodkowaniem napisu zrobionym obrotem przycisku zamiast writing-mode.
why: Przy ~112 ofertach na profil dojście do sekcji archiwalnych wymagało długiego scrollowania; przyciski na liście zasłaniałyby karty ofert, a pionowy napis przez `writing-mode` wychodził wizualnie krzywo.
how: Paski są przyklejone do prawej krawędzi `.map-col` (leżą na mapie, nie na wierszach), tint zielony/czerwony niesie znaczenie sekcji, biała plakietka pokazuje liczbę ofert. Kluczowy chwyt: `writing-mode: vertical-rl` centruje LINE-BOX, a nie litery — łaciński ascent > descent, więc napis siada ~1,5 px od osi. Zamiast nudge'a w pikselach (zależnego od fontu) tło/ramka/cień siedzą na pionowym kontenerze 22 × 86, a w środku leży POZIOMY `<button>` 84 × 20 z `rotate(90deg)`; ikona i licznik dostają `rotate(-90deg)`, żeby stać prosto. Centrowanie wychodzi z geometrii, nie z metryki fontu.
surface: docs/profile_tracker.html
generality: family
propagate: maybe
commit: 2db819c
---

# Kontekst

**Co jest tu warte przeniesienia, a co nie.** Same przyciski „skocz do sekcji" są specyficzne dla
podziału lista aktywne/archiwalne w zakładce Firmy — brat bez takiej listy nic z tego nie ma.
Przenośny jest natomiast **wzorzec pionowej etykiety**: wszędzie tam, gdzie rysujesz wąski pionowy
pasek z napisem (szyna boczna, uchwyt panelu, zakładka przy krawędzi), `writing-mode` da napis
optycznie przesunięty względem ikon rysowanych poziomo. Obrót całego przycisku rozwiązuje to raz
i bez magicznych liczb.

**Jak to zdiagnozowano.** Nie na oko — zrzutami z Playwrighta w powiększeniu 5× z narysowaną osią
paska. Widać wtedy, że licznik i strzałka (poziome) stoją na osi, a litery leżą obok niej.
Alternatywa `margin-left: 1.5px` działała dla tego konkretnego fontu i rozmiaru, ale rozjeżdżałaby
się przy każdej zmianie kroju — dlatego odrzucona.

**Pułapki przy adaptacji.**
- Dekoracje (tło, ramka, zaokrąglenie, cień) trzymaj na NIEobróconym kontenerze — w obróconym
  układzie „prawa krawędź" przycisku ląduje na dole ekranu i mapowanie stron robi się nieczytelne.
- Elementy, które mają stać prosto (ikony, cyfry), potrzebują `rotate(-90deg)`; ich pudełko
  w layoucie zostaje nieobrócone, więc grubość paska musi pomieścić ich SZEROKOŚĆ.
- Nad mapą Leafletu potrzebny jest `z-index` ≥ 1000 (kontrolki Leafletu siedzą na 1000).
