// SONAR POKOJOWY - JavaScript
// Interaktywna mapa z filtrami, wyszukiwaniem i warstwami

let map;
let mapData;
let allMarkers = [];
let markerLayers = {
    active: L.layerGroup(),
    inactive: L.layerGroup(),
    damaged: L.layerGroup()  // Warstwa dla ogłoszeń oznaczonych jako uszkodzone
};

// LocalStorage dla ogłoszeń oznaczonych jako uszkodzone
const DAMAGED_KEY = 'sonar_damaged_listings';

// Pomocnicze funkcje dla damaged listings
function getDamagedListings() {
    const stored = localStorage.getItem(DAMAGED_KEY);
    return stored ? JSON.parse(stored) : [];
}

function addToDamaged(offerId) {
    const damaged = getDamagedListings();
    if (!damaged.includes(offerId)) {
        damaged.push(offerId);
        localStorage.setItem(DAMAGED_KEY, JSON.stringify(damaged));
        return true;
    }
    return false;
}

function removeFromDamaged(offerId) {
    let damaged = getDamagedListings();
    damaged = damaged.filter(id => id !== offerId);
    localStorage.setItem(DAMAGED_KEY, JSON.stringify(damaged));
}

function isDamaged(offerId) {
    return getDamagedListings().includes(offerId);
}

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
    markerLayers.inactive.addTo(map);
    // markerLayers.damaged NIE dodajemy - będzie domyślnie ukryta
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
        createMarkers();
        updateStats();  // Wywołaj PO createMarkers(), żeby allMarkers był wypełniony
        setupEventListeners();
        
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
        
        try {
            const parts = offer.first_seen.split(' ');
            const dateParts = parts[0].split('.');
            const timeParts = parts[1].split(':');
            const offerDate = new Date(
                parseInt('20' + dateParts[2]), // year
                parseInt(dateParts[1]) - 1,     // month (0-indexed)
                parseInt(dateParts[0]),         // day
                parseInt(timeParts[0]),         // hour
                parseInt(timeParts[1])          // minute
            );
            return offerDate >= cutoffDate;
        } catch (e) {
            return true; // Jeśli błąd parsowania, uwzględnij ofertę
        }
    }
    
    // Zbierz wszystkie widoczne oferty (aktywne + nieaktywne razem)
    const visibleOffers = [];
    
    allMarkers.forEach(item => {
        // Sprawdź filtr warstwy
        if (item.isActive && !showActive) return;
        if (!item.isActive && !showInactive) return;
        
        // Sprawdź czy marker jest widoczny (jest w odpowiedniej warstwie na mapie)
        const isOnMap = (item.isActive && markerLayers.active.hasLayer(item.marker)) ||
                        (!item.isActive && markerLayers.inactive.hasLayer(item.marker));
        
        if (!isOnMap) return;
        
        // Sprawdź wyszukiwanie
        if (searchTerm && !item.address.toLowerCase().includes(searchTerm)) return;
        
        // Sprawdź zakres cenowy (wspólny dla obu warstw)
        if (!selectedRanges.includes(item.priceRange)) return;
        
        // Przetwórz każdą ofertę z tego markera
        item.offers.forEach(offer => {
            // Sprawdź filtr czasowy
            if (!passesTimeFilter(offer)) return;
            
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
            ${range.label}
        `;
        container.appendChild(label);
    });
}

// Tworzenie markerów
function createMarkers() {
    allMarkers = [];
    
    mapData.markers.forEach(marker => {
        const coords = marker.coords;
        const address = marker.address;
        const offers = marker.offers;
        const priceRange = marker.price_range;
        const hasActive = marker.has_active;
        
        // Grupuj oferty: aktywne osobno, nieaktywne osobno
        const activeOffers = offers.filter(o => o.active);
        const inactiveOffers = offers.filter(o => !o.active);
        
        // Twórz marker dla aktywnych (jeśli są)
        if (activeOffers.length > 0) {
            createMarkerGroup(coords, address, activeOffers, priceRange, true);
        }
        
        // Twórz marker dla nieaktywnych (jeśli są)
        if (inactiveOffers.length > 0) {
            createMarkerGroup(coords, address, inactiveOffers, priceRange, false);
        }
    });
}

// Tworzenie grupy markerów (rozsunięcie dla tego samego adresu)
function createMarkerGroup(baseCoords, address, offers, priceRange, isActive) {
    const zoom = map.getZoom();
    const offsetDistance = zoom > 15 ? 0.0001 : 0;  // 15-20px przy dużym zoomie
    
    // Pobierz kolor z zakresu cenowego
    const color = mapData.price_ranges[priceRange]?.color || '#808080';
    
    offers.forEach((offer, index) => {
        // Sprawdź czy oferta jest oznaczona jako uszkodzona
        const isDamagedOffer = isDamaged(offer.id);
        
        // Oblicz offset w kole (rozsunięcie)
        const angle = (index / offers.length) * 2 * Math.PI;
        const offsetLat = Math.cos(angle) * offsetDistance * index;
        const offsetLon = Math.sin(angle) * offsetDistance * index;
        
        // Konwersja z obiektu {lat, lon} na tablicę [lat, lon] dla Leaflet
        const coords = [
            baseCoords.lat + offsetLat,
            baseCoords.lon + offsetLon
        ];
        
        // Tooltip (pojawia się przy hover)
        const price = offer.price;
        const tooltipText = isDamagedOffer 
            ? `⚠️ USZKODZONE: ${address} - ${price} zł`
            : `${address} - ${price} zł`;
        
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
        // Jeśli uszkodzone - pomarańczowy, jeśli nowa - czerwona obwódka, inaczej - biała
        const strokeColor = isDamagedOffer ? '#ff6600' : (isNew ? '#ff0000' : 'white');
        const strokeWidth = isDamagedOffer ? '4' : (isNew ? '3' : '2');
        const markerColor = isDamagedOffer ? '#ff9933' : color;  // Pomarańczowy dla uszkodzonych
        
        // Badge zmiany ceny - ikona dolara ze strzałką
        let priceChangeBadge = '';
        if (hasPriceChange && !isDamagedOffer) {
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
        
        const icon = L.divIcon({
            className: 'pin-marker',
            html: `
                <div style="position: relative; width: 40px; height: 50px;" title="${tooltipText}">
                    <svg width="40" height="50" viewBox="0 0 40 50" style="filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));">
                        <path d="M20 0 C9 0 0 9 0 20 C0 35 20 50 20 50 C20 50 40 35 40 20 C40 9 31 0 20 0 Z" 
                              fill="${markerColor}" 
                              stroke="${strokeColor}" 
                              stroke-width="${strokeWidth}"/>
                        <circle cx="20" cy="18" r="8" fill="white" opacity="0.9"/>
                    </svg>
                    ${!isActive ? '<div style="position: absolute; top: 8px; left: 50%; transform: translateX(-50%); font-size: 24px;">×</div>' : ''}
                    ${isNew && !hasPriceChange ? '<div style="position: absolute; top: -5px; right: -5px; background: #ff0000; color: white; border-radius: 50%; width: 16px; height: 16px; font-size: 10px; font-weight: bold; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 3px rgba(0,0,0,0.3);">N</div>' : ''}
                    ${priceChangeBadge}
                    ${isDamagedOffer ? '<div style="position: absolute; top: -5px; left: -5px; background: #ff6600; color: white; border-radius: 50%; width: 18px; height: 18px; font-size: 12px; font-weight: bold; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 3px rgba(0,0,0,0.3);">⚠</div>' : ''}
                </div>
            `,
            iconSize: [40, 50],
            iconAnchor: [20, 50],
            popupAnchor: [0, -50]
        });
        
        // Popup content
        const popupContent = createPopupContent(address, [offer]);
        
        // Tworzenie markera z tooltip
        const markerObj = L.marker(coords, { 
            icon: icon,
            title: tooltipText  // Tooltip przy hover
        })
            .bindPopup(popupContent, { maxWidth: 400 });
        
        // Dodaj do odpowiedniej warstwy
        if (isDamagedOffer) {
            markerObj.addTo(markerLayers.damaged);
        } else if (isActive) {
            markerObj.addTo(markerLayers.active);
        } else {
            markerObj.addTo(markerLayers.inactive);
        }
        
        // Zapisz referencję
        allMarkers.push({
            marker: markerObj,
            address: address,
            offers: [offer],
            priceRange: priceRange,
            isActive: isActive,
            isDamaged: isDamagedOffer
        });
    });
}

// Tworzenie HTML popup
function createPopupContent(address, offers) {
    let html = `<div class="offer-popup">`;
    html += `<h3>📍 ${address}</h3>`;
    
    offers.forEach(offer => {
        const isActive = offer.active;
        
        html += `<div class="offer-item ${isActive ? '' : 'inactive'}" data-offer-id="${offer.id}">`;
        
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
                html += ` <span style="font-size: 0.85em;">(zmiana: ${offer.price_changed_at})</span>`;
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
        
        // Media info
        html += `<div class="media-info">Skład: ${offer.media_info}</div>`;
        
        // Link
        html += `<a href="${offer.url}" target="_blank" class="offer-link">🔗 Otwórz ogłoszenie</a>`;
        
        // Przycisk: Oznacz jako uszkodzone / Przywróć
        if (isDamaged(offer.id)) {
            html += `<button class="restore-listing-btn" onclick="restoreListing('${offer.id}')" style="margin-top: 10px; padding: 5px 10px; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer;">✅ Przywróć ogłoszenie</button>`;
        } else {
            html += `<button class="mark-damaged-btn" onclick="markAsDamaged('${offer.id}')" style="margin-top: 10px; padding: 5px 10px; background: #ff6600; color: white; border: none; border-radius: 4px; cursor: pointer;">⚠️ Oznacz jako uszkodzone</button>`;
        }
        
        // Opis - z funkcją zwijania/rozwijania
        const maxChars = 100; // Maksymalna długość podglądu (~1-2 linie)
        const needsTruncate = offer.description.length > maxChars;
        
        if (needsTruncate) {
            const uniqueId = `desc-${offer.id}`;
            const shortDescription = offer.description.substring(0, maxChars);
            
            html += `
                <div class="offer-description">
                    <div id="${uniqueId}-short">
                        📝 ${shortDescription}...
                        <br><a href="javascript:void(0)" onclick="toggleDescription('${uniqueId}')" class="show-more-link">▼ Pokaż całość</a>
                    </div>
                    <div id="${uniqueId}-full" style="display: none;">
                        📝 ${offer.description}
                        <br><a href="javascript:void(0)" onclick="toggleDescription('${uniqueId}')" class="show-more-link">▲ Zwiń</a>
                    </div>
                </div>
            `;
        } else {
            html += `<div class="offer-description">📝 ${offer.description}</div>`;
        }
        
        // Daty
        if (isActive) {
            html += `<div class="offer-dates">`;
            html += `📅 Dodano: ${offer.first_seen}<br>`;
            html += `📅 Ostatnio widziane: ${offer.last_seen}<br>`;
            html += `⏱️ Dni aktywności: ${offer.days_active}`;
            html += `</div>`;
        } else {
            html += `<div class="offer-dates">`;
            html += `📅 Aktywna przez: ${offer.days_active} dni<br>`;
            html += `📅 Nieaktywna od: ${offer.last_seen}<br>`;
            html += `💰 Ostatnia cena: ${offer.price} zł`;
            html += `</div>`;
        }
        
        // Przycisk usuwania
        html += `<button class="delete-offer-btn" onclick="deleteOffer('${offer.id}', '${address}')">🗑️ Usuń z mapy</button>`;
        
        html += `</div>`;
    });
    
    html += `</div>`;
    return html;
}

// Filtrowanie markerów
function filterMarkers() {
    // Pobierz ustawienia filtrów
    const showActive = document.getElementById('layer-active').checked;
    const showInactive = document.getElementById('layer-inactive').checked;
    
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
    
    // Filtruj markery
    allMarkers.forEach(item => {
        let visible = true;
        
        // Filtr aktywne/nieaktywne
        if (item.isActive && !showActive) {
            visible = false;
        }
        if (!item.isActive && !showInactive) {
            visible = false;
        }
        
        // NOWY: Filtr czasowy (sprawdź first_seen każdej oferty)
        if (visible && cutoffDate && item.offers) {
            const hasRecentOffer = item.offers.some(offer => {
                try {
                    // Parse first_seen date (format: "28.02.2026 19:57")
                    const parts = offer.first_seen.split(' ');
                    const dateParts = parts[0].split('.');
                    const timeParts = parts[1].split(':');
                    const offerDate = new Date(
                        parseInt('20' + dateParts[2]), // year
                        parseInt(dateParts[1]) - 1,     // month (0-indexed)
                        parseInt(dateParts[0]),         // day
                        parseInt(timeParts[0]),         // hour
                        parseInt(timeParts[1])          // minute
                    );
                    return offerDate >= cutoffDate;
                } catch (e) {
                    return true; // Jeśli błąd parsowania, pokaż ofertę
                }
            });
            
            if (!hasRecentOffer) {
                visible = false;
            }
        }
        
        // Filtr zakresów cenowych - wspólny dla obu warstw
        if (!selectedRanges.includes(item.priceRange)) {
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
        
        // Pokaż/ukryj marker
        if (visible) {
            if (item.isActive) {
                markerLayers.active.addLayer(item.marker);
            } else {
                markerLayers.inactive.addLayer(item.marker);
            }
        } else {
            if (item.isActive) {
                markerLayers.active.removeLayer(item.marker);
            } else {
                markerLayers.inactive.removeLayer(item.marker);
            }
        }
    });
    
    // Przelicz i zaktualizuj statystyki po filtrowaniu
    updateStats();
}

// Wyszukiwanie z zoomem
function searchAndZoom() {
    const searchTerm = document.getElementById('search-input').value.toLowerCase();
    
    if (!searchTerm) {
        filterMarkers();
        return;
    }
    
    // Znajdź pierwsze dopasowanie
    const match = allMarkers.find(item => 
        item.address.toLowerCase().includes(searchTerm) &&
        (item.isActive ? document.getElementById('layer-active').checked : document.getElementById('layer-inactive').checked)
    );
    
    if (match) {
        const coords = match.marker.getLatLng();
        map.setView(coords, 17);
        match.marker.openPopup();
    }
    
    filterMarkers();
}

// Setup event listeners
function setupEventListeners() {
    // Warstwy
    document.getElementById('layer-active').addEventListener('change', filterMarkers);
    document.getElementById('layer-inactive').addEventListener('change', filterMarkers);
    document.getElementById('layer-damaged').addEventListener('change', toggleDamagedLayer);
    
    // NOWY: Filtr czasowy
    document.getElementById('time-filter').addEventListener('change', filterMarkers);
    
    // Zakresy cenowe - wspólne dla obu warstw
    document.querySelectorAll('.price-range-filter').forEach(cb => {
        cb.addEventListener('change', filterMarkers);
    });
    
    // Precyzyjne filtry cen - wspólne dla obu warstw
    document.getElementById('price-min').addEventListener('input', filterMarkers);
    document.getElementById('price-max').addEventListener('input', filterMarkers);
    
    // Wyszukiwanie
    document.getElementById('search-input').addEventListener('input', searchAndZoom);
    
    // Zoom mapy - aktualizuj rozsunięcie markerów
    map.on('zoomend', function() {
        // TODO: Rekonstruuj markery z nowym offsetem
        // Na razie zostawiam jak jest (offset statyczny)
    });
}

// Inicjalizacja po załadowaniu DOM
document.addEventListener('DOMContentLoaded', function() {
    initMap();
    loadData();
});

// NOWA funkcja: Oznaczanie ogłoszenia jako uszkodzone
function markAsDamaged(offerId) {
    if (!confirm('⚠️ Oznaczyć to ogłoszenie jako uszkodzone?\n\nOgłoszenie trafi do warstwy "Uszkodzone" (domyślnie ukrytej).\nMożesz je przywrócić w każdej chwili.')) {
        return;
    }
    
    if (addToDamaged(offerId)) {
        console.log('⚠️ Oznaczono jako uszkodzone:', offerId);
        alert('✅ Ogłoszenie oznaczone jako uszkodzone!\n\nOdśwież stronę (F5) aby zobaczyć zmiany.');
        
        // Opcjonalnie: odśwież automatycznie
        setTimeout(() => {
            location.reload();
        }, 1000);
    }
}

// NOWA funkcja: Przywracanie ogłoszenia z warstwy uszkodzone
function restoreListing(offerId) {
    if (!confirm('✅ Przywrócić to ogłoszenie?\n\nOgłoszenie wróci do normalnej warstwy.')) {
        return;
    }
    
    removeFromDamaged(offerId);
    console.log('✅ Przywrócono ogłoszenie:', offerId);
    alert('✅ Ogłoszenie przywrócone!\n\nOdśwież stronę (F5) aby zobaczyć zmiany.');
    
    // Opcjonalnie: odśwież automatycznie
    setTimeout(() => {
        location.reload();
    }, 1000);
}

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

// NOWA funkcja: Włączanie/wyłączanie warstwy "Uszkodzone"
function toggleDamagedLayer() {
    const isChecked = document.getElementById('layer-damaged').checked;
    
    if (isChecked) {
        // Dodaj warstwę do mapy
        markerLayers.damaged.addTo(map);
        console.log('✅ Warstwa "Uszkodzone" włączona');
    } else {
        // Usuń warstwę z mapy
        map.removeLayer(markerLayers.damaged);
        console.log('⚠️ Warstwa "Uszkodzone" wyłączona');
    }
}
