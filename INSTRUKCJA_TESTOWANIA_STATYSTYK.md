# 🧪 INSTRUKCJA TESTOWANIA - Dynamiczne statystyki

## 🎯 Co zostało zaimplementowane?

Statystyki w prawym panelu (najtańsza oferta, średnia cena, najdroższa oferta, liczba ofert) **teraz reagują na filtry**!

---

## 📊 Nowy wygląd statystyk

**Przed:**
```
Aktywnych ofert: 105
Średnia cena: 904 zł
Najtańsza oferta: 300 zł
Najdroższa oferta: 2400 zł
```

**Teraz:**
```
📊 Aktywne (widoczne)
Liczba ofert: [dynamiczna]
Średnia cena: [dynamiczna]
Najtańsza: [dynamiczna]
Najdroższa: [dynamiczna]

📊 Nieaktywne (widoczne)
Liczba ofert: [dynamiczna]
Średnia cena: [dynamiczna]
Najtańsza: [dynamiczna]
Najdroższa: [dynamiczna]
```

---

## 🔍 JAK PRZETESTOWAĆ?

### **KROK 1: Odśwież stronę**
- Wciśnij **Ctrl+F5** (Windows) lub **Cmd+Shift+R** (Mac)
- To wymuś pełne odświeżenie bez cache

### **KROK 2: Test podstawowy**
1. Przy starcie zobaczysz wszystkie statystyki (wszystkie filtry zaznaczone)
2. **Odznacz "Aktywne oferty"** → sekcja "Aktywne" pokaże **"-"**
3. **Odznacz "Nieaktywne oferty"** → sekcja "Nieaktywne" pokaże **"-"**
4. **Zaznacz obie** → obie sekcje pokażą liczby

✅ **Oczekiwany wynik:** Statystyki zmieniają się natychmiast po kliknięciu checkboxów

---

### **KROK 3: Test zakresów cenowych**
1. Zaznacz **tylko "Aktywne oferty"** i **tylko zakres "0-600 zł"**
2. Zobacz sekcję "Aktywne (widoczne)":
   - **Najtańsza:** nie powinna być < 0 zł
   - **Najdroższa:** nie powinna być > 600 zł
   - **Liczba:** powinna być mniejsza niż przy wszystkich zakresach
3. Zaznacz **dodatkowe zakresy** → liczba ofert rośnie

✅ **Oczekiwany wynik:** Statystyki pokazują tylko oferty z zaznaczonych zakresów

---

### **KROK 4: Test filtra czasowego**
1. Zaznacz **tylko "Aktywne"** + **wszystkie zakresy**
2. Zmień filtr czasowy na **"7 dni"**
3. Zobacz sekcję "Aktywne":
   - **Liczba ofert:** powinna być mniejsza (tylko z ostatnich 7 dni)
4. Zmień na **"30 dni"** → liczba powinna wzrosnąć

✅ **Oczekiwany wynik:** Statystyki uwzględniają tylko oferty z wybranego okresu

---

### **KROK 5: Test wyszukiwania**
1. Zaznacz **"Aktywne" + wszystkie zakresy**
2. W polu wyszukiwania wpisz **"Chopina"** (lub inny popularny adres)
3. Zobacz sekcję "Aktywne":
   - **Liczba:** tylko oferty z tym adresem
4. Wyczyść wyszukiwanie → liczba wraca do pełnej

✅ **Oczekiwany wynik:** Statystyki filtrują po adresie

---

### **KROK 6: Test precyzyjnych filtrów Min/Max (weryfikacja że NIE wpływają)**
1. Zaznacz **"Aktywne" + wszystkie zakresy**
2. Ustaw **Min: 500 zł, Max: 1000 zł** (precyzyjny filtr dla aktywnych)
3. **WAŻNE:** Sprawdź statystyki - czy się zmieniły?

✅ **Oczekiwany wynik:** Statystyki **NIE powinny się zmienić** (zgodnie z wymaganiami)
❌ **Jeśli się zmieniły:** To BUG - zgłoś!

---

### **KROK 7: Test "brak ofert"**
1. Zaznacz **tylko "Aktywne"** + **tylko zakres "0-600 zł"** + **filtr "7 dni"**
2. Jeśli nie ma takich ofert, zobaczysz:
   ```
   📊 Aktywne (widoczne)
   Liczba ofert: -
   Średnia cena: -
   Najtańsza: -
   Najdroższa: -
   ```

✅ **Oczekiwany wynik:** Wyświetla "-" gdy brak ofert spełniających kryteria

---

## 🐛 CO SPRAWDZIĆ W KONSOLI PRZEGLĄDARKI?

1. Otwórz konsolę: **F12** → zakładka "Console"
2. Przy każdej zmianie filtrów **NIE powinno być błędów** (czerwonych wpisów)
3. Opcjonalnie zobaczysz logi typu:
   ```
   ✅ Załadowano 200 markerów
   🎉 Mapa gotowa!
   ```

---

## ⚠️ ZNANE OGRANICZENIA

1. **Precyzyjne filtry Min/Max** → NIE wpływają na statystyki (zgodnie z wymaganiami)
2. **Filtr uszkodzonych** → NIE wpływa na statystyki (uszkodzone są w osobnej warstwie)

---

## 📞 W RAZIE PROBLEMÓW

### **Problem 1: Statystyki nie zmieniają się**
**Rozwiązanie:**
- Wymuś pełne odświeżenie: **Ctrl+F5** (Windows) lub **Cmd+Shift+R** (Mac)
- Sprawdź czy wersja skryptu to `?v=4` (Zobacz źródło strony)

### **Problem 2: Błędy w konsoli**
**Rozwiązanie:**
- Skopiuj treść błędu i wyślij mi
- Sprawdź czy plik `data.json` jest dostępny (otwórz w przeglądarce: `/data.json`)

### **Problem 3: Sekcja nieaktywnych zawsze "-"**
**Możliwe przyczyny:**
- Checkbox "Nieaktywne oferty" jest odznaczony
- Nie ma żadnych nieaktywnych ofert w bazie
- Wszystkie nieaktywne są poza zaznaczonymi zakresami cenowymi

---

## ✅ CHECKLIST TESTÓW

- [ ] Odświeżono stronę (Ctrl+F5)
- [ ] Statystyki zmieniają się po kliknięciu checkboxów warstw
- [ ] Filtry zakresów cenowych wpływają na statystyki
- [ ] Filtr czasowy wpływa na statystyki
- [ ] Wyszukiwanie wpływa na statystyki
- [ ] Precyzyjne Min/Max NIE wpływają na statystyki
- [ ] Gdy brak ofert → wyświetla "-"
- [ ] Brak błędów w konsoli przeglądarki
- [ ] Obie sekcje (aktywne + nieaktywne) działają niezależnie

---

**Sukces!** 🎉 Jeśli wszystkie testy przeszły, funkcja działa poprawnie!
