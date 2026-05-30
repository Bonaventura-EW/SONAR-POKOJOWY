# Zasady oznaczania ogłoszeń jako "NOWE" 🆕

## Definicja "nowego" ogłoszenia

Ogłoszenie jest oznaczane jako **NOWE** gdy spełnia warunek:

```python
is_new = (days_active == 0)
```

**W praktyce:** Ogłoszenie jest nowe gdy `first_seen` i `last_seen` są **z tego samego dnia**.

---

## Mechanizm działania

### 1. Pierwsza detekcja (nowa oferta)

Gdy system po raz pierwszy wykrywa ogłoszenie na OLX:

```python
# src/main.py - _process_offer()
{
    'id': 'nowe-ogloszenie-CID3-IDxxxxx',
    'first_seen': '2026-03-02T11:30:34+01:00',  # Teraz
    'last_seen': '2026-03-02T11:30:34+01:00',   # Teraz (to samo!)
    'active': True,
    'days_active': 0  # ← ZERO = NOWE!
}
```

**Rezultat:** `is_new = true` ✅

### 2. Kolejne skany (tego samego dnia)

Gdy system ponownie widzi to samo ogłoszenie **w tym samym dniu**:

```python
# main.py - _update_existing_offer()
existing['last_seen'] = now  # Aktualizuje last_seen

# Obliczenie days_active:
first_seen = datetime(2026, 3, 2, 11, 30, 34)
last_seen = datetime(2026, 3, 2, 15, 00, 00)  # Następny skan
days_active = (last_seen - first_seen).days  # = 0 dni (to sam dzień!)
```

**Rezultat:** `is_new = true` ✅ (nadal tego samego dnia!)

### 3. Następny dzień

Gdy system widzi ogłoszenie **kolejnego dnia**:

```python
first_seen = datetime(2026, 3, 2, 11, 30, 34)
last_seen = datetime(2026, 3, 3, 9, 00, 00)   # Dzień później
days_active = (last_seen - first_seen).days  # = 1 dzień
```

**Rezultat:** `is_new = false` ❌ (już nie jest nowe)

---

## Obliczanie `days_active`

### Dla aktywnych ogłoszeń

```python
# map_generator.py
is_new = offer.get('days_active', 0) == 0
```

`days_active` dla aktywnych ofert jest **zawsze 0** (nie jest aktualizowane).

### Dla nieaktywnych ogłoszeń

Dopiero gdy ogłoszenie **znika z OLX**, system oblicza `days_active`:

```python
# main.py - _mark_inactive_offers()
if offer['id'] not in current_offer_ids and offer['active']:
    offer['active'] = False
    
    first_seen = datetime.fromisoformat(offer['first_seen'])
    last_seen = datetime.fromisoformat(offer['last_seen'])
    offer['days_active'] = (last_seen - first_seen).days
```

**Przykład:**
- `first_seen`: 2026-03-02 11:30
- `last_seen`: 2026-03-10 15:00 (ostatni raz widziane)
- `days_active`: (10 - 2) = **8 dni**

---

## Wizualne oznaczenia na mapie

### Nowa oferta (bez zmiany ceny)

```
Pinezka z:
- Czerwona obwódka (stroke: #ff0000, width: 3)
- Badge "N" w prawym górnym rogu (czerwone kółko)
```

**Kod:**
```javascript
const strokeColor = isNew ? '#ff0000' : 'white';
const strokeWidth = isNew ? '3' : '2';

// Badge "N"
${isNew && !hasPriceChange ? 
  '<div style="...background: #ff0000...">N</div>' 
  : ''}
```

### Nowa oferta ZE zmianą ceny

```
Jeśli oferta jest nowa I ma zmianę ceny:
- Priorytet: Badge zmiany ceny (💲↑ lub 💲↓)
- Badge "N" NIE jest pokazywany (linia 257)
```

**Logika:**
```javascript
${isNew && !hasPriceChange ? '<div>N</div>' : ''}
//        ^^^^^^^^^^^^^^^^
//        Badge "N" tylko gdy NIE MA zmiany ceny
```

---

## Przykłady praktyczne

### Scenariusz 1: Całkiem nowe ogłoszenie

```
Skan 1 (02.03 godz. 9:00):
- Ogłoszenie pojawia się po raz pierwszy
- first_seen: 02.03 9:00
- last_seen: 02.03 9:00
- days_active: 0
- is_new: TRUE ✅
- Oznaczenie: Czerwona obwódka + badge "N"

Skan 2 (02.03 godz. 15:00):
- Ogłoszenie nadal widoczne
- first_seen: 02.03 9:00 (bez zmian)
- last_seen: 02.03 15:00 (zaktualizowane)
- days_active: 0 (to sam dzień!)
- is_new: TRUE ✅
- Oznaczenie: Nadal czerwona obwódka + "N"

Skan 3 (03.03 godz. 9:00):
- Ogłoszenie nadal widoczne
- first_seen: 02.03 9:00
- last_seen: 03.03 9:00
- days_active: 0 (aktywne nie mają obliczonego days_active)
- is_new: FALSE ❌ (minęła doba od first_seen)
- Oznaczenie: Biała obwódka (normalny marker)
```

**UWAGA:** Tutaj jest potencjalny błąd! `days_active` dla aktywnych ofert zawsze wynosi 0, więc `is_new` będzie zawsze TRUE!

### Scenariusz 2: Ponownie pojawienie się ogłoszenia

```
Stan początkowy:
- Ogłoszenie było nieaktywne
- first_seen: 20.02 10:00
- last_seen: 25.02 15:00
- days_active: 5
- active: false

Skan (02.03 godz. 9:00):
- Ogłoszenie ponownie się pojawia!
- System traktuje to jako NOWE ogłoszenie (nowy ID? lub...)
```

---

## WYKRYTY PROBLEM! 🐛

### Problem z aktywnym `days_active`

Dla **aktywnych** ofert, `days_active` jest zawsze **0**, co powoduje że:

```python
is_new = offer.get('days_active', 0) == 0  # Zawsze TRUE dla aktywnych!
```

**To znaczy że WSZYSTKIE aktywne oferty są oznaczane jako NOWE!** ❌

### Poprawna implementacja powinna być:

```python
# Oblicz różnicę dni między first_seen a teraz
from datetime import datetime
first_seen = datetime.fromisoformat(offer['first_seen'])
now = datetime.now(tz)
days_since_first_seen = (now - first_seen).days

is_new = days_since_first_seen == 0  # Nowe tylko jeśli dzisiaj
```

---

## Rekomendacje naprawy

### Opcja A: Fix w map_generator.py (szybkie)

```python
# map_generator.py - linia 147
from datetime import datetime
import pytz

tz = pytz.timezone('Europe/Warsaw')
now = datetime.now(tz)

for offer in offers:
    first_seen = datetime.fromisoformat(offer['first_seen'])
    days_since_first = (now - first_seen).days
    
    offer_data = {
        # ...
        'is_new': days_since_first == 0,  # ✅ Poprawne
        # ...
    }
```

### Opcja B: Fix w main.py (właściwe)

Aktualizuj `days_active` dla WSZYSTKICH ofert (nie tylko nieaktywnych):

```python
# main.py - w _update_existing_offer()
first_seen = datetime.fromisoformat(existing['first_seen'])
now_dt = datetime.fromisoformat(now)
existing['days_active'] = (now_dt - first_seen).days
```

---

## Podsumowanie

### Obecny stan
- ✅ Mechanizm obliczania `days_active` działa dla nieaktywnych
- ❌ Dla aktywnych `days_active` zawsze = 0
- ❌ **WSZYSTKIE aktywne oferty są oznaczane jako NOWE**

### Wymagana naprawa
Dodać obliczanie `days_active` dla aktywnych ofert lub zmienić logikę `is_new` na porównanie dat.

---

*Dokument utworzony: 2026-03-02*
