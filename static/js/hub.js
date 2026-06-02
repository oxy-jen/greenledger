// Operations Hub JavaScript - RootLedger Admin Panel

// Global state
let hubState = {
    participants: [],
    filteredParticipants: [],
    currentFilter: 'all',
    searchQuery: '',
    stats: {
        trees: 0,
        participants: 0,
        co2: 0,
        pending: 0
    },
    selectedParticipant: null
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    initializeHub();
    setupEventListeners();
    startRealtimeUpdates();
});

function initializeHub() {
    // Load initial data
    fetchHubStats();
    fetchParticipants();
    setupCharts();
    
    // Set up verification modal
    setupVerificationModal();
}

function csrfHeader() {
    const token = document.querySelector('meta[name="csrf-token"]')?.content;
    return token ? { 'X-CSRF-Token': token } : {};
}

function setupEventListeners() {
    // Search functionality
    const searchInput = document.getElementById('participantSearch');
    if (searchInput) {
        searchInput.addEventListener('input', function(e) {
            hubState.searchQuery = e.target.value.toLowerCase();
            filterParticipants();
        });
    }
    
    // Filter buttons
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(btn => {
        btn.addEventListener('click', function() {
            filterButtons.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            hubState.currentFilter = this.dataset.filter;
            filterParticipants();
        });
    });
    
    // Export buttons
    document.querySelectorAll('.export-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const format = this.dataset.format;
            exportData(format);
        });
    });
    
    // Backup button
    const backupBtn = document.getElementById('createBackup');
    if (backupBtn) {
        backupBtn.addEventListener('click', createBackup);
    }
}

function fetchHubStats() {
    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            hubState.stats = data;
            updateStatsDisplay(data);
        })
        .catch(error => {
            console.error('Error fetching stats:', error);
            showToast('Failed to load statistics', 'error');
        });
}

function updateStatsDisplay(data) {
    // Update main stat cards
    const elements = {
        totalTrees: document.getElementById('totalTrees'),
        totalParticipants: document.getElementById('totalParticipants'),
        totalCO2: document.getElementById('totalCO2'),
        pendingVerification: document.getElementById('pendingVerification')
    };
    
    if (elements.totalTrees) elements.totalTrees.textContent = formatNumber(data.trees);
    if (elements.totalParticipants) elements.totalParticipants.textContent = formatNumber(data.participants);
    if (elements.totalCO2) elements.totalCO2.textContent = formatNumber(Math.round(data.co2)) + ' kg';
    
    // Calculate pending from participants list
    const pendingCount = hubState.participants.filter(p => p.status === 'Pending').length;
    if (elements.pendingVerification) elements.pendingVerification.textContent = pendingCount;
}

function fetchParticipants() {
    fetch('/api/participants')
        .then(response => response.json())
        .then(data => {
            hubState.participants = data;
            hubState.filteredParticipants = data;
            renderParticipants(data);
            updateStatsDisplay(hubState.stats);
        })
        .catch(error => {
            console.error('Error fetching participants:', error);
            showToast('Failed to load participants', 'error');
        });
}

function renderParticipants(participants) {
    const container = document.getElementById('participantList');
    if (!container) return;
    
    if (!participants || participants.length === 0) {
        container.innerHTML = `
            <div class="text-center py-8 text-gray-500">
                <i class="fa-solid fa-seedling" style="font-size: 32px; color: var(--leaf);"></i>
                <p>No participants yet</p>
                <p class="text-sm">Start planting to see records here</p>
            </div>
        `;
        return;
    }
    
    let html = '';
    participants.forEach((p, index) => {
        const statusClass = p.status === 'Verified' ? 'status-verified' : 
                           p.status === 'Rejected' ? 'status-rejected' : 'status-pending';
        const isVIP = p.is_vip === 1 || p.is_vip === true;
        const photoUrl = p.photo_path ? `/static/${encodeURI(p.photo_path)}` : '/static/images/placeholder.jpg';
        
        html += `
            <div class="participant-item ${isVIP ? 'vip' : ''}" data-id="${p.id}">
                <div class="participant-info">
                    <img src="${photoUrl}" alt="${escapeHtml(p.full_name)}" class="participant-photo"
                         onerror="this.src='/static/images/placeholder.jpg'">
                    <div class="participant-details">
                        <div class="participant-name">
                            ${escapeHtml(p.full_name)}
                            ${isVIP ? '<span class="status-badge status-pending"><i class="fa-solid fa-star"></i> VIP</span>' : ''}
                        </div>
                        <div class="participant-meta">
                            <span>${escapeHtml(p.role)}</span>
                            <span>|</span>
                            <span>${formatNumber(p.quantity)} x ${escapeHtml(p.tree_species)}</span>
                            <span>|</span>
                            <span>${escapeHtml(p.planting_zone)}</span>
                        </div>
                        <div class="participant-time">${formatDate(p.timestamp)}</div>
                    </div>
                </div>
                <div class="participant-actions">
                    <span class="status-badge ${statusClass}">${escapeHtml(p.status)}</span>
                    ${p.status === 'Pending' ? `
                        <button onclick="verifyParticipant('${p.id}', 'Verified')" class="btn btn-sm btn-success">
                            <i class="fa-solid fa-check"></i> Approve
                        </button>
                        <button onclick="openRejectModal('${p.id}')" class="btn btn-sm btn-danger">
                            <i class="fa-solid fa-xmark"></i> Reject
                        </button>
                        <button onclick="pinParticipant('${p.id}')" class="btn btn-sm btn-warning">
                            <i class="fa-solid fa-thumbtack"></i> Pin
                        </button>
                    ` : `
                        <button onclick="viewParticipant('${p.id}')" class="btn btn-sm btn-primary">
                            View
                        </button>
                    `}
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

function filterParticipants() {
    let filtered = hubState.participants;
    
    // Apply status filter
    if (hubState.currentFilter !== 'all') {
        filtered = filtered.filter(p => p.status === hubState.currentFilter);
    }
    
    // Apply search filter
    if (hubState.searchQuery) {
        filtered = filtered.filter(p => 
            p.full_name.toLowerCase().includes(hubState.searchQuery) ||
            p.role.toLowerCase().includes(hubState.searchQuery) ||
            p.tree_species.toLowerCase().includes(hubState.searchQuery) ||
            p.record_number.toLowerCase().includes(hubState.searchQuery)
        );
    }
    
    hubState.filteredParticipants = filtered;
    renderParticipants(filtered);
}

function verifyParticipant(id, status, rejectionScope = null, rejectionNote = '') {
    if (status !== 'Rejected' && !confirm(`Are you sure you want to ${status.toLowerCase()} this participant?`)) {
        return;
    }
    
    fetch(`/api/verify/${id}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...csrfHeader()
        },
        body: JSON.stringify({
            status: status,
            rejection_scope: rejectionScope,
            rejection_note: rejectionNote
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast(`Participant ${status.toLowerCase()} successfully`, 'success');
            fetchParticipants();
            fetchHubStats();
        } else {
            showToast('Failed to update status', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Failed to update status', 'error');
    });
}

function openRejectModal(id) {
    const participant = hubState.participants.find(p => p.id === id);
    if (!participant) return;

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal-content reject-modal">
            <div class="modal-header">
                <h3>Reject Record</h3>
                <button onclick="this.closest('.modal-overlay').remove()" class="modal-close" aria-label="Close">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>
            <div class="reject-body">
                <img src="/static/${encodeURI(participant.photo_path)}" alt="${escapeHtml(participant.full_name)}" class="modal-photo">
                <div class="modal-details">
                    <p><strong>${escapeHtml(participant.full_name)}</strong></p>
                    <p>${escapeHtml(participant.quantity)} x ${escapeHtml(participant.tree_species)} | ${escapeHtml(participant.planting_zone)}</p>
                    <label class="reject-option">
                        <input type="radio" name="rejectScope" value="photo" checked>
                        <span><strong>Reject photo only</strong> Photo is unclear, fake, repeated, or not the planted tree.</span>
                    </label>
                    <label class="reject-option">
                        <input type="radio" name="rejectScope" value="details">
                        <span><strong>Reject details only</strong> Tree name, quantity, department, or zone is wrong.</span>
                    </label>
                    <label class="reject-option">
                        <input type="radio" name="rejectScope" value="all">
                        <span><strong>Reject all</strong> The whole planting record should be removed from the live display.</span>
                    </label>
                    <textarea id="rejectNote" class="reject-note" rows="3" placeholder="Optional admin note"></textarea>
                    <div class="actions-row">
                        <button type="button" class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
                        <button type="button" class="btn btn-danger" id="confirmReject">
                            <i class="fa-solid fa-ban"></i> Reject and Hide
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    modal.querySelector('#confirmReject').addEventListener('click', () => {
        const scope = modal.querySelector('input[name="rejectScope"]:checked').value;
        const note = modal.querySelector('#rejectNote').value.trim();
        verifyParticipant(id, 'Rejected', scope, note);
        modal.remove();
    });

    modal.addEventListener('click', function(e) {
        if (e.target === this) this.remove();
    });
}

function pinParticipant(id) {
    fetch(`/api/pin/${id}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...csrfHeader()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Participant pinned to spotlight!', 'success');
            fetchParticipants();
        } else {
            showToast('Failed to pin participant', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Failed to pin participant', 'error');
    });
}

function viewParticipant(id) {
    // Show detailed view modal
    const participant = hubState.participants.find(p => p.id === id);
    if (!participant) return;
    
    // Implementation for modal view
    showParticipantModal(participant);
}

function showParticipantModal(participant) {
    // Create and show modal with participant details
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3>${escapeHtml(participant.full_name)}</h3>
                <button onclick="this.closest('.modal-overlay').remove()" class="modal-close" aria-label="Close">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>
            <div class="modal-body">
                <img src="/static/${encodeURI(participant.photo_path)}" alt="${escapeHtml(participant.full_name)}" class="modal-photo">
                <div class="modal-details">
                    <p><strong>Record:</strong> ${escapeHtml(participant.record_number)}</p>
                    <p><strong>Role:</strong> ${escapeHtml(participant.role)}</p>
                    <p><strong>Species:</strong> ${escapeHtml(participant.tree_species)}</p>
                    <p><strong>Quantity:</strong> ${formatNumber(participant.quantity)}</p>
                    <p><strong>Zone:</strong> ${escapeHtml(participant.planting_zone)}</p>
                    <p><strong>CO2 Saved:</strong> ${formatNumber(Math.round(participant.co2_saved_kg || 0))} kg</p>
                    <p><strong>Status:</strong> ${escapeHtml(participant.status)}</p>
                    ${participant.rejection_scope ? `<p><strong>Rejected Part:</strong> ${escapeHtml(participant.rejection_scope)}</p>` : ''}
                    ${participant.rejection_note ? `<p><strong>Admin Note:</strong> ${escapeHtml(participant.rejection_note)}</p>` : ''}
                    <p><strong>Time:</strong> ${formatDate(participant.timestamp)}</p>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    
    // Close on click outside
    modal.addEventListener('click', function(e) {
        if (e.target === this) {
            this.remove();
        }
    });
}

function setupCharts() {
    // Setup department leaderboard chart
    const ctx = document.getElementById('departmentChart');
    if (!ctx) return;
    
    const chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Trees Planted',
                data: [],
                backgroundColor: 'rgba(34, 197, 94, 0.5)',
                borderColor: 'rgb(34, 197, 94)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true
                }
            },
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });
    
    // Update chart with data
    updateDepartmentChart(chart);
}

function updateDepartmentChart(chart) {
    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            const labels = data.leaderboard.map(item => item.role);
            const values = data.leaderboard.map(item => item.total);
            
            chart.data.labels = labels;
            chart.data.datasets[0].data = values;
            chart.update();
        })
        .catch(error => {
            console.error('Error updating chart:', error);
        });
}

function setupVerificationModal() {
    // Setup verification detail modal
    const modal = document.getElementById('verificationModal');
    if (!modal) return;
    
    // Handle verification actions
    modal.querySelectorAll('.verify-action').forEach(btn => {
        btn.addEventListener('click', function() {
            const action = this.dataset.action;
            const participantId = modal.dataset.participantId;
            verifyParticipant(participantId, action);
            modal.style.display = 'none';
        });
    });
}

function exportData(format) {
    window.location.href = `/export?format=${format}`;
}

function createBackup() {
    if (!confirm('This will create a complete backup of all data and photos. Continue?')) {
        return;
    }
    
    const btn = document.getElementById('createBackup');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Creating backup...';
    }
    
    fetch('/backup/create', {
        method: 'POST',
        headers: csrfHeader()
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Backup created successfully! Downloading...', 'success');
            // Trigger download
            window.location.href = data.path;
        } else {
            showToast('Failed to create backup', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Failed to create backup', 'error');
    })
    .finally(() => {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Create Backup';
        }
    });
}

function startRealtimeUpdates() {
    // Update stats every 10 seconds
    setInterval(() => {
        fetchHubStats();
        if (hubState.currentFilter === 'all') {
            fetchParticipants();
        }
    }, 10000);
    
    // Update department chart every 30 seconds
    setInterval(() => {
        const ctx = document.getElementById('departmentChart');
        if (ctx) {
            const chart = Chart.getChart(ctx);
            if (chart) {
                updateDepartmentChart(chart);
            }
        }
    }, 30000);
}

// Export functions for global use
window.verifyParticipant = verifyParticipant;
window.openRejectModal = openRejectModal;
window.pinParticipant = pinParticipant;
window.viewParticipant = viewParticipant;
window.exportData = exportData;
window.createBackup = createBackup;
