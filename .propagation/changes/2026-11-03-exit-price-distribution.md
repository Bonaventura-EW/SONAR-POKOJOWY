---
id: 2026-11-03-exit-price-distribution
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-11-03
category: feature
what: Karta „Zejścia z rynku” na stronie Indeksu — rozkład cen ofert, które w wybranym dniu zeszły z rynku i nie wróciły, z kreską mediany rynku tego dnia i kafelkami (czas na rynku, odsetek z obniżką ceny, mediana vs rynek).
why: Wykres odpływu mówi, ILE ofert znika, ale nie KTÓRE — tanie czy drogie. Porównanie cen zejść z ceną typowej aktywnej oferty tego samego dnia pokazuje, który segment rynku schodzi najszybciej.
how: Rekord liczy się raz, w dniu ostatniego zejścia (konwencja dnia z wykresu odpływu, bez mignięć), i tylko gdy dziś jest nieaktywny — rekordy, które wróciły, nie wchodzą. Dni, krok kubełka, próg i oś karta dziedziczy z karty rozkładu cen aktywnych ofert, więc słupki obu kart stoją pod sobą. Obie karty rysuje jedna funkcja front-endowa sparametryzowana prefiksem id i funkcją kafelków.
surface: src/trend_generator.py, docs/trend.html, test_trend_index.py
generality: family
propagate: maybe
commit: HEAD
---

# Kontekst dla brata-ewaluatora

Wymaga wcześniejszej zmiany 2026-11-03-daily-price-distribution (oś, dni i mediana
rynku pochodzą z tamtej karty).

**Pułapka definicji.** „Zeszła i nie wróciła” to co innego niż odpływ: odpływ liczy
każde zejście (poza mignięciem), także te, po których rekord wrócił po kilku dniach.
Tu liczy się wyłącznie ostatnie zejście rekordu nieaktywnego dziś, więc liczby są
niższe (u nas ~10%) i ostatnie dni mogą jeszcze maleć, gdy rekord wróci.

**Okno.** Przy ~16 zejściach dziennie i 66 kubełkach widok jednego dnia bywa rzadki;
alternatywą jest okno 7 dni kończących się wybranym dniem (~115 rekordów). U nas
wybrano 1 dzień.
