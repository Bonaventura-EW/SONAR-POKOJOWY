# 📐 INSTRUKCJE: Zmiany wizualne w projekcie

**Data utworzenia:** 2026-03-06  
**Projekt:** SONAR POKOJOWY  
**Dla:** Claude Assistant

---

## 🎨 ZASADA GŁÓWNA

**PRZED wprowadzeniem jakichkolwiek zmian wizualnych (CSS, HTML layout, kolory, czcionki, spacing):**

### ✅ **WYMAGANE KROKI:**

1. **Stwórz wizualizację PRZED/PO w artefakcie HTML**
   - Pokaż obecny wygląd (PRZED)
   - Pokaż proponowany wygląd (PO)
   - Użyj prawdziwych kolorów i stylów
   - Dodaj opisy zmian

2. **Poczekaj na akceptację użytkownika**
   - Nie commituj zmian bez zgody
   - Pozwól użytkownikowi wybrać opcje
   - Jeśli potrzeba - stwórz warianty A/B/C

3. **Dopiero po akceptacji - implementuj**
   - Zmień pliki CSS/HTML
   - Commit z opisowym message
   - Zaktualizuj dokumentację

---

## 📋 SZABLON ARTEFAKTU WIZUALIZACYJNEGO

```html
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wizualizacja: [Nazwa zmiany]</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f5f5f5;
            padding: 40px;
            margin: 0;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        h1 {
            color: #667eea;
            margin-bottom: 10px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 40px;
        }
        .comparison {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 40px;
            margin-bottom: 40px;
        }
        .version {
            border: 2px solid #ddd;
            border-radius: 8px;
            padding: 20px;
        }
        .version h2 {
            margin-top: 0;
            font-size: 18px;
            color: #333;
        }
        .before {
            border-color: #ff6b6b;
        }
        .after {
            border-color: #51cf66;
        }
        .before h2 {
            color: #ff6b6b;
        }
        .after h2 {
            color: #51cf66;
        }
        .changes {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin-top: 20px;
        }
        .changes h3 {
            margin-top: 0;
            color: #667eea;
        }
        .changes ul {
            margin: 10px 0;
            padding-left: 20px;
        }
        .changes li {
            margin-bottom: 8px;
        }
        .demo-box {
            /* Tu wklej style demonstracyjne */
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Wizualizacja: [Nazwa zmiany]</h1>
        <p class="subtitle">Porównanie obecnego i proponowanego wyglądu</p>
        
        <div class="comparison">
            <div class="version before">
                <h2>❌ PRZED</h2>
                <!-- Demo obecnego wyglądu -->
                <div class="demo-box">
                    [Obecny wygląd]
                </div>
            </div>
            
            <div class="version after">
                <h2>✅ PO</h2>
                <!-- Demo nowego wyglądu -->
                <div class="demo-box">
                    [Nowy wygląd]
                </div>
            </div>
        </div>
        
        <div class="changes">
            <h3>📋 Lista zmian:</h3>
            <ul>
                <li>Zmiana 1</li>
                <li>Zmiana 2</li>
                <li>Zmiana 3</li>
            </ul>
        </div>
    </div>
</body>
</html>
```

---

## 🎯 PRZYKŁADY UŻYCIA

### **Przykład 1: Zmiana kolorów statystyk**

**KROK 1:** Stwórz artefakt HTML pokazujący:
- PRZED: Obecny gradient fioletowy
- PO: Proponowany gradient niebieski
- Lista zmian: hex kolorów

**KROK 2:** Poczekaj na akceptację

**KROK 3:** Zmień `style.css` + commit

---

### **Przykład 2: Nowy układ filtrów**

**KROK 1:** Stwórz artefakt HTML pokazujący:
- PRZED: Filtry w kolumnie
- PO: Filtry w 2 kolumnach
- Lista zmian: grid layout, spacing

**KROK 2:** Zapytaj użytkownika o preferowaną opcję

**KROK 3:** Implementuj wybraną opcję

---

### **Przykład 3: Zmiana czcionek**

**KROK 1:** Stwórz artefakt HTML pokazujący:
- PRZED: Segoe UI, 11-13px
- PO: System fonts, 13-18px
- Lista zmian: font-family, font-size

**KROK 2:** Pokaż różne rozmiary do wyboru (opcje A/B/C)

**KROK 3:** Implementuj po wyborze

---

## ⚠️ WYJĄTKI OD ZASADY

**Możesz pominąć wizualizację tylko gdy:**

1. **Drobne poprawki techniczne:**
   - Naprawa błędów w CSS (np. brakujący średnik)
   - Dodanie vendor prefixes
   - Optymalizacja wydajności bez zmian wizualnych

2. **Użytkownik wyraźnie prosi "zrób X" bez wizualizacji:**
   - "Zmień kolor przycisku na niebieski" (konkretna wartość)
   - "Ustaw padding na 20px" (konkretna wartość)

3. **Mikro-zmiany poniżej progu percepcji:**
   - Zmiana 1-2px padding
   - Drobne poprawki alignment

**W KAŻDYM INNYM PRZYPADKU - ZAWSZE WIZUALIZACJA!**

---

## 🛠️ NARZĘDZIA DO WIZUALIZACJI

### **Co pokazywać w artefakcie:**

1. **Statystyki:**
   ```html
   <div class="sidebar-stats">
       <div class="stat-item">
           <span class="stat-label">Widocznych ofert:</span>
           <span class="stat-value">15</span>
       </div>
   </div>
   ```

2. **Filtry:**
   ```html
   <div class="filter-group">
       <h3>Zakresy cenowe</h3>
       <label>
           <input type="checkbox" checked> 0-600 zł
       </label>
   </div>
   ```

3. **Przyciski:**
   ```html
   <button class="offer-link">Zobacz OLX</button>
   ```

4. **Kolory:**
   ```html
   <div style="display: flex; gap: 10px;">
       <div style="width: 100px; height: 100px; background: #667eea;"></div>
       <div style="width: 100px; height: 100px; background: #764ba2;"></div>
   </div>
   ```

---

## 📊 CHECKLIST PRZED ZMIANĄ

- [ ] Stworzyłem artefakt HTML z wizualizacją PRZED/PO
- [ ] Pokazałem rzeczywiste style i kolory (nie placeholder)
- [ ] Opisałem wszystkie zmiany w liście
- [ ] Jeśli potrzeba - stworzyłem warianty A/B/C
- [ ] Poczekałem na akceptację użytkownika
- [ ] Otrzymałem pozwolenie na implementację
- [ ] Dopiero teraz zmieniam kod

---

## ✅ DOBRE PRAKTYKI

### **DO:**
- ✅ Pokazuj prawdziwe kolory hex (#667eea, nie "niebieski")
- ✅ Używaj prawdziwych wymiarów (18px, nie "większe")
- ✅ Dodawaj interactive hover states w artefakcie
- ✅ Pokazuj kontekst (nie tylko sam element, ale otoczenie)
- ✅ Numeruj opcje (A, B, C) jeśli są warianty
- ✅ Dodaj sekcję "Korzyści" dla każdej zmiany

### **NIE RÓB:**
- ❌ Nie używaj placeholder tekstu ("Lorem ipsum")
- ❌ Nie pokazuj samego opisu bez wizualizacji
- ❌ Nie implementuj od razu bez akceptacji
- ❌ Nie pokazuj tylko fragmentu (pokaż cały komponent)
- ❌ Nie używaj screenshotów (zawsze live HTML)

---

## 🎓 PRZYKŁAD DOBREJ WIZUALIZACJI

**Temat:** Zmiana kolorów statystyk

**Artefakt zawiera:**
1. Grid 2 kolumny (PRZED | PO)
2. Pełny komponent statystyk z prawdziwymi stylami
3. Hover states działające
4. Lista zmian z hex kolorami
5. Sekcja "Korzyści" wyjaśniająca dlaczego ta zmiana

**Artefakt NIE zawiera:**
- Placeholder "kolor niebieski" bez hex
- Tylko opisu bez wizualizacji
- Samego elementu bez kontekstu

---

## 💡 WSKAZÓWKI

1. **Zawsze kopiuj istniejące style z `style.css` do artefaktu**
   - Nie zgaduj jak wygląda obecnie
   - Skopiuj faktyczny CSS

2. **Jeśli zmiana dotyczy wielu elementów - pokaż wszystkie**
   - Nie tylko jeden przycisk, ale całą grupę
   - Nie tylko jeden filtr, ale cały sidebar

3. **Dodaj toggle między PRZED/PO jeśli to możliwe**
   ```html
   <button onclick="toggle()">Przełącz PRZED/PO</button>
   ```

4. **Opisz techniczne detale**
   - Nie tylko "większe" ale "13px → 18px"
   - Nie tylko "ładniejsze" ale "box-shadow: 0 2px 8px"

---

## 🚫 BŁĘDY DO UNIKNIĘCIA

### **Błąd #1: Brak wizualizacji**
```
❌ "Mogę zmienić kolory statystyk na bardziej kontrastowe?"
✅ "Stworzyłem wizualizację z 3 wariantami kolorów - wybierz:"
   [Artefakt z opcjami A/B/C]
```

### **Błąd #2: Niejasny opis**
```
❌ "Powiększę czcionki w statystykach"
✅ "Zwiększę czcionki: 13px → 18px (+38%), weight: 600 → 700"
   [Artefakt pokazujący różnicę]
```

### **Błąd #3: Brak opcji wyboru**
```
❌ "Zmienię układ na grid 2 kolumny"
✅ "Który układ preferujesz?
   A) Grid 2 kolumny
   B) Flex z wrap
   C) Accordion"
   [Artefakt z wszystkimi opcjami]
```

---

## 📝 TEMPLATE COMMIT MESSAGE

Po akceptacji wizualizacji:

```
Zmiana wizualna: [Krótki opis]

ZMIANY:
- [Zmiana 1 z konkretnymi wartościami]
- [Zmiana 2 z konkretnymi wartościami]

WIZUALIZACJA:
Użytkownik zaakceptował wariant [A/B/C] z artefaktu

PLIKI:
- docs/assets/style.css: [opis zmian]
- docs/index.html: [opis zmian jeśli dotyczy]
```

---

## 🎯 PODSUMOWANIE

**ZAWSZE PRZED ZMIANĄ WIZUALNĄ:**

1. 🎨 Stwórz artefakt HTML z wizualizacją PRZED/PO
2. 📊 Pokaż prawdziwe style, kolory, wymiary
3. ❓ Zapytaj o akceptację / wybór wariantu
4. ⏳ Poczekaj na odpowiedź
5. ✅ Dopiero po akceptacji - implementuj
6. 📝 Commit z opisem referencjonującym wizualizację

**Dzięki temu:**
- ✅ Użytkownik widzi co dostanie przed zmianą
- ✅ Można łatwo porównać opcje
- ✅ Unikamy niechcianych zmian
- ✅ Oszczędzamy czas na poprawkach

---

**Ten plik jest OBOWIĄZKOWY do przeczytania przed każdą zmianą wizualną!**

---

**Data ostatniej aktualizacji:** 2026-03-06  
**Wersja:** 1.0
