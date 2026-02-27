# 📖 INSTRUKCJA - Jak uruchomić scan i usuwać ogłoszenia

## 🚀 Uruchomienie scanu ręcznego

### Opcja 1: Lokalnie (polecane)
```bash
cd /ścieżka/do/SONAR-POKOJOWY
cd src
python3 main.py
```

Po skanie:
```bash
cd src
python3 map_generator.py
```

Następnie wypchnij zmiany:
```bash
git add data/offers.json docs/data.json
git commit -m "📊 Zaktualizowano dane - scan $(date +%Y-%m-%d)"
git push
```

### Opcja 2: Przez GitHub Actions
1. Wejdź na https://github.com/Bonaventura-EW/SONAR-POKOJOWY/actions
2. Wybierz workflow "Scan OLX Pokoje"
3. Kliknij "Run workflow"
4. Wybierz branch "main"
5. Kliknij "Run workflow" (zielony przycisk)

Scan wykona się automatycznie i wyniki pojawią się na mapie.

---

## 🗑️ Usuwanie niechcianych ogłoszeń

### Krok 1: Znajdź ID ogłoszenia
**Metoda A:** Z mapy
1. Otwórz mapę: https://bonaventura-ew.github.io/SONAR-POKOJOWY/
2. Kliknij marker
3. W popup znajdź przycisk "🗑️ Usuń to ogłoszenie"
4. Skopiuj ID z alertu (np. `pokoj-jednoosobowy-CID3-ID14gaar`)

**Metoda B:** Z URL ogłoszenia
URL: `https://www.olx.pl/d/oferta/pokoj-jednoosobowy-CID3-ID14gaar.html`  
ID: `pokoj-jednoosobowy-CID3-ID14gaar`

### Krok 2: Usuń ogłoszenie
```bash
cd /ścieżka/do/SONAR-POKOJOWY
python src/remove_listing.py pokoj-jednoosobowy-CID3-ID14gaar
```

Wynik:
```
✅ Ogłoszenie pokoj-jednoosobowy-CID3-ID14gaar dodane do listy usuniętych
💡 Przy następnym scanie to ogłoszenie nie pojawi się na mapie
```

### Krok 3: Wypchnij zmiany (opcjonalnie)
```bash
git add data/removed_listings.json
git commit -m "🗑️ Usunięto ogłoszenie"
git push
```

### Krok 4: Uruchom ponowny scan
Teraz uruchom scan (opcja 1 lub 2) - usunięte ogłoszenie nie pojawi się.

---

## 📋 Zarządzanie usuniętymi ogłoszeniami

### Lista usuniętych
```bash
python src/remove_listing.py list
```

Wynik:
```
🗑️ Usunięte ogłoszenia (3):
============================================================
1. pokoj-jednoosobowy-CID3-ID14gaar
2. stancja-dla-studenta-CID3-ID15xyz
3. wynajem-pokoju-CID3-ID16abc
============================================================
Ostatnia aktualizacja: 2026-02-27T14:30:00+01:00
```

### Przywracanie ogłoszenia
```bash
python src/remove_listing.py restore pokoj-jednoosobowy-CID3-ID14gaar
```

Wynik:
```
✅ Ogłoszenie pokoj-jednoosobowy-CID3-ID14gaar przywrócone
💡 Przy następnym scanie to ogłoszenie pojawi się ponownie na mapie
```

---

## 🔍 Weryfikacja zmian

### Sprawdź nowe ceny
Po scanie otwórz: https://bonaventura-ew.github.io/SONAR-POKOJOWY/

1. Znajdź ogłoszenie które miało błędną cenę
2. Kliknij marker
3. Sprawdź czy cena jest poprawna (900 zł zamiast 140 zł)

### Sprawdź usunięte ogłoszenia
1. Otwórz mapę
2. Szukaj ogłoszeń które usunąłeś
3. Nie powinny się wyświetlać

---

## ⚠️ Najczęstsze problemy

### Problem: "ModuleNotFoundError: No module named 'requests'"
**Rozwiązanie:**
```bash
pip install -r requirements.txt
```

### Problem: Ceny nadal błędne
**Możliwe przyczyny:**
1. Nie uruchomiłeś nowego scanu
2. Struktura OLX się zmieniła

**Rozwiązanie:**
```bash
# Sprawdź pojedyncze ogłoszenie
cd src
python3 -c "
from scraper import OLXScraper
scraper = OLXScraper()
details = scraper.fetch_offer_details('URL_OGLOSZENIA')
print('Cena:', details.get('official_price'))
"
```

### Problem: Ogłoszenie nie znika po usunięciu
**Rozwiązanie:**
1. Sprawdź czy ID jest poprawne: `python src/remove_listing.py list`
2. Sprawdź czy wypchałeś zmiany: `git status`
3. Uruchom ponowny scan

---

## 📞 Wsparcie

Jeśli coś nie działa:
1. Sprawdź logi scanu w terminalu
2. Sprawdź plik `data/offers.json` - czy ma nowe dane
3. Sprawdź `data/removed_listings.json` - czy zawiera usunięte ID
4. Uruchom `git status` - czy wszystkie zmiany są zatwierdzone

---

**Ostatnia aktualizacja:** 27.02.2026  
**Wersja:** 2.0
