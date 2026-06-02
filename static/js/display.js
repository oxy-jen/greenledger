const EVENT_LOCATION = {
    name: 'Mathenge TTI, Othaya',
    lat: -0.5084917,
    lng: 36.8919167
};

const MAP_MAX_ZOOM = 20;
const SATELLITE_NATIVE_ZOOM = 18;

const plantingZones = [
    {
        name: 'Main Gate',
        leader: 'Security Desk',
        target: 80,
        points: [[-0.50696, 36.8906], [-0.50696, 36.8915], [-0.50765, 36.89155], [-0.50772, 36.89062]]
    },
    {
        name: 'Administration Block',
        leader: 'Administration',
        target: 120,
        points: [[-0.50772, 36.89086], [-0.50768, 36.89205], [-0.50848, 36.89208], [-0.50852, 36.8909]]
    },
    {
        name: 'ICT Block',
        leader: 'ICT Department',
        target: 140,
        points: [[-0.50836, 36.8901], [-0.50826, 36.89102], [-0.50908, 36.89112], [-0.50916, 36.8902]]
    },
    {
        name: 'Engineering Area',
        leader: 'Engineering Department',
        target: 160,
        points: [[-0.50858, 36.89205], [-0.50852, 36.89308], [-0.50936, 36.89312], [-0.50942, 36.89212]]
    },
    {
        name: 'Agriculture Farm',
        leader: 'Agriculture Department',
        target: 220,
        points: [[-0.50922, 36.89064], [-0.50922, 36.89208], [-0.5102, 36.89212], [-0.51026, 36.89072]]
    }
];

const displayState = {
    map: null,
    records: new Map(),
    clusterLayer: null,
    heatLayer: null,
    zoneLayer: null,
    userMarker: null,
    previewMarker: null,
    layers: {},
    activeLayer: 'street',
    viewMode: 'street',
    densityEnabled: false,
    firstFit: true
};

document.addEventListener('DOMContentLoaded', () => {
    setupClock();
    setupTheme();
    setupMap();
    setupControls();
    setupSocket();
    refreshDisplay();
    setupWeather();

    setInterval(refreshDisplay, 6000);
    setInterval(setupWeather, 600000);
});

function setupClock() {
    const clock = document.getElementById('liveClock');
    const tick = () => {
        if (!clock) return;
        clock.textContent = new Date().toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    };
    tick();
    setInterval(tick, 1000);
}

function setupMap() {
    displayState.map = L.map('liveMap', {
        center: [EVENT_LOCATION.lat, EVENT_LOCATION.lng],
        zoom: 17,
        minZoom: 14,
        maxZoom: MAP_MAX_ZOOM,
        zoomControl: false,
        preferCanvas: true,
        attributionControl: false,
        zoomSnap: 0.25,
        wheelPxPerZoomLevel: 90
    });

    displayState.layers.street = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: MAP_MAX_ZOOM,
        maxNativeZoom: 19,
        updateWhenIdle: true,
        keepBuffer: 3
    }).addTo(displayState.map);

    displayState.layers.satellite = L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        {
            maxZoom: MAP_MAX_ZOOM,
            maxNativeZoom: SATELLITE_NATIVE_ZOOM,
            updateWhenIdle: true,
            keepBuffer: 3
        }
    );

    L.control.zoom({ position: 'bottomright' }).addTo(displayState.map);

    displayState.clusterLayer = L.markerClusterGroup({
        chunkedLoading: true,
        showCoverageOnHover: false,
        spiderfyOnMaxZoom: true,
        animate: true,
        animateAddingMarkers: true,
        maxClusterRadius: zoom => (zoom >= 18 ? 34 : 56),
        iconCreateFunction: cluster => clusterIcon(cluster.getChildCount())
    }).addTo(displayState.map);

    displayState.zoneLayer = L.layerGroup().addTo(displayState.map);
    drawZones();
    setTimeout(() => displayState.map.invalidateSize(), 120);
}

function setupControls() {
    document.getElementById('streetLayerBtn')?.addEventListener('click', () => setMapView('street'));
    document.getElementById('satelliteLayerBtn')?.addEventListener('click', () => setMapView('satellite'));
    document.getElementById('threeDLayerBtn')?.addEventListener('click', () => setMapView('3d'));
    document.getElementById('densityToggle')?.addEventListener('click', toggleDensity);
    document.getElementById('gpsButton')?.addEventListener('click', locateVolunteer);
    document.getElementById('plantHereButton')?.addEventListener('click', plantTreeHere);
}

function setupTheme() {
    const page = document.querySelector('.tv-page');
    const toggle = document.getElementById('themeToggle');
    if (!page || !toggle) return;

    const setTheme = isGreenMode => {
        page.classList.toggle('neon-mode', isGreenMode);
        toggle.setAttribute('aria-pressed', String(isGreenMode));
        toggle.innerHTML = isGreenMode
            ? '<i class="fa-solid fa-moon"></i><span>Green Mode</span>'
            : '<i class="fa-solid fa-sun"></i><span>Light Mode</span>';
        if (displayState.map) {
            setTimeout(() => displayState.map.invalidateSize(), 80);
        }
    };

    setTheme(page.classList.contains('neon-mode'));
    toggle.addEventListener('click', () => setTheme(!page.classList.contains('neon-mode')));
}

function setupSocket() {
    const socket = io();
    socket.on('connect', () => setConnectionState(true));
    socket.on('disconnect', () => setConnectionState(false));
    socket.on('new_planting', data => {
        const record = normalizeSocketRecord(data);
        if (record) {
            displayState.records.set(record.id, record);
            renderMap();
            updatePanels();
            addFeedItem(record, true);
        }
    });
    socket.on('participant_verified', data => {
        if (data.status === 'Rejected') {
            displayState.records.delete(data.record_number || data.id);
            renderMap();
            updatePanels();
        }
    });
}

function refreshDisplay() {
    Promise.all([
        fetch('/api/stats').then(response => response.json()),
        fetch('/api/map-records').then(response => response.json())
    ])
        .then(([stats, records]) => {
            displayState.records = new Map(records.map(record => [record.id, record]));
            updateStats(stats);
            renderMap();
            updatePanels();
            updateFeed(records.slice(0, 8));
        })
        .catch(() => setConnectionState(false));
}

function setBaseLayer(layerName) {
    if (displayState.activeLayer === layerName) return;
    displayState.map.removeLayer(displayState.layers[displayState.activeLayer]);
    displayState.layers[layerName].addTo(displayState.map);
    displayState.activeLayer = layerName;
}

function setMapView(viewMode) {
    const layerName = viewMode === 'street' ? 'street' : 'satellite';
    setBaseLayer(layerName);
    displayState.viewMode = viewMode;

    const mapCard = document.querySelector('.map-forest-card');
    mapCard?.classList.toggle('map-3d-mode', viewMode === '3d');

    document.getElementById('streetLayerBtn')?.classList.toggle('active', viewMode === 'street');
    document.getElementById('satelliteLayerBtn')?.classList.toggle('active', viewMode === 'satellite');
    document.getElementById('threeDLayerBtn')?.classList.toggle('active', viewMode === '3d');
    document.getElementById('streetLayerBtn')?.setAttribute('aria-pressed', String(viewMode === 'street'));
    document.getElementById('satelliteLayerBtn')?.setAttribute('aria-pressed', String(viewMode === 'satellite'));
    document.getElementById('threeDLayerBtn')?.setAttribute('aria-pressed', String(viewMode === '3d'));

    if (viewMode === '3d') {
        displayState.map.setZoom(Math.max(displayState.map.getZoom(), 18), { animate: true });
    }
    setTimeout(() => displayState.map.invalidateSize(), 120);
}

function toggleDensity() {
    displayState.densityEnabled = !displayState.densityEnabled;
    const button = document.getElementById('densityToggle');
    button?.classList.toggle('active', displayState.densityEnabled);
    button?.setAttribute('aria-pressed', String(displayState.densityEnabled));
    renderHeatLayer();
}

function renderMap() {
    const records = Array.from(displayState.records.values()).filter(hasCoordinates);
    const treePoints = expandTreePoints(records);
    displayState.clusterLayer.clearLayers();

    treePoints.forEach(tree => {
        displayState.clusterLayer.addLayer(createTreeMarker(tree));
    });

    renderHeatLayer();
    drawZones();
    displayState.map.invalidateSize();

    if (displayState.firstFit && treePoints.length) {
        const bounds = L.latLngBounds(treePoints.map(tree => [tree.lat, tree.lng]));
        displayState.map.fitBounds(bounds.pad(0.22), { maxZoom: 17, animate: true, duration: 0.8 });
        displayState.firstFit = false;
    }
}

function createTreeMarker(record) {
    const marker = L.circleMarker([record.lat, record.lng], {
        radius: 5,
        color: '#eaf7ee',
        weight: 1.5,
        fillColor: speciesColor(record.species),
        fillOpacity: 0.92,
        className: 'tree-dot-marker'
    });

    marker.bindPopup(treePopup(record), {
        className: 'tree-popup',
        maxWidth: 280
    });
    return marker;
}

function clusterIcon(count) {
    let className = 'tree-cluster cluster-low';
    let size = 36;
    if (count > 100) {
        className = 'tree-cluster cluster-forest';
        size = 64;
    } else if (count > 50) {
        className = 'tree-cluster cluster-high';
        size = 56;
    } else if (count > 10) {
        className = 'tree-cluster cluster-mid';
        size = 46;
    }

    return L.divIcon({
        html: `<div><i class="fa-solid fa-tree"></i><span>${formatNumber(count)}</span></div>`,
        className,
        iconSize: [size, size]
    });
}

function renderHeatLayer() {
    if (displayState.heatLayer) {
        displayState.map.removeLayer(displayState.heatLayer);
        displayState.heatLayer = null;
    }
    if (!displayState.densityEnabled) return;

    const points = expandTreePoints(Array.from(displayState.records.values()).filter(hasCoordinates))
        .map(tree => [tree.lat, tree.lng, 0.72]);

    displayState.heatLayer = L.heatLayer(points, {
        radius: 34,
        blur: 26,
        maxZoom: 18,
        minOpacity: 0.26,
        gradient: {
            0.2: '#d9f5d6',
            0.45: '#7ed68b',
            0.7: '#25a45d',
            1.0: '#064d2f'
        }
    }).addTo(displayState.map);
}

function drawZones() {
    const zoneStats = getZoneStats();
    displayState.zoneLayer.clearLayers();

    plantingZones.forEach(zone => {
        const stats = zoneStats.get(zone.name) || { trees: 0 };
        const completion = Math.min(Math.round((stats.trees / zone.target) * 100), 100);
        const polygon = L.polygon(zone.points, {
            color: '#1e6a45',
            weight: 1.4,
            opacity: 0.62,
            fillColor: zoneFillColor(completion),
            fillOpacity: 0.14 + completion / 520
        });
        polygon.bindPopup(`
            <div class="zone-popup">
                <strong>${escapeHtml(zone.name)}</strong>
                <span>Zone leader: ${escapeHtml(zone.leader)}</span>
                <span>${formatNumber(stats.trees)} trees planted</span>
                <span>${completion}% complete</span>
            </div>
        `);
        polygon.addTo(displayState.zoneLayer);
    });
}

function updateStats(data) {
    setText('treeCounter', formatNumber(data.trees));
    setText('participantCounter', formatNumber(data.participants));
    setText('co2Counter', `${formatNumber(Math.round(data.co2))} kg`);
    renderLeaderboard(data.leaderboard || []);
}

function updatePanels() {
    const zoneStats = getZoneStats();
    setText('zoneCounter', formatNumber(zoneStats.size));
    renderZoneList(zoneStats);
}

function renderZoneList(zoneStats) {
    const list = document.getElementById('zoneList');
    if (!list) return;

    list.innerHTML = plantingZones.map(zone => {
        const stats = zoneStats.get(zone.name) || { trees: 0 };
        const completion = Math.min(Math.round((stats.trees / zone.target) * 100), 100);
        return `
            <article class="zone-row">
                <div>
                    <strong>${escapeHtml(zone.name)}</strong>
                    <span>${escapeHtml(zone.leader)}</span>
                </div>
                <b>${formatNumber(stats.trees)}</b>
                <div class="zone-progress"><span style="width: ${completion}%"></span></div>
                <small>${completion}% complete</small>
            </article>
        `;
    }).join('');
}

function updateFeed(records) {
    const feed = document.getElementById('liveFeed');
    if (!feed) return;
    if (!records.length) {
        feed.innerHTML = '<div class="empty-state">Waiting for participant submissions.</div>';
        renderMoments([]);
        return;
    }
    feed.innerHTML = '';
    records.forEach(record => addFeedItem(record, false));
    renderMoments(records);
}

function addFeedItem(record, prepend) {
    const feed = document.getElementById('liveFeed');
    if (!feed) return;
    feed.querySelector('.empty-state')?.remove();

    const item = document.createElement('article');
    item.className = feed.classList.contains('tv-feed') ? 'feed-item' : 'gis-feed-item';
    item.innerHTML = feed.classList.contains('tv-feed') ? `
        <img class="feed-image" src="${photoUrl(record.photo)}" alt="${escapeHtml(record.name || 'Volunteer')}">
        <div>
            <strong class="feed-name">${escapeHtml(record.name || 'Volunteer')}</strong>
            <span class="feed-details">${formatNumber(record.quantity || 1)} planted ${escapeHtml(record.species || 'Tree')}</span>
            <span class="feed-role">${escapeHtml(record.role || record.zone || 'Participant')}</span>
        </div>
        <img class="feed-thumb" src="${photoUrl(record.photo)}" alt="">
    ` : `
        <img src="${photoUrl(record.photo)}" alt="${escapeHtml(record.name || 'Volunteer')}">
        <div>
            <strong>${escapeHtml(record.name || 'Volunteer')}</strong>
            <span>${formatNumber(record.quantity || 1)} x ${escapeHtml(record.species || 'Tree')} in ${escapeHtml(record.zone || 'Planting zone')}</span>
        </div>
        <i class="fa-solid fa-tree"></i>
    `;
    if (prepend) feed.prepend(item);
    else feed.appendChild(item);
    while (feed.children.length > 8) {
        feed.removeChild(feed.lastElementChild);
    }
}

function renderMoments(records) {
    const grid = document.getElementById('momentsGrid');
    if (!grid) return;

    const photos = records.filter(record => record.photo).slice(0, 12);
    if (!photos.length) {
        grid.innerHTML = '<div class="empty-state">Waiting for participant photos.</div>';
        return;
    }

    grid.innerHTML = photos.map(record => `
        <img src="${photoUrl(record.photo)}" alt="${escapeHtml(record.name || 'Planting moment')}">
    `).join('');
}

function renderLeaderboard(rows) {
    const list = document.getElementById('leaderboardList');
    if (!list) return;

    if (!rows.length) {
        list.innerHTML = '<div class="empty-state">Waiting for team totals.</div>';
        return;
    }

    const max = Math.max(...rows.map(row => Number(row.total || 0)), 1);
    list.innerHTML = rows.slice(0, 6).map((row, index) => {
        const width = Math.max(Math.round((Number(row.total || 0) / max) * 100), 8);
        return `
            <article class="leader-row">
                <span class="leader-rank">${index + 1}</span>
                <div>
                    <div class="leader-name">${escapeHtml(row.role || 'Department')}</div>
                    <div class="bar"><span style="width: ${width}%"></span></div>
                </div>
                <strong class="leader-count">${formatNumber(row.total)}</strong>
            </article>
        `;
    }).join('');
}

function locateVolunteer() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(position => {
        const latlng = [position.coords.latitude, position.coords.longitude];
        if (displayState.userMarker) displayState.userMarker.remove();
        displayState.userMarker = L.circleMarker(latlng, {
            radius: 8,
            color: '#ffffff',
            weight: 3,
            fillColor: '#2477d4',
            fillOpacity: 0.95,
            className: 'gps-dot'
        }).addTo(displayState.map).bindPopup('Your current GPS location');
        displayState.map.flyTo(latlng, 18, { duration: 0.9 });
    });
}

function plantTreeHere() {
    if (!navigator.geolocation) {
        window.location.href = '/';
        return;
    }
    navigator.geolocation.getCurrentPosition(
        position => {
            const latlng = [position.coords.latitude, position.coords.longitude];
            if (displayState.previewMarker) displayState.previewMarker.remove();
            displayState.previewMarker = L.circleMarker(latlng, {
                radius: 7,
                color: '#ffffff',
                weight: 2,
                fillColor: '#1f9d55',
                fillOpacity: 0.95,
                className: 'tree-dot-marker pending'
            }).addTo(displayState.map).bindPopup(`
                <div class="tree-popup-card">
                    <strong>Plant Tree Here</strong>
                    <span>GPS point captured. Complete the registration form with photo evidence.</span>
                    <a class="popup-action" href="/">Open registration</a>
                </div>
            `).openPopup();
            displayState.map.flyTo(latlng, 18, { duration: 0.9 });
        },
        () => { window.location.href = '/'; },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
}

function setupWeather() {
    fetch(`https://api.open-meteo.com/v1/forecast?latitude=${EVENT_LOCATION.lat}&longitude=${EVENT_LOCATION.lng}&current_weather=true`)
        .then(response => response.json())
        .then(data => {
            const weather = data.current_weather;
            const icon = weather.weathercode > 2 ? 'fa-cloud' : 'fa-cloud-sun';
            document.getElementById('weatherDisplay').innerHTML =
                `<i class="fa-solid ${icon}"></i> ${Math.round(weather.temperature)} C`;
        })
        .catch(() => {
            document.getElementById('weatherDisplay').innerHTML = '<i class="fa-solid fa-cloud-sun"></i> Mathenge TTI';
        });
}

function treePopup(record) {
    return `
        <div class="tree-popup-card">
            <img src="${photoUrl(record.photo)}" alt="${escapeHtml(record.species || 'Tree photo')}">
            <div class="popup-meta">
                <span>Tree ID</span>
                <strong>${escapeHtml(record.treeId || record.id)}</strong>
            </div>
            <div class="popup-grid">
                <span>Species</span><strong>${escapeHtml(record.species || 'Tree')}</strong>
                <span>Date planted</span><strong>${formatShortDate(record.timestamp)}</strong>
                <span>Volunteer</span><strong>${escapeHtml(record.name || 'Volunteer')}</strong>
                <span>Survival status</span><strong>${escapeHtml(record.status || 'Pending')}</strong>
            </div>
        </div>
    `;
}

function getZoneStats() {
    const stats = new Map();
    Array.from(displayState.records.values()).forEach(record => {
        const zoneName = record.zone || 'Other';
        const current = stats.get(zoneName) || { trees: 0 };
        current.trees += Number(record.quantity || 1);
        stats.set(zoneName, current);
    });
    return stats;
}

function normalizeSocketRecord(data) {
    const lat = Number(data.lat);
    const lng = Number(data.lng);
    if (Number.isNaN(lat) || Number.isNaN(lng)) return null;
    return {
        id: data.record_number,
        name: data.full_name,
        role: data.role,
        species: data.tree_species,
        quantity: Number(data.quantity || 1),
        zone: data.planting_zone,
        photo: data.photo_path,
        lat,
        lng,
        timestamp: data.timestamp,
        status: 'Pending',
        co2: data.co2_saved
    };
}

function hasCoordinates(record) {
    return !Number.isNaN(Number(record.lat)) && !Number.isNaN(Number(record.lng));
}

function expandTreePoints(records) {
    const maxRenderedTrees = 8000;
    const points = [];
    for (const record of records) {
        const quantity = Math.max(Number(record.quantity || 1), 1);
        for (let index = 0; index < quantity && points.length < maxRenderedTrees; index += 1) {
            const offset = treeOffset(record.id, index);
            points.push({
                ...record,
                treeId: `${record.id}-${String(index + 1).padStart(3, '0')}`,
                lat: Number(record.lat) + offset.lat,
                lng: Number(record.lng) + offset.lng,
                quantity: 1
            });
        }
        if (points.length >= maxRenderedTrees) break;
    }
    return points;
}

function treeOffset(seed, index) {
    if (index === 0) return { lat: 0, lng: 0 };
    const base = hashCode(`${seed}-${index}`);
    const angle = (base % 360) * Math.PI / 180;
    const ring = Math.floor(Math.sqrt(index));
    const distance = Math.min(0.000018 * ring, 0.00009);
    return {
        lat: Math.sin(angle) * distance,
        lng: Math.cos(angle) * distance
    };
}

function hashCode(value) {
    let hash = 0;
    const text = String(value);
    for (let index = 0; index < text.length; index += 1) {
        hash = ((hash << 5) - hash) + text.charCodeAt(index);
        hash |= 0;
    }
    return Math.abs(hash);
}

function speciesColor(species) {
    const name = String(species || '').toLowerCase();
    if (name.includes('moringa')) return '#4f9f46';
    if (name.includes('jacaranda')) return '#558f5a';
    if (name.includes('acacia')) return '#2f8f4e';
    if (name.includes('baobab')) return '#287047';
    return '#1f9d55';
}

function zoneFillColor(completion) {
    if (completion >= 75) return '#1f7a4a';
    if (completion >= 40) return '#4f9f46';
    return '#84c98d';
}

function photoUrl(path) {
    return path ? `/static/${encodeURI(path)}` : 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22240%22 height=%22160%22 viewBox=%220 0 240 160%22%3E%3Crect width=%22240%22 height=%22160%22 fill=%22%23eef5ee%22/%3E%3Ccircle cx=%22120%22 cy=%2272%22 r=%2228%22 fill=%22%2384c98d%22/%3E%3Cpath d=%22M120 76v40%22 stroke=%22%231f6b45%22 stroke-width=%228%22 stroke-linecap=%22round%22/%3E%3C/svg%3E';
}

function setConnectionState(connected) {
    const state = document.getElementById('connectionState');
    if (!state) return;
    state.classList.toggle('offline', !connected);
    state.innerHTML = connected
        ? '<i class="fa-solid fa-circle"></i> Live'
        : '<i class="fa-solid fa-triangle-exclamation"></i> Reconnecting';
}

function formatNumber(num) {
    return Number(num || 0).toLocaleString();
}

function formatShortDate(value) {
    if (!value) return 'Pending';
    return new Date(value).toLocaleDateString([], {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
    });
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}
