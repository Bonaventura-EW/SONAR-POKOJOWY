# 🎯 SONAR POKOJOWY

**Automatyczny agent monitorujący oferty pokoi do wynajęcia w Lublinie**

[![Scan Status](https://img.shields.io/badge/Skany-3x%20dziennie-brightgreen)](https://bonaventura-ew.github.io/SONAR-POKOJOWY/)
[![GitHub Pages](https://img.shields.io/badge/Demo-Live-blue)](https://bonaventura-ew.github.io/SONAR-POKOJOWY/)
[![Mobile API](https://img.shields.io/badge/API-JSON-orange)](https://bonaventura-ew.github.io/SONAR-POKOJOWY/api/status.json)

---

## 🌐 Demo na żywo

| Strona | Opis |
|--------|------|
| [**🗺️ Mapa ofert**](https://bonaventura-ew.github.io/SONAR-POKOJOWY/) | Interaktywna mapa z pinezkami |
| [**📊 Analityka**](https://bonaventura-ew.github.io/SONAR-POKOJOWY/analytics.html) | Wykresy i statystyki rynku |
| [**📈 Monitoring**](https://bonaventura-ew.github.io/SONAR-POKOJOWY/monitoring.html) | Status systemu i historia skanów |
| [**📱 Mobile API**](https://bonaventura-ew.github.io/SONAR-POKOJOWY/api/status.json) | JSON API dla aplikacji mobilnych |

---

## ✨ Funkcje

### 🔄 Automatyczne skanowanie
- **3 skany dziennie** (09:00, 15:00, 21:00 CET)
- Scraping wszystkich stron OLX z ofertami pokoi w Lublinie
- Inteligentne pomijanie ofert bez zmian (oszczędność requestów)
- Wykrywanie duplikatów (95% podobieństwa)

### 🗺️ Interaktywna mapa
- Pinezki kolorowane według ceny
- Filtry: zakres cenowy, aktywne/nieaktywne
- Wyszukiwarka po adresie
- Popup z pełnymi szczegółami oferty
- Warstwa "Uszkodzone" do oznaczania błędnych ofert

### 📊 Analityka rynku
- Średnie ceny w czasie
- Rozkład cenowy ofert
- Trendy: nowe vs wygasłe ogłoszenia
- Mapa ciepła popularnych lokalizacji

### 📈 Monitoring systemu
- Status ostatniego skanu
- Historia błędów
- Czas wykonania skanów
- Success rate

### 📱 Mobile API
- REST-like API (statyczne JSON-y)
- Gotowe na integrację z Flutter/React Native
- Health check dla aplikacji
- Architektura przygotowana na SZPERACZ

---

## 🎨 Kolory pinezek

| Kolor | Zakres | Hex |
|-------|--------|-----|
| 🟢 Jasna zieleń | < 600 zł | `#90EE90` |
| 🟡 Złoty | 600-799 zł | `#FFD700` |
| 🟠 Pomarańczowy | 800-999 zł | `#FFA500` |
| 🔴 Pomidorowy | 1000-1199 zł | `#FF6347` |
| 🔴 Ciemna czerwień | 1200+ zł | `#8B0000` |

---

## 📱 Mobile API

### Endpointy

```
GET /api/status.json   → Aktualny status + ostatni skan
GET /api/history.json  → Historia 20 ostatnich skanów
GET /api/health.json   → Health check
```

### Przykład odpowiedzi `/api/status.json`

```json
{
  "system": "sonar",
  "status": {
    "current": "operational",
    "isHealthy": true,
    "hasErrors": false
  },
  "lastScan": {
    "timestamp": "2026-03-07T15:51:04+01:00",
    "durationFormatted": "4m 53s",
    "uiStatus": "success",
    "offers": {
      "found": 459,
      "processed": 88,
      "new": 0,
      "active": 109
    }
  },
  "schedule": {
    "times": ["09:00", "15:00", "21:00"],
    "nextScanAt": "2026-03-07T21:00:00+01:00"
  }
}
```

📖 **Pełna dokumentacja API:** [docs/API.md](docs/API.md)

---

## 🏗️ Architektura

```
SONAR-POKOJOWY/
├── .github/workflows/
│   └── scanner.yml              # GitHub Actions - automatyczne skany
│
├── src/
│   ├── main.py                  # Główny agent
│   ├── scraper.py               # Scraping OLX
│   ├── address_parser.py        # Parsowanie adresów
│   ├── price_parser.py          # Parsowanie cen (JSON-LD)
│   ├── geocoder.py              # Geokodowanie (Nominatim)
│   ├── duplicate_detector.py    # Wykrywanie duplikatów
│   ├── map_generator.py         # Generator data.json
│   ├── monitoring_generator.py  # Generator monitoring_data.json
│   ├── api_generator.py         # Generator Mobile API
│   └── scan_logger.py           # Logger skanów
│
├── data/
│   ├── offers.json              # Baza danych ofert
│   ├── scan_history.json        # Historia skanów
│   └── geocoding_cache.json     # Cache geokodowania
│
├── docs/                        # GitHub Pages
│   ├── index.html               # Mapa
│   ├── analytics.html           # Analityka
│   ├── monitoring.html          # Monitoring
│   ├── data.json                # Dane dla mapy
│   ├── monitoring_data.json     # Dane dla monitoringu
│   ├── api/                     # Mobile API
│   │   ├── status.json
│   │   ├── history.json
│   │   └── health.json
│   └── assets/
│       ├── style.css
│       └── script.js
│
└── requirements.txt
```

---

## 🚀 Uruchomienie lokalne

### 1. Klonowanie
```bash
git clone https://github.com/Bonaventura-EW/SONAR-POKOJOWY.git
cd SONAR-POKOJOWY
```

### 2. Instalacja zależności
```bash
pip install -r requirements.txt
```

### 3. Uruchomienie skanu
```bash
cd src
python main.py
```

### 4. Generowanie danych
```bash
python map_generator.py          # Mapa
python monitoring_generator.py   # Monitoring
python api_generator.py          # Mobile API
```

### 5. Podgląd lokalny
```bash
cd docs
python -m http.server 8000
# Otwórz http://localhost:8000
```

---

## 🔧 Konfiguracja

### Harmonogram skanów
Edytuj `.github/workflows/scanner.yml`:
```yaml
schedule:
  - cron: '0 8,14,20 * * *'  # UTC → 09:00, 15:00, 21:00 CET
```

### Zakresy cenowe
Edytuj `src/map_generator.py`:
```python
PRICE_RANGES = {
    'under_600': {'label': '< 600 zł', 'color': '#90EE90', 'min': 0, 'max': 599},
    # ...
}
```

### Próg duplikatów
Edytuj `src/duplicate_detector.py`:
```python
detector = DuplicateDetector(similarity_threshold=0.95)
```

---

## 📊 Statystyki projektu

- **Dokładność cen:** 99.9% (JSON-LD z OLX)
- **Średni czas skanu:** ~5 minut
- **Oferty w bazie:** ~150 aktywnych
- **Historia:** ostatnie 100 skanów

---

## 🛣️ Roadmap

- [x] Etap 1-5: Core scraping + mapa + analityka
- [x] Etap 6: Mobile API (statyczny JSON)
- [ ] Etap 7: Powiadomienia email
- [ ] Etap 8: Rozszerzenie na inne miasta
- [ ] Etap 9: Integracja z SZPERACZ

---

## 🐛 Zgłaszanie błędów

1. Sprawdź [Issues](https://github.com/Bonaventura-EW/SONAR-POKOJOWY/issues)
2. Opisz problem z logami/screenshotami
3. Podaj URL oferty jeśli dotyczy konkretnego ogłoszenia

---

## 📝 Licencja

MIT License - swobodne użycie i modyfikacja.

---

## 👨‍💻 Autor

Projekt monitoringu rynku wynajmu pokoi w Lublinie.

**Ostatnia aktualizacja:** 07.03.2026
