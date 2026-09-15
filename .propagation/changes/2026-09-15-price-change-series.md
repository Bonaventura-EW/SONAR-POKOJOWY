---
id: 2026-09-15-price-change-series
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonary
date: 2026-09-15
category: feature
what: Dwa nowe szeregi dzienne na stronie Indeks — ile ogłoszeń tego dnia potaniało i ile podrożało — plus doprecyzowanie, że kreska doby w toku pokazuje stan po OSTATNIM skanie, a nie maksimum doby.
why: Mieliśmy skalę złotówkową zmian cen (Top 5 największych obniżek/podwyżek), ale nie mieliśmy ich CZĘSTOTLIWOŚCI — a to ona mówi, czy rynek zaczyna schodzić z cen. Historia cen leży w bazie od pierwszego skanu, więc szereg da się policzyć wstecz bez dodatkowych requestów. Druga część: pusty marker doby w toku podpisany był maksimum doby, a licznik na mapie stanem po ostatnim skanie — dwa miejsca odpowiadały różnie na pytanie „ile jest ogłoszeń dzisiaj".
how: (1) `build_price_changes()` czyta historię cen każdej oferty parami sąsiednich wpisów — DWA rozłączne źródła: `price.history_full` bieżącej wersji i `versions[].price_history` wersji sprzed zmiany adresu (zmiana adresu zeruje bieżącą historię, ta sama pułapka co przy `collect_dates`); każdy szereg osobno, bo sklejenie dorobiłoby fałszywe zdarzenie na styku wersji. (2) Metryka liczy ZDARZENIA, nie oferty: dwie obniżki jednej oferty w jednym dniu to dwa punkty — świadoma różnica wobec odpływu, gdzie dedup po (oferta, dzień) jest konieczny, bo tam jedna oferta to jeden marker na mapie. (3) Oba szeregi idą przez istniejące `_flow_metric` na wspólnej osi Indeksu, więc dzień bez skanu jest luką, nie zerem. (4) Dwa osobne wykresy zamiast dwóch linii na jednym: podwyżek jest ~2,4× mniej niż obniżek, na wspólnej skali leżą płasko przy zerze. (5) `partial_day()` wystawia obok `value` (max doby, konwencja Indeksu) także `now` — liczbę ofert `active=true` po ostatnim skanie, czyli ten sam licznik co na mapie; front rysuje `now` i podpisuje „dzisiaj: N ofert".
surface: src/trend_generator.py, docs/trend.html, test_trend_index.py
generality: family
propagate: maybe
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

Przenośne jest jedno: **historia cen w bazie wystarcza na szereg częstotliwości
zmian** — jeśli u Was oferta też trzyma listę (cena, data), to ~40 linii
generatora i karta na froncie. Sprawdźcie tylko dwie rzeczy, na których my się
potknęliśmy przy podobnych metrykach:

1. Czy Wasz model oferty ma wersjonowanie (u nas `versions[]` przy zmianie
   adresu). Jeśli tak, historia sprzed przeprowadzki jest w osobnym polu i bez
   niej szereg robi się wstecz coraz rzadszy.
2. Czy dzień bez skanu rysuje się u Was jako luka. Zero w takim dniu wchodzi
   potem do średniej 7-dniowej i zaniża trend przez tydzień po awarii.

Decyzja „liczymy zdarzenia, nie oferty" była wyborem Mateusza, nie oczywistością
— pytanie brzmi, czy wykres ma odpowiadać „ile ogłoszeń dziś potaniało" (dedup),
czy „ile było obniżek" (bez dedupu). Warto zapytać u siebie, zanim skopiujecie.

Część o `partial.now` jest ciekawa tylko wtedy, gdy macie trwającą dobę liczoną
jako maksimum odczytów (patrz nasz wcześniejszy manifest
`2026-09-12-partial-day-dashed`). Wniosek: skoro doba w toku i tak nie wchodzi do
serii ani do delt, to na wykresie warto pokazywać na niej tę liczbę, którą widać
w reszcie serwisu, a maksimum doby zostawić na moment domknięcia dnia.
