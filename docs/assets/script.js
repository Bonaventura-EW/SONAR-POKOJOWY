// SONAR POKOJOWY - JavaScript
// Interaktywna mapa z filtrami, wyszukiwaniem i warstwami

let map;
let mapData;
let allMarkers = [];
let markerLayers = {
    active: L.layerGroup(),
    inactive: L.layerGroup()
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
    markerLayers.inactive.addTo(map);
}

// Wczytanie danych
async function loadData() {
    try {
        // Próba 1: Z cache-busting
        const timestamp = new Date().getTime();
        let response = await fetch(`../data.json?v=${timestamp}`);
        
        // Jeśli 404, spróbuj bez cache-busting
        if (!response.ok) {
            console.warn('Fetch z cache-busting nie udał się, próbuję bez...');
            response = await fetch('../data.json');
        }
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const text = await response.text();
        mapData = JSON.parse(text);
        
        updateStats();
        updateScanInfo();
        createPriceRangeFilters();
        createMarkers();
        setupEventListeners();
        
    } catch (error) {
        console.error('Błąd wczytywania danych:', error);
        alert('Nie udało się wczytać danych mapy. Sprawdź czy plik data.json istnieje.');
    }
}

// Aktualizacja statystyk
function updateStats() {
    document.getElementById('active-count').textContent = mapData.stats.active_count;
    document.getElementById('avg-price').textContent = mapData.stats.avg_price + ' zł';
    document.getElementById('min-price').textContent = mapData.stats.min_price + ' zł';
    document.getElementById('max-price').textContent = mapData.stats.max_price + ' zł';
}

// Aktualizacja informacji o skanach
function updateScanInfo() {
    document.getElementById('last-scan').textContent = mapData.scan_info.last;
    document.getElementById('next-scan').textContent = mapData.scan_info.next;
}

// Tworzenie checkboxów dla zakresów cenowych
function createPriceRangeFilters() {
    const activeContainer = document.getElementById('price-range-filters-active');
    const inactiveContainer = document.getElementById('price-range-filters-inactive');
    
    Object.entries(mapData.price_ranges).forEach(([key, range]) => {
        // Aktywne
        const labelActive = document.createElement('label');
        labelActive.innerHTML = `
            <input type="checkbox" class="price-range-filter-active" data-range="${key}" checked>
            <span style="display:inline-block; width:15px; height:15px; background:${range.color}; margin-right:5px; vertical-align:middle; border-radius:50%;"></span>
            ${range.label}
        `;
        activeContainer.appendChild(labelActive);
        
        // Nieaktywne
        const labelInactive = document.createElement('label');
        labelInactive.innerHTML = `
            <input type="checkbox" class="price-range-filter-inactive" data-range="${key}" checked>
            <span style="display:inline-block; width:15px; height:15px; background:${range.color}; margin-right:5px; vertical-align:middle; border-radius:50%; opacity:0.5;">×</span>
            ${range.label}
        `;
        inactiveContainer.appendChild(labelInactive);
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
    
    offers.forEach((offer, index) => {
        // Oblicz offset w kole (rozsunięcie)
        const angle = (index / offers.length) * 2 * Math.PI;
        const offsetLat = Math.cos(angle) * offsetDistance * index;
        const offsetLon = Math.sin(angle) * offsetDistance * index;
        
        const coords = [
            baseCoords[0] + offsetLat,
            baseCoords[1] + offsetLon
        ];
        
        // Kolor markera
        const color = mapData.price_ranges[priceRange].color;
        
        // Ikona markera
        const icon = L.divIcon({
            className: 'custom-marker' + (isActive ? '' : ' inactive'),
            html: isActive ? '●' : '×',
            iconSize: [30, 30],
            iconAnchor: [15, 15],
            popupAnchor: [0, -15]
        });
        
        // Popup content
        const popupContent = createPopupContent(address, [offer]);
        
        // Tworzenie markera
        const marker = L.marker(coords, { icon: icon })
            .bindPopup(popupContent, { maxWidth: 400 });
        
        // Stylizacja ikony
        marker.on('add', function() {
            const markerElement = marker.getElement();
            if (markerElement) {
                markerElement.querySelector('.custom-marker').style.backgroundColor = color;
            }
        });
        
        // Dodaj do odpowiedniej warstwy
        if (isActive) {
            marker.addTo(markerLayers.active);
        } else {
            marker.addTo(markerLayers.inactive);
        }
        
        // Zapisz referencję
        allMarkers.push({
            marker: marker,
            address: address,
            offers: [offer],
            priceRange: priceRange,
            isActive: isActive
        });
    });
}

// Tworzenie HTML popup
function createPopupContent(address, offers) {
    let html = `<div class="offer-popup">`;
    html += `<h3>📍 ${address}</h3>`;
    
    offers.forEach(offer => {
        const isActive = offer.active;
        
        html += `<div class="offer-item ${isActive ? '' : 'inactive'}">`;
        
        if (!isActive) {
            html += `<div class="inactive-badge">❌ Nieaktywne</div>`;
        }
        
        // Cena
        html += `<div class="offer-price ${isActive ? '' : 'inactive'}">💰 ${offer.price} zł</div>`;
        
        // Historia cen
        if (offer.price_history.length > 1) {
            const history = offer.price_history.map(p => p + ' zł').join(' → ');
            html += `<div class="price-history">Historia: ${history}</div>`;
        }
        
        // Media info
        html += `<div class="media-info">Skład: ${offer.media_info}</div>`;
        
        // Link
        html += `<a href="${offer.url}" target="_blank" class="offer-link">🔗 Otwórz ogłoszenie</a>`;
        
        // Opis
        html += `<div class="offer-description">📝 ${offer.description}</div>`;
        
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
    
    // Zakresy cenowe - aktywne
    const activeRanges = Array.from(document.querySelectorAll('.price-range-filter-active:checked'))
        .map(cb => cb.dataset.range);
    
    // Zakresy cenowe - nieaktywne
    const inactiveRanges = Array.from(document.querySelectorAll('.price-range-filter-inactive:checked'))
        .map(cb => cb.dataset.range);
    
    // Precyzyjne filtry cen
    const priceMinActive = parseInt(document.getElementById('price-min-active').value) || 0;
    const priceMaxActive = parseInt(document.getElementById('price-max-active').value) || 999999;
    const priceMinInactive = parseInt(document.getElementById('price-min-inactive').value) || 0;
    const priceMaxInactive = parseInt(document.getElementById('price-max-inactive').value) || 999999;
    
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
        
        // Filtr zakresów cenowych
        if (item.isActive && !activeRanges.includes(item.priceRange)) {
            visible = false;
        }
        if (!item.isActive && !inactiveRanges.includes(item.priceRange)) {
            visible = false;
        }
        
        // Precyzyjny filtr cen
        const price = item.offers[0].price;
        if (item.isActive && (price < priceMinActive || price > priceMaxActive)) {
            visible = false;
        }
        if (!item.isActive && (price < priceMinInactive || price > priceMaxInactive)) {
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
    
    // Zakresy cenowe
    document.querySelectorAll('.price-range-filter-active').forEach(cb => {
        cb.addEventListener('change', filterMarkers);
    });
    document.querySelectorAll('.price-range-filter-inactive').forEach(cb => {
        cb.addEventListener('change', filterMarkers);
    });
    
    // Precyzyjne filtry cen
    document.getElementById('price-min-active').addEventListener('input', filterMarkers);
    document.getElementById('price-max-active').addEventListener('input', filterMarkers);
    document.getElementById('price-min-inactive').addEventListener('input', filterMarkers);
    document.getElementById('price-max-inactive').addEventListener('input', filterMarkers);
    
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
