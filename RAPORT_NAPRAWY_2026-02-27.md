# 🔧 RAPORT NAPRAWY SYSTEMU - 27.02.2026

## 📋 Zidentyfikowane problemy

### 1. ❌ Błędne ceny na mapie
**Problem:**
- Ogłoszenie https://www.olx.pl/d/oferta/komfortowy-pokoj-dla-kobiety-felin-balkon-wysoki-standard-klima-CID3-ID19ch3j.html
  - Oficjalna cena: **900 zł**
  - Wyświetlana cena: **140 zł** ❌
  
- Ogłoszenie https://www.olx.pl/d/oferta/wynajme-pokoj-w-samodzielnym-mieszkaniu-bez-lokatorow-tumidajskiego-CID3-ID19uL0L.html
  - Oficjalna cena: **1100 zł**
  - Wyświetlana cena: **150 zł** ❌

**Przyczyna:**
Parser ceny (`price_parser.py`) analizował treść ogłoszenia i wyciągał pierwszą znalezioną liczbę (często był to numer ulicy lub inna przypadkowa wartość).

**Rozwiązanie:**
1. Zaktualizowano `scraper.py` - dodano pobieranie oficjalnej ceny ze strony ogłoszenia (tag `<h3>`)
2. Zaktualizowano `main.py` - priorytet dla oficjalnej ceny, parser tylko jako fallback
3. Parser ceny pozostaje jako backup dla starszych ogłoszeń

### 2. ❌ Usunięte ogłoszenia powracały po scanie
**Problem:**
Użytkownik usuwał niechciane ogłoszenia z mapy, ale po kolejnym automatycznym scanie pojawiały się ponownie.

**Rozwiązanie:**
1. Stworzono system trwałego usuwania: `data/removed_listings.json`
2. Dodano filtrowanie podczas scanu - ogłoszenia z listy usuniętych są pomijane
3. Stworzono skrypt `remove_listing.py` do zarządzania:
   ```bash
   python src/remove_listing.py <offer_id>        # usuń
   python src/remove_listing.py list              # lista
   python src/remove_listing.py restore <offer_id> # przywróć
   ```
4. Dodano przycisk "🗑️ Usuń" w popup mapy

---

## ✅ Zmiany w kodzie

### 1. **src/scraper.py**
**Nowa funkcjonalność:** Pobieranie oficjalnej ceny

```python
def fetch_offer_details(self, url: str) -> Optional[Dict]:
    # ... 
    # Oficjalna cena - szukaj h3 z ceną
    official_price = None
    for h3 in soup.find_all('h3'):
        text = h3.get_text(strip=True)
        if 'zł' in text.lower() and any(char.isdigit() for char in text):
            # Wyciągnij liczbę
            official_price = int(price_str)
    
    return {
        'description': description,
        'official_price': official_price,
        'official_price_raw': official_price_raw
    }
```

### 2. **src/main.py**
**Nowa logika:** Priorytet dla oficjalnej ceny

```python
# PRIORYTET 1: Oficjalna cena ze strony ogłoszenia
if raw_offer.get('official_price'):
    price = raw_offer['official_price']
    media_info = "sprawdź w opisie"
else:
    # FALLBACK: Parser ceny z treści
    price_data = self.price_parser.extract_price(full_text)
    price = price_data['price']
```

**Filtrowanie usuniętych:**
```python
# Wczytaj listę usuniętych
self.removed_listings = self._load_removed_listings()

# Podczas scanu:
if offer_id in self.removed_listings:
    print(f"🚫 Pominięto - ogłoszenie usunięte")
    continue
```

### 3. **data/removed_listings.json**
**Nowy plik:** Lista usuniętych ogłoszeń

```json
{
  "removed_ids": [
    "pokoj-example-ID123"
  ],
  "last_updated": "2026-02-27T14:30:00+01:00"
}
```

### 4. **src/remove_listing.py**
**Nowy skrypt:** Zarządzanie usuniętymi ogłoszeniami

```bash
# Użycie:
python src/remove_listing.py pokoj-example-ID123    # usuń
python src/remove_listing.py list                   # lista
python src/remove_listing.py restore ID123          # przywróć
```

### 5. **docs/assets/script.js**
**Nowa funkcja:** Przycisk usuwania w popup

```javascript
function removeListingPrompt(offerId) {
    alert('📝 Skopiuj i wykonaj polecenie:\n\n' + 
          'python src/remove_listing.py ' + offerId);
}
```

---

## 🧪 Testy

### Test 1: Oficjalna cena - Ogłoszenie 1
```bash
URL: https://www.olx.pl/d/oferta/komfortowy-pokoj-dla-kobiety-felin-balkon-wysoki-standard-klima-CID3-ID19ch3j.html

Wynik:
✅ Oficjalna cena: 900 zł
✅ Raw: 900 zł
✅ Opis poprawnie pobrany
```

### Test 2: Oficjalna cena - Ogłoszenie 2
```bash
URL: https://www.olx.pl/d/oferta/wynajme-pokoj-w-samodzielnym-mieszkaniu-bez-lokatorow-tumidajskiego-CID3-ID19uL0L.html

Wynik:
✅ Oficjalna cena: 1100 zł
✅ Raw: 1 100 zł
✅ Opis poprawnie pobrany
```

---

## 📊 Kolejne kroki

### Pilne (do wykonania przy następnym scanie):
1. ✅ Sprawdź czy nowe ceny są poprawne
2. ✅ Przetestuj usuwanie ogłoszeń

### Opcjonalne usprawnienia:
1. **Geocoding bez numeru ulicy:**
   - Obecnie: wymaga numeru
   - Propozycja: geocoduj samo "Tumidajskiego, Lublin"
   
2. **Walidacja geocodingu:**
   - Sprawdzaj czy współrzędne są w Lublinie
   - Odrzucaj oferty poza granicami miasta

3. **UI dla usuwania:**
   - Obecnie: kopiuj-wklej komendę
   - Propozycja: API endpoint do usuwania z poziomu mapy

---

## 🎯 Podsumowanie

### Co zostało naprawione:
✅ Ceny są teraz pobierane z oficjalnych metadanych OLX (nie z treści)  
✅ System trwałego usuwania niechcianych ogłoszeń  
✅ Usunięte ogłoszenia nie powracają po scanie  

### Jak używać nowego systemu:
1. **Automatycznie:** Przy kolejnym scanie ceny będą poprawne
2. **Usuwanie ogłoszeń:**
   - Kliknij "🗑️ Usuń" w popup
   - Skopiuj polecenie i wykonaj w terminalu:
     ```bash
     cd /ścieżka/do/projektu
     python src/remove_listing.py <offer_id>
     ```
   - Przy następnym scanie ogłoszenie zniknie z mapy

### Następny scan:
Po następnym automatycznym scanie (GitHub Actions):
- Wszystkie ceny powinny być **poprawne** (900 zł, 1100 zł, itd.)
- Usunięte ogłoszenia **nie pojawią się** na mapie

---

**Data raportu:** 27.02.2026  
**Status:** ✅ NAPRAWIONO  
**Commit:** c204cd6
