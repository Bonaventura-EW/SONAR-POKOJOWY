# 🐛 LISTA BŁĘDÓW - ZAKŁADKA ANALITYKA

**Data analizy:** 2026-03-01  
**URL:** https://bonaventura-ew.github.io/SONAR-POKOJOWY/analytics.html  
**Status:** ⚠️ Sprawna, ale dane zawierają błędne ceny z przeszłości

---

## ❌ BŁĘDY KRYTYCZNE

### Brak błędów krytycznych w kodzie
Strona ładuje się poprawnie, wszystkie wykresy działają.

---

## ⚠️ OSTRZEŻENIA I PROBLEMY

### 1. **Błędne ceny w danych historycznych**
**Priorytet:** 🟡 Średni  
**Lokalizacja:** `docs/data.json`  
**Problem:**

Znaleziono **9 ofert z podejrzanie niskimi cenami** (< 200 zł):

```
1. 140 zł - Królowej Jadwigi 27 (dodano: 28.02.2026)
2. 100 zł - Kraśnicka 2i (dodano: 28.02.2026)
3. 144 zł - Spółdzielczości Pracy 36 (dodano: 01.03.2026) ← 3x duplikat
4. 144 zł - Spółdzielczości Pracy 36 (dodano: 28.02.2026)
5. 120 zł - Gościnna 26 (dodano: 28.02.2026)
6. 150 zł - Rolna 2P (dodano: 01.03.2026) ← 2x duplikat
7. 150 zł - Rolna 2P (dodano: 01.03.2026)
8. 100 zł - Kazimierza Wielkiego 9 (dodano: 01.03.2026)
9. 144 zł - Studio 2 (dodano: 01.03.2026)
```

**Przyczyna:**
Te oferty zostały dodane **PRZED naprawą ekstrakcji cen** (commit fff24f0, 2026-03-01).

- **144 zł** to prawdopodobnie **2400 zł** (błąd parsowania separatora tysięcy)
- **150 zł** to prawdopodobnie **700 zł** (ten sam błąd który naprawiłem)

**Wpływ:**
- ⚠️ Wykresy pokazują błędne dane historyczne
- ⚠️ Średnia cena jest zaniżona (~815 zł zamiast ~850 zł)
- ⚠️ Mediana ceny może być nieprecyzyjna
- ⚠️ Histogram rozkładu cen pokazuje nieprawidłowe przedziały

**Rozwiązanie:**
Automatyczne skanowanie (za ~8h) zaktualizuje te oferty z poprawnymi cenami z JSON-LD.

**Tymczasowe obejście:**
Można manualnie uruchomić skanowanie:
```bash
python3 src/main.py
```

---

### 2. **Brak walidacji zakresu cen w wykresach**
**Priorytet:** 🟢 Niski  
**Lokalizacja:** `docs/analytics.html` (funkcje `createPriceChart`, `createPriceDistribution`)  
**Problem:**

Kod **nie filtruje** podejrzanych cen przed tworzeniem wykresów:

```javascript
// createPriceChart (linia 419-426)
offers.forEach(offer => {
    if (offer.first_seen_date >= startDate) {
        const dateKey = offer.first_seen_date.toISOString().split('T')[0];
        if (!dailyPrices[dateKey]) {
            dailyPrices[dateKey] = [];
        }
        dailyPrices[dateKey].push(offer.price);  // ← Nie ma walidacji!
    }
});
```

**Wpływ:**
Błędne ceny (100 zł, 144 zł) są uwzględniane w wykresach, co:
- Zniekształca średnią cenę
- Tworzy fałszywe trendy
- Wprowadza w błąd użytkowników

**Rozwiązanie:**
Dodać filtrowanie:
```javascript
offers.forEach(offer => {
    // Filtruj tylko sensowne ceny
    if (offer.first_seen_date >= startDate && 
        offer.price >= 200 && offer.price <= 3000) {
        const dateKey = offer.first_seen_date.toISOString().split('T')[0];
        if (!dailyPrices[dateKey]) {
            dailyPrices[dateKey] = [];
        }
        dailyPrices[dateKey].push(offer.price);
    }
});
```

**Podobnie dla:**
- `createPriceDistribution()` - filtruj ceny przed tworzeniem histogramu
- `processAnalytics()` - filtruj przy obliczaniu statystyk

---

### 3. **Brak obsługi pustych dat w wykresach**
**Priorytet:** 🟢 Niski  
**Lokalizacja:** `docs/analytics.html` (funkcje tworzące wykresy)  
**Problem:**

Jeśli **brak ofert dla pewnych dni**, wykresy mogą pokazywać luki:

```javascript
// createNewOffersChart (linia 488)
const labels = Object.keys(dailyCounts).sort();
const counts = labels.map(date => dailyCounts[date]);
```

Jeśli np. 28.02 było 5 ofert, 01.03 było 3 oferty, ale **29.02 i 02.03 brak** → wykres pominie te dni.

**Wpływ:**
- Wykres nie pokazuje ciągłej osi czasu
- Trudno zobaczyć dni bez ofert (które też są informacją)
- Użytkownik może pomyśleć że dane są niekompletne

**Rozwiązanie:**
Wypełnij brakujące dni zerami:
```javascript
function fillMissingDates(dailyCounts, startDate, endDate) {
    const filled = {};
    let currentDate = new Date(startDate);
    
    while (currentDate <= endDate) {
        const dateKey = currentDate.toISOString().split('T')[0];
        filled[dateKey] = dailyCounts[dateKey] || 0;
        currentDate.setDate(currentDate.getDate() + 1);
    }
    
    return filled;
}
```

---

### 4. **Brak tooltipów z dodatkowymi informacjami**
**Priorytet:** 🟢 Niski  
**Lokalizacja:** Wszystkie wykresy  
**Problem:**

Wykresy **nie mają** zaawansowanych tooltipów pokazujących:
- Dla wykresu cen: min/max cena tego dnia, liczba ofert
- Dla wykresu nowych ofert: linki do ofert, adresy
- Dla histogramu: procent całości, przykładowe adresy

**Przykład obecnego tooltipa:**
```
Średnia cena: 850 zł  ← tylko wartość
```

**Oczekiwany tooltip:**
```
📅 28.02.2026
💰 Średnia: 850 zł
   Min: 500 zł
   Max: 1200 zł
📊 Liczba ofert: 12
```

**Wpływ:**
UX - użytkownik musi szukać dodatkowych informacji gdzie indziej.

**Rozwiązanie:**
Dodać custom tooltips w Chart.js:
```javascript
options: {
    plugins: {
        tooltip: {
            callbacks: {
                title: function(context) {
                    return '📅 ' + context[0].label;
                },
                label: function(context) {
                    const date = labels[context.dataIndex];
                    const prices = dailyPrices[date];
                    const min = Math.min(...prices);
                    const max = Math.max(...prices);
                    const avg = prices.reduce((a,b) => a+b, 0) / prices.length;
                    
                    return [
                        `💰 Średnia: ${avg.toFixed(0)} zł`,
                        `   Min: ${min} zł`,
                        `   Max: ${max} zł`,
                        `📊 Liczba: ${prices.length}`
                    ];
                }
            }
        }
    }
}
```

---

### 5. **Brak eksportu danych do CSV**
**Priorytet:** 🟢 Bardzo niski  
**Lokalizacja:** Brak funkcjonalności  
**Problem:**

Użytkownik **nie może** wyeksportować danych analitycznych do CSV/Excel.

**Wpływ:**
- Nie można zrobić własnych analiz w Excel
- Nie można udostępnić danych
- Ograniczona użyteczność dla power users

**Rozwiązanie:**
Dodać przycisk "Eksportuj do CSV":
```javascript
function exportToCSV() {
    const csvRows = [];
    csvRows.push(['Data', 'Cena', 'Adres', 'Link'].join(','));
    
    window.allOffersData.forEach(offer => {
        csvRows.push([
            offer.first_seen,
            offer.price,
            offer.address,
            offer.url
        ].join(','));
    });
    
    const csvString = csvRows.join('\n');
    const blob = new Blob([csvString], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `sonar-pokojowy-${new Date().toISOString()}.csv`;
    a.click();
}
```

---

## 📊 PODSUMOWANIE BŁĘDÓW

| # | Problem | Priorytet | Wpływ | Status |
|---|---------|-----------|-------|--------|
| 1 | Błędne ceny historyczne (9 ofert) | 🟡 Średni | Nieprecyzyjne statystyki | Czeka na skan |
| 2 | Brak walidacji zakresu cen | 🟡 Średni | Zniekształcone wykresy | Do naprawy |
| 3 | Brak wypełniania pustych dat | 🟢 Niski | Luki w wykresach | Nice-to-have |
| 4 | Podstawowe tooltips | 🟢 Niski | UX | Nice-to-have |
| 5 | Brak eksportu CSV | 🟢 Bardzo niski | Funkcjonalność | Nice-to-have |

---

## ✅ CO DZIAŁA DOBRZE

- ✅ Wszystkie 3 wykresy renderują się poprawnie
- ✅ Suwaki zakresu czasowego działają (7-180 dni)
- ✅ Parsowanie dat działa dla formatu DD.MM.YYYY
- ✅ Statystyki ogólne są wyświetlane
- ✅ Chart.js ładuje się z CDN
- ✅ Responsywność OK
- ✅ Brak błędów JavaScript w konsoli
- ✅ Histogram cen działa (przedziały co 50 zł)

---

## 🔧 REKOMENDOWANE NAPRAWY

### Natychmiastowe (automatyczne):
**Problem #1** rozwiąże się sam przy następnym skanowaniu (~8h).

### Krótkoterminowe (quick wins):
1. **Dodaj walidację cen** (200-3000 zł) we wszystkich funkcjach wykresów
2. **Wypełnij puste dni** zerami w wykresie nowych ofert

### Długoterminowe (nice-to-have):
3. Ulepsz tooltips (min/max/count)
4. Dodaj eksport do CSV
5. Dodaj filtrowanie po adresach/dzielnicach

---

## 🎯 PRIORYTET NAPRAWY

**Zalecam naprawę problemu #2** (walidacja cen):
- Szybka naprawa (~10 minut)
- Chroni przed przyszłymi błędnymi danymi
- Poprawia jakość wykresów

**Problem #1** rozwiąże się automatycznie przy skanowaniu.

**Problemy #3-5** są ulepszeniami UX, nie błędami.

---

## 📝 DANE DIAGNOSTYCZNE

```
Aktywnych ofert: 107
Zakres cen: 100 - 2000 zł
Średnia cena: 815 zł (zaniżona przez błędne ceny)
Mediana ceny: ~800 zł
Podejrzane ceny (< 200 zł): 9 ofert
Formaty dat: DD.MM.YYYY (poprawny)
```

---

## 🚀 NASTĘPNE KROKI

1. **Automatyczne:** Skanowanie za ~8h usunie błędne ceny
2. **Opcjonalne:** Dodaj walidację cen w JS (problem #2)
3. **Nice-to-have:** Ulepsz tooltips i dodaj eksport CSV
