# 🔧 RAPORT NAPRAWY - 2026-03-01

## Przegląd
Naprawa 3 krytycznych błędów zgłoszonych przez użytkownika:
1. **Kolor markera** bazował na sumie (pokój + media) zamiast czystej ceny pokoju
2. **Błędne parsowanie adresu** "Bukietowa 10" → "Bukietowa 1O" (litera O zamiast cyfry 0)
3. **Logika "is_new"** pozwalała ofertom być jednocześnie "nowe" i "nieaktywne"

---

## ETAP 1: Priorytet ceny pokoju nad sumą z OLX

### Problem
**Przykład:** https://www.olx.pl/d/oferta/pokoje-do-wynajecia-rogatka-warszawska-ul-bukietowa-1-CID3-ID19x6uN.html
- Cena pokoju: **800 zł**
- Kolor markera pokazywał: **suma** (800 zł + media)
- **Powód:** `main.py` priorytetowo używał `official_price` z OLX, która zawiera całkowitą kwotę

### Rozwiązanie
**Plik:** `src/main.py` (linie 146-159)

**PRZED:**
```python
# PRIORYTET 1: Oficjalna cena ze strony ogłoszenia
if raw_offer.get('official_price'):
    price = raw_offer['official_price']  # ← SUMA (pokój + media)
    media_info = "sprawdź w opisie"
else:
    # FALLBACK: Parser ceny z treści
    price_data = self.price_parser.extract_price(full_text)
```

**PO:**
```python
# PRIORYTET 1: Parser ceny z treści (wyciąga czystą cenę pokoju)
price_data = self.price_parser.extract_price(full_text)
if price_data:
    price = price_data['price']  # ← CZYSTA cena pokoju
    media_info = price_data['media_info']
elif raw_offer.get('official_price'):
    # FALLBACK: Oficjalna cena z OLX
    price = raw_offer['official_price']
    media_info = "sprawdź w opisie - cena może zawierać media"
```

### Korzyści
✅ Kolor markera teraz bazuje na **czystej cenie pokoju** (bez mediów)  
✅ `price_parser.py` wyciąga wzorce typu "850 zł – pokój + 250 zł – opłaty"  
✅ Fallback na `official_price` tylko gdy parser nie znajdzie ceny w opisie  

---

## ETAP 2: Filtrowanie błędnych adresów z literą 'O'

### Problem
**Przykład:** https://www.olx.pl/d/oferta/pokoj-1-osobowy-lublin-blisko-uczelni-do-wynajecia-CID3-ID19jsg9.html
- Adres w ogłoszeniu: **"Bukietowa 1O"** (litera O zamiast cyfry 0)
- Prawidłowy adres: **"Bukietowa 10"**
- **Powód:** Błąd OCR lub literówka w tekście ogłoszenia

### Rozwiązanie
**Plik:** `src/address_parser.py` (linie 115-120)

**DODANO:**
```python
# FILTR BEZPIECZEŃSTWA: Odrzuć numery z literą O/o zaraz po cyfrze
if re.search(r'\d[Oo](?:[^a-zA-Z]|$)', main_number):
    print(f"⚠️ Odrzucono podejrzany numer: {number}")
    continue
```

### Działanie
- Pattern `\d[Oo](?:[^a-zA-Z]|$)` wykrywa:
  - `"1O"` → odrzucone
  - `"10O"` → odrzucone  
  - `"2o"` → odrzucone
- **NIE** wykrywa:
  - `"10a"` → prawidłowa litera po cyfrze (OK)
  - `"Narutowicza 5"` → brak litery O po cyfrze (OK)

### Dlaczego nie automatyczna normalizacja?
❌ Normalizacja `'O' → '0'` mogłaby tworzyć fałszywe adresy  
✅ Bezpieczniejsze: odrzucić podejrzane ogłoszenia (tracimy kilka, ale bez błędów)  

---

## ETAP 3: Poprawienie logiki "is_new"

### Problem
**Przykład:** https://www.olx.pl/d/oferta/pokoj-juranda-1-room-for-rent-total-1000-bills-CID3-ID16haaa.html
- Oferta oznaczona jako **"nowe"** (zielony badge)
- Jednocześnie **"nieaktywne"** (szare tło)
- **Logika paradoks:** oferta nie może być nowa i nieaktywna jednocześnie

### Rozwiązanie
**Plik:** `src/map_generator.py` (linie 83-91)

**PRZED:**
```python
is_new = False
if last_scan:  # ← BEZ sprawdzenia active
    first_seen = datetime.fromisoformat(offer['first_seen'])
    time_diff = abs((last_scan - first_seen).total_seconds())
    is_new = time_diff < 900  # 15 minut
```

**PO:**
```python
is_new = False
if offer['active'] and last_scan:  # ← TYLKO AKTYWNE
    first_seen = datetime.fromisoformat(offer['first_seen'])
    time_diff = abs((last_scan - first_seen).total_seconds())
    is_new = time_diff < 900  # 15 minut
```

### Logika po naprawie
✅ **Nowe** = dodane w ostatnim scanie **AND** nadal aktywne  
✅ Oferty nieaktywne **nigdy** nie są oznaczane jako "nowe"  
✅ Spójność: "nowy" badge tylko dla świeżych i dostępnych ofert  

---

## 📊 Podsumowanie zmian

| Plik | Linie | Zmiana |
|------|-------|--------|
| `src/main.py` | 146-159 | Odwrócenie priorytetu: parser opisu → official_price |
| `src/address_parser.py` | 115-120 | Filtr numerów z literą O/o po cyfrze |
| `src/map_generator.py` | 83-91 | Warunek `offer['active']` dla flagi is_new |

## ✅ Rezultat
- **Problem 1:** Kolory markerów teraz bazują na czystej cenie pokoju ✅
- **Problem 2:** Adresy z błędną literą "O" są odrzucane (bezpiecznie) ✅
- **Problem 3:** Flaga "nowe" tylko dla aktywnych ofert ✅

## 🔄 Następne kroki
1. GitHub Actions uruchomi automatyczny scan (9:00/15:00/21:00)
2. Sprawdź mapę po następnym scanie czy problemy zniknęły
3. Jeśli zbyt wiele ofert odrzuconych przez filtr 'O' → rozważ whitelist ulic Lublina

---

**Commit:** `4b29dbc`  
**Data:** 2026-03-01  
**Status:** ✅ Wdrożone do production
