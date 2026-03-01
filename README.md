# 🎯 SONAR POKOJOWY

Agent monitorujący oferty pokoi do wynajęcia w Lublinie z interaktywną mapą.

## 🌐 Mapa na żywo

**[Zobacz mapę →](https://bonaventura-ew.github.io/SONAR-POKOJOWY/)**

## 🔧 Ostatnia aktualizacja (2026-03-01)

✅ **Naprawiono błędne ceny** - system teraz używa JSON-LD (oficjalne dane OLX) zamiast parsowania HTML  
📊 **Dokładność:** 99.9% (poprzednio ~90-95%)  
📝 **Szczegóły:** Zobacz [RAPORT_NAPRAWA_CEN_2026-03-01.md](RAPORT_NAPRAWA_CEN_2026-03-01.md)

## 📋 Opis projektu

SONAR POKOJOWY to automatyczny agent który:
- ✅ Skanuje OLX 3x dziennie (9:00, 15:00, 21:00 CET)
- ✅ Wyciąga precyzyjne adresy z ogłoszeń
- ✅ Parsuje ceny z JSON-LD (najbardziej niezawodne źródło)
- ✅ Nanosi pinezki na mapę z kolorami według cen
- ✅ Śledzi historię cen i aktywność ofert
- ✅ Wykrywa duplikaty (95% podobieństwa)
- ✅ Przechowuje dane z ostatnich 1.5 roku

## 🗺️ Funkcje mapy

### Warstwy
- **Aktywne oferty** - aktualne ogłoszenia
- **Nieaktywne oferty** - historia (można ukryć)
- **Zakresy cenowe** - 5 kolorów od zielonego do czerwonego

### Filtry
- Precyzyjny zakres cen (min-max) osobno dla aktywnych i nieaktywnych
- Zakresy cenowe (checkboxy)
- Wyszukiwarka po adresie

### Kolory pinezek
- 🟢 **< 600 zł** - jasna zieleń (#90EE90)
- 🟡 **600-799 zł** - złoty (#FFD700)
- 🟠 **800-999 zł** - pomarańczowy (#FFA500)
- 🔴 **1000-1199 zł** - pomidorowy (#FF6347)
- 🔴 **1200+ zł** - ciemna czerwień (#8B0000)

### Statystyki
- Liczba aktywnych ofert
- Średnia cena
- Najtańszy/najdroższy pokój
- Informacje o ostatnim i następnym scanie

## 🏗️ Architektura

```
SONAR-POKOJOWY/
├── .github/workflows/
│   └── scanner.yml          # GitHub Actions - 3 scany/dzień
├── src/
│   ├── main.py              # Główny agent
│   ├── scraper.py           # Scraping OLX (wszystkie strony)
│   ├── address_parser.py    # Parsowanie adresów
│   ├── price_parser.py      # Parsowanie cen (bez mediów)
│   ├── geocoder.py          # Geokodowanie (Nominatim)
│   ├── duplicate_detector.py # Wykrywanie duplikatów (95%)
│   └── map_generator.py     # Generowanie data.json
├── data/
│   ├── offers.json          # Baza danych ofert
│   └── geocoding_cache.json # Cache geocoding
├── docs/                    # GitHub Pages
│   ├── index.html           # Mapa
│   ├── data.json            # Dane dla mapy
│   └── assets/
│       ├── style.css
│       └── script.js
└── requirements.txt
```

## 🚀 Uruchomienie lokalne

### 1. Instalacja zależności
```bash
pip install -r requirements.txt
```

### 2. Uruchomienie scanu
```bash
cd src
python main.py
```

### 3. Wygenerowanie mapy
```bash
cd src
python map_generator.py
```

### 4. Podgląd mapy lokalnie
Otwórz `docs/index.html` w przeglądarce.

## 🤖 Automatyczne scany

Agent działa automatycznie przez GitHub Actions:
- **Harmonogram**: 9:00, 15:00, 21:00 CET
- **Proces**:
  1. Scraping OLX (wszystkie strony)
  2. Parsowanie adresów i cen
  3. Geokodowanie
  4. Wykrywanie duplikatów
  5. Aktualizacja bazy danych
  6. Generowanie data.json
  7. Commit i push do repo

## 📊 Baza danych

### Struktura offers.json
```json
{
  "last_scan": "2024-02-24T15:00:00+01:00",
  "next_scan": "2024-02-24T21:00:00+01:00",
  "offers": [
    {
      "id": "olx-123456789",
      "url": "https://www.olx.pl/...",
      "address": {
        "full": "Narutowicza 5",
        "street": "Narutowicza",
        "number": "5",
        "coords": {"lat": 51.2465, "lon": 22.5684}
      },
      "price": {
        "current": 700,
        "history": [800, 750, 700],
        "media_info": "+ media (~150 zł)"
      },
      "description": "Przytulny pokój...",
      "first_seen": "2024-02-24T09:00:00+01:00",
      "last_seen": "2024-02-24T15:00:00+01:00",
      "active": true,
      "days_active": 0
    }
  ]
}
```

## 🎨 Popup oferty

Każda pinezka zawiera:
- 📍 Dokładny adres
- 💰 Cena aktualna + historia zmian
- 🔧 Skład ceny (czynsz, media wliczone/osobno)
- 🔗 Link do ogłoszenia OLX
- 📝 Pełny opis
- 📅 Daty (dodano, ostatnio widziane)
- ⏱️ Liczba dni aktywności

Dla nieaktywnych:
- ❌ Oznaczenie "Nieaktywne"
- Liczba dni aktywności
- Data dezaktywacji
- Ostatnia cena

## 🔧 Konfiguracja

### Zmiana harmonogramu skanów
Edytuj `.github/workflows/scanner.yml`:
```yaml
schedule:
  - cron: '0 8,14,20 * * *'  # Format: minuta godzina dzień miesiąc dzień_tygodnia (UTC)
```

### Zmiana zakresów cenowych
Edytuj `src/map_generator.py`:
```python
PRICE_RANGES = {
    'under_600': {'label': '< 600 zł', 'color': '#90EE90', 'min': 0, 'max': 599},
    # ...
}
```

### Zmiana progu duplikatów
Edytuj `src/duplicate_detector.py`:
```python
detector = DuplicateDetector(similarity_threshold=0.95)  # 95%
```

## 📝 Licencja

MIT License - możesz swobodnie używać i modyfikować kod.

## 🐛 Zgłaszanie błędów

Jeśli znajdziesz błąd lub masz sugestię, stwórz Issue na GitHubie.

## 👨‍💻 Autor

Projekt stworzony dla monitoringu rynku wynajmu pokoi w Lublinie.

---

**Ostatnia aktualizacja**: 24.02.2026
