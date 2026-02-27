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
        
        updateStats();
        updateScanInfo();
        createPriceRangeFilters();
        createMarkers();
        setupEventListeners();
        
        console.log('🎉 Mapa gotowa!');
        
    } catch (error) {
        console.error('❌ Błąd wczytywania danych:', error);
        alert('Nie udało się wczytać danych mapy. Sprawdź czy plik data.json istnieje.\n\nBłąd: ' + error.message);
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
    
    // Pobierz kolor z zakresu cenowego
    const color = mapData.price_ranges[priceRange]?.color || '#808080';
    
    offers.forEach((offer, index) => {
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
        const tooltipText = `${address} - ${price} zł`;
        
        // Ikona markera - pinezka z kolorem
        const icon = L.divIcon({
            className: 'pin-marker',
            html: `
                <div style="position: relative; width: 40px; height: 50px;" title="${tooltipText}">
                    <svg width="40" height="50" viewBox="0 0 40 50" style="filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));">
                        <path d="M20 0 C9 0 0 9 0 20 C0 35 20 50 20 50 C20 50 40 35 40 20 C40 9 31 0 20 0 Z" 
                              fill="${color}" 
                              stroke="white" 
                              stroke-width="2"/>
                        <circle cx="20" cy="18" r="8" fill="white" opacity="0.9"/>
                    </svg>
                    ${!isActive ? '<div style="position: absolute; top: 8px; left: 50%; transform: translateX(-50%); font-size: 24px;">×</div>' : ''}
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
        if (isActive) {
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
        
        html += `<div class="offer-item ${isActive ? '' : 'inactive'}" data-offer-id="${offer.id}">`;
        
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
        
        // NOWY: Przycisk "Usuń"
        html += `<button class="remove-listing-btn" onclick="removeListingPrompt('${offer.id}')" style="margin-top: 10px; padding: 5px 10px; background: #dc3545; color: white; border: none; border-radius: 4px; cursor: pointer;">🗑️ Usuń to ogłoszenie</button>`;
        
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

// NOWA funkcja: Usuwanie ogłoszenia (dodaje do removed_listings.json)
function removeListingPrompt(offerId) {
    if (!confirm('⚠️ Czy na pewno chcesz usunąć to ogłoszenie?\n\nOgłoszenie zostanie dodane do listy blokowanych i nie pojawi się ponownie przy kolejnych skanach.\n\nAby je usunąć, uruchom skrypt:\npython src/remove_listing.py ' + offerId)) {
        return;
    }
    
    alert('📝 Skopiuj i wykonaj polecenie:\n\npython src/remove_listing.py ' + offerId + '\n\nPo wykonaniu uruchom ponownie scan.');
}

// Usuwanie oferty z mapy (STARA funkcja - tylko usuwa z widoku)
function deleteOffer(offerId, address) {
    if (!confirm(`Czy na pewno chcesz usunąć ofertę z adresu "${address}"?`)) {
        return;
    }
    
    console.log('🗑️ Usuwam ofertę:', offerId);
    
    // Znajdź i usuń marker
    const markerIndex = allMarkers.findIndex(m => m.address === address);
    
    if (markerIndex !== -1) {
        const markerData = allMarkers[markerIndex];
        markerData.marker.remove();
        allMarkers.splice(markerIndex, 1);
        
        console.log('✅ Oferta usunięta');
        alert('Oferta usunięta z mapy. Przy kolejnym scanie pojawi się ponownie jeśli nadal istnieje na OLX.');
    }
}
