# 📊 PRZYKŁADY DZIAŁANIA - Dynamiczne statystyki

## 🎬 SCENARIUSZ 1: Podstawowe użycie

### Dane początkowe:
- **Baza:** 105 aktywnych ofert, 20 nieaktywnych
- **Ceny aktywne:** 300-2400 zł
- **Ceny nieaktywne:** 500-1800 zł

### Akcja: Użytkownik otwiera stronę

**Widok statystyk:**
```
📊 Aktywne (widoczne)
Liczba ofert: 105
Średnia cena: 904 zł
Najtańsza: 300 zł
Najdroższa: 2400 zł

📊 Nieaktywne (widoczne)
Liczba ofert: 20
Średnia cena: 1050 zł
Najtańsza: 500 zł
Najdroższa: 1800 zł
```

**✅ Wszystkie filtry domyślnie zaznaczone → pokazuje pełne dane**

---

## 🎬 SCENARIUSZ 2: Filtrowanie po zakresach cenowych

### Akcja: Użytkownik odznacza wszystkie zakresy OPRÓCZ "0-600 zł" i "601-800 zł"

**Filtrowane oferty:**
- Aktywne w zakresie 0-800 zł: **35 ofert**
- Nieaktywne w zakresie 0-800 zł: **8 ofert**

**Widok statystyk:**
```
📊 Aktywne (widoczne)
Liczba ofert: 35
Średnia cena: 580 zł
Najtańsza: 300 zł
Najdroższa: 800 zł

📊 Nieaktywne (widoczne)
Liczba ofert: 8
Średnia cena: 650 zł
Najtańsza: 500 zł
Najdroższa: 780 zł
```

**✅ Statystyki pokazują tylko oferty z wybranych zakresów**

---

## 🎬 SCENARIUSZ 3: Filtrowanie czasowe

### Akcja: Użytkownik zmienia filtr czasowy na "7 dni"

**Dane:**
- Oferty aktywne z ostatnich 7 dni: **12 ofert** (z 105 ogółem)
- Oferty nieaktywne z ostatnich 7 dni: **2 oferty** (z 20 ogółem)

**Widok statystyk:**
```
📊 Aktywne (widoczne)
Liczba ofert: 12
Średnia cena: 850 zł
Najtańsza: 450 zł
Najdroższa: 1200 zł

📊 Nieaktywne (widoczne)
Liczba ofert: 2
Średnia cena: 720 zł
Najtańsza: 600 zł
Najdroższa: 840 zł
```

**✅ Pokazuje tylko świeże oferty**

---

## 🎬 SCENARIUSZ 4: Kombinacja filtrów

### Akcja: 
- Zakresy: **tylko "0-600 zł"**
- Czas: **"30 dni"**
- Warstwy: **Aktywne ✓, Nieaktywne ✓**

**Dane:**
- Aktywne 0-600 zł z ostatnich 30 dni: **8 ofert**
- Nieaktywne 0-600 zł z ostatnich 30 dni: **3 oferty**

**Widok statystyk:**
```
📊 Aktywne (widoczne)
Liczba ofert: 8
Średnia cena: 480 zł
Najtańsza: 300 zł
Najdroższa: 600 zł

📊 Nieaktywne (widoczne)
Liczba ofert: 3
Średnia cena: 550 zł
Najtańsza: 500 zł
Najdroższa: 590 zł
```

**✅ Wszystkie filtry działają razem**

---

## 🎬 SCENARIUSZ 5: Tylko nieaktywne oferty

### Akcja: Użytkownik odznacza "Aktywne oferty"

**Widok statystyk:**
```
📊 Aktywne (widoczne)
Liczba ofert: -
Średnia cena: -
Najtańsza: -
Najdroższa: -

📊 Nieaktywne (widoczne)
Liczba ofert: 20
Średnia cena: 1050 zł
Najtańsza: 500 zł
Najdroższa: 1800 zł
```

**✅ Sekcja aktywnych pokazuje "-" bo warstwa wyłączona**

---

## 🎬 SCENARIUSZ 6: Wyszukiwanie

### Akcja: Użytkownik wpisuje "Chopina" w wyszukiwaniu

**Dane:**
- Oferty aktywne z adresem "Chopina": **3 oferty**
- Oferty nieaktywne z adresem "Chopina": **1 oferta**

**Widok statystyk:**
```
📊 Aktywne (widoczne)
Liczba ofert: 3
Średnia cena: 750 zł
Najtańsza: 650 zł
Najdroższa: 900 zł

📊 Nieaktywne (widoczne)
Liczba ofert: 1
Średnia cena: 800 zł
Najtańsza: 800 zł
Najdroższa: 800 zł
```

**✅ Filtrowanie po adresie działa**

---

## 🎬 SCENARIUSZ 7: Brak ofert spełniających kryteria

### Akcja:
- Zakresy: **tylko "0-600 zł"**
- Czas: **"7 dni"**
- Warstwy: **Aktywne ✓, Nieaktywne ✓**

**Dane:**
- W ostatnich 7 dniach nie ma żadnych ofert 0-600 zł

**Widok statystyk:**
```
📊 Aktywne (widoczne)
Liczba ofert: -
Średnia cena: -
Najtańsza: -
Najdroższa: -

📊 Nieaktywne (widoczne)
Liczba ofert: -
Średnia cena: -
Najtańsza: -
Najdroższa: -
```

**✅ System nie crashuje, pokazuje "-" gdy brak danych**

---

## 🎬 SCENARIUSZ 8: Precyzyjne filtry Min/Max (weryfikacja że NIE wpływają)

### Ustawienia przed testem:
**Widok statystyk (wszystkie filtry domyślne):**
```
📊 Aktywne (widoczne)
Liczba ofert: 105
Średnia cena: 904 zł
Najtańsza: 300 zł
Najdroższa: 2400 zł
```

### Akcja: Użytkownik ustawia precyzyjny filtr dla aktywnych:
- **Min: 500 zł**
- **Max: 1000 zł**

**Co się dzieje:**
- ✅ Markery na mapie **są filtrowane** (widoczne tylko 500-1000 zł)
- ❌ Statystyki **NIE zmieniają się** (nadal pokazują 300-2400 zł)

**Widok statystyk (PO ustawieniu Min/Max):**
```
📊 Aktywne (widoczne)
Liczba ofert: 105      ← BEZ ZMIAN
Średnia cena: 904 zł   ← BEZ ZMIAN
Najtańsza: 300 zł      ← BEZ ZMIAN
Najdroższa: 2400 zł    ← BEZ ZMIAN
```

**✅ Precyzyjne filtry Min/Max NIE wpływają na statystyki (zgodnie z wymaganiami)**

---

## 🎬 SCENARIUSZ 9: Oferta z wieloma cenami na tym samym adresie

### Dane:
**Adres:** ul. Narutowicza 10
- Oferta 1: 500 zł (aktywna)
- Oferta 2: 600 zł (nieaktywna)
- Oferta 3: 700 zł (nieaktywna)

### Akcja: Użytkownik wybiera:
- Warstwy: **Aktywne ✓, Nieaktywne ✓**
- Zakresy: **"0-600 zł"** dla obu warstw

**Logika filtrowania:**
1. Oferta 1 (500 zł, aktywna) → **PASUJE** (aktywna + zakres 0-600)
2. Oferta 2 (600 zł, nieaktywna) → **PASUJE** (nieaktywna + zakres 0-600)
3. Oferta 3 (700 zł, nieaktywna) → **NIE PASUJE** (poza zakresem 0-600)

**Widok statystyk (fragment):**
```
📊 Aktywne (widoczne)
Liczba ofert: ... + 1 (oferta 500 zł)
...

📊 Nieaktywne (widoczne)
Liczba ofert: ... + 1 (oferta 600 zł)
...
```

**✅ Każda oferta jest filtrowana osobno według zakresu dla swojej warstwy**

---

## 🎬 SCENARIUSZ 10: Zmiana filtrów w locie

### Sekwencja akcji:

**1. Start (wszystkie filtry domyślne):**
```
Aktywne: 105 ofert, 904 zł średnia
Nieaktywne: 20 ofert, 1050 zł średnia
```

**2. Użytkownik klika "0-600 zł" (tylko ten zakres):**
```
Aktywne: 18 ofert, 480 zł średnia   ← ZMIANA
Nieaktywne: 5 ofert, 550 zł średnia  ← ZMIANA
```

**3. Użytkownik dodaje "601-800 zł":**
```
Aktywne: 35 ofert, 580 zł średnia   ← ZMIANA
Nieaktywne: 8 ofert, 650 zł średnia  ← ZMIANA
```

**4. Użytkownik wpisuje "Chopina" w wyszukiwaniu:**
```
Aktywne: 2 oferty, 700 zł średnia   ← ZMIANA
Nieaktywne: 0 ofert, - średnia      ← ZMIANA
```

**5. Użytkownik czyści wyszukiwanie:**
```
Aktywne: 35 ofert, 580 zł średnia   ← POWRÓT DO STANU 3
Nieaktywne: 8 ofert, 650 zł średnia  ← POWRÓT DO STANU 3
```

**✅ Statystyki reagują natychmiast na każdą zmianę filtrów**

---

## 📊 PODSUMOWANIE ZACHOWAŃ

| Filtr | Wpływa na statystyki? | Uwagi |
|-------|----------------------|-------|
| ☑️ Aktywne/Nieaktywne | **TAK** | Osobne sekcje |
| ☑️ Zakresy cenowe | **TAK** | Osobno dla każdej warstwy |
| 🕐 Filtr czasowy | **TAK** | Wspólny dla obu warstw |
| 🔍 Wyszukiwanie | **TAK** | Wspólne dla obu warstw |
| 💲 Precyzyjne Min/Max | **NIE** | Zgodnie z wymaganiami |
| ⚠️ Warstwa uszkodzonych | **NIE** | Osobna warstwa |

---

## 🎯 KLUCZOWE ZACHOWANIA

### ✅ **TAK - DZIAŁA POPRAWNIE:**
- Statystyki zmieniają się po każdej zmianie filtrów
- Osobne liczby dla aktywnych i nieaktywnych
- Wyświetla "-" gdy brak ofert
- Brak błędów w konsoli
- Wydajność < 5ms na typowej ilości danych

### ❌ **NIE - ZGODNIE Z WYMAGANIAMI:**
- Precyzyjne filtry Min/Max nie wpływają na statystyki
- Uszkodzone oferty nie są zliczane (osobna warstwa)

---

**Koniec przykładów** 🎉
