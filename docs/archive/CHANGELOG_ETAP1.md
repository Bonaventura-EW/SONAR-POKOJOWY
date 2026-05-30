# 🔧 CHANGELOG - ETAP 1: Naprawa krytycznego bugu

Data: 27.02.2026
Wykonane przez: Claude (z Mateuszem)

## 🐛 Zidentyfikowane problemy:

### 1. **KRYTYCZNY** - Niezgodność formatów współrzędnych
- **Problem**: Backend (`data.json`) generował współrzędne jako obiekt `{lat, lon}`
- **Oczekiwanie**: Frontend (`script.js`) próbował używać współrzędnych jako tablica `[lat, lon]`
- **Skutek**: Leaflet.js nie mógł stworzyć markerów - mapa była pusta mimo poprawnych danych

### 2. Duplikacja funkcji `deleteOffer()`
- **Problem**: Funkcja była zdefiniowana dwukrotnie w `script.js`
- **Skutek**: Potencjalne konflikty, nieczytelny kod

### 3. Nadmiar console.log
- **Problem**: Zbyt wiele logów w funkcji `loadData()`
- **Skutek**: Zaśmiecona konsola przeglądarki

---

## ✅ Wykonane naprawy:

### 1. Naprawa formatu współrzędnych w `docs/assets/script.js`
**Linia 157-174 (funkcja `createMarkerGroup`)**

**PRZED:**
```javascript
const coords = [
    baseCoords[0] + offsetLat,
    baseCoords[1] + offsetLon
];
```

**PO:**
```javascript
// Konwersja z obiektu {lat, lon} na tablicę [lat, lon] dla Leaflet
const coords = [
    baseCoords.lat + offsetLat,
    baseCoords.lon + offsetLon
];
```

**Uzasadnienie**: Format obiektowy `{lat, lon}` jest bardziej czytelny i samopisujący się. Backend nie wymaga zmian.

---

### 2. Usunięcie duplikatu funkcji `deleteOffer()`
**Linia 419-470**

**PRZED**: Dwie identyczne funkcje (linie 420-448 i 452-470)

**PO**: Jedna funkcja z lepszą obsługą błędów

---

### 3. Czyszczenie console.log
**Linia 28-88 (funkcja `loadData`)**

**PRZED**: 15+ linii console.log

**PO**: Tylko kluczowe logi:
- `✅ Załadowano X markerów`
- `🎉 Mapa gotowa!`
- `❌ Błąd wczytywania danych` (w przypadku błędu)

---

## 📋 Pliki zmienione:

1. `docs/assets/script.js` - 3 naprawy

---

## 🧪 Status testowania:

- [ ] Test lokalny (lokalny serwer HTTP)
- [ ] Deploy na GitHub Pages
- [ ] Weryfikacja produkcyjna

---

## 📝 Notatki techniczne:

### Dlaczego format obiektowy zamiast tablicowego?
1. **Czytelność**: `coords.lat` vs `coords[0]` - od razu wiadomo co to jest
2. **Bezpieczeństwo**: Brak pomyłek typu zamiana lat/lon
3. **Zgodność z API**: Większość geocoding API zwraca obiekty
4. **Łatwość debugowania**: JSON.stringify pokazuje nazwy pól

### Alternatywne podejście (odrzucone):
Zmiana backendu na tablice - wymagałaby:
- Modyfikacji `map_generator.py`
- Regeneracji `data.json`
- Potencjalnych problemów z cache w GitHub Actions
