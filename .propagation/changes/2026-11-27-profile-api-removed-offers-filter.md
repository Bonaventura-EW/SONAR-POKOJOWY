---
id: 2026-11-27-profile-api-removed-offers-filter
repo: Bonaventura-EW/SONAR-POKOJOWY
family: sonar
date: 2026-11-27
category: bugfix
what: Oferty z API profilu OLX, które w bazie są nieaktywne albo nowe, przechodzą HEAD-a przed przetworzeniem; 404/410 = odrzucone.
why: API v1 profilu (/api/v1/offers/?user_id=X) zaczęło oddawać ogłoszenia już zdjęte z OLX (27.11.2026: 63 zamiast ~27). Każde przechodziło _update_existing_offer i wracało na mapę jako „reaktywowane" — 34 fałszywe reaktywacje w jednym skanie, wszystkie ze stronami 410/404.
how: W scrape_all_profiles po Fazie 1 równoległy HEAD (allow_redirects=False, 0 B) tylko dla ofert nieaktywnych/nieznanych w indeksie existing_offers; aktywnych nie ruszamy. 404/410 → wypada z wyników, błąd sieci lub inny kod → zostaje (nie wyrzucamy żywej oferty na niepewnym sygnale).
surface: src/scraper.py
generality: family
propagate: maybe
commit:
---
Bracia, którzy też biorą oferty z endpointu użytkownika OLX API v1, mają tę samą dziurę — samo „jest w API" nie znaczy „żyje".
