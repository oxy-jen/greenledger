const displayState = {
    map: null,
    markers: new Map(),
    milestones: [10, 25, 50, 100, 200, 500, 1000]
};
const EVENT_LOCATION = {
    name: 'Mathenge TTI, Othaya',
    lat: -0.5084917,
    lng: 36.8919167
};

document.addEventListener('DOMContentLoaded', () => {
    setupThemeToggle();
    setupClock();
    setupMap();
    setupSocket();
    refreshDisplay();
    setupWeather();

    setInterval(refreshDisplay, 5000);
    setInterval(setupWeather, 600000);
});

function setupThemeToggle() {
    const toggle = document.getElementById('displayThemeToggle');
    const savedTheme = localStorage.getItem('greenledger-display-theme');
    if (savedTheme === 'neon') {
        document.body.classList.add('neon-mode');
    }
    if (!toggle) return;
    toggle.addEventListener('click', () => {
        document.body.classList.toggle('neon-mode');
        localStorage.setItem(
            'greenledger-display-theme',
            document.body.classList.contains('neon-mode') ? 'neon' : 'light'
        );
    });
}

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
        minZoom: 15,
        zoomControl: true,
        attributionControl: false
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19
    }).addTo(displayState.map);

    L.circle([EVENT_LOCATION.lat, EVENT_LOCATION.lng], {
        radius: 220,
        color: '#2f7d55',
        weight: 2,
        fillColor: '#6fb35a',
        fillOpacity: 0.16
    }).addTo(displayState.map);

    L.marker([EVENT_LOCATION.lat, EVENT_LOCATION.lng], {
        icon: L.divIcon({
            className: 'campus-map-marker',
            html: '<i class="fa-solid fa-location-dot"></i>',
            iconSize: [38, 38],
            iconAnchor: [19, 34]
        })
    }).addTo(displayState.map).bindPopup('Mathenge TTI planting area');
}

function setupSocket() {
    const socket = io();
    socket.on('new_planting', data => {
        addFeedItem({
            name: data.full_name,
            role: data.role,
            species: data.tree_species,
            quantity: data.quantity,
            photo: data.photo_path,
            vip: Boolean(data.is_vip),
            zone: data.planting_zone,
            lat: data.lat,
            lng: data.lng,
            timestamp: data.timestamp,
            record_number: data.record_number
        }, true);
        addMarker(data);
        refreshDisplay();
    });

    socket.on('participant_verified', data => {
        addSystemMessage(`${data.full_name} marked ${data.status}`);
        if (data.status === 'Rejected') {
            removeMarker(data.record_number || data.id);
            refreshDisplay();
        }
    });
}

function refreshDisplay() {
    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            updateStats(data);
            updateLeaderboard(data.leaderboard || []);
            updateFeed(data.recent || []);
            updateGallery(data.recent || []);
            updateMap(data.recent || []);
            updateTreeOfMoment();
        })
        .catch(() => {});
}

function updateStats(data) {
    setText('treeCounter', formatNumber(data.trees));
    setText('participantCounter', formatNumber(data.participants));
    setText('participantSessionCount', formatNumber(data.participants));
    setText('co2Counter', `${formatNumber(Math.round(data.co2))} kg CO2`);
}

function updateLeaderboard(leaderboard) {
    const panel = document.querySelector('#departmentLeaderboard');
    if (!panel) return;

    if (!leaderboard.length) {
        panel.innerHTML = '<div class="empty-state">Rankings appear after submissions.</div>';
        return;
    }

    const max = Math.max(...leaderboard.map(item => item.total), 1);
    panel.innerHTML = leaderboard.map((item, index) => `
        <div class="leader-row">
            <strong>${index + 1}</strong>
            <span class="leader-name">${escapeHtml(item.role)}</span>
            <span class="leader-count">${formatNumber(item.total)}</span>
            <div class="bar"><span style="width: ${(item.total / max) * 100}%"></span></div>
        </div>
    `).join('');
}

function updateFeed(recent) {
    const feed = document.getElementById('liveFeed');
    if (!recent.length) {
        feed.innerHTML = '<div class="empty-state">Waiting for participant submissions.</div>';
        return;
    }
    feed.innerHTML = '';
    recent.slice(0, 8).forEach(item => addFeedItem(item, false));
}

function addFeedItem(item, prepend) {
    const feed = document.getElementById('liveFeed');
    const empty = feed.querySelector('.empty-state');
    if (empty) empty.remove();

    const node = document.createElement('div');
    node.className = `feed-item ${item.vip ? 'vip' : ''}`;
    node.innerHTML = `
        <img src="${photoUrl(item.photo)}" class="feed-image" alt="${escapeHtml(item.name)}">
        <div>
            <div class="feed-name">${escapeHtml(item.name || 'Participant')}</div>
            <div class="feed-details">planted ${formatNumber(item.quantity || 0)} ${escapeHtml(item.species || 'tree')}</div>
            <div class="feed-role">${escapeHtml(item.role || 'Contributor')}</div>
        </div>
        <img src="${photoUrl(item.photo)}" class="feed-thumb" alt="">
    `;

    if (prepend) feed.prepend(node);
    else feed.appendChild(node);

    while (feed.children.length > 10) {
        feed.removeChild(feed.lastElementChild);
    }
}

function addSystemMessage(message) {
    const feed = document.getElementById('liveFeed');
    const node = document.createElement('div');
    node.className = 'feed-item';
    node.innerHTML = `<div><div class="feed-name"><i class="fa-solid fa-shield-halved"></i> ${escapeHtml(message)}</div></div>`;
    feed.prepend(node);
}

function updateGallery(recent) {
    const gallery = document.getElementById('photoGallery');
    if (!recent.length) {
        gallery.innerHTML = '<div class="empty-state">Photos arrive from real submissions.</div>';
        return;
    }

    gallery.innerHTML = recent
        .filter(item => item.photo)
        .slice(0, 12)
        .map(item => `<img src="${photoUrl(item.photo)}" alt="${escapeHtml(item.name)}">`)
        .join('');
}

function updateMap(recent) {
    const visibleIds = new Set(recent.map(item => item.record_number).filter(Boolean));
    displayState.markers.forEach((marker, id) => {
        if (!visibleIds.has(id)) {
            marker.remove();
            displayState.markers.delete(id);
        }
    });

    recent.forEach(item => addMarker({
        id: item.record_number,
        full_name: item.name,
        role: item.role,
        tree_species: item.species,
        quantity: item.quantity,
        photo_path: item.photo,
        is_vip: item.vip,
        lat: item.lat,
        lng: item.lng
    }));
}

function addMarker(item) {
    const lat = Number(item.lat);
    const lng = Number(item.lng);
    const id = item.id || item.record_number;
    if (!displayState.map || !id || Number.isNaN(lat) || Number.isNaN(lng)) return;
    if (displayState.markers.has(id)) return;

    const marker = L.marker([lat, lng], {
        icon: L.divIcon({
            className: `tree-map-marker ${item.is_vip ? 'vip' : ''}`,
            html: '<i class="fa-solid fa-tree"></i>',
            iconSize: [34, 42],
            iconAnchor: [17, 38],
            popupAnchor: [0, -34]
        })
    }).addTo(displayState.map);

    marker.bindPopup(`
        <div class="map-popup">
            <img src="${photoUrl(item.photo_path)}" alt="">
            <strong>${escapeHtml(item.full_name || 'Participant')}</strong>
            <span>${escapeHtml(item.role || '')}</span>
            <span>${formatNumber(item.quantity || 0)} x ${escapeHtml(item.tree_species || 'Tree')}</span>
        </div>
    `);

    displayState.markers.set(id, marker);
    const allMarkers = Array.from(displayState.markers.values());
    if (allMarkers.length > 1) {
        displayState.map.fitBounds(L.featureGroup(allMarkers).getBounds().pad(0.18), { maxZoom: 17 });
    } else {
        displayState.map.setView([lat, lng], 16);
    }
}

function removeMarker(id) {
    if (!id || !displayState.markers.has(id)) return;
    displayState.markers.get(id).remove();
    displayState.markers.delete(id);
}

function updateTreeOfMoment() {
    const container = document.getElementById('treeOfTheMoment');
    if (!container) return;

    fetch('/api/tree-of-the-moment')
        .then(response => response.json())
        .then(data => {
            if (!data || !data.full_name) {
                container.innerHTML = '<div class="empty-state">A real record will appear after submissions.</div>';
                return;
            }

            container.innerHTML = `
                <img src="${photoUrl(data.photo_path)}" alt="${escapeHtml(data.full_name)}">
                <div>
                    <strong>${escapeHtml(data.full_name)}</strong>
                    <span>${escapeHtml(data.role)} | ${escapeHtml(data.planting_zone)}</span><br>
                    <span>${formatNumber(data.quantity)} x ${escapeHtml(data.tree_species)}</span><br>
                    <span>${formatNumber(Math.round(data.co2_saved_kg || 0))} kg CO2 impact</span>
                </div>
            `;
        })
        .catch(() => {});
}

function setupWeather() {
    fetch(`https://api.open-meteo.com/v1/forecast?latitude=${EVENT_LOCATION.lat}&longitude=${EVENT_LOCATION.lng}&current_weather=true`)
        .then(response => response.json())
        .then(data => {
            const weather = data.current_weather;
            const icon = weather.weathercode > 2 ? 'fa-cloud' : 'fa-cloud-sun';
            document.getElementById('weatherDisplay').innerHTML =
                `<i class="fa-solid ${icon}"></i> ${Math.round(weather.temperature)} C <span>Mathenge TTI</span>`;
        })
        .catch(() => {
            document.getElementById('weatherDisplay').innerHTML = '<i class="fa-solid fa-cloud-sun"></i> Mathenge TTI';
        });
}

function photoUrl(path) {
    return path ? `/static/${path}` : 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2280%22 height=%2280%22 viewBox=%220 0 80 80%22%3E%3Crect width=%2280%22 height=%2280%22 fill=%22%23e6eee4%22/%3E%3Cpath d=%22M40 16c8 7 13 15 13 23a13 13 0 1 1-26 0c0-8 5-16 13-23Z%22 fill=%22%235d8f48%22/%3E%3Cpath d=%22M40 40v20%22 stroke=%22%23244f32%22 stroke-width=%224%22 stroke-linecap=%22round%22/%3E%3C/svg%3E';
}

function formatNumber(num) {
    return Number(num || 0).toLocaleString();
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
