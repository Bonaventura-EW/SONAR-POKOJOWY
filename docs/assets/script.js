// SONAR POKOJOWY - JavaScript
// Interaktywna mapa z filtrami, wyszukiwaniem i warstwami

// Helper: parsowanie daty z formatu polskiego "DD.MM.YYYY HH:MM"
function parsePolishDate(str) {
    if (!str) return null;
    try {
        const parts = str.split(' ');
        const d = parts[0].split('.');
        const t = (parts[1] || '00:00').split(':');
        return new Date(
            parseInt(d[2]),
            parseInt(d[1]) - 1,
            parseInt(d[0]),
            parseInt(t[0]),
            parseInt(t[1])
        );
    } catch (e) {
        return null;
    }
}

// Helper: escapowanie HTML — dane ofert (adres, opis, URL) pochodzą z OLX,
// czyli od zewnętrznych ogłoszeniodawców. Wszystko co trafia do innerHTML/popupów
// MUSI przejść przez escapeHtml(), inaczej XSS.
function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Helper: URL oferty do atrybutu href — tylko http(s), inaczej '#'
function safeOfferUrl(url) {
    return /^https?:\/\//i.test(url || '') ? escapeHtml(url) : '#';
}

// Helper: debounce dla zdarzeń ciągłych (wpisywanie, suwaki) — filterMarkers
// przebudowuje warstwy markerów, bez debounce odpala się na każdy keystroke/tick
function debounce(fn, wait) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => fn.apply(this, args), wait);
    };
}

let map;
let mapData;
let allMarkers = [];
let markerLayers = {
    active: L.layerGroup(),
    inactive: L.layerGroup(),
    activeApprox: L.layerGroup(),   // aktywne przybliżone (precision: street_only)
    inactiveApprox: L.layerGroup(), // nieaktywne przybliżone
    firm: L.layerGroup(),            // aktywne oferty profili firmowych
    firmInactive: L.layerGroup(),    // nieaktywne oferty profili firmowych
    addrArchival: L.layerGroup()     // archiwalne pinezki poprzednich adresów (po zmianie adresu)
};

// ===== Filtr daty dodania (suwak dni) =====
// Stan: mapowanie "YYYY-MM-DD" -> liczba ofert w tym dniu, lista dni w zakresie
let dateSliderState = {
    enabled: false,
    days: [],            // posortowana tablica Date (północ) od najstarszego do najnowszego
    countsPerDay: {},    // klucz "YYYY-MM-DD" -> liczba ofert z first_seen tego dnia
    selectedIndex: -1    // indeks aktualnie wybranego dnia w days[]
};

// Filtr daty zniknięcia (last_seen nieaktywnych ofert)
let goneSliderState = {
    enabled: false,
    days: [],            // posortowana tablica Date last_seen nieaktywnych
    countsPerDay: {},    // "YYYY-MM-DD" -> liczba ofert które zniknęły tego dnia
    selectedIndex: -1
};

function dayKey(date) {
    // Format klucza "YYYY-MM-DD" niezależny od strefy
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function formatDayPL(date) {
    const d = String(date.getDate()).padStart(2, '0');
    const m = String(date.getMonth() + 1).padStart(2, '0');
    return `${d}.${m}.${date.getFullYear()}`;
}

// Warstwy uczelni
let universityLayers = {};
const universities = {
    kul: {
        name: "KUL",
        fullName: "Katolicki Uniwersytet Lubelski",
        color: "#1e88e5",
        locations: [
            { name: "Kampus Główny", lat: 51.2475, lng: 22.5450, radius: 120 },
            { name: "Konstantynów (Medyczny)", lat: 51.2382, lng: 22.5014, radius: 140 },
            { name: "Biblioteka", lat: 51.2438, lng: 22.5538, radius: 70 },
            { name: "Collegium Iuridicum", lat: 51.2494, lng: 22.5543, radius: 60 },
            { name: "Akademik Idzi", lat: 51.2505, lng: 22.5605, radius: 50 }
        ]
    },
    umcs: {
        name: "UMCS",
        fullName: "Uniwersytet Marii Curie-Skłodowskiej",
        color: "#43a047",
        locations: [
            { name: "Rektorat", lat: 51.2455, lng: 22.5409, radius: 100 },
            { name: "Biblioteka Główna", lat: 51.2464, lng: 22.5411, radius: 70 },
            { name: "Wydz. Ekonomiczny", lat: 51.2456, lng: 22.5408, radius: 80 },
            { name: "Wydz. Prawa", lat: 51.2454, lng: 22.5408, radius: 80 },
            { name: "Wydz. Mat-Fiz-Inf", lat: 51.2458, lng: 22.5422, radius: 90 },
            { name: "Wydz. Chemii", lat: 51.2447, lng: 22.5424, radius: 80 },
            { name: "Wydz. Filozofii", lat: 51.2452, lng: 22.5412, radius: 70 },
            { name: "Wydz. Pedagogiki", lat: 51.2466, lng: 22.5259, radius: 80 },
            { name: "Wydz. Artystyczny", lat: 51.2480, lng: 22.5222, radius: 70 },
            { name: "Wydz. Politologii", lat: 51.2470, lng: 22.5243, radius: 80 },
            { name: "Wydz. Nauk o Ziemi", lat: 51.2478, lng: 22.5235, radius: 70 },
            { name: "Miasteczko Akad.", lat: 51.2466, lng: 22.5336, radius: 150 }
        ]
    },
    politechnika: {
        name: "Politechnika",
        fullName: "Politechnika Lubelska",
        color: "#ff5722",
        locations: [
            { name: "Wydz. Budownictwa", lat: 51.2354, lng: 22.5480, radius: 80 },
            { name: "Wydz. Zarządzania", lat: 51.2347, lng: 22.5484, radius: 70 },
            { name: "Wydz. Mechaniczny", lat: 51.2369, lng: 22.5501, radius: 90 },
            { name: "Wydz. Elektrotechniki", lat: 51.2368, lng: 22.5488, radius: 80 },
            { name: "Wydz. Inż. Środowiska", lat: 51.2346, lng: 22.5478, radius: 70 },
            { name: "Wydz. Matematyki", lat: 51.2350, lng: 22.5489, radius: 60 },
            { name: "Centrum Innowacji", lat: 51.2362, lng: 22.5512, radius: 70 }
        ]
    },
    wspa: {
        name: "WSPA",
        fullName: "Wyższa Szkoła Przedsiębiorczości i Administracji",
        color: "#9c27b0",
        locations: [
            { name: "Kampus WSPA", lat: 51.2701, lng: 22.5695, radius: 100 }
        ]
    },
    up: {
        name: "UP",
        fullName: "Uniwersytet Przyrodniczy",
        color: "#009688",
        locations: [
            { name: "Rektorat", lat: 51.2437, lng: 22.5401, radius: 90 },
            { name: "Biblioteka Główna", lat: 51.2435, lng: 22.5414, radius: 60 },
            { name: "Wydz. Weterynarii", lat: 51.2444, lng: 22.5435, radius: 80 },
            { name: "Klinika Weteryn.", lat: 51.2414, lng: 22.5424, radius: 90 },
            { name: "Centrum Innowacji", lat: 51.2408, lng: 22.5450, radius: 70 },
            { name: "Wydz. Inż. Produkcji", lat: 51.2438, lng: 22.5404, radius: 70 },
            { name: "Wydz. Żywności", lat: 51.2493, lng: 22.5110, radius: 90 },
            { name: "Felin (Doświadcz.)", lat: 51.2271, lng: 22.6350, radius: 150 }
        ]
    },
    umed: {
        name: "UM",
        fullName: "Uniwersytet Medyczny",
        color: "#e91e63",
        locations: [
            { name: "Rektorat", lat: 51.2482, lng: 22.5488, radius: 80 },
            { name: "Collegium Medicum", lat: 51.2496, lng: 22.5594, radius: 70 },
            { name: "Collegium Maximum", lat: 51.2487, lng: 22.5620, radius: 60 },
            { name: "Szpital SPSK1", lat: 51.2507, lng: 22.5626, radius: 100 },
            { name: "Collegium Universum", lat: 51.2593, lng: 22.5681, radius: 90 },
            { name: "Centrum Symulacji", lat: 51.2611, lng: 22.5642, radius: 70 },
            { name: "Pharmaceuticum", lat: 51.2618, lng: 22.5636, radius: 60 },
            { name: "Szpital Dziecięcy", lat: 51.2605, lng: 22.5607, radius: 100 }
        ]
    },
    awp: {
        name: "AWP",
        fullName: "Akademia Wincentego Pola",
        color: "#ff9800",
        locations: [
            { name: "Kampus AWP", lat: 51.2700, lng: 22.5572, radius: 100 }
        ]
    },
    ansim: {
        name: "ANSiM",
        fullName: "Akademia Nauk Społecznych i Medycznych",
        color: "#795548",
        locations: [
            { name: "Kampus ANSiM", lat: 51.2403, lng: 22.5700, radius: 90 }
        ]
    }
};

// Inicjalizacja mapy
function initMap() {
    // Centrum Lublina
    map = L.map('map').setView([51.2465, 22.5684], 13);
    
    // Tile layer (OpenStreetMap)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);
    
    // Dodaj warstwy do mapy
    markerLayers.active.addTo(map);
    markerLayers.activeApprox.addTo(map); // domyślnie włączone
    markerLayers.firm.addTo(map);          // firmy domyślnie włączone
    markerLayers.addrArchival.addTo(map);  // archiwalne adresy domyślnie widoczne
    // markerLayers.inactive / inactiveApprox NIE dodajemy - domyślnie wyłączone
    
    // Tworzenie warstw uczelni
    createUniversityLayers();
}

// Wczytanie danych
async function loadData() {
    try {
        // Użyj absolutnej ścieżki dla GitHub Pages
        const baseUrl = window.location.pathname.includes('/SONAR-POKOJOWY/') 
            ? '/SONAR-POKOJOWY/data.json' 
            : '/data.json';
        
        // Próba 1: Z cache-busting
        const timestamp = new Date().getTime();
        const urlWithCache = `${baseUrl}?v=${timestamp}`;
        
        let response = await fetch(urlWithCache);
        
        // Jeśli 404, spróbuj bez cache-busting
        if (!response.ok) {
            console.warn('⚠️ Fetch z cache-busting nie udał się, próbuję bez...');
            response = await fetch(baseUrl);
        }
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const text = await response.text();
        mapData = JSON.parse(text);
        
        console.log(`✅ Załadowano ${mapData.markers?.length || 0} markerów`);
        
        updateScanInfo();
        createPriceRangeFilters();
        await createMarkers();  // async batch - czekamy aż wszystkie markery będą gotowe
        renderArchivalPins();  // archiwalne pinezki poprzednich adresów (po zmianie adresu)
        updateStats();  // Wywołaj PO createMarkers(), żeby allMarkers był wypełniony
        initDateSlider();  // Suwak dni - wymaga wypełnionego allMarkers
        initGoneSlider(); // Suwak daty zniknięcia
        setupEventListeners();
        filterMarkers();  // ✅ Przefiltruj markery zgodnie z początkowymi stanami checkboxów
        buildFirmProfilesTree();  // Drzewo profili firmowych w sidebarze

        // NOWE: jeśli URL ma ?offer=ID, pokaż wskazany marker
        focusOfferFromUrl();

        console.log('🎉 Mapa gotowa!');
        
    } catch (error) {
        console.error('❌ Błąd wczytywania danych:', error);
        alert('Nie udało się wczytać danych mapy. Sprawdź czy plik data.json istnieje.\n\nBłąd: ' + error.message);
    }
}

// Obliczanie statystyk dla widocznych ofert (po filtrowaniu)
function calculateFilteredStats() {
    // Pobierz ustawienia filtrów
    const showActive = document.getElementById('layer-active').checked;
    const showInactive = document.getElementById('layer-inactive').checked;
    const showActiveApprox = document.getElementById('layer-active-approx')?.checked ?? false;
    const showInactiveApprox = document.getElementById('layer-inactive-approx')?.checked ?? false;
    const showFirm = document.getElementById('layer-firm')?.checked ?? true;
    const showFirmInactive = document.getElementById('layer-firm-inactive')?.checked ?? false;

    // Filtr czasowy
    const timeFilter = document.getElementById('time-filter').value;
    const now = new Date();
    let cutoffDate = null;
    
    if (timeFilter !== 'all') {
        const daysAgo = parseInt(timeFilter);
        cutoffDate = new Date(now.getTime() - (daysAgo * 24 * 60 * 60 * 1000));
    }
    
    // Zakresy cenowe - wspólne dla obu warstw
    const selectedRanges = Array.from(document.querySelectorAll('.price-range-filter:checked'))
        .map(cb => cb.dataset.range);
    
    // Wyszukiwanie
    const searchTerm = document.getElementById('search-input').value.toLowerCase();
    
    // Funkcja pomocnicza sprawdzająca czy oferta spełnia kryteria czasowe
    function passesTimeFilter(offer) {
        if (!cutoffDate) return true;
        
        // Użycie wspólnego helpera parsePolishDate (linia 5)
        // parsePolishDate zwraca null przy błędzie - uwzględniamy ofertę (zachowane zachowanie)
        const offerDate = parsePolishDate(offer.first_seen);
        if (!offerDate) return true;
        return offerDate >= cutoffDate;
    }
    
    // Zbierz wszystkie widoczne oferty (aktywne + nieaktywne razem)
    const visibleOffers = [];
    
    allMarkers.forEach(item => {
        // Sprawdź filtr warstwy - osobne checkboxy dla exact i approx i firm
        if (item.isFirmOffer && item.isActive) {
            if (!showFirm) return;
        } else if (item.isFirmOffer && !item.isActive) {
            if (!showFirmInactive) return;
        } else if (item.isApprox) {
            if (item.isActive && !showActiveApprox) return;
            if (!item.isActive && !showInactiveApprox) return;
        } else {
            if (item.isActive && !showActive) return;
            if (!item.isActive && !showInactive) return;
        }

        // Sprawdź czy marker jest widoczny (jest w odpowiedniej warstwie na mapie)
        let isOnMap;
        if (item.isFirmOffer && item.isActive) {
            isOnMap = markerLayers.firm.hasLayer(item.marker);
        } else if (item.isFirmOffer && !item.isActive) {
            isOnMap = markerLayers.firmInactive.hasLayer(item.marker);
        } else if (item.isApprox) {
            isOnMap = (item.isActive && markerLayers.activeApprox.hasLayer(item.marker)) ||
                      (!item.isActive && markerLayers.inactiveApprox.hasLayer(item.marker));
        } else {
            isOnMap = (item.isActive && markerLayers.active.hasLayer(item.marker)) ||
                      (!item.isActive && markerLayers.inactive.hasLayer(item.marker));
        }
        
        if (!isOnMap) return;
        
        // Sprawdź wyszukiwanie
        if (searchTerm && !item.address.toLowerCase().includes(searchTerm)) return;
        
        // Sprawdź zakres cenowy (wspólny dla obu warstw)
        if (!selectedRanges.includes(item.priceRange)) return;
        
        // Przetwórz każdą ofertę z tego markera
        item.offers.forEach(offer => {
            // Sprawdź filtr czasowy
            if (!passesTimeFilter(offer)) return;

            // Sprawdź filtr dzienny (suwak dni)
            if (!passesDaySliderFilter(parsePolishDate(offer.first_seen))) return;
            if (!passesGoneSliderFilter(offer)) return;

            // Oferta przeszła wszystkie filtry - dodaj do listy
            visibleOffers.push(offer);
        });
    });
    
    // Oblicz statystyki
    if (visibleOffers.length === 0) {
        return null; // Brak ofert
    }
    
    const prices = visibleOffers.map(o => o.price);
    return {
        count: visibleOffers.length,
        avg: Math.round(prices.reduce((a, b) => a + b, 0) / prices.length),
        min: Math.min(...prices),
        max: Math.max(...prices)
    };
}

// Aktualizacja wyświetlanych statystyk
function updateStats() {
    const stats = calculateFilteredStats();
    
    if (stats) {
        document.getElementById('visible-count').textContent = stats.count;
        document.getElementById('avg-price').textContent = stats.avg + ' zł';
        document.getElementById('min-price').textContent = stats.min + ' zł';
        document.getElementById('max-price').textContent = stats.max + ' zł';
    } else {
        // Brak ofert spełniających kryteria
        document.getElementById('visible-count').textContent = '-';
        document.getElementById('avg-price').textContent = '-';
        document.getElementById('min-price').textContent = '-';
        document.getElementById('max-price').textContent = '-';
    }
}

// Aktualizacja informacji o skanach
function updateScanInfo() {
    document.getElementById('last-scan').textContent = mapData.scan_info.last;
    document.getElementById('next-scan').textContent = mapData.scan_info.next;
}

// Tworzenie checkboxów dla zakresów cenowych
function createPriceRangeFilters() {
    const container = document.getElementById('price-range-filters');
    
    Object.entries(mapData.price_ranges).forEach(([key, range]) => {
        const label = document.createElement('label');
        label.innerHTML = `
            <input type="checkbox" class="price-range-filter" data-range="${key}" checked>
            <span style="display:inline-block; width:15px; height:15px; background:${range.color}; margin-right:5px; vertical-align:middle; border-radius:50%;"></span>
            <span class="price-range-label-text">${range.label}</span>
            <span id="price-range-count-${key}" class="badge-count">(0)</span>
        `;
        container.appendChild(label);
    });
}

// Tworzenie markerów (async batch - wsady po 100 z requestIdleCallback,
// żeby nie blokować głównego wątku przy ~600+ markerach)
function createMarkers() {
    return new Promise(resolve => {
        allMarkers = [];
        const markers = mapData.markers;
        const BATCH_SIZE = 100;
        let i = 0;

        function processBatch() {
            const end = Math.min(i + BATCH_SIZE, markers.length);
            for (; i < end; i++) {
                const marker = markers[i];
                const coords = marker.coords;
                const address = marker.address;
                const offers = marker.offers;

                // Grupuj oferty: aktywne osobno, nieaktywne osobno
                const activeOffers = offers.filter(o => o.active);
                const inactiveOffers = offers.filter(o => !o.active);

                // Twórz marker dla aktywnych (jeśli są)
                if (activeOffers.length > 0) {
                    createMarkerGroup(coords, address, activeOffers, true);
                }

                // Twórz marker dla nieaktywnych (jeśli są)
                if (inactiveOffers.length > 0) {
                    createMarkerGroup(coords, address, inactiveOffers, false);
                }
            }

            if (i < markers.length) {
                // Następny wsad w bezczynnym slocie - strona pozostaje responsywna
                if (window.requestIdleCallback) {
                    requestIdleCallback(processBatch, { timeout: 50 });
                } else {
                    setTimeout(processBatch, 0);
                }
            } else {
                resolve();
            }
        }

        processBatch();
    });
}

// Tworzenie grupy markerów (rozsunięcie dla tego samego adresu)

function buildActiveCircle() {
    return '<circle cx="20" cy="18" r="8" fill="white" opacity="0.9"/>';
}

function createMarkerGroup(baseCoords, address, offers, isActive) {
    // Oblicz offset bazowy - ~10 metrów między markerami (0.0001 stopnia ≈ 10m)
    const baseOffset = 0.0001;
    
    offers.forEach((offer, index) => {
        // Pobierz kolor z zakresu cenowego oferty
        const offerPriceRange = offer.price_range;
        const color = mapData.price_ranges[offerPriceRange]?.color || '#808080';
        
        // Oblicz offset w kole (rozsunięcie)
        // Każda oferta na innym kącie, promień rośnie z ilością ofert
        const totalOffers = offers.length;
        
        let offsetLat = 0;
        let offsetLon = 0;
        
        if (totalOffers > 1) {
            const angle = (index / totalOffers) * 2 * Math.PI;
            // Promień zależny od pozycji - spirala
            const radius = baseOffset * (0.5 + index * 0.5);
            offsetLat = Math.cos(angle) * radius;
            offsetLon = Math.sin(angle) * radius * 1.5; // 1.5x bo longitude jest "węższa"
        }
        
        // Konwersja z obiektu {lat, lon} na tablicę [lat, lon] dla Leaflet
        const coords = [
            baseCoords.lat + offsetLat,
            baseCoords.lon + offsetLon
        ];
        
        // Tooltip (pojawia się przy hover)
        const price = offer.price;
        const tooltipText = `${address} - ${price} zł`;
        
        // Sprawdź czy oferta jest nowa (z ostatniego skanu)
        const isNew = offer.is_new === true;
        
        // Sprawdź czy cena się zmieniła
        const hasPriceChange = offer.previous_price && offer.price_trend;
        const priceUp = offer.price_trend === 'up';
        const priceDown = offer.price_trend === 'down';
        
        // DEBUG: Log ofert ze zmianą ceny
        if (hasPriceChange) {
            console.log(`💲 Zmiana ceny: ${address} | ${offer.previous_price} → ${offer.price} (${offer.price_trend})`);
        }
        
        // Ikona markera - pinezka z kolorem
        // Jeśli nowa - czerwona obwódka; firmowa - złota; inaczej - biała
        const isFirmOffer = offer.is_firm_offer === true;
        const offerType = offer.offer_type || null;
        const offerCity = (offer.city || '').toLowerCase();
        const strokeColor = isNew ? '#ff0000' : isFirmOffer ? '#FFD700' : 'white';
        const strokeWidth = isNew ? '3' : isFirmOffer ? '4' : '2';
        const markerColor = color;


        // Czy oferta to "przybliżony adres" (sama ulica bez numeru lub centroid dzielnicy)?
        const isApprox = offer.precision === 'street_only' || offer.precision === 'district';

        // Badge zmiany ceny - ikona dolara ze strzałką
        let priceChangeBadge = '';
        if (hasPriceChange) {
            const badgeColor = priceDown ? '#28a745' : '#dc3545';  // Zielony=spadek, Czerwony=wzrost
            const arrow = priceDown ? '↓' : '↑';
            priceChangeBadge = `
                <div style="
                    position: absolute;
                    top: -8px;
                    right: -8px;
                    background: ${badgeColor};
                    color: white;
                    border-radius: 10px;
                    min-width: 28px;
                    height: 20px;
                    font-size: 11px;
                    font-weight: bold;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                    padding: 0 4px;
                    border: 2px solid white;
                    z-index: 1000;
                ">💲${arrow}</div>
            `;
        }

        // ===== IKONA =====
        // Dwa warianty: pinezka (precision: exact) lub kwadrat (precision: street_only).
        // Krzyżyk × dla nieaktywnych: dla pinezki = czarny tekst w białym kole (środek)
        //                            dla kwadratu = biały tekst z cieniem na środku kwadratu
        let icon;
        if (isApprox) {
            // KWADRAT 34x34 z przerywaną obwódką - decyzja 2b
            // Anchor w środku (nie u dołu jak pinezka)
            const squareSize = 34;
            // Krzyżyk × dla nieaktywnych - biały tekst z cieniem (czytelny na każdym kolorze)
            const inactiveCross = !isActive
                ? `<text x="17" y="17" text-anchor="middle" dominant-baseline="central" font-size="22" font-weight="700" fill="white" font-family="-apple-system, sans-serif" style="paint-order: stroke; stroke: rgba(0,0,0,0.5); stroke-width: 2px;">×</text>`
                : '';
            icon = L.divIcon({
                className: 'square-marker',
                html: `
                    <div style="position: relative; width: ${squareSize}px; height: ${squareSize}px;" title="${tooltipText}">
                        <svg width="${squareSize}" height="${squareSize}" viewBox="0 0 ${squareSize} ${squareSize}">
                            <rect x="3" y="3" width="${squareSize - 6}" height="${squareSize - 6}"
                                  fill="${markerColor}"
                                  stroke="${isNew ? '#ff0000' : 'white'}"
                                  stroke-width="3"
                                  stroke-dasharray="4 3"/>
                            ${inactiveCross}
                        </svg>
                        ${isNew && !hasPriceChange ? '<div style="position: absolute; top: -5px; right: -5px; background: #ff0000; color: white; border-radius: 50%; width: 16px; height: 16px; font-size: 10px; font-weight: bold; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 3px rgba(0,0,0,0.3);">N</div>' : ''}
                        ${priceChangeBadge}
                    </div>
                `,
                iconSize: [squareSize, squareSize],
                iconAnchor: [squareSize / 2, squareSize / 2],  // środek
                popupAnchor: [0, -squareSize / 2]
            });
        } else {
            // PINEZKA (standard, precision: exact)
            // Krzyżyk × dla nieaktywnych: czarny tekst w białym kole wewnątrz SVG (zgodnie z mockupem v2)
            const inactiveMarker = !isActive
                ? `<circle cx="20" cy="18" r="9" fill="white"/><text x="20" y="18" text-anchor="middle" dominant-baseline="central" font-size="16" font-weight="700" fill="#1f2937" font-family="-apple-system, sans-serif">×</text>`
                : buildActiveCircle();
            icon = L.divIcon({
                className: 'pin-marker',
                html: `
                    <div style="position: relative; width: 40px; height: 50px;" title="${tooltipText}">
                        <svg width="40" height="50" viewBox="0 0 40 50">
                            <path d="M20 0 C9 0 0 9 0 20 C0 35 20 50 20 50 C20 50 40 35 40 20 C40 9 31 0 20 0 Z"
                                  fill="${markerColor}"
                                  stroke="${strokeColor}"
                                  stroke-width="${strokeWidth}"/>
                            ${inactiveMarker}
                        </svg>
                        ${isNew && !hasPriceChange ? '<div style="position: absolute; top: -5px; right: -5px; background: #ff0000; color: white; border-radius: 50%; width: 16px; height: 16px; font-size: 10px; font-weight: bold; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 3px rgba(0,0,0,0.3);">N</div>' : ''}
                        ${priceChangeBadge}
                    </div>
                `,
                iconSize: [40, 50],
                iconAnchor: [20, 50],
                popupAnchor: [0, -50]
            });
        }

        // Popup content - LAZY: HTML generowany dopiero przy kliknięciu (oszczędność ~620 niepotrzebnych konstrukcji przy starcie)

        // Tworzenie markera z tooltip
        const markerObj = L.marker(coords, {
            icon: icon,
            title: tooltipText  // Tooltip przy hover
        })
            .bindPopup(() => createPopupContent(address, [offer]), { maxWidth: 400 });

        // Dodaj do odpowiedniej warstwy
        // Priorytet: firma > approx > exact
        // FIX 2026-05-23: WSZYSTKIE oferty firmowe (isFirmOffer && isActive) idą
        // do markerLayers.firm, niezależnie od offer_type/offer_city. Wcześniej
        // gdy offer_type=null lub city != 'lublin', marker lądował w markerLayers.active
        // ale w allMarkers miał flagę isFirmOffer=true → filterMarkers próbował go
        // usunąć z markerLayers.firm (gdzie go nie było) i marker zostawał widoczny
        // mimo odznaczonej warstwy "Firmy / Agencje".
        // isFirmLublin nadal liczone do wykluczania z innych liczników (np. layer-count-active).
        const isFirmLublin = isFirmOffer && isActive
            && (offerType === 'pokoj' || offerType === 'mieszkanie')
            && (!offerCity || offerCity === 'lublin');

        if (isFirmOffer && isActive) {
            markerObj.addTo(markerLayers.firm);
        } else if (isFirmOffer && !isActive) {
            markerObj.addTo(markerLayers.firmInactive);
        } else if (isApprox) {
            markerObj.addTo(isActive ? markerLayers.activeApprox : markerLayers.inactiveApprox);
        } else if (isActive) {
            markerObj.addTo(markerLayers.active);
        } else {
            markerObj.addTo(markerLayers.inactive);
        }

        // Zapisz referencję - używamy price_range z oferty
        allMarkers.push({
            marker: markerObj,
            address: address,
            offers: [offer],
            priceRange: offerPriceRange,  // ✅ Zakres cenowy z oferty
            isActive: isActive,
            isApprox: isApprox,  // NOWE: czy to przybliżona lokalizacja (street_only)
            primaryTag: offer.tags ? offer.tags.primary : 'pokoj',  // B1: Tag główny
            // Flagi oznaczeń pinezek (do filtrowania legendy)
            isNew: isNew,
            priceDown: hasPriceChange && priceDown,
            priceUp: hasPriceChange && priceUp,
            isFirmOffer: isFirmOffer,
            isFirmLublin: isFirmLublin,
            offerType: offerType,
            offerCity: offerCity,
            originalOffer: offer,  // referencja do pełnych danych oferty
            // Daty do filtrowania zakresem dat
            firstSeenDate: parsePolishDate(offer.first_seen),
            priceChangedAtDate: parsePolishDate(offer.price_changed_at)
        });
    });
    
    // B1: Aktualizuj liczniki tagów
    updateTagCounts();
    // Aktualizuj liczniki oznaczeń (legenda)
    updateBadgeCounts();
    // Aktualizuj liczniki w zakresach cenowych (legenda)
    updatePriceRangeCounts();
}

// Archiwalna pinezka poprzedniego adresu (po zmianie adresu) — fioletowa kropla, ↩
function makeArchivalMapIcon() {
    return L.divIcon({
        className: 'pin-marker',
        html: `<div style="position:relative;width:34px;height:44px">
            <svg width="34" height="44" viewBox="0 0 40 50" style="filter:drop-shadow(0 1px 2px rgba(0,0,0,.25))">
                <path d="M20 0 C9 0 0 9 0 20 C0 35 20 50 20 50 C20 50 40 35 40 20 C40 9 31 0 20 0 Z"
                      fill="#a855f7" fill-opacity="0.25" stroke="#7c3aed" stroke-width="3" stroke-dasharray="4 3"/>
                <circle cx="20" cy="18" r="9" fill="white"/>
                <text x="20" y="19" text-anchor="middle" dominant-baseline="central" font-size="16" fill="#7c3aed">↩</text>
            </svg></div>`,
        iconSize: [34, 44], iconAnchor: [17, 44], popupAnchor: [0, -44]
    });
}

// Rejestr archiwalnych pinów: "offerId:vIndex" → marker (do nawigacji z popupu oferty)
let archivalRegistry = {};

// Renderuje archiwalne pinezki w miejscach POPRZEDNICH adresów ofert, które zmieniły adres
function renderArchivalPins() {
    markerLayers.addrArchival.clearLayers();
    archivalRegistry = {};
    let count = 0;
    (mapData.markers || []).forEach(m => {
        (m.offers || []).forEach(offer => {
            const vers = offer.address_versions || [];
            if (!(offer.address_change_count > 0) || vers.length < 2) return;
            const offerId = offer.id;
            const curAddr = vers[0].address || '—';
            vers.forEach((v, i) => {
                if (i === 0 || !v.lat || !v.lon) return;  // [0] = bieżąca
                const prices = v.prices || [];
                const lastPrice = prices.length ? prices[prices.length - 1] + ' zł' : '—';
                const popup = `<div class="offer-popup"><div style="font-size:11px;color:#7c3aed;font-weight:700;margin-bottom:4px">↩ POPRZEDNI ADRES</div>`
                    + `<div style="font-weight:700;font-size:15px;color:#212529">${escapeHtml(v.address || '—')}</div>`
                    + `<div style="font-size:11px;color:#94a3b8;margin:3px 0 6px">${escapeHtml(v.first_seen || '')} → ${escapeHtml(v.last_seen || '')} · 🔄${v.refresh_count || 0} ♻${v.reactivation_count || 0}</div>`
                    + `<div style="font-size:16px;font-weight:800;color:#667eea">${escapeHtml(lastPrice)}</div>`
                    + `<div style="font-size:11px;color:#64748b;margin-top:6px">oferta przeniesiona do: <b>${escapeHtml(curAddr)}</b></div>`
                    + `<button data-oid="${escapeHtml(offerId)}" onclick="focusCurrentOffer(this.dataset.oid)" style="margin-top:10px;width:100%;padding:8px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer">→ Przejdź do aktualnego ogłoszenia</button>`
                    + `</div>`;
                const am = L.marker([v.lat, v.lon], { icon: makeArchivalMapIcon(), zIndexOffset: -200 })
                    .bindPopup(popup, { maxWidth: 320 });
                am.addTo(markerLayers.addrArchival);
                archivalRegistry[offerId + ':' + i] = am;
                count++;
            });
        });
    });
    const badge = document.getElementById('layer-count-addr-archival');
    if (badge) badge.textContent = '(' + count + ')';
}

// Przełącznik warstwy "Przeniesione" (archiwalne adresy)
function onArchivalLayerToggle() {
    const show = document.getElementById('layer-addr-archival')?.checked ?? true;
    if (show) {
        if (!map.hasLayer(markerLayers.addrArchival)) markerLayers.addrArchival.addTo(map);
    } else {
        map.removeLayer(markerLayers.addrArchival);
    }
}

// Upewnia się, że marker jest widoczny na mapie (gdy jego warstwa była schowana)
function ensureMarkerVisible(marker) {
    if (map.hasLayer(marker)) return;
    for (const layer of Object.values(markerLayers)) {
        if (layer.hasLayer && layer.hasLayer(marker)) {
            if (!map.hasLayer(layer)) layer.addTo(map);
            return;
        }
    }
    marker.addTo(map);  // fallback — marker bez przypisanej warstwy
}

// Nawigacja: z archiwalnego pinu → do aktualnego ogłoszenia
function focusCurrentOffer(offerId) {
    const entry = allMarkers.find(m => m.originalOffer && m.originalOffer.id === offerId);
    if (!entry) return;
    map.closePopup();
    ensureMarkerVisible(entry.marker);
    map.flyTo(entry.marker.getLatLng(), 17, { duration: 1.0 });
    setTimeout(() => entry.marker.openPopup(), 700);
}

// Nawigacja: z ogłoszenia z historią → do konkretnego archiwalnego (fioletowego) pinu
function focusArchivalPin(offerId, vIndex) {
    const am = archivalRegistry[offerId + ':' + vIndex];
    if (!am) return;
    // Upewnij się, że warstwa jest widoczna
    const cb = document.getElementById('layer-addr-archival');
    if (cb && !cb.checked) { cb.checked = true; onArchivalLayerToggle(); }
    if (!map.hasLayer(markerLayers.addrArchival)) markerLayers.addrArchival.addTo(map);
    map.closePopup();
    map.flyTo(am.getLatLng(), 17, { duration: 1.0 });
    setTimeout(() => am.openPopup(), 700);
}

// Tworzenie HTML popup
function createPopupContent(address, offers) {
    let html = `<div class="offer-popup">`;
    html += `<h3>📍 ${escapeHtml(address)}</h3>`;

    offers.forEach(offer => {
        const isActive = offer.active;

        html += `<div class="offer-item ${isActive ? '' : 'inactive'}" data-offer-id="${escapeHtml(offer.id)}">`;
        
        if (!isActive) {
            html += `<div class="inactive-badge">❌ Nieaktywne</div>`;
        }
        
        // Cena - NOWE: wyświetlanie zmiany ceny
        if (offer.previous_price && offer.price_trend) {
            const priceDiff = offer.price - offer.previous_price;
            const trendIcon = offer.price_trend === 'down' ? '📉' : '📈';
            const trendColor = offer.price_trend === 'down' ? '#28a745' : '#dc3545';
            const trendSign = offer.price_trend === 'down' ? '' : '+';
            
            html += `<div class="offer-price ${isActive ? '' : 'inactive'}">`;
            html += `💰 <strong style="font-size: 1.2em;">${offer.price} zł</strong>`;
            html += `<span style="color: ${trendColor}; font-weight: bold; margin-left: 8px;">`;
            html += `${trendIcon} ${trendSign}${priceDiff} zł</span>`;
            html += `</div>`;
            
            // Poprzednia cena
            html += `<div class="previous-price" style="color: #888; font-size: 0.9em; margin-top: 2px;">`;
            html += `<s>Poprzednio: ${offer.previous_price} zł</s>`;
            if (offer.price_changed_at) {
                html += ` <span style="font-size: 0.85em;">(zmiana: ${escapeHtml(offer.price_changed_at)})</span>`;
            }
            html += `</div>`;
        } else {
            html += `<div class="offer-price ${isActive ? '' : 'inactive'}">💰 ${offer.price} zł</div>`;
        }
        
        // Historia cen (pełna)
        if (offer.price_history && offer.price_history.length > 1) {
            const history = offer.price_history.map(p => p + ' zł').join(' → ');
            html += `<div class="price-history" style="color: #666; font-size: 0.85em; margin-top: 4px;">📊 Historia: ${history}</div>`;
        }

        // Historia adresu (zmiana adresu tego samego listingu OLX) — styl 2: mini-blok
        if (offer.address_change_count > 0 && (offer.address_versions || []).length > 1) {
            const vers = offer.address_versions;
            html += `<div class="addr-history">`;
            html += `<div class="addr-history-h">📜 Historia adresu — ${vers.length} wersje <span style="font-weight:400;opacity:.7">(kliknij poprzedni → pokaż na mapie)</span></div>`;
            vers.forEach((v, i) => {
                const dot = v.current ? '#16a34a' : '#cbd5e1';
                const range = v.current ? ('od ' + (v.first_seen || '') + (v.active ? ' · aktywna' : ''))
                                        : ((v.first_seen || '') + ' → ' + (v.last_seen || ''));
                const prices = v.prices || [];
                const priceStr = prices.length
                    ? (prices.length > 1 ? prices[0] + '→' + prices[prices.length - 1] : prices[prices.length - 1]) + ' zł'
                    : '—';
                const clickable = !v.current && v.lat && v.lon;
                const attrs = clickable
                    ? ` class="addr-history-r clickable" data-oid="${escapeHtml(offer.id)}" onclick="focusArchivalPin(this.dataset.oid, ${i})" title="Pokaż poprzedni adres na mapie"`
                    : ` class="addr-history-r"`;
                html += `<div${attrs}>`
                    + `<span class="ah-l"><span style="color:${dot}">●</span> <span class="${v.current ? 'ah-new' : 'ah-old'}">${escapeHtml(v.address || '—')}</span>`
                    + `<span class="ah-d">${escapeHtml(range)} · 🔄${v.refresh_count || 0} ♻${v.reactivation_count || 0}${clickable ? ' · ↩ pokaż' : ''}</span></span>`
                    + `<span class="ah-p ${v.current ? '' : 'old'}">${priceStr}</span></div>`;
            });
            html += `</div>`;
        }

        // Media info
        html += `<div class="media-info">Skład: ${escapeHtml(offer.media_info)}</div>`;

        // B1: Tag oferty
        if (offer.tags && offer.tags.primary) {
            const tagIcons = { pokoj: '🛏️', kawalerka: '🏠', mieszkanie: '🏢' };
            const tagLabels = { pokoj: 'Pokój', kawalerka: 'Kawalerka', mieszkanie: 'Mieszkanie' };
            const tagColors = { pokoj: '#3b82f6', kawalerka: '#10b981', mieszkanie: '#8b5cf6' };
            
            const primary = offer.tags.primary;
            html += `<div class="offer-tag" style="margin: 8px 0; display: inline-block; padding: 4px 10px; background: ${tagColors[primary]}22; border: 1px solid ${tagColors[primary]}; border-radius: 12px; font-size: 12px; color: ${tagColors[primary]}; font-weight: 600;">`;
            html += `${tagIcons[primary] || ''} ${tagLabels[primary] || primary}`;
            if (offer.tags.secondary && offer.tags.secondary.length > 0) {
                html += ` <span style="opacity: 0.7;">+ ${offer.tags.secondary.map(t => tagLabels[t] || t).join(', ')}</span>`;
            }
            html += `</div>`;
        }
        
        // Profil firmowy (jeśli ogłoszenie pochodzi z monitorowanego profilu)
        if (offer.profile_name && mapData.tracked_profiles) {
            const profileKey = Object.keys(mapData.tracked_profiles).find(k =>
                mapData.tracked_profiles[k].name === offer.profile_name
            ) || Object.keys(mapData.tracked_profiles).find(k => k === offer.profile_name);
            if (profileKey) {
                const prof = mapData.tracked_profiles[profileKey];
                html += `<div style="margin: 6px 0 4px; padding: 5px 9px; background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.35); border-radius: 6px; font-size: 11px; display: flex; align-items: center; gap: 6px;">`;
                html += `<span style="color: #d97706; font-weight: 700;">🏢 ${escapeHtml(prof.name)}</span>`;
                html += `<a href="profile_tracker.html#${escapeHtml(profileKey)}" style="color: #3b82f6; text-decoration: none; margin-left: auto; font-size: 10px;">Zobacz profil →</a>`;
                html += `</div>`;
            }
        }

        // Link
        html += `<a href="${safeOfferUrl(offer.url)}" target="_blank" class="offer-link">🔗 Otwórz ogłoszenie</a>`;

        // Opis - z funkcją zwijania/rozwijania
        const maxChars = 100; // Maksymalna długość podglądu (~1-2 linie)
        const needsTruncate = offer.description.length > maxChars;

        if (needsTruncate) {
            // ID oferty trafia do atrybutu id i onclick — tylko znaki bezpieczne
            const uniqueId = `desc-${String(offer.id).replace(/[^\w-]/g, '')}`;
            const shortDescription = offer.description.substring(0, maxChars);

            html += `
                <div class="offer-description">
                    <div id="${uniqueId}-short">
                        📝 ${escapeHtml(shortDescription)}...
                        <br><a href="javascript:void(0)" onclick="toggleDescription('${uniqueId}')" class="show-more-link">▼ Pokaż całość</a>
                    </div>
                    <div id="${uniqueId}-full" style="display: none;">
                        📝 ${escapeHtml(offer.description)}
                        <br><a href="javascript:void(0)" onclick="toggleDescription('${uniqueId}')" class="show-more-link">▲ Zwiń</a>
                    </div>
                </div>
            `;
        } else {
            html += `<div class="offer-description">📝 ${escapeHtml(offer.description)}</div>`;
        }

        // Daty
        if (isActive) {
            html += `<div class="offer-dates">`;
            html += `📅 Dodano: ${escapeHtml(offer.first_seen)}<br>`;
            html += `📅 Ostatnio widziane: ${escapeHtml(offer.last_seen)}<br>`;
            html += `⏱️ Dni aktywności: ${offer.days_active}`;
            html += `</div>`;
        } else {
            html += `<div class="offer-dates">`;
            html += `📅 Aktywna przez: ${offer.days_active} dni<br>`;
            html += `📅 Nieaktywna od: ${escapeHtml(offer.last_seen)}<br>`;
            html += `💰 Ostatnia cena: ${offer.price} zł`;
            html += `</div>`;
        }
        
        html += `</div>`;
    });
    
    html += `</div>`;
    return html;
}

// Debounced wariant filterMarkers dla zdarzeń ciągłych (pola cen, suwaki)
const filterMarkersDebounced = debounce(() => filterMarkers(), 250);

// Filtrowanie markerów
// ── DRZEWO PROFILI FIRMOWYCH ─────────────────────────────────────────
function buildFirmProfilesTree() {
    const tree = document.getElementById('firm-profiles-tree');
    if (!tree || !mapData?.tracked_profiles) return;

    const profiles = mapData.tracked_profiles;

    // Policz oferty per profil z allMarkers
    const profileCounts = {};
    Object.keys(profiles).forEach(k => { profileCounts[k] = 0; });

    allMarkers.forEach(item => {
        if (!item.isFirmOffer || !item.isActive) return;
        const offer = item.originalOffer || {};
        if (!offer.profile_name) return;
        // Znajdź klucz profilu po nazwie
        const key = Object.keys(profiles).find(k =>
            profiles[k].name === offer.profile_name || k === offer.profile_name
        );
        if (key) profileCounts[key] = (profileCounts[key] || 0) + 1;
    });

    tree.innerHTML = Object.entries(profiles).map(([key, prof]) => {
        const count = profileCounts[key] || 0;
        return `<label style="display:flex;align-items:center;gap:5px;padding:3px 6px;border-radius:4px;cursor:pointer;font-size:12px;background:rgba(255,215,0,0.05);border:1px solid rgba(255,215,0,0.2);">
            <input type="checkbox" id="firm-profile-${key}" checked
                onchange="onFirmProfileToggle()"
                style="accent-color:#d97706;cursor:pointer;">
            <span style="flex:1;color:#92400e;font-weight:500">${prof.name}</span>
            <span id="firm-count-${key}" style="background:rgba(255,215,0,0.15);color:#b45309;border-radius:10px;padding:0px 6px;font-size:10px;font-weight:600;">${count}</span>
        </label>`;
    }).join('');
}

function updateFirmProfileCounts() {
    if (!mapData?.tracked_profiles) return;
    const profiles = mapData.tracked_profiles;

    const profileCounts = {};
    Object.keys(profiles).forEach(k => { profileCounts[k] = 0; });

    allMarkers.forEach(item => {
        if (!item.isFirmOffer || !item.isActive) return;
        if (!markerLayers.firm.hasLayer(item.marker)) return;
        const offer = item.originalOffer || {};
        if (!offer.profile_name) return;
        const key = Object.keys(profiles).find(k =>
            profiles[k].name === offer.profile_name || k === offer.profile_name
        );
        if (key) profileCounts[key] = (profileCounts[key] || 0) + 1;
    });

    Object.keys(profiles).forEach(key => {
        const el = document.getElementById('firm-count-' + key);
        if (el) el.textContent = profileCounts[key] || 0;
    });
}

function getEnabledProfiles() {
    if (!mapData?.tracked_profiles) return null; // null = all
    const enabled = new Set();
    let anyUnchecked = false;
    Object.keys(mapData.tracked_profiles).forEach(key => {
        const cb = document.getElementById('firm-profile-' + key);
        if (cb && cb.checked) enabled.add(key);
        else anyUnchecked = true;
    });
    return anyUnchecked ? enabled : null; // null = wszystkie zaznaczone = brak filtra
}

function getProfileKeyForOffer(profileName) {
    if (!mapData?.tracked_profiles || !profileName) return null;
    return Object.keys(mapData.tracked_profiles).find(k =>
        mapData.tracked_profiles[k].name === profileName || k === profileName
    ) || null;
}

function onFirmLayerToggle() {
    const showFirm = document.getElementById('layer-firm')?.checked ?? true;
    // Synchronizuj checkboxy profili
    if (mapData?.tracked_profiles) {
        Object.keys(mapData.tracked_profiles).forEach(key => {
            const cb = document.getElementById('firm-profile-' + key);
            if (cb) cb.checked = showFirm;
        });
    }
    filterMarkers();
}

function onFirmProfileToggle() {
    // Jeśli wszystkie profile odznaczone → odznacz główny checkbox
    // Jeśli przynajmniej jeden zaznaczony → zaznacz główny
    const enabled = getEnabledProfiles();
    const mainCb = document.getElementById('layer-firm');
    if (mainCb) {
        mainCb.checked = enabled === null || enabled.size > 0;
    }
    filterMarkers();
}

function filterMarkers() {
    // Pobierz ustawienia filtrów
    const showActive = document.getElementById('layer-active').checked;
    const showInactive = document.getElementById('layer-inactive').checked;

    // Dodaj/usuń warstwę nieaktywnych z mapy (analogicznie do toggleInactiveApproxLayer)
    if (showInactive && !map.hasLayer(markerLayers.inactive)) {
        markerLayers.inactive.addTo(map);
    } else if (!showInactive && map.hasLayer(markerLayers.inactive)) {
        map.removeLayer(markerLayers.inactive);
    }
    const showFirmInactive = document.getElementById('layer-firm-inactive')?.checked ?? false;
    if (showFirmInactive && !map.hasLayer(markerLayers.firmInactive)) {
        markerLayers.firmInactive.addTo(map);
    } else if (!showFirmInactive && map.hasLayer(markerLayers.firmInactive)) {
        map.removeLayer(markerLayers.firmInactive);
    }
    const showActiveApprox = document.getElementById('layer-active-approx')?.checked ?? false;
    const showInactiveApprox = document.getElementById('layer-inactive-approx')?.checked ?? false;
    
    // B1: Filtry tagów
    const showPokoj = document.getElementById('layer-tag-pokoj')?.checked ?? true;
    const showKawalerka = document.getElementById('layer-tag-kawalerka')?.checked ?? true;
    const showMieszkanie = document.getElementById('layer-tag-mieszkanie')?.checked ?? true;
    
    // Filtry oznaczeń pinezek (legenda)
    const showPriceDown = document.getElementById('badge-filter-price-down')?.checked ?? true;
    const showPriceUp = document.getElementById('badge-filter-price-up')?.checked ?? true;
    const showNew = document.getElementById('badge-filter-new')?.checked ?? true;
    const showUnchanged = document.getElementById('badge-filter-unchanged')?.checked ?? true;
    
    // NOWY: Filtr czasowy
    const timeFilter = document.getElementById('time-filter').value;
    const now = new Date();
    let cutoffDate = null;
    
    if (timeFilter !== 'all') {
        const daysAgo = parseInt(timeFilter);
        cutoffDate = new Date(now.getTime() - (daysAgo * 24 * 60 * 60 * 1000));
    }
    
    // Zakresy cenowe - wspólne dla obu warstw
    const selectedRanges = Array.from(document.querySelectorAll('.price-range-filter:checked'))
        .map(cb => cb.dataset.range);
    
    // Precyzyjne filtry cen - wspólne dla obu warstw
    const priceMin = parseInt(document.getElementById('price-min').value) || 0;
    const priceMax = parseInt(document.getElementById('price-max').value) || 999999;
    
    // Wyszukiwanie
    const searchTerm = document.getElementById('search-input').value.toLowerCase();
    
    // Liczniki warstw - liczone PO wszystkich filtrach OPRÓCZ checkboxa danej warstwy
    // Odpowiadają na pytanie: "ile ofert pojawi się na mapie, gdy włączę tę warstwę?"
    const layerCounts = {
        active: 0,
        inactive: 0,
        activeApprox: 0,
        inactiveApprox: 0,
        firm: 0,
        firmInactive: 0
    };
    
    // Filtruj markery
    allMarkers.forEach(item => {
        let visible = true;
        
        // Filtr aktywne/nieaktywne - osobne checkboxy dla exact i approx
        // (sprawdzane PÓŹNIEJ - na końcu, po policzeniu warstw)
        const showFirm = document.getElementById('layer-firm')?.checked ?? true;
        const enabledProfiles = getEnabledProfiles(); // null = wszystkie
        let passesLayerFilter = true;
        if (item.isFirmOffer && item.isActive) {
            if (!showFirm) {
                passesLayerFilter = false;
            } else if (enabledProfiles !== null) {
                const offerProfile = getProfileKeyForOffer(item.originalOffer?.profile_name);
                passesLayerFilter = offerProfile ? enabledProfiles.has(offerProfile) : false;
            }
        } else if (item.isFirmOffer && !item.isActive) {
            passesLayerFilter = showFirmInactive;
        } else if (item.isApprox) {
            if (item.isActive) passesLayerFilter = showActiveApprox;
            else passesLayerFilter = showInactiveApprox;
        } else {
            if (item.isActive) passesLayerFilter = showActive;
            else passesLayerFilter = showInactive;
        }
        
        // B1: Filtr tagów
        if (visible) {
            const tag = item.primaryTag || 'pokoj';
            if (tag === 'pokoj' && !showPokoj) visible = false;
            if (tag === 'kawalerka' && !showKawalerka) visible = false;
            if (tag === 'mieszkanie' && !showMieszkanie) visible = false;
        }
        
        // Filtr oznaczeń pinezek (OR) - oferty bez badge'a filtrowane przez "Bez zmian"
        if (visible) {
            const hasAnyBadge = item.isNew || item.priceDown || item.priceUp;
            if (hasAnyBadge) {
                // Pokaż, jeśli CHOĆ JEDNO z oznaczeń pinezki jest zaznaczone w legendzie
                const passes =
                    (item.isNew && showNew) ||
                    (item.priceDown && showPriceDown) ||
                    (item.priceUp && showPriceUp);
                if (!passes) visible = false;
            } else {
                // Oferta bez żadnego badge'a - widoczna tylko gdy "Bez zmian" jest zaznaczone
                if (!showUnchanged) visible = false;
            }
        }
        
        // Filtr czasowy - uwzględnia first_seen ORAZ price_changed_at
        // Oferta przechodzi gdy KTÓRAKOLWIEK z dat mieści się w zakresie
        if (visible && cutoffDate) {
            const firstSeenOk = item.firstSeenDate && item.firstSeenDate >= cutoffDate;
            const priceChangedOk = item.priceChangedAtDate && item.priceChangedAtDate >= cutoffDate;
            if (!firstSeenOk && !priceChangedOk) {
                visible = false;
            }
        }

        // Filtr dzienny (suwak dni) - oferta widoczna jeśli first_seen = wybrany dzień
        if (visible && !passesDaySliderFilter(item.firstSeenDate)) {
            visible = false;
        }

        // Filtr daty zniknięcia — dotyczy nieaktywnych ofert
        if (visible && !item.isActive && goneSliderState.enabled) {
            const lastSeenDate = item.originalOffer ? parsePolishDate(item.originalOffer.last_seen) : null;
            if (!passesGoneSliderFilter(item.originalOffer || {})) {
                visible = false;
            }
        }
        
        // Filtr zakresów cenowych - wspólny dla obu warstw
        // Jeśli selectedRanges jest puste (żaden checkbox), pokaż wszystkie
        if (selectedRanges.length > 0 && !selectedRanges.includes(item.priceRange)) {
            visible = false;
        }
        
        // Precyzyjny filtr cen - wspólny dla obu warstw
        const price = item.offers[0].price;
        if (price < priceMin || price > priceMax) {
            visible = false;
        }
        
        // Wyszukiwanie
        if (searchTerm && !item.address.toLowerCase().includes(searchTerm)) {
            visible = false;
        }
        
        // ZLICZANIE WARSTW: oferta przechodzi wszystkie pozostałe filtry,
        // więc liczymy ją w odpowiedniej warstwie (niezależnie od checkboxa warstwy)
        if (visible) {
            if (item.isFirmOffer && item.isActive) {
                layerCounts.firm++;
            } else if (item.isFirmOffer && !item.isActive) {
                layerCounts.firmInactive++;
            } else if (item.isApprox) {
                if (item.isActive) layerCounts.activeApprox++;
                else layerCounts.inactiveApprox++;
            } else if (item.isActive) {
                layerCounts.active++;
            } else {
                layerCounts.inactive++;
            }
        }
        
        // Zastosuj filtr warstwy DOPIERO TERAZ (po policzeniu)
        if (!passesLayerFilter) visible = false;
        
        // Pokaż/ukryj marker
        // Priorytet warstw: firma > approx > exact (zgodnie z createMarkerGroup)
        if (visible) {
            if (item.isFirmOffer && item.isActive) {
                markerLayers.firm.addLayer(item.marker);
            } else if (item.isFirmOffer && !item.isActive) {
                markerLayers.firmInactive.addLayer(item.marker);
            } else if (item.isApprox) {
                (item.isActive ? markerLayers.activeApprox : markerLayers.inactiveApprox).addLayer(item.marker);
            } else if (item.isActive) {
                markerLayers.active.addLayer(item.marker);
            } else {
                markerLayers.inactive.addLayer(item.marker);
            }
        } else {
            if (item.isFirmOffer && item.isActive) {
                markerLayers.firm.removeLayer(item.marker);
            } else if (item.isFirmOffer && !item.isActive) {
                markerLayers.firmInactive.removeLayer(item.marker);
            } else if (item.isApprox) {
                (item.isActive ? markerLayers.activeApprox : markerLayers.inactiveApprox).removeLayer(item.marker);
            } else if (item.isActive) {
                markerLayers.active.removeLayer(item.marker);
            } else {
                markerLayers.inactive.removeLayer(item.marker);
            }
        }
    });
    
    // Aktualizuj liczniki warstw w DOM
    const setLayerCount = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = `(${value})`;
    };
    setLayerCount('layer-count-active', layerCounts.active);
    setLayerCount('layer-count-inactive', layerCounts.inactive);
    setLayerCount('layer-count-active-approx', layerCounts.activeApprox);
    setLayerCount('layer-count-inactive-approx', layerCounts.inactiveApprox);
    setLayerCount('layer-count-firm', layerCounts.firm);
    setLayerCount('layer-count-firm-inactive', layerCounts.firmInactive);
    
    // Przelicz i zaktualizuj statystyki po filtrowaniu
    updateStats();
    // Zaktualizuj liczniki oznaczeń (respektują aktualny zakres dat)
    updateBadgeCounts();
    // Zaktualizuj liczniki w zakresach cenowych (respektują wszystkie filtry oprócz samych zakresów)
    updatePriceRangeCounts();
}

// Wyszukiwanie z zoomem
function searchAndZoom() {
    const searchTerm = document.getElementById('search-input').value.toLowerCase();
    
    if (!searchTerm) {
        filterMarkers();
        return;
    }
    
    // Znajdź pierwsze dopasowanie (uwzględnij właściwy checkbox warstwy)
    const match = allMarkers.find(item => {
        if (!item.address.toLowerCase().includes(searchTerm)) return false;
        let layerCheckbox;
        if (item.isApprox) {
            layerCheckbox = item.isActive
                ? document.getElementById('layer-active-approx')
                : document.getElementById('layer-inactive-approx');
        } else {
            layerCheckbox = item.isActive
                ? document.getElementById('layer-active')
                : document.getElementById('layer-inactive');
        }
        return layerCheckbox && layerCheckbox.checked;
    });
    
    if (match) {
        const coords = match.marker.getLatLng();
        map.setView(coords, 17);
        match.marker.openPopup();
    }
    
    filterMarkers();
}

// ===== Inicjalizacja suwaka dni =====
// Buduje zakres dni od najstarszego first_seen do DZISIAJ,
// zlicza oferty per dzień i renderuje mini-histogram.
function initDateSlider() {
    const slider = document.getElementById('date-slider');
    const enableCb = document.getElementById('date-filter-enable');
    const control = document.getElementById('date-slider-control');
    const minLabel = document.getElementById('date-slider-min');
    const maxLabel = document.getElementById('date-slider-max');
    const histogram = document.getElementById('date-slider-histogram');

    if (!slider || !enableCb) return;

    // 1. Wyłoń najstarszy first_seen
    let earliest = null;
    allMarkers.forEach(item => {
        if (item.firstSeenDate && (!earliest || item.firstSeenDate < earliest)) {
            earliest = item.firstSeenDate;
        }
    });

    if (!earliest) {
        // Brak danych z datami - wyłącz filtr
        enableCb.disabled = true;
        minLabel.textContent = '—';
        maxLabel.textContent = '—';
        return;
    }

    // 2. Zbuduj tablicę dni: od północy earliest do północy dzisiaj (włącznie)
    const startDay = new Date(earliest.getFullYear(), earliest.getMonth(), earliest.getDate());
    const now = new Date();
    const endDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    const days = [];
    const cursor = new Date(startDay);
    while (cursor <= endDay) {
        days.push(new Date(cursor));
        cursor.setDate(cursor.getDate() + 1);
    }

    // 3. Zlicz oferty per dzień
    const counts = {};
    days.forEach(d => { counts[dayKey(d)] = 0; });
    allMarkers.forEach(item => {
        item.offers.forEach(offer => {
            const fs = parsePolishDate(offer.first_seen);
            if (!fs) return;
            const key = dayKey(fs);
            if (key in counts) {
                counts[key]++;
            }
        });
    });

    dateSliderState.days = days;
    dateSliderState.countsPerDay = counts;
    dateSliderState.selectedIndex = days.length - 1; // start na ostatnim dniu

    // 4. Skonfiguruj suwak
    slider.min = 0;
    slider.max = days.length - 1;
    slider.value = days.length - 1;

    minLabel.textContent = formatDayPL(days[0]);
    maxLabel.textContent = formatDayPL(days[days.length - 1]);

    // 5. Zbuduj histogram
    histogram.innerHTML = '';
    const maxCount = Math.max(1, ...Object.values(counts));

    days.forEach((d, i) => {
        const c = counts[dayKey(d)];
        const bar = document.createElement('div');
        bar.className = 'bar' + (c === 0 ? ' empty' : '');
        const pct = c === 0 ? 8 : Math.max(15, Math.round((c / maxCount) * 100));
        bar.style.height = pct + '%';
        bar.dataset.index = i;
        bar.title = `${formatDayPL(d)}: ${c} ofert`;
        bar.addEventListener('click', () => {
            if (!dateSliderState.enabled) return;
            slider.value = i;
            dateSliderState.selectedIndex = i;
            updateDateSliderReadout();
            filterMarkers();
        });
        histogram.appendChild(bar);
    });

    // 6. Listenery (tylko raz)
    enableCb.addEventListener('change', () => {
        dateSliderState.enabled = enableCb.checked;
        if (enableCb.checked) {
            control.classList.add('enabled');
            slider.disabled = false;
            histogram.classList.remove('disabled');
            // Użyj aktualnej pozycji suwaka
            dateSliderState.selectedIndex = parseInt(slider.value);
        } else {
            control.classList.remove('enabled');
            slider.disabled = true;
            histogram.classList.add('disabled');
        }
        updateDateSliderReadout();
        filterMarkers();
    });

    slider.addEventListener('input', () => {
        dateSliderState.selectedIndex = parseInt(slider.value);
        updateDateSliderReadout();   // odczyt na żywo
        filterMarkersDebounced();    // przebudowa markerów po puszczeniu suwaka
    });

    // 7. Stan początkowy - wyłączony
    control.classList.remove('enabled');
    histogram.classList.add('disabled');
    updateDateSliderReadout();
}

// Aktualizuje wyświetlaną datę i licznik po zmianie suwaka / checkboxa
function updateDateSliderReadout() {
    const dateEl = document.getElementById('date-slider-current');
    const countEl = document.getElementById('date-slider-count');
    const histogram = document.getElementById('date-slider-histogram');
    if (!dateEl || !countEl) return;

    const idx = dateSliderState.selectedIndex;
    const days = dateSliderState.days;

    // Podświetl aktywny słupek
    if (histogram) {
        Array.from(histogram.children).forEach((bar, i) => {
            bar.classList.toggle('active', dateSliderState.enabled && i === idx);
        });
    }

    if (!dateSliderState.enabled || idx < 0 || idx >= days.length) {
        dateEl.textContent = '—';
        dateEl.classList.remove('active');
        countEl.textContent = '— ofert';
        return;
    }

    const day = days[idx];
    const count = dateSliderState.countsPerDay[dayKey(day)] || 0;
    dateEl.textContent = formatDayPL(day);
    dateEl.classList.add('active');
    countEl.textContent = `${count} ${pluralOffers(count)}`;
}

// Polska deklinacja dla "oferta"
function pluralOffers(n) {
    if (n === 1) return 'oferta';
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'oferty';
    return 'ofert';
}

// Czy oferta/marker pasuje do wybranego dnia w suwaku dni
// Używane wspólnie przez filterMarkers, calculateFilteredStats, updateBadgeCounts
function passesDaySliderFilter(firstSeenDate) {
    if (!dateSliderState.enabled) return true;
    if (!firstSeenDate) return false;
    const idx = dateSliderState.selectedIndex;
    const days = dateSliderState.days;
    if (idx < 0 || idx >= days.length) return true;
    const selected = days[idx];
    return firstSeenDate.getFullYear() === selected.getFullYear() &&
           firstSeenDate.getMonth() === selected.getMonth() &&
           firstSeenDate.getDate() === selected.getDate();
}

// Sprawdź czy oferta (nieaktywna) przeszła przez filtr daty zniknięcia
function passesGoneSliderFilter(offer) {
    if (!goneSliderState.enabled) return true;
    // Filtr dotyczy tylko nieaktywnych
    if (offer.active) return true;
    const lastSeenDate = parsePolishDate(offer.last_seen);
    if (!lastSeenDate) return false;
    const idx = goneSliderState.selectedIndex;
    const days = goneSliderState.days;
    if (idx < 0 || idx >= days.length) return true;
    const selected = days[idx];
    return lastSeenDate.getFullYear() === selected.getFullYear() &&
           lastSeenDate.getMonth() === selected.getMonth() &&
           lastSeenDate.getDate() === selected.getDate();
}

// Inicjalizacja suwaka daty zniknięcia
function initGoneSlider() {
    const enableCb = document.getElementById('date-gone-enable');
    const slider = document.getElementById('date-gone-slider');
    if (!enableCb || !slider) return;

    // Zbierz daty last_seen nieaktywnych ofert
    const countsPerDay = {};
    allMarkers.forEach(item => {
        if (item.isActive) return;
        const offer = item.originalOffer || {};
        const d = parsePolishDate(offer.last_seen);
        if (!d) return;
        const k = dayKey(d);
        countsPerDay[k] = (countsPerDay[k] || 0) + 1;
    });

    if (Object.keys(countsPerDay).length === 0) return;

    // Zakres: od najstarszego do najnowszego last_seen
    const sortedKeys = Object.keys(countsPerDay).sort();
    const days = sortedKeys.map(k => {
        const [y, m, d] = k.split('-').map(Number);
        return new Date(y, m - 1, d);
    });

    goneSliderState.days = days;
    goneSliderState.countsPerDay = countsPerDay;
    goneSliderState.selectedIndex = days.length - 1;

    slider.min = 0;
    slider.max = days.length - 1;
    slider.value = days.length - 1;
    slider.disabled = false;

    document.getElementById('date-gone-min').textContent = sortedKeys[0].slice(5).replace('-', '.');
    document.getElementById('date-gone-max').textContent = sortedKeys[sortedKeys.length - 1].slice(5).replace('-', '.');

    updateGoneSliderReadout();

    // Event listeners
    enableCb.addEventListener('change', () => {
        goneSliderState.enabled = enableCb.checked;
        document.getElementById('date-gone-control').style.opacity = enableCb.checked ? '1' : '0.4';
        filterMarkers();
        updateGoneSliderReadout();
    });

    slider.addEventListener('input', () => {
        goneSliderState.selectedIndex = parseInt(slider.value);
        updateGoneSliderReadout();   // odczyt na żywo
        filterMarkersDebounced();    // przebudowa markerów po puszczeniu suwaka
    });

    document.getElementById('date-gone-control').style.opacity = '0.4';
    buildGoneHistogram();
}

function updateGoneSliderReadout() {
    const idx = goneSliderState.selectedIndex;
    const days = goneSliderState.days;
    const dateEl = document.getElementById('date-gone-current');
    const countEl = document.getElementById('date-gone-count');
    if (!dateEl || !countEl) return;
    if (!goneSliderState.enabled || idx < 0 || idx >= days.length) {
        dateEl.textContent = '—';
        countEl.textContent = '— ofert';
        return;
    }
    const day = days[idx];
    const k = dayKey(day);
    const count = goneSliderState.countsPerDay[k] || 0;
    const dd = String(day.getDate()).padStart(2, '0');
    const mm = String(day.getMonth() + 1).padStart(2, '0');
    const dayNames = ['niedziela', 'poniedziałek', 'wtorek', 'środa', 'czwartek', 'piątek', 'sobota'];
    const dayName = dayNames[day.getDay()];
    dateEl.innerHTML = `${dd}.${mm}.${day.getFullYear()}<br><span style="font-size:0.8em;opacity:0.7;">${dayName}</span>`;
    countEl.textContent = `${count} ofert`;
    buildGoneHistogram();
}

function buildGoneHistogram() {
    const container = document.getElementById('date-gone-histogram');
    if (!container) return;
    const days = goneSliderState.days;
    if (!days.length) return;
    const max = Math.max(...days.map(d => goneSliderState.countsPerDay[dayKey(d)] || 0));
    const idx = goneSliderState.selectedIndex;
    container.innerHTML = days.map((d, i) => {
        const k = dayKey(d);
        const cnt = goneSliderState.countsPerDay[k] || 0;
        const h = max > 0 ? Math.max(2, Math.round((cnt / max) * 20)) : 2;
        return `<div class="histogram-bar${i === idx && goneSliderState.enabled ? ' active' : ''}"
            style="height:${h}px" title="${k}: ${cnt} ofert"></div>`;
    }).join('');
}

// Setup event listeners
function setupEventListeners() {
    // Warstwy
    document.getElementById('layer-active').addEventListener('change', filterMarkers);
    document.getElementById('layer-inactive').addEventListener('change', filterMarkers);
    document.getElementById('layer-active-approx').addEventListener('change', toggleActiveApproxLayer);
    document.getElementById('layer-inactive-approx').addEventListener('change', toggleInactiveApproxLayer);
    
    // NOWY: Filtr czasowy
    document.getElementById('time-filter').addEventListener('change', filterMarkers);
    
    // Zakresy cenowe - wspólne dla obu warstw
    document.querySelectorAll('.price-range-filter').forEach(cb => {
        cb.addEventListener('change', filterMarkers);
    });
    
    // Filtry oznaczeń pinezek (legenda)
    ['badge-filter-price-down', 'badge-filter-price-up', 'badge-filter-new', 'badge-filter-unchanged']
        .forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', filterMarkers);
        });
    
    // Precyzyjne filtry cen - wspólne dla obu warstw (debounce: zdarzenia na każdy znak)
    document.getElementById('price-min').addEventListener('input', filterMarkersDebounced);
    document.getElementById('price-max').addEventListener('input', filterMarkersDebounced);

    // Wyszukiwanie (debounce: nie skanuj markerów na każdy keystroke)
    document.getElementById('search-input').addEventListener('input', debounce(searchAndZoom, 300));
    
    // Zoom mapy - aktualizuj rozsunięcie markerów
    map.on('zoomend', function() {
        // TODO: Rekonstruuj markery z nowym offsetem
        // Na razie zostawiam jak jest (offset statyczny)
    });
}

// Inicjalizacja po załadowaniu DOM
document.addEventListener('DOMContentLoaded', function() {
    initMap();
    loadData().then(() => {
        // Obsługa linku z ostatnie.html: #goto:lat,lon
        const hash = window.location.hash;
        const m = hash.match(/^#goto:([\d.]+),([\d.]+)$/);
        if (m) {
            const lat = parseFloat(m[1]);
            const lon = parseFloat(m[2]);
            map.setView([lat, lon], 17);
            // Pulsujący marker wskazujący lokalizację
            const pulse = L.circleMarker([lat, lon], {
                radius: 18,
                color: '#f97316',
                fillColor: '#f97316',
                fillOpacity: 0.25,
                weight: 3,
                opacity: 0.9
            }).addTo(map);
            // Usuń po 4 sekundach
            setTimeout(() => map.removeLayer(pulse), 4000);
            // Wyczyść hash bez przeładowania
            history.replaceState(null, '', window.location.pathname);
        }
    });
});

// NOWA funkcja: Przełączanie widoku opisu (pokaż całość / zwiń)
function toggleDescription(uniqueId) {
    const shortDiv = document.getElementById(`${uniqueId}-short`);
    const fullDiv = document.getElementById(`${uniqueId}-full`);
    
    if (shortDiv && fullDiv) {
        if (shortDiv.style.display === 'none') {
            // Pokazuj krótką wersję
            shortDiv.style.display = 'block';
            fullDiv.style.display = 'none';
        } else {
            // Pokazuj pełną wersję
            shortDiv.style.display = 'none';
            fullDiv.style.display = 'block';
        }
    }
}

// Włączanie/wyłączanie warstwy "Przybliżone aktywne"
function toggleActiveApproxLayer() {
    const isChecked = document.getElementById('layer-active-approx').checked;
    if (isChecked) {
        markerLayers.activeApprox.addTo(map);
        console.log('✅ Warstwa "Przybliżone aktywne" włączona');
    } else {
        map.removeLayer(markerLayers.activeApprox);
        console.log('⚠️ Warstwa "Przybliżone aktywne" wyłączona');
    }
    // Przelicz markery aby uwzględnić zmianę widoczności warstwy
    filterMarkers();
}

// Włączanie/wyłączanie warstwy "Przybliżone nieaktywne"
function toggleInactiveApproxLayer() {
    const isChecked = document.getElementById('layer-inactive-approx').checked;
    if (isChecked) {
        markerLayers.inactiveApprox.addTo(map);
        console.log('✅ Warstwa "Przybliżone nieaktywne" włączona');
    } else {
        map.removeLayer(markerLayers.inactiveApprox);
        console.log('⚠️ Warstwa "Przybliżone nieaktywne" wyłączona');
    }
    filterMarkers();
}

// ========== WARSTWY UCZELNI ==========

// Tworzenie warstw uczelni
function createUniversityLayers() {
    Object.entries(universities).forEach(([key, uni]) => {
        const layerGroup = L.layerGroup();
        
        uni.locations.forEach(loc => {
            // Okrąg
            const circle = L.circle([loc.lat, loc.lng], {
                radius: loc.radius,
                color: uni.color,
                weight: 2,
                fillColor: uni.color,
                fillOpacity: 0.4
            });
            
            circle.bindPopup(`
                <div style="text-align: center; min-width: 150px;">
                    <strong style="color: ${uni.color}; font-size: 14px;">${uni.name}</strong><br>
                    <span style="font-size: 12px;">${loc.name}</span><br>
                    <span style="font-size: 10px; color: #888;">${uni.fullName}</span><br>
                    <span style="font-size: 10px; color: #666;">Promień: ${loc.radius}m</span>
                </div>
            `);
            
            layerGroup.addLayer(circle);
            
            // Etykieta
            const label = L.marker([loc.lat, loc.lng], {
                icon: L.divIcon({
                    className: 'uni-label',
                    html: `<span style="color: ${uni.color};">${loc.name}</span>`,
                    iconSize: [90, 14],
                    iconAnchor: [45, 7]
                })
            });
            layerGroup.addLayer(label);
        });
        
        // Domyślnie warstwy uczelni są WYŁĄCZONE
        universityLayers[key] = layerGroup;
    });
    
    console.log('🎓 Warstwy uczelni utworzone');
}

// Przełączanie warstwy uczelni
function toggleUniversityLayer(key) {
    const checkbox = document.getElementById(`layer-uni-${key}`);
    if (!checkbox) return;
    
    if (checkbox.checked) {
        universityLayers[key].addTo(map);
    } else {
        map.removeLayer(universityLayers[key]);
    }
}

// Zwijanie/rozwijanie sekcji uczelni
function toggleUniSection() {
    const list = document.getElementById('uni-list');
    const icon = document.getElementById('uni-toggle-icon');
    if (list.style.display === 'none') {
        list.style.display = 'block';
        icon.textContent = '▼';
    } else {
        list.style.display = 'none';
        icon.textContent = '▶';
    }
}

// B1: Aktualizacja liczników tagów
function updateTagCounts() {
    const counts = { pokoj: 0, kawalerka: 0, mieszkanie: 0 };
    
    allMarkers.forEach(item => {
        if (item.isActive) {
            const tag = item.primaryTag || 'pokoj';
            if (counts[tag] !== undefined) {
                counts[tag]++;
            }
        }
    });
    
    // Aktualizuj wyświetlane liczniki
    const pokojEl = document.getElementById('tag-count-pokoj');
    const kawalerkaEl = document.getElementById('tag-count-kawalerka');
    const mieszkanieEl = document.getElementById('tag-count-mieszkanie');
    
    if (pokojEl) pokojEl.textContent = `(${counts.pokoj})`;
    if (kawalerkaEl) kawalerkaEl.textContent = `(${counts.kawalerka})`;
    if (mieszkanieEl) mieszkanieEl.textContent = `(${counts.mieszkanie})`;
}

// Aktualizacja liczników w zakresach cenowych (legenda)
// Respektuje WSZYSTKIE aktywne filtry OPRÓCZ samych zakresów cenowych
// (analogicznie jak updateBadgeCounts dla pinezek)
function updatePriceRangeCounts() {
    if (!mapData || !mapData.price_ranges) return;
    
    // Pobierz aktualne ustawienia filtrów (oprócz zakresów cenowych)
    const showActive = document.getElementById('layer-active')?.checked ?? true;
    const showInactive = document.getElementById('layer-inactive')?.checked ?? true;
    const showActiveApprox = document.getElementById('layer-active-approx')?.checked ?? false;
    const showInactiveApprox = document.getElementById('layer-inactive-approx')?.checked ?? false;
    
    const showPokoj = document.getElementById('layer-tag-pokoj')?.checked ?? true;
    const showKawalerka = document.getElementById('layer-tag-kawalerka')?.checked ?? true;
    const showMieszkanie = document.getElementById('layer-tag-mieszkanie')?.checked ?? true;
    
    const showPriceDown = document.getElementById('badge-filter-price-down')?.checked ?? true;
    const showPriceUp = document.getElementById('badge-filter-price-up')?.checked ?? true;
    const showNew = document.getElementById('badge-filter-new')?.checked ?? true;
    const showUnchanged = document.getElementById('badge-filter-unchanged')?.checked ?? true;
    
    const timeFilter = document.getElementById('time-filter')?.value || 'all';
    let cutoffDate = null;
    if (timeFilter !== 'all') {
        const daysAgo = parseInt(timeFilter);
        cutoffDate = new Date(Date.now() - (daysAgo * 24 * 60 * 60 * 1000));
    }
    
    const priceMin = parseInt(document.getElementById('price-min')?.value) || 0;
    const priceMax = parseInt(document.getElementById('price-max')?.value) || 999999;
    
    const searchTerm = (document.getElementById('search-input')?.value || '').toLowerCase();
    
    // Inicjalizuj liczniki dla każdego zakresu
    const counts = {};
    Object.keys(mapData.price_ranges).forEach(key => { counts[key] = 0; });
    
    // Iteruj po wszystkich ofertach (allMarkers = oferty 1:1)
    allMarkers.forEach(item => {
        // Filtr aktywne/nieaktywne - osobne checkboxy dla exact i approx
        if (item.isApprox) {
            if (item.isActive && !showActiveApprox) return;
            if (!item.isActive && !showInactiveApprox) return;
        } else {
            if (item.isActive && !showActive) return;
            if (!item.isActive && !showInactive) return;
        }
        
        // Filtr tagów
        const tag = item.primaryTag || 'pokoj';
        if (tag === 'pokoj' && !showPokoj) return;
        if (tag === 'kawalerka' && !showKawalerka) return;
        if (tag === 'mieszkanie' && !showMieszkanie) return;
        
        // Filtr oznaczeń pinezek (OR) - oferty bez badge'a filtrowane przez "Bez zmian"
        const hasAnyBadge = item.isNew || item.priceDown || item.priceUp;
        if (hasAnyBadge) {
            const passes =
                (item.isNew && showNew) ||
                (item.priceDown && showPriceDown) ||
                (item.priceUp && showPriceUp);
            if (!passes) return;
        } else {
            if (!showUnchanged) return;
        }
        
        // Filtr czasowy (first_seen LUB price_changed_at)
        if (cutoffDate) {
            const firstSeenOk = item.firstSeenDate && item.firstSeenDate >= cutoffDate;
            const priceChangedOk = item.priceChangedAtDate && item.priceChangedAtDate >= cutoffDate;
            if (!firstSeenOk && !priceChangedOk) return;
        }
        
        // Filtr suwaka dni
        if (!passesDaySliderFilter(item.firstSeenDate)) return;
        
        // Precyzyjny filtr cen
        const price = item.offers[0].price;
        if (price < priceMin || price > priceMax) return;
        
        // Wyszukiwanie
        if (searchTerm && !item.address.toLowerCase().includes(searchTerm)) return;
        
        // CELOWO POMIJAMY filtr selectedRanges - bo to jego liczniki właśnie wyliczamy
        
        // Zlicz po zakresie cenowym
        if (item.priceRange && counts.hasOwnProperty(item.priceRange)) {
            counts[item.priceRange]++;
        }
    });
    
    // Zaktualizuj UI
    Object.entries(counts).forEach(([key, value]) => {
        const el = document.getElementById(`price-range-count-${key}`);
        if (el) el.textContent = `(${value})`;
    });
}

// B1: Filtrowanie po tagach - alias do filterMarkers
function filterByTags() {
    filterMarkers();
}

// Aktualizacja liczników oznaczeń pinezek (legenda)
// Każdy licznik pokazuje: "ile ofert pojawi się na mapie, gdy włączę ten checkbox?"
// Respektuje WSZYSTKIE aktywne filtry OPRÓCZ checkboxa danej kategorii.
function updateBadgeCounts() {
    if (!allMarkers || allMarkers.length === 0) {
        ['badge-count-price-down', 'badge-count-price-up', 'badge-count-new', 'badge-count-unchanged']
            .forEach(id => {
                const el = document.getElementById(id);
                if (el) el.textContent = '(0)';
            });
        return;
    }
    
    // Pobierz aktualne ustawienia wszystkich filtrów (oprócz samych checkboxów legendy)
    const showActive = document.getElementById('layer-active')?.checked ?? true;
    const showInactive = document.getElementById('layer-inactive')?.checked ?? true;
    const showActiveApprox = document.getElementById('layer-active-approx')?.checked ?? false;
    const showInactiveApprox = document.getElementById('layer-inactive-approx')?.checked ?? false;
    
    const showPokoj = document.getElementById('layer-tag-pokoj')?.checked ?? true;
    const showKawalerka = document.getElementById('layer-tag-kawalerka')?.checked ?? true;
    const showMieszkanie = document.getElementById('layer-tag-mieszkanie')?.checked ?? true;
    
    const timeFilter = document.getElementById('time-filter')?.value || 'all';
    let cutoffDate = null;
    if (timeFilter !== 'all') {
        const daysAgo = parseInt(timeFilter);
        cutoffDate = new Date(Date.now() - (daysAgo * 24 * 60 * 60 * 1000));
    }
    
    const selectedRanges = Array.from(document.querySelectorAll('.price-range-filter:checked'))
        .map(cb => cb.dataset.range);
    
    const priceMin = parseInt(document.getElementById('price-min')?.value) || 0;
    const priceMax = parseInt(document.getElementById('price-max')?.value) || 999999;
    
    const searchTerm = (document.getElementById('search-input')?.value || '').toLowerCase();
    
    const counts = { priceDown: 0, priceUp: 0, isNew: 0, unchanged: 0 };
    
    allMarkers.forEach(item => {
        // Filtr aktywne/nieaktywne
        if (item.isApprox) {
            if (item.isActive && !showActiveApprox) return;
            if (!item.isActive && !showInactiveApprox) return;
        } else {
            if (item.isActive && !showActive) return;
            if (!item.isActive && !showInactive) return;
        }
        
        // Filtr tagów
        const tag = item.primaryTag || 'pokoj';
        if (tag === 'pokoj' && !showPokoj) return;
        if (tag === 'kawalerka' && !showKawalerka) return;
        if (tag === 'mieszkanie' && !showMieszkanie) return;
        
        // Filtr czasowy (first_seen LUB price_changed_at)
        if (cutoffDate) {
            const firstSeenOk = item.firstSeenDate && item.firstSeenDate >= cutoffDate;
            const priceChangedOk = item.priceChangedAtDate && item.priceChangedAtDate >= cutoffDate;
            if (!firstSeenOk && !priceChangedOk) return;
        }
        
        // Filtr suwaka dni
        if (!passesDaySliderFilter(item.firstSeenDate)) return;
        
        // Filtr zakresów cenowych
        if (selectedRanges.length > 0 && !selectedRanges.includes(item.priceRange)) return;
        
        // Precyzyjny filtr cen
        const price = item.offers[0].price;
        if (price < priceMin || price > priceMax) return;
        
        // Wyszukiwanie
        if (searchTerm && !item.address.toLowerCase().includes(searchTerm)) return;
        
        // CELOWO POMIJAMY filtry checkboxów legendy - to ich liczniki właśnie wyliczamy
        
        // Zlicz kategorie. Oferta może mieć jednocześnie wiele oznaczeń
        // (np. isNew + priceDown), więc liczona jest w każdej pasującej kategorii.
        // Dla zmian ceny dodatkowo wymagamy, by data zmiany ceny była w zakresie czasowym.
        const priceChangeInRange = !cutoffDate ||
            (item.priceChangedAtDate && item.priceChangedAtDate >= cutoffDate);
        const firstSeenInRange = !cutoffDate ||
            (item.firstSeenDate && item.firstSeenDate >= cutoffDate);
        
        if (item.priceDown && priceChangeInRange) counts.priceDown++;
        if (item.priceUp && priceChangeInRange) counts.priceUp++;
        if (item.isNew && firstSeenInRange) counts.isNew++;
        
        // "Bez zmian" - oferta nie ma żadnego z trzech badge'y
        const hasAnyBadge = item.isNew || item.priceDown || item.priceUp;
        if (!hasAnyBadge) counts.unchanged++;
    });
    
    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = `(${value})`;
    };
    
    setText('badge-count-price-down', counts.priceDown);
    setText('badge-count-price-up', counts.priceUp);
    setText('badge-count-new', counts.isNew);
    setText('badge-count-unchanged', counts.unchanged);
}

// ============================================================
// Linkowanie z innych stron (np. top5.html) — ?offer=ID
// ============================================================
function focusOfferFromUrl() {
    const params = new URLSearchParams(window.location.search);

    // ?loc=LAT,LON — przeniesienie z profile_tracker
    const locParam = params.get('loc');
    if (locParam) {
        const parts = locParam.split(',');
        const lat = parseFloat(parts[0]);
        const lon = parseFloat(parts[1]);
        if (!isNaN(lat) && !isNaN(lon)) {
            map.flyTo([lat, lon], 17, { duration: 1.2 });
            return;
        }
    }

    const targetId = params.get('offer');
    if (!targetId) return;
    
    console.log(`🎯 Szukam markera dla oferty: ${targetId}`);
    
    // Znajdź marker który zawiera ofertę o tym ID
    const found = allMarkers.find(m => 
        m.offers && m.offers.some(o => o.id === targetId)
    );
    
    if (!found) {
        console.warn(`⚠️ Nie znaleziono markera dla oferty: ${targetId}`);
        return;
    }
    
    console.log(`✓ Znaleziono marker: ${found.address} (active=${found.isActive}, approx=${found.isApprox})`);
    
    // KROK 1: Włącz wszystkie checkboxy warstw, tagów, zakresów cenowych
    // żeby żaden filtr nie ukrywał markera
    const layerCheckboxIds = [
        'layer-active', 'layer-inactive', 'layer-active-approx', 'layer-inactive-approx'
    ];
    layerCheckboxIds.forEach(id => {
        const cb = document.getElementById(id);
        if (cb && !cb.checked) {
            cb.checked = true;
            console.log(`  ✓ Włączono: ${id}`);
        }
    });
    
    // Wyłącz filtry tagów/zakresów cenowych żeby nic nie ukrywało
    document.querySelectorAll('.price-range-filter').forEach(cb => {
        if (!cb.checked) cb.checked = true;
    });
    const tagCheckboxIds = ['layer-tag-pokoj', 'layer-tag-kawalerka', 'layer-tag-mieszkanie'];
    tagCheckboxIds.forEach(id => {
        const cb = document.getElementById(id);
        if (cb && !cb.checked) cb.checked = true;
    });
    
    // Wyczyść wyszukiwarkę
    const search = document.getElementById('search-input');
    if (search && search.value) {
        search.value = '';
    }
    
    // Reset zakresów cenowych do pełnego zakresu
    const priceMin = document.getElementById('price-min');
    const priceMax = document.getElementById('price-max');
    if (priceMin) priceMin.value = '';
    if (priceMax) priceMax.value = '';
    
    // Reset filtra czasowego
    const timeFilter = document.getElementById('time-filter');
    if (timeFilter && timeFilter.value !== 'all') {
        timeFilter.value = 'all';
    }
    
    // Wyłącz filtr dat
    const dateEnable = document.getElementById('date-filter-enable');
    if (dateEnable && dateEnable.checked) {
        dateEnable.checked = false;
    }
    
    // KROK 2: Przefiltruj markery z nowymi ustawieniami
    if (typeof filterMarkers === 'function') {
        filterMarkers();
    }
    
    // KROK 3: SAFETY NET — wymuś dodanie markera do swojej warstwy
    // (na wypadek gdyby jakiś filtr go usunął)
    let targetLayer;
    if (found.isApprox && found.isActive) targetLayer = markerLayers.activeApprox;
    else if (found.isApprox) targetLayer = markerLayers.inactiveApprox;
    else if (found.isActive) targetLayer = markerLayers.active;
    else targetLayer = markerLayers.inactive;
    
    if (!targetLayer.hasLayer(found.marker)) {
        targetLayer.addLayer(found.marker);
        console.log('  ✓ Wymuszono dodanie markera do warstwy');
    }
    // Upewnij się że warstwa jest na mapie
    if (!map.hasLayer(targetLayer)) {
        targetLayer.addTo(map);
        console.log('  ✓ Wymuszono dodanie warstwy na mapę');
    }
    
    // KROK 4: Przelot + popup
    const coords = found.marker.getLatLng();
    console.log(`  → Lecę do [${coords.lat}, ${coords.lng}]`);
    map.flyTo(coords, 17, { duration: 1.2 });
    
    setTimeout(() => {
        found.marker.openPopup();
        console.log('  ✓ Popup otwarty');
        
        // Krótka animacja pulsowania ikony
        const iconEl = found.marker._icon;
        if (iconEl) {
            iconEl.style.transition = 'transform 0.4s ease-in-out';
            const originalTransform = iconEl.style.transform || '';
            let pulses = 0;
            const pulse = setInterval(() => {
                iconEl.style.transform = (pulses % 2 === 0)
                    ? originalTransform + ' scale(1.5)'
                    : originalTransform;
                pulses++;
                if (pulses >= 6) {
                    clearInterval(pulse);
                    iconEl.style.transform = originalTransform;
                }
            }, 400);
        }
    }, 1300);
}
