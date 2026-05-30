# RAPORT NAPRAWY: Oznaczanie nowych ofert na mapie

## 🎯 Problem
Wszystkie znaczniki na mapie miały symbol "nowej oferty" 🆕, mimo że większość ofert nie była nowa.

## 🔍 Analiza przyczyn

### Przyczyna główna
W `map_generator.py` linia 147 oznaczała ofertę jako nową gdy `days_active == 0`:
```python
'is_new': offer.get('days_active', 0) == 0
```

Ale w `main.py` pole `days_active` było **obliczane tylko dla nieaktywnych ofert** (linia 350), więc:
- ✅ Nieaktywne oferty: `days_active` obliczane poprawnie
- ❌ **Aktywne oferty: zawsze `days_active = 0`**

Rezultat: **115/115 ofert (100%) było oznaczanych jako nowe**

## ✅ Rozwiązanie

### ETAP 1: Naprawa `days_active` w main.py
**Plik: `src/main.py`**

#### Zmiana 1: Dodanie nowej metody `_update_days_active()`
```python
def _update_days_active(self):
    """
    Aktualizuje pole days_active dla WSZYSTKICH ofert (aktywnych i nieaktywnych).
    Oblicza różnicę w dniach między first_seen a last_seen.
    """
    for offer in self.database['offers']:
        try:
            first_seen = datetime.fromisoformat(offer['first_seen'])
            last_seen = datetime.fromisoformat(offer['last_seen'])
            offer['days_active'] = (last_seen - first_seen).days
        except (ValueError, KeyError) as e:
            print(f"⚠️ Błąd obliczania days_active dla oferty {offer.get('id')}: {e}")
            offer['days_active'] = 0
```

#### Zmiana 2: Wywołanie `_update_days_active()` w `run_scan()`
Dodano wywołanie po `_mark_inactive_offers()`:
```python
# Oznacz nieaktywne
self._mark_inactive_offers(current_offer_ids)

# Aktualizuj days_active dla WSZYSTKICH ofert
self._update_days_active()
```

#### Zmiana 3: Uproszczenie `_mark_inactive_offers()`
Usunięto duplikujące obliczenie `days_active` (teraz wykonywane w `_update_days_active()`):
```python
def _mark_inactive_offers(self, current_offer_ids: List[str]):
    """Oznacza ogłoszenia jako nieaktywne jeśli nie ma ich w bieżącym scanie."""
    for offer in self.database['offers']:
        if offer['id'] not in current_offer_ids and offer['active']:
            offer['active'] = False
```

---

### ETAP 2: Naprawa logiki `is_new` w map_generator.py
**Plik: `src/map_generator.py`**

#### Zmiana 1: Nowa funkcja `is_offer_new()`
```python
def is_offer_new(first_seen_str: str, hours_threshold: int = 24) -> bool:
    """
    Sprawdza czy oferta jest "nowa" - czy first_seen jest w ciągu ostatnich X godzin.
    
    Args:
        first_seen_str: ISO datetime string
        hours_threshold: Próg w godzinach (domyślnie 24h)
    
    Returns:
        True jeśli oferta jest nowa, False w przeciwnym razie
    """
```

**Logika:**
- Parsuje `first_seen` do datetime
- Oblicza różnicę między teraz a `first_seen` w godzinach
- Zwraca `True` jeśli różnica ≤ 24h

**Zalety:**
- ✅ Niezależna od `days_active`
- ✅ Łatwa konfiguracja progu (24h)
- ✅ Precyzyjna (godziny zamiast dni)

#### Zmiana 2: Wykorzystanie nowej funkcji
```python
'is_new': is_offer_new(offer.get('first_seen', ''), hours_threshold=24),
'days_active': offer.get('days_active', 0),  # Dodane dla informacji
```

---

### ETAP 3: Skrypt naprawczy `fix_days_active.py`
**Plik: `fix_days_active.py`**

Jednorazowy skrypt do przeliczenia `days_active` dla wszystkich ofert w istniejącej bazie:
```bash
python3 fix_days_active.py
```

**Wynik działania:**
```
📊 PODSUMOWANIE NAPRAWY
============================================================
✅ Naprawiono: 63 ofert
❌ Błędy: 0

📈 Rozkład dni aktywności:
   0 dni (nowe): 52
   1-3 dni: 63
   4-7 dni: 0
   8+ dni: 0
```

---

## 📊 Wyniki testów

### Test 1: Przeliczenie `days_active`
```
Przed naprawą: 115/115 ofert z days_active=0
Po naprawie:   52 ofert z days_active=0 (rzeczywiście nowe)
               63 oferty z days_active=1-3
```

### Test 2: Generowanie mapy
```
✅ Zapisano map_data.json (89 markerów, 83 aktywnych ofert)
```

### Test 3: Sprawdzenie `is_new`
```
Oferty NOWE (is_new=true):  21  ← first_seen w ciągu ostatnich 24h
Oferty STARE (is_new=false): 94  ← first_seen starsze niż 24h
```

**Przykłady NOWYCH ofert:**
- `first_seen: 02.03.2026 11:36` ✅ (dzisiaj)
- `first_seen: 02.03.2026 11:37` ✅ (dzisiaj)

**Przykłady STARYCH ofert:**
- `first_seen: 28.02.2026 20:46` ✅ (3 dni temu)

---

## 🎯 Efekt końcowy

### Przed naprawą:
- 🆕 **100% ofert** oznaczonych jako nowe (błąd!)

### Po naprawie:
- 🆕 **18% ofert** oznaczonych jako nowe (21/115)
- 📅 **82% ofert** poprawnie oznaczonych jako starsze (94/115)

---

## 📝 Pliki zmodyfikowane

1. **src/main.py**
   - Dodano: `_update_days_active()`
   - Zmodyfikowano: `_mark_inactive_offers()`
   - Zmodyfikowano: `run_scan()` - wywołanie `_update_days_active()`

2. **src/map_generator.py**
   - Dodano: `is_offer_new()`
   - Zmodyfikowano: logika `is_new` w `generate_map_data()`

3. **fix_days_active.py** (nowy)
   - Jednorazowy skrypt naprawczy

---

## 🚀 Wdrożenie

### Kroki:
1. ✅ Commit zmian do repozytorium
2. ✅ Uruchomienie `fix_days_active.py` przez GitHub Actions
3. ✅ Regeneracja mapy
4. ✅ Deploy do GitHub Pages

### Harmonogram:
- Natychmiastowe wdrożenie
- Automatyczne działanie przy kolejnych skanach

---

## 🔄 Kompatybilność wsteczna

✅ **Pełna kompatybilność:**
- Istniejące oferty zachowują wszystkie dane
- Nowe pole `days_active` dodawane automatycznie
- Frontend nie wymaga zmian

---

## 📈 Przyszłe usprawnienia

### Możliwe do konfiguracji:
- Zmiana progu "nowości" z 24h na inną wartość (np. 48h, 72h)
- Dodanie kategorii "bardzo nowa" (< 6h) z innym symbolem
- Kategoria "powróciła" dla ofert nieaktywnych, które stały się aktywne

Wystarczy zmienić `hours_threshold` w `map_generator.py`:
```python
'is_new': is_offer_new(offer.get('first_seen', ''), hours_threshold=48),  # 2 dni
```

---

**Data naprawy:** 2026-03-02  
**Status:** ✅ UKOŃCZONO  
**Tester:** Claude + walidacja na rzeczywistych danych
