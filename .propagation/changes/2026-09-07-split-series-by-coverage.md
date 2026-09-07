---
id: 2026-09-07-split-series-by-coverage
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-09-07
category: feature
what: Nowa metryka na wykresie czasowym rozbita na DWA szeregi zamiast jednego, bo jej dwa źródła mają różne początki rzetelnego pomiaru.
why: Jedno pole zbierało dane z dwóch źródeł uruchomionych w odstępie 2,5 miesiąca. Sklejone w jedną linię dawałyby w dniu włączenia szerszego źródła uskok (17 → 36), który każdy przeczyta jako skok zjawiska, a jest skokiem zasięgu pomiaru.
how: Generator zwraca dwa niezależne bloki tego samego kształtu, każdy z własną datą startu. Węższy (starsze źródło) startuje od pierwszego zapisu, ale niesie granicę rzetelności do zakreskowania — jego pierwsze dni to rozruch trackera, rozpoznany po tym, że 7 z 13 dni nie ma ANI JEDNEGO wpisu przy późniejszej medianie 21/dzień. Szerszy (nowe źródło) startuje dopiero od dnia wdrożenia i dni wcześniejszych w ogóle nie zawiera — bo tam nie ma słabszego pomiaru, tylko backfill po jednej dacie na rekord; zakreskowanie sugerowałoby, że dane są. Front renderuje oba istniejącym wspólnym rendererem, któremu doszedł parametr etykiety zakreskowania. Przy okazji: seria krótsza niż 4 dni rysuje się jako punkty bez linii — średnia krocząca z jednego dnia niczego nie mówi, a linia przez jeden punkt renderowała się jako pionowa kreska do zera.
surface: src/trend_generator.py, docs/trend.html, test_trend_index.py, .github/workflows/tests.yml
generality: universal
propagate: yes
commit: (uzupełniany przy merge)
---

# Kontekst dla brata-ewaluatora

**Reguła, która się przenosi:** gdy pole zbiera dane z dwóch źródeł o różnym zasięgu,
domyślnym odruchem jest jedna linia i przypis pod wykresem. Przypisu nikt nie czyta,
a uskok w miejscu zmiany źródła wygląda jak zdarzenie w mierzonym świecie. Dwa
szeregi obok siebie są brzydsze i uczciwsze — i nie wymagają, żeby czytelnik
pamiętał, kiedy zmienił się pipeline.

**Trzy stopnie „nie mamy danych", które warto rozróżniać na wykresie:**
w tym repo mamy już wszystkie trzy i każdy renderuje się inaczej.

| co się stało | jak rysować |
|---|---|
| dzień bez pomiaru (awaria) | luka w linii, poza mianownikiem średniej |
| pomiar słabszy/niepełny (rozruch) | zakreskowany odcinek z podpisem |
| brak pomiaru, są tylko dane wsteczne | szereg tam się nie zaczyna |

Trzeci przypadek jest najmniej oczywisty i najczęściej mylony z drugim. Backfill
wygląda jak dane, ma daty i liczby — ale opisuje moment, w którym zaczęliśmy
patrzeć, nie to, co się wtedy działo.

**Jak wybrać granicę rzetelności bez zgadywania:** dla starszego źródła wzięliśmy
pierwszy dzień, od którego KAŻDA kolejna doba ma zapis. To reguła obliczalna z
danych, a nie data wybrana okiem z wykresu — i sama się tłumaczy w opisie („zero
znaczy tu «nikt nie podbił», nie «jeszcze nie patrzyliśmy»”).
