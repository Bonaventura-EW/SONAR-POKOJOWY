# 🚀 RAPORT: Inteligentne Skanowanie + Śledzenie Zmian Cen

**Data:** 2026-03-01  
**Commit:** 7c1fa8d

---

## 📋 Podsumowanie zmian

### Problem (przed)
```
KAŻDY SCAN (co 8h)
       │
       ▼
┌─────────────────────────────────┐
│  Pobierz WSZYSTKIE oferty      │  ← ~100 requestów
│  z OLX (każda strona szczegółów)│     nawet dla znanych ofert!
└─────────────────────────────────┘
```

### Rozwiązanie (po)
```
KAŻDY SCAN (co 8h)
       │
       ▼
┌─────────────────────────────────┐
│  1. Pobierz listę ofert z OLX  │  ← ~5 requestów (strony listy)
└─────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────┐
│  2. Porównaj ceny z listingu   │
│     z cenami w bazie           │
└─────────────────────────────────┘
       │                │
       ▼                ▼
┌────────────┐   ┌─────────────────┐
│ Ta sama    │   │ Nowa oferta LUB │
│ cena       │   │ zmiana ceny     │
│            │   │                 │
│ → POMIŃ    │   │ → Pobierz       │
│   szczegóły│   │   szczegóły     │
└────────────┘   └─────────────────┘
```

---

## 📊 Oszczędności

| Scenariusz | Przed | Po | Oszczędność |
|------------|-------|-----|-------------|
| 100 ofert, 0 zmian | 100 requestów | 5 requestów | **95%** |
| 100 ofert, 10 nowych | 100 requestów | 15 requestów | **85%** |
| 100 ofert, 5 zmian cen | 100 requestów | 10 requestów | **90%** |

---

## 🔧 Zmiany techniczne

### 1. `src/scraper.py`

```python
# NOWE: Parametr existing_offers
def __init__(self, ..., existing_offers: dict = None):
    self.existing_offers = existing_offers or {}
    self.stats = {
        'skipped_same_price': 0,
        'fetched_new': 0,
        'fetched_price_changed': 0
    }

# NOWE: Wyciąganie cyfr z ceny
def _extract_price_number(self, price_raw: str) -> Optional[int]:
    """
    '850 zł' → 850
    'od 850 zł' → 850
    '1 200 zł' → 1200
    """
```

### 2. `src/main.py`

```python
# NOWE: Budowanie indeksu istniejących ofert
def _build_existing_offers_index(self) -> Dict:
    """
    Returns: {offer_id: {'price': X, 'description': '...'}}
    """

# NOWE: Rozszerzone śledzenie ceny
offer['price']['previous_price'] = old_price
offer['price']['price_changed_at'] = now
offer['price']['price_trend'] = 'down'  # lub 'up'
```

### 3. `src/map_generator.py`

```python
# NOWE: Przekazywanie danych do frontendu
offer_data = {
    ...
    'previous_price': price_data.get('previous_price'),
    'price_trend': price_data.get('price_trend'),
    'price_changed_at': format_datetime(price_data.get('price_changed_at')),
}
```

### 4. `docs/assets/script.js`

```javascript
// NOWE: Wyświetlanie zmiany ceny w popup
if (offer.previous_price && offer.price_trend) {
    const trendIcon = offer.price_trend === 'down' ? '📉' : '📈';
    const trendColor = offer.price_trend === 'down' ? '#28a745' : '#dc3545';
    // Pokazuje: 💰 850 zł 📉 -100 zł
    //           Poprzednio: 950 zł (zmiana: 01.03.2026)
}
```

---

## 🎨 Wygląd w UI

### Popup ze zmianą ceny:
```
📍 Paganiniego 12

💰 1400 zł 📈 +100 zł
   Poprzednio: 1300 zł (zmiana: 01.03.2026 15:51)
📊 Historia: 1300 zł → 1400 zł
Skład: + media

🔗 Otwórz ogłoszenie
```

### Popup ze spadkiem ceny:
```
📍 Nowy Świat 5

💰 500 zł 📉 -350 zł
   Poprzednio: 850 zł (zmiana: 01.03.2026 15:51)
📊 Historia: 850 zł → 500 zł
Skład: brak informacji

🔗 Otwórz ogłoszenie
```

---

## ✅ Testy

```bash
# Test inicjalizacji
📚 Zaindeksowano 106 aktywnych ofert do inteligentnego pomijania
✅ SonarPokojowy zainicjalizowany
   Oferty w bazie: 107
   Scraper.existing_offers: 106 ofert

# Test wyciągania ceny
"850 zł" → 850
"od 850 zł" → 850  
"1 200 zł" → 1200

# Oferty ze zmianami cen w bazie
📈 1300 → 1400 zł (+100 zł)
📉 850 → 500 zł (-350 zł)
📈 1200 → 1500 zł (+300 zł)
...
```

---

## 📝 Następne kroki (opcjonalne)

1. **Notyfikacje o spadkach cen** - powiadomienia email/push gdy cena spadnie
2. **Wykres zmian cen** - historia cenowa na wykresie
3. **Filtr "tylko ze zmianą ceny"** - szybkie znajdowanie okazji
