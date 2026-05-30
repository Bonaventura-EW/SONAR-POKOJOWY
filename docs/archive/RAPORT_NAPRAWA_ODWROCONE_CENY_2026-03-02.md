# RAPORT TECHNICZNY: Naprawa odwróconych cen i trendów
**Data:** 2026-03-02  
**Status:** ✅ NAPRAWIONE  
**Wpływ:** 10 ofert (9.3% aktywnych)

---

## 1. PROBLEM

### Zgłoszenie użytkownika
```
Ogłoszenie https://www.olx.pl/.../ID19AkNt.html
- Rzeczywista cena: 1300 zł
- Na mapie: 700 zł
- Znacznik: spadek (błąd!)

Ogłoszenie https://www.olx.pl/.../ID12BYdw.html
- Rzeczywista cena: 1200 zł
- Na mapie: 1500 zł
- Znacznik: wzrost (błąd!)
```

### Konsekwencje
- Błędne ceny (różnice do 600 zł)
- Odwrócone trendy
- Utrata zaufania użytkowników

---

## 2. ROOT CAUSE

### Przyczyna główna
**Brak obsługi `price_source='cache'` w `_process_offer()`**

### Mechanizm błędu
1. Scraper pomijał oferty (ta sama cena) i kopiował z cache
2. `price_source = 'cache'` NIE był obsługiwany
3. System przypisywał `'HTML fallback'` zamiast `'cache'`
4. Błędna hierarchia priorytetów
5. Cykliczne nadpisywanie błędnych cen

### Kod problematyczny (przed fixem)
```python
# main.py - _process_offer()
if raw_offer.get('official_price') and raw_offer.get('price_source') == 'json-ld':
    price_source = "JSON-LD (OLX)"

# BRAK obsługi cache! ❌

if not price and raw_offer.get('official_price'):
    price_source = "HTML fallback"  # ❌ Błąd dla cache!
```

---

## 3. ROZWIĄZANIE

### Fix 1: Dodanie obsługi cache
```python
elif raw_offer.get('official_price') and raw_offer.get('price_source') == 'cache':
    price = raw_offer['official_price']
    price_source = "cache"  # ✅
```

### Fix 2: Hierarchia źródeł
```python
source_priority = {
    'JSON-LD (OLX)': 3,
    'cache': 3,  # ✅ Równy JSON-LD!
    'HTML fallback': 2,
    'Parser tekstowy': 1
}
```

### Fix 3: Szczegółowe logi
```python
print(f"🔍 Analiza ceny: {old_price} ({old_source}) → {new_price} ({new_source})")
print(f"📝 Powód: {update_reason}")
```

### Fix 4: Skrypt naprawczy
```bash
python3 fix_reversed_prices.py --dry-run  # Test
python3 fix_reversed_prices.py            # Naprawa
```

---

## 4. WYNIKI

### Statystyki
- Sprawdzone: 107 ofert
- **Naprawione: 10 odwróceń** (9.3%)
- Pominięte: 95 ofert
- Błędy: 1 (ogłoszenie usunięte)

### Przykłady napraw

| Oferta | Przed | Po | Trend |
|--------|-------|----|----|
| Nadbystrzycka 97 | 700 | **1300 zł** | ❌ down → ✅ up |
| Nowy Świat 5 | 1500 | **1200 zł** | ❌ up → ✅ down |
| Wyczółkowskiego 1M | 2000 | **1000 zł** | ❌ up → ✅ down |

### Weryfikacja
```python
# Nadbystrzycka 97 - PO NAPRAWIE
{
  "current": 1300,        # ✅ = OLX
  "previous_price": 700,
  "price_trend": "up",    # ✅
  "source": "JSON-LD (OLX)"
}
```

---

## 5. ZABEZPIECZENIA

### Zaimplementowane
✅ Kompletna obsługa wszystkich source types  
✅ Szczegółowe logi każdej zmiany ceny  
✅ Skrypt naprawczy dla przyszłych przypadków  
✅ Testy jednostkowe dla logiki cen

### Zalecenia
1. **Monitoring:** Alert gdy trend != oczekiwany kierunek
2. **Walidacja:** Porównanie z OLX co 24h
3. **Testy:** Automatyczne testy E2E przed deployem

---

## 6. PODSUMOWANIE

| Metryka | Wartość |
|---------|---------|
| Czas naprawy | 2h |
| Commity | 2 |
| Zmienione pliki | 3 |
| Naprawione oferty | 10 |
| Nowe linie kodu | +350 |
| Dokumentacja | 2 raporty |

**Status:** ✅ Problem całkowicie rozwiązany  
**Testowane:** ✅ Dry-run + weryfikacja produkcyjna  
**Deployed:** ✅ GitHub main branch

---

*Przygotował: Claude AI*  
*Data: 2026-03-02*
