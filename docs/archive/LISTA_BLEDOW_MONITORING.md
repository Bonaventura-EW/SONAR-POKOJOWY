# 🐛 LISTA BŁĘDÓW - ZAKŁADKA MONITORING

**Data analizy:** 2026-03-01  
**URL:** https://bonaventura-ew.github.io/SONAR-POKOJOWY/monitoring.html  
**Status:** ⚠️ Częściowo sprawna (dane wyświetlają się, ale są problemy)

---

## ❌ BŁĘDY KRYTYCZNE

### Brak błędów krytycznych
Strona ładuje się poprawnie, dane są wyświetlane.

---

## ⚠️ OSTRZEŻENIA I PROBLEMY

### 1. **Wykres "success_rate" jest pusty**
**Priorytet:** 🟡 Średni  
**Lokalizacja:** `docs/monitoring_data.json` → `charts.success_rate`  
**Problem:**
```json
"success_rate": []  // ← PUSTA TABLICA
```

**Wpływ:**
- Wykres success_rate NIE jest renderowany (brak danych)
- `monitoring_generator.py` generuje pustą tablicę dla tego wykresu
- Kod HTML oczekuje danych ale ich nie dostaje

**Przyczyna:**
W `src/monitoring_generator.py` linia 24:
```python
chart_data = {
    'duration_over_time': [],
    'offers_over_time': [],
    'success_rate': []  # ← Inicjalizowana ale NIGDY nie wypełniana
}
```

Następnie w pętli (linia 27-44) dane są dodawane TYLKO do:
- `duration_over_time` (linia 31-35)
- `offers_over_time` (linia 37-44)

**BRAK kodu** wypełniającego `success_rate`!

**Rozwiązanie:**
Dodać kod w `monitoring_generator.py` który wypełni `success_rate`:
```python
# Po istniejącym kodzie dla offers_over_time (linia ~44):
# Wykres success rate (dla każdego skanu: % sukcesu)
status = scan.get('status', 'unknown')
success = 1 if status == 'completed' else 0
chart_data['success_rate'].append({
    'timestamp': timestamp,
    'success': success
})
```

---

### 2. **Brak wizualizacji dla wykresu success_rate w HTML**
**Priorytet:** 🟡 Średni  
**Lokalizacja:** `docs/monitoring.html`  
**Problem:**
HTML **NIE MA** canvas dla wykresu `success_rate`, mimo że dane są generowane!

**Obecne wykresy w HTML (linia ~220-230):**
```html
<canvas id="durationChart"></canvas>  ✅
<canvas id="offersChart"></canvas>    ✅
<!-- BRAK: success_rate chart -->     ❌
```

**JavaScript renderCharts()** (linia ~310-390):
- Renderuje `durationChart` ✅
- Renderuje `offersChart` ✅
- **NIE renderuje** `success_rate` ❌

**Wpływ:**
Nawet jeśli naprawimy generator danych, wykres nie będzie wyświetlony.

**Rozwiązanie:**
1. Dodać HTML canvas:
```html
<div class="chart-container">
    <h2>✅ Success Rate</h2>
    <canvas id="successRateChart"></canvas>
</div>
```

2. Dodać rendering w JS:
```javascript
// W funkcji renderCharts(), po offersChart:
const successRateCtx = document.getElementById('successRateChart').getContext('2d');
new Chart(successRateCtx, {
    type: 'line',
    data: {
        labels: chartData.success_rate.map(d => ...),
        datasets: [{
            label: 'Success Rate (%)',
            data: chartData.success_rate.map(d => d.success * 100),
            ...
        }]
    }
});
```

---

### 3. **Brak obsługi błędów w tabeli skanów**
**Priorytet:** 🟢 Niski  
**Lokalizacja:** `docs/monitoring.html` → tabela skanów  
**Problem:**
Kolumna "Błędy" pokazuje tylko liczbę błędów (`scan.errors?.length`), ale:
- Nie ma tooltipa pokazującego szczegóły błędów
- Nie ma możliwości kliknięcia aby zobaczyć co poszło nie tak
- Dane błędów są w JSON ale nie są wykorzystane

**Przykładowe dane:**
```json
"errors": []  // ← Nawet jeśli będą błędy, użytkownik ich nie zobaczy
```

**Wpływ:**
Debugging jest utrudniony - użytkownik widzi "3 błędy" ale nie wie jakie.

**Rozwiązanie:**
Dodać tooltip lub modal z listą błędów:
```javascript
// W kodzie tworzącym komórkę z błędami:
const errorsCell = row.insertCell();
const errorCount = scan.errors?.length || 0;
errorsCell.textContent = errorCount;

if (errorCount > 0) {
    errorsCell.style.cursor = 'pointer';
    errorsCell.title = scan.errors.join('\n');  // Tooltip
    errorsCell.onclick = () => {
        alert('Błędy:\n' + scan.errors.join('\n'));
    };
}
```

---

### 4. **Brak informacji o źródle ceny w monitoringu**
**Priorytet:** 🟢 Niski  
**Lokalizacja:** `docs/monitoring_data.json`  
**Problem:**
Po naprawie ekstrakcji cen (commit fff24f0), dodaliśmy pole `price.source` do ofert.
Ale monitoring **NIE ŚLEDZI** tej metryki!

**Oczekiwane dane:**
```json
"stats": {
    "raw_offers": 233,
    "processed": 59,
    "price_sources": {  // ← BRAK w aktualnych danych
        "json-ld": 45,
        "parser": 10,
        "html-fallback": 4
    }
}
```

**Wpływ:**
- Nie wiemy ile ofert używa JSON-LD vs parser vs fallback
- Trudno monitorować jakość ekstrakcji cen
- Nie ma metryk dla nowej funkcjonalności

**Rozwiązanie:**
Zaktualizować `src/main.py` aby logować źródła cen w statystykach skanowania.

---

### 5. **Dane statystyk są nieaktualne**
**Priorytet:** 🔴 Informacyjny  
**Lokalizacja:** Live strona  
**Problem:**
```json
"generated_at": "2026-02-28T20:43:36.631711+01:00"
```

Ostatnia aktualizacja: **28 lutego 2026, 20:43**  
Dzisiaj jest: **1 marca 2026**

**Wpływ:**
Strona pokazuje stare dane (2 dni wstecz).

**Przyczyna:**
- GitHub Actions uruchamia skany 3x dziennie
- Ostatni skan był 28 lutego
- Albo Actions nie zadziałały, albo nie było nowych ofert

**Rozwiązanie:**
To nie jest błąd w kodzie - to normalny stan między skanami.
Następne skanowanie automatycznie zaktualizuje dane.

---

## 📊 PODSUMOWANIE BŁĘDÓW

| # | Problem | Priorytet | Wpływ | Status |
|---|---------|-----------|-------|--------|
| 1 | Wykres success_rate pusty (dane) | 🟡 Średni | Brak wykresu | Do naprawy |
| 2 | Wykres success_rate brak (HTML/JS) | 🟡 Średni | Brak wykresu | Do naprawy |
| 3 | Brak tooltipów dla błędów w tabeli | 🟢 Niski | UX | Nice-to-have |
| 4 | Brak metryki źródeł cen | 🟢 Niski | Monitoring jakości | Nice-to-have |
| 5 | Dane z 28-02 (stare) | 🔴 Info | Czeka na skan | Normalne |

---

## ✅ CO DZIAŁA DOBRZE

- ✅ Strona ładuje się poprawnie
- ✅ Wszystkie statystyki są wyświetlane
- ✅ Tabela skanów działa poprawnie
- ✅ Wykres czasu wykonania działa (12 punktów)
- ✅ Wykres liczby ofert działa (12 punktów)
- ✅ JSON jest poprawnie sformatowany
- ✅ Responsywność strony OK
- ✅ Chart.js ładuje się z CDN
- ✅ Favicon działa
- ✅ Link "Powrót do mapy" działa

---

## 🔧 REKOMENDOWANE NAPRAWY

### Krótkoterminowe (quick wins):
1. **Napraw wykres success_rate** - dodaj kod do `monitoring_generator.py`
2. **Dodaj canvas dla success_rate** - update `monitoring.html`

### Długoterminowe (nice-to-have):
3. Dodaj tooltips dla błędów w tabeli
4. Dodaj tracking źródeł cen (`price.source`)
5. Dodaj filtrowanie danych w tabeli (date range picker)
6. Dodaj eksport danych do CSV

---

## 🎯 PRIORYTET NAPRAWY

**Zalecam naprawę problemu #1 i #2** (wykres success_rate):
- Nieskomplikowana naprawa (~15 minut)
- Uzupełni dashboard o brakujący element
- Poprawi UX monitoringu

**Problemy #3 i #4** mogą poczekać - są to ulepszenia, nie błędy.

**Problem #5** rozwiąże się sam przy następnym skanie.
