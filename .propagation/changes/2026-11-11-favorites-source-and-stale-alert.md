---
id: 2026-11-11-favorites-source-and-stale-alert
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-11-11
category: bugfix
what: Tracker ulubionych bierze snapshot ze strony oferty zamiast z zablokowanego API v1 OLX, a cicha porażka pomiaru zapala alert w statycznym API.
why: OLX od 06.11.2026 oddaje 403 (CloudFront) na anonimowe /api/v1/offers/<id>/ z maszyn w chmurze. Tracker traktował to jak błąd sieci i pomijał zapis — zakładka Ulubione zamarła na 6 dni (15 skanów × 28 ofert bez pomiaru), a status.json przez cały ten czas mówił "operational".
how: Snapshot składany z HTML-a strony oferty, która z tych samych maszyn nadal odpowiada 200: daty i status z zaescape'owanego window.__PRERENDERED_STATE__ (okno kotwiczone na lastRefreshTime, bo samo "status" pada w HTML-u kilkanaście razy w tłumaczeniach UI), cena i tytuł z bloku JSON-LD. HEAD przed GET odsiewa zdjęte oferty po 410/404 za 0 B zamiast 1,7 MB strony błędu (49 MB → 10 MB na skan). Strona bez bloku oferty (interstitial, zgoda na ciasteczka) = brak snapshotu, nie pusty. Tracker pisze meldunek data/favorites_status.json (tracked/measured/failed/last_snapshot_at), z którego api_generator buduje alert `favorites_stale`: warning przy części ofert bez pomiaru, critical gdy nie zmierzono nic albo gdy dane mają >72 h.
surface: src/favorites_tracker.py, src/api_generator.py, test_favorites.py
generality: family
propagate: maybe
commit:
---

# Kontekst dla brata-ewaluatora

Dwie niezależne rzeczy, które warto rozważyć osobno.

**1. Zmiana źródła danych** jest warta uwagi tylko wtedy, gdy u Ciebie coś
sięga po `www.olx.pl/api/v1/offers/<id>/`. Blokada jest po stronie OLX-a i
dotyczy ścieżki `/api/`, nie konkretnego nagłówka: 403 wychodzi tak samo z
nagłówkami przeglądarki, z Refererem i z impersonacją TLS (`curl_cffi`,
`safari17_0`), z dwóch różnych maszyn w chmurze. Z przeglądarki na domowym
łączu ten sam URL działa, co przez chwilę myliło trop. Strona oferty z tych
samych maszyn odpowiada 200 i niesie **komplet** tych samych pól —
`status`, `isActive`, `createdTime`, `validToTime`, `lastRefreshTime`,
`pushupTime` (`null` tam, gdzie API dawało `''`), a cena w JSON-LD zgadza się
co do złotówki z ceną, którą nasz zwykły scraper zapisuje w `offers.json`
(sprawdzone na 4 żywych ofertach: 650/650/749/825). Dzięki temu istniejąca
historia pomiarów została porównywalna i nie trzeba było jej migrować.

Odrzucony wariant: brać cenę i status z własnej bazy (`offers.json`) —
zero requestów, ale pokrycie 25/28 (ulubione spoza skanowanego listingu
wypadają), brak `valid_to`/`created`/`pushup`, a liczba odświeżeń liczona
inną konwencją niż dotąd rozjechałaby serię w połowie.

**2. Alert o cichej porażce** jest przenośny niezależnie od OLX-a i
prawdopodobnie ciekawszy. Wzorzec do skopiowania: *generator pisze meldunek
o swoim przebiegu do małego pliku stanu, a warstwa statusu robi z niego
alert*. U nas krok workflow ma `continue-on-error` i `|| echo ::warning::`,
a skrypt kończył się kodem 0 niezależnie od wyniku — więc żaden mechanizm
nie miał z czego wywnioskować awarii. `scan_logger` nie pomógł, bo pisze
tylko do skanu trzymanego w pamięci procesu `main.py`, a tracker jest
osobnym procesem uruchamianym później. Stąd osobny plik stanu zamiast
dopisywania do `scan_history.json` po fakcie.

Próg „doba bez pomiaru" wynika z naszego harmonogramu (3 skany dziennie),
u siebie dobierz do własnego.
