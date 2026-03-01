# 🛡️ INSTRUKCJA: Warstwa "Uszkodzone"

## Problem który rozwiązuje
Niektóre ogłoszenia na OLX mogą być:
- **Błędne** (zła cena, błędny adres)
- **Spam** (te same oferty wielokrotnie)
- **Niechciane** z jakiegokolwiek powodu

Poprzedni mechanizm wymagał uruchamiania skryptów Python - **nie działał z przeglądarki**.

---

## Rozwiązanie: Warstwa "Uszkodzone"

### ✅ Jak to działa?

1. **Oznacz ogłoszenie jako uszkodzone**
   - Kliknij marker na mapie
   - W popup kliknij: **⚠️ Oznacz jako uszkodzone**
   - Potwierdź w oknie dialogowym
   
2. **Ogłoszenie zostaje przeniesione**
   - Marker znika z normalnych warstw (Aktywne/Nieaktywne)
   - Trafia do warstwy **"Uszkodzone"** (domyślnie ukryta)
   - Dane zapisują się w **localStorage** twojej przeglądarki

3. **Przeglądanie uszkodzonych**
   - W prawym panelu zaznacz: **⚠️ Uszkodzone**
   - Markery pomarańczowe z ikoną **⚠️**
   - Możesz je przywrócić przyciskiem **✅ Przywróć ogłoszenie**

---

## 🎯 Kluczowe cechy

| Cecha | Opis |
|-------|------|
| **Persystencja** | Dane zapisane w localStorage - przetrwają odświeżenie strony |
| **Lokalne** | Działa tylko w twojej przeglądarce (nie dla innych użytkowników) |
| **Odwracalne** | Możesz przywrócić ogłoszenie w każdej chwili |
| **Wizualne** | Pomarańczowe markery + ikona ⚠️ |
| **Domyślnie ukryte** | Warstwa startuje wyłączona |

---

## 📋 Przykład użycia

### Scenariusz: Ogłoszenie "Jutrzenki 12" jest błędne

**KROK 1:** Kliknij marker na mapie
```
📍 Jutrzenki 12
💰 850 zł
🔗 Otwórz ogłoszenie
⚠️ [Oznacz jako uszkodzone]  ← KLIKNIJ
```

**KROK 2:** Potwierdź
```
⚠️ Oznaczyć to ogłoszenie jako uszkodzone?

Ogłoszenie trafi do warstwy "Uszkodzone" (domyślnie ukrytej).
Możesz je przywrócić w każdej chwili.

[Anuluj]  [OK]
```

**KROK 3:** Automatyczne odświeżenie
```
✅ Ogłoszenie oznaczone jako uszkodzone!

Odśwież stronę (F5) aby zobaczyć zmiany.
```

**Strona odświeża się automatycznie po 1 sekundzie**

---

## 🔄 Przywracanie ogłoszenia

Jeśli oznaczyłeś omyłkowo:

1. Zaznacz checkbox **⚠️ Uszkodzone** (warstwa się pojawi)
2. Kliknij marker pomarańczowy
3. W popup kliknij: **✅ Przywróć ogłoszenie**
4. Strona odświeży się - ogłoszenie wraca do normalnej warstwy

---

## 🛠️ Techniczne szczegóły

### Gdzie są przechowywane dane?
```javascript
localStorage.setItem('sonar_damaged_listings', JSON.stringify([...]))
```

**Format danych:**
```json
[
  "pokoj-z-poludniowym-balkonem-od-zaraz-lublin-ul-jutrzenki-CID3-ID19wxC2",
  "pokoj-jednoosobowy-z-balkonem-CID3-ID14gaar",
  ...
]
```

### Jak czyścić wszystkie oznaczenia?

**Konsola przeglądarki (F12):**
```javascript
localStorage.removeItem('sonar_damaged_listings');
location.reload();
```

Lub:

**Panel Application → Storage → Local Storage → [twoja domena] → usuń klucz `sonar_damaged_listings`**

---

## ⚠️ Ważne informacje

### Dane lokalne (nie synchronizowane)
- Oznaczenia **NIE są współdzielone** między urządzeniami
- Jeśli otworzysz mapę na telefonie - **nie zobaczysz** oznaczeń z komputera
- Czyszczenie cache przeglądarki **usunie** wszystkie oznaczenia

### Co jeśli ogłoszenie zniknie z OLX?
- Oznaczenie pozostaje w localStorage
- Przy kolejnym scanie ogłoszenie stanie się **nieaktywne**
- Nadal będzie w warstwie "Uszkodzone" (można usunąć ręcznie z localStorage)

### Różnica między "Nieaktywne" a "Uszkodzone"

| Właściwość | Nieaktywne | Uszkodzone |
|------------|------------|------------|
| **Źródło** | Automatyczne (scan nie znalazł) | Ręczne (użytkownik oznaczył) |
| **Kolor** | Szary | Pomarańczowy |
| **Ikona** | × (krzyżyk) | ⚠️ (wykrzyknik) |
| **Domyślnie** | Pokazane | Ukryte |
| **Przywracanie** | Automatyczne (jeśli pojawi się na OLX) | Ręczne (użytkownik) |

---

## 🎨 Wygląd markerów

### Marker normalny (aktywny)
```
🟢 (zielony)  - cena < 600 zł
🟡 (żółty)    - 600-799 zł
🟠 (pomarańczowy) - 800-999 zł
🔴 (czerwony) - 1000+ zł
```

### Marker uszkodzony
```
🟠 (pomarańczowy) + gruba pomarańczowa obwódka + ikona ⚠️
```

### Marker nowy
```
Dowolny kolor + czerwona obwódka + badge "N"
```

---

## 💡 Wskazówki

1. **Regularnie sprawdzaj warstwę "Uszkodzone"**  
   Niektóre ogłoszenia mogą zostać naprawione na OLX - warto je przywrócić

2. **Eksportuj dane przed czyszczeniem cache**
   ```javascript
   console.log(localStorage.getItem('sonar_damaged_listings'));
   // Skopiuj wynik i zapisz
   ```

3. **Import danych po przeniesieniu**
   ```javascript
   localStorage.setItem('sonar_damaged_listings', '[...]');
   location.reload();
   ```

---

## 🐛 Troubleshooting

### Problem: Checkbox warstwy nie działa
**Rozwiązanie:** Odśwież stronę (Ctrl+F5 - pełne odświeżenie z cache)

### Problem: Oznaczone ogłoszenie nadal widoczne
**Rozwiązanie:** 
1. Sprawdź czy checkbox "Uszkodzone" jest **odznaczony**
2. Odśwież stronę (F5)
3. Jeśli problem pozostaje - sprawdź konsolę (F12) czy są błędy JS

### Problem: Straciłem oznaczenia po aktualizacji przeglądarki
**Rozwiązanie:** localStorage mógł zostać wyczyszczony. Niestety dane są nieodwracalnie utracone.

---

**Autor:** SONAR POKOJOWY  
**Data:** 2026-03-01  
**Wersja:** 1.0
