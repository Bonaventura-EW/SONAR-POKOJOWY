# RAPORT NAPRAWY: Błędna aktualizacja cen
**Data:** 2026-03-01  
**Status:** ✅ NAPRAWIONE

---

## 🔴 PROBLEM

System nadpisywał **poprawne ceny z JSON-LD** (oficjalne dane OLX) **błędnymi wartościami z parsera tekstowego** podczas UPDATE istniejących ofert.

### Przykłady błędów:
| ID oferty | Prawdziwa cena (JSON-LD) | Błędna cena (po UPDATE) | Różnica |
|-----------|--------------------------|-------------------------|---------|
| pokoj-1-osobowy-obok-umcs... | 1400 zł | 100 zł | -93% |
| pokoj-jednoosobowy-lsm... | 700 zł | 100 zł | -86% |
| wolny-od-zaraz-pokoj... | 640 zł | 200 zł | -69% |
| pokoj-2-osobowy-16m2... | 1500 zł | 144 zł | -90% |

### Źródło problemu:
W funkcji `_update_existing_offer()` w `src/main.py`:
- Brak hierarchii źródeł cen
- Każda nowa cena bezwarunkowo nadpisywała poprzednią
- Parser tekstowy (mniej niezawodny) nadpisywał JSON-LD (najbardziej niezawodny)

---

## ✅ ROZWIĄZANIE

### 1. **Hierarchia źródeł cen**
Wprowadzono priorytety (najwyższy = najlepszy):
```
3. JSON-LD (OLX)      - oficjalne dane z metadanych strony
2. HTML fallback      - cena z HTML jeśli JSON-LD niedostępne  
1. Parser tekstowy    - ekstrakcja z tekstu (ostateczność)
```

### 2. **Inteligentna logika UPDATE**
Cena jest aktualizowana **TYLKO** gdy:
- Nowe źródło ma **wyższy priorytet**, LUB
- Ten sam priorytet + realna zmiana ceny **<50%**, LUB
- JSON-LD nadpisuje parser (upgrade źródła)

### 3. **Zabezpieczenia**
- Blokada zmian >50% (ochrona przed błędami)
- Logowanie wszystkich decyzji UPDATE
- Pole `price_source` zapisywane dla każdej oferty

---

## 🔧 ZMIANY W KODZIE

### `src/main.py` - funkcja `_update_existing_offer()`
```python
# PRZED (bez hierarchii):
if existing['price']['current'] != new_data['price']['current']:
    existing['price']['history'].append(new_data['price']['current'])
    existing['price']['current'] = new_data['price']['current']

# PO (z hierarchią i zabezpieczeniami):
source_priority = {
    'JSON-LD (OLX)': 3,
    'HTML fallback': 2,
    'Parser tekstowy': 1,
}

if new_priority > old_priority:
    should_update = True
elif new_priority == old_priority and price_diff_percent < 50:
    should_update = True
else:
    should_update = False
```

### Nowy skrypt: `fix_price_history.py`
- Usuwa błędne wpisy z historii (spadki >50%)
- Przywraca poprzednie prawidłowe ceny
- Tworzy backup przed zmianami

---

## 📊 WYNIKI NAPRAWY

### Czyszczenie bazy (`fix_price_history.py`):
```
✅ Naprawione oferty: 13
🗑️ Usunięte błędne wpisy: 13
💾 Backup: data/offers.json.backup_20260301_213144
```

### Przykłady naprawionych ofert:
| Oferta | Było | Jest | Status |
|--------|------|------|--------|
| pokoj-1-osobowy-obok-umcs... | 100 zł | 1400 zł | ✅ |
| komfortowy-pokoj-felin... | 140 zł | 900 zł | ✅ |
| pokoj-jednoosobowy-lsm... | 100 zł | 700 zł | ✅ |
| wolny-od-zaraz-pokoj... | 200 zł | 640 zł | ✅ |
| pokoj-2-osobowy-16m2... | 144 zł | 1500 zł | ✅ |

### Weryfikacja:
```bash
🧪 TEST LOGIKI UPDATE CEN
1. JSON-LD nadpisuje Parser ✅ PASS
2. Parser NIE nadpisuje JSON-LD ✅ PASS
3. JSON-LD aktualizuje JSON-LD (realna zmiana) ✅ PASS
4. Blokada dużej zmiany (>50%) ✅ PASS
📊 Wynik: 4/4 testów OK
```

---

## 🎯 CO DALEJ

### Automatyczne działanie:
- ✅ Kolejne skany będą używać nowej logiki
- ✅ JSON-LD zawsze ma priorytet
- ✅ Parser tekstowy tylko jako fallback
- ✅ Wszystkie decyzje logowane

### Monitorowanie:
- Sprawdź logi przy następnym scanie (9:00/15:00/21:00)
- Szukaj komunikatów: `"💰 Upgrade źródła"`, `"⚠️ PODEJRZANA zmiana"`

### Dokumentacja:
- Pole `price.source` w każdej ofercie
- Historia cen bez błędnych wpisów
- Backup dostępny w razie potrzeby

---

## 📝 COMMIT

```
FIX: Naprawa błędnej aktualizacji cen + czyszczenie historii

PROBLEM:
- Parser tekstowy nadpisywał poprawne ceny z JSON-LD przy UPDATE
- Błędne ceny (100, 144, 200 zł) zapisywane zamiast prawdziwych

ROZWIĄZANIE:
1. Hierarchia źródeł w _update_existing_offer
2. Inteligentna aktualizacja z zabezpieczeniami  
3. Skrypt naprawczy (fix_price_history.py)

WYNIKI:
- Naprawione: 13 ofert
- Usunięte błędne wpisy: 13
- Wszystkie ceny zgodne z JSON-LD z OLX
```

---

**Status:** System naprawiony i gotowy do produkcji ✅
