// Operations Hub JavaScript - Green Ledger Admin Panel

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

const PHOTO_PLACEHOLDER = 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22240%22 height=%22160%22 viewBox=%220 0 240 160%22%3E%3Crect width=%22240%22 height=%22160%22 fill=%22%23eef5ee%22/%3E%3Ccircle cx=%22120%22 cy=%2272%22 r=%2228%22 fill=%22%2384c98d%22/%3E%3Cpath d=%22M120 76v40%22 stroke=%22%231f6b45%22 stroke-width=%228%22 stroke-linecap=%22round%22/%3E%3C/svg%3E';

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

    const deleteAllBtn = document.getElementById('deleteAllRecords');
    if (deleteAllBtn) {
        deleteAllBtn.addEventListener('click', deleteAllParticipants);
    }

    const adminForm = document.getElementById('adminParticipantForm');
    if (adminForm) {
        adminForm.addEventListener('submit', submitAdminParticipant);
        const photoInput = adminForm.querySelector('input[name="photos"]');
        if (photoInput) photoInput.addEventListener('change', () => renderAdminPhotoPreview(photoInput.files));
    }

    const importForm = document.getElementById('participantImportForm');
    if (importForm) {
        importForm.addEventListener('submit', extractParticipantDrafts);
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

function participantPhotoUrl(participant) {
    const gallery = participantPhotoUrls(participant);
    const path = gallery[0] || participant?.photo_url || participant?.photo_path;
    if (!path) return PHOTO_PLACEHOLDER;
    const value = String(path);
    if (/^(data:|blob:|https?:\/\/|\/)/i.test(value)) return value;

    const normalized = value.replace(/\\/g, '/').replace(/^static\//, '');
    return `/static/${normalized.split('/').map(encodeURIComponent).join('/')}?v=${encodeURIComponent(participant?.timestamp || Date.now())}`;
}

function participantPhotoUrls(participant) {
    const paths = Array.isArray(participant?.photo_urls) && participant.photo_urls.length
        ? participant.photo_urls
        : (Array.isArray(participant?.photos) ? participant.photos : []);
    return paths.map(path => {
        const value = String(path);
        if (/^(data:|blob:|https?:\/\/|\/)/i.test(value)) return value;
        const normalized = value.replace(/\\/g, '/').replace(/^static\//, '');
        return `/static/${normalized.split('/').map(encodeURIComponent).join('/')}?v=${encodeURIComponent(participant?.timestamp || Date.now())}`;
    });
}

function rejectionLabel(participant) {
    if (participant.status !== 'Rejected') return '';
    const labels = {
        photo: 'Photo rejected',
        details: 'Data rejected',
        all: 'Photo + data rejected'
    };
    return labels[participant.rejection_scope] || 'Rejected';
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
        const photoUrl = participantPhotoUrl(p);
        
        html += `
            <div class="participant-item ${isVIP ? 'vip' : ''}" data-id="${p.id}">
                <div class="participant-info">
                    <img src="${photoUrl}" alt="${escapeHtml(p.full_name)}" class="participant-photo"
                         loading="lazy" decoding="async" onerror="this.onerror=null;this.src='${PHOTO_PLACEHOLDER}'">
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
                            <span>${formatNumber(p.student_count || 1)} planters</span>
                            <span>|</span>
                            <span>${escapeHtml(p.manual_location_name || p.planting_zone)}</span>
                        </div>
                        <div class="participant-time">${formatDate(p.timestamp)}</div>
                    </div>
                </div>
                <div class="participant-actions">
                    <span class="status-badge ${statusClass}">${escapeHtml(rejectionLabel(p) || p.status)}</span>
                    <button onclick="viewParticipant('${p.id}')" class="btn btn-sm btn-primary">
                        <i class="fa-solid fa-eye"></i> Details
                    </button>
                    <button onclick="editParticipant('${p.id}')" class="btn btn-sm btn-secondary">
                        <i class="fa-solid fa-pen"></i> Edit
                    </button>
                    ${p.status !== 'Verified' ? `
                        <button onclick="verifyParticipant('${p.id}', 'Verified')" class="btn btn-sm btn-success">
                            <i class="fa-solid fa-check"></i> Approve
                        </button>
                    ` : ''}
                    <button onclick="verifyParticipant('${p.id}', 'Rejected', 'photo', 'Photo rejected by admin')" class="btn btn-sm btn-warning">
                        <i class="fa-solid fa-image"></i> Reject Photo
                    </button>
                    <button onclick="verifyParticipant('${p.id}', 'Rejected', 'details', 'Tree data rejected by admin')" class="btn btn-sm btn-danger">
                        <i class="fa-solid fa-list-check"></i> Reject Data
                    </button>
                    <button onclick="verifyParticipant('${p.id}', 'Rejected', 'all', 'Photo and tree data rejected by admin')" class="btn btn-sm btn-danger">
                        <i class="fa-solid fa-ban"></i> Reject Both
                    </button>
                    <button onclick="${isVIP ? `unpinParticipant('${p.id}')` : `pinParticipant('${p.id}')`}" class="btn btn-sm btn-warning">
                        <i class="fa-solid fa-thumbtack"></i> ${isVIP ? 'Unpin' : 'Pin'}
                    </button>
                    <button onclick="deleteParticipant('${p.id}')" class="btn btn-sm btn-danger">
                        <i class="fa-solid fa-trash"></i> Delete
                    </button>
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

async function verifyParticipant(id, status, rejectionScope = null, rejectionNote = '') {
    const actionLabel = status === 'Rejected'
        ? (rejectionScope === 'photo' ? 'reject this photo'
            : rejectionScope === 'details' ? 'reject this tree data'
            : 'reject this photo and tree data')
        : (status === 'Verified' ? 'approve this participant' : `${status.toLowerCase()} this participant`);

    const confirmed = await showConfirmDialog({
        title: status === 'Rejected' ? 'Reject Record' : 'Update Record',
        message: `Are you sure you want to ${actionLabel}?`,
        confirmText: status === 'Rejected' ? 'Reject' : 'Approve',
        danger: status === 'Rejected'
    });
    if (!confirmed) {
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
                <img src="${participantPhotoUrl(participant)}" alt="${escapeHtml(participant.full_name)}" class="modal-photo">
                <div class="modal-details">
                    <p><strong>${escapeHtml(participant.full_name)}</strong></p>
                    <p>${escapeHtml(participant.quantity)} x ${escapeHtml(participant.tree_species)} | ${escapeHtml(participant.planting_zone)}</p>
                    <label class="reject-option">
                        <input type="radio" name="rejectScope" value="photo" checked>
                        <span><strong>Reject photo only</strong> Hide the image but keep the tree data live.</span>
                    </label>
                    <label class="reject-option">
                        <input type="radio" name="rejectScope" value="details">
                        <span><strong>Reject data only</strong> Trees planted, species, quantity, department, or location is not real.</span>
                    </label>
                    <label class="reject-option">
                        <input type="radio" name="rejectScope" value="all">
                        <span><strong>Reject photo + data</strong> Hide the whole record from the public display.</span>
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

function unpinParticipant(id) {
    fetch(`/api/unpin/${id}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...csrfHeader()
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Official spotlight removed', 'success');
            fetchParticipants();
        } else {
            showToast('Failed to unpin participant', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Failed to unpin participant', 'error');
    });
}

async function deleteParticipant(id) {
    const participant = hubState.participants.find(p => p.id === id);
    const name = participant ? participant.full_name : 'this participant';
    const confirmed = await showConfirmDialog({
        title: 'Delete Participant',
        message: `Delete ${name} permanently? This removes the record and uploaded photos.`,
        confirmText: 'Delete',
        danger: true
    });
    if (!confirmed) {
        return;
    }

    fetch(`/api/participants/${id}`, {
        method: 'DELETE',
        headers: csrfHeader()
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Participant deleted', 'success');
            fetchParticipants();
            fetchHubStats();
        } else {
            showToast(data.error || 'Failed to delete participant', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Failed to delete participant', 'error');
    });
}

async function deleteAllParticipants() {
    const typed = await showConfirmDialog({
        title: 'Delete All Records',
        message: 'This will permanently delete every participant record and uploaded photo.',
        inputLabel: 'Type DELETE ALL RECORDS to continue',
        requiredText: 'DELETE ALL RECORDS',
        confirmText: 'Delete All',
        danger: true
    });
    if (typed !== 'DELETE ALL RECORDS') {
        showToast('Delete all cancelled', 'warning');
        return;
    }

    const finalConfirmed = await showConfirmDialog({
        title: 'Final Confirmation',
        message: 'Clear all planting records from the database now?',
        confirmText: 'Clear Database',
        danger: true
    });
    if (!finalConfirmed) {
        return;
    }

    fetch('/api/participants', {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json',
            ...csrfHeader()
        },
        body: JSON.stringify({ confirm: typed })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('All participant records deleted', 'success');
            hubState.participants = [];
            hubState.filteredParticipants = [];
            renderParticipants([]);
            fetchHubStats();
        } else {
            showToast(data.error || 'Failed to delete all records', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Failed to delete all records', 'error');
    });
}

function viewParticipant(id) {
    // Show detailed view modal
    const participant = hubState.participants.find(p => p.id === id);
    if (!participant) return;
    
    // Implementation for modal view
    showParticipantModal(participant);
}

function renderAdminPhotoPreview(files) {
    const preview = document.getElementById('adminPhotoPreview');
    if (!preview) return;
    const selected = Array.from(files || []).slice(0, 12);
    preview.innerHTML = selected.map(file => `
        <figure>
            <img src="${URL.createObjectURL(file)}" alt="${escapeHtml(file.name)}">
            <figcaption>${escapeHtml(file.name)}</figcaption>
        </figure>
    `).join('');
}

function submitAdminParticipant(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    if (button) button.disabled = true;
    fetch('/api/participants', {
        method: 'POST',
        headers: csrfHeader(),
        body: new FormData(form)
    })
    .then(response => response.json().then(data => ({ ok: response.ok, data })))
    .then(({ ok, data }) => {
        if (!ok || !data.success) throw new Error(data.error || 'Failed to add participant');
        showToast('Participant added and counted', 'success');
        form.reset();
        const count = form.querySelector('input[name="student_count"]');
        const quantity = form.querySelector('input[name="quantity"]');
        const species = form.querySelector('input[name="tree_species"]');
        const zone = form.querySelector('input[name="planting_zone"]');
        if (count) count.value = '1';
        if (quantity) quantity.value = '1';
        if (species) species.value = 'Tree';
        if (zone) zone.value = 'Admin entry';
        renderAdminPhotoPreview([]);
        fetchParticipants();
        fetchHubStats();
    })
    .catch(error => {
        showToast(error.message, 'error');
    })
    .finally(() => {
        if (button) button.disabled = false;
    });
}

function extractParticipantDrafts(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const result = document.getElementById('importResult');
    const draftsEl = document.getElementById('importDrafts');
    if (result) result.textContent = 'Extracting...';
    if (draftsEl) draftsEl.innerHTML = '';

    fetch('/api/import-participants', {
        method: 'POST',
        headers: csrfHeader(),
        body: new FormData(form)
    })
    .then(response => response.json().then(data => ({ ok: response.ok, data })))
    .then(({ ok, data }) => {
        if (!ok || !data.success) throw new Error(data.error || 'Import failed');
        if (result) {
            const fieldText = data.fields?.length ? ` Fields found: ${data.fields.join(', ')}` : '';
            result.textContent = `${data.note || 'Drafts extracted.'}${fieldText}`;
        }
        renderImportDrafts(data.drafts || []);
    })
    .catch(error => {
        if (result) result.textContent = error.message;
        showToast(error.message, 'error');
    });
}

function renderImportDrafts(drafts) {
    const container = document.getElementById('importDrafts');
    if (!container) return;
    if (!drafts.length) {
        container.innerHTML = '<div class="empty-state">No participant rows were found.</div>';
        return;
    }
    container.innerHTML = `
        <div class="import-draft-actions">
            <button type="button" class="btn btn-success btn-sm" id="saveAllDrafts">
                <i class="fa-solid fa-cloud-arrow-up"></i> Save All Drafts
            </button>
        </div>
        ${drafts.map((draft, index) => importDraftHtml(draft, index)).join('')}
    `;
    container.querySelector('#saveAllDrafts')?.addEventListener('click', saveAllImportDrafts);
    container.querySelectorAll('.save-draft').forEach(button => {
        button.addEventListener('click', () => saveImportDraft(button.closest('.import-draft')));
    });
}

function importDraftHtml(draft, index) {
    return `
        <form class="import-draft" data-index="${index}">
            <div class="form-row">
                <label>Name<input name="full_name" value="${escapeHtml(draft.full_name || '')}" required></label>
                <label>Role<input name="role" value="${escapeHtml(draft.role || 'Participant')}" required></label>
            </div>
            <div class="form-row">
                <label>Group label<input name="group_label" value="${escapeHtml(draft.group_label || '')}"></label>
                <label>Planters<input name="student_count" type="number" min="1" max="500" value="${escapeHtml(String(draft.student_count || 1))}" required></label>
            </div>
            <label>Participant names<textarea name="planter_names" rows="2">${escapeHtml(draft.planter_names || '')}</textarea></label>
            <div class="form-row">
                <label>Species<input name="tree_species" value="${escapeHtml(draft.tree_species || 'Tree')}" required></label>
                <label>Trees<input name="quantity" type="number" min="1" max="1000" value="${escapeHtml(String(draft.quantity || 1))}" required></label>
            </div>
            <div class="form-row">
                <label>Zone<input name="planting_zone" value="${escapeHtml(draft.planting_zone || 'Imported')}" required></label>
                <label>Place<input name="manual_location_name" value="${escapeHtml(draft.manual_location_name || '')}"></label>
            </div>
            <div class="form-row">
                <label>Lat<input name="latitude" type="number" step="any" value="${escapeHtml(String(draft.latitude || ''))}"></label>
                <label>Lng<input name="longitude" type="number" step="any" value="${escapeHtml(String(draft.longitude || ''))}"></label>
            </div>
            <button type="button" class="btn btn-secondary btn-sm save-draft"><i class="fa-solid fa-plus"></i> Save This Row</button>
        </form>
    `;
}

function draftFormData(form) {
    const data = {};
    new FormData(form).forEach((value, key) => {
        data[key] = value;
    });
    return data;
}

function saveImportDraft(form) {
    if (!form) return;
    const data = draftFormData(form);
    const body = new FormData();
    Object.entries(data).forEach(([key, value]) => body.append(key, value));
    body.append('status', 'Verified');
    fetch('/api/participants', {
        method: 'POST',
        headers: csrfHeader(),
        body
    })
    .then(response => response.json().then(payload => ({ ok: response.ok, payload })))
    .then(({ ok, payload }) => {
        if (!ok || !payload.success) throw new Error(payload.error || 'Failed to save draft');
        showToast('Imported row saved', 'success');
        form.remove();
        fetchParticipants();
        fetchHubStats();
    })
    .catch(error => showToast(error.message, 'error'));
}

function saveAllImportDrafts() {
    const forms = Array.from(document.querySelectorAll('.import-draft'));
    const participants = forms.map(draftFormData);
    if (!participants.length) return;
    fetch('/api/participants/bulk', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...csrfHeader()
        },
        body: JSON.stringify({ participants })
    })
    .then(response => response.json())
    .then(data => {
        if (data.created?.length) {
            showToast(`${data.created.length} imported participants saved`, 'success');
            document.getElementById('importDrafts').innerHTML = '';
            fetchParticipants();
            fetchHubStats();
        }
        if (data.errors?.length) {
            showToast(`${data.errors.length} rows need correction`, 'warning');
        }
    })
    .catch(error => showToast(error.message, 'error'));
}

function editParticipant(id) {
    const participant = hubState.participants.find(p => p.id === id);
    if (!participant) return;
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3>Edit Participant</h3>
                <button onclick="this.closest('.modal-overlay').remove()" class="modal-close" aria-label="Close">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>
            <form id="editParticipantForm" class="modal-details admin-participant-form">
                <div class="form-row">
                    <label>Name<input name="full_name" value="${escapeHtml(participant.full_name || '')}" required></label>
                    <label>Role<input name="role" value="${escapeHtml(participant.role || 'Participant')}" required></label>
                </div>
                <div class="form-row">
                    <label>Group label<input name="group_label" value="${escapeHtml(participant.group_label || '')}"></label>
                    <label>Planters<input name="student_count" type="number" min="1" max="500" value="${escapeHtml(String(participant.student_count || 1))}" required></label>
                </div>
                <label>Participant names<textarea name="planter_names" rows="2">${escapeHtml(participant.planter_names || '')}</textarea></label>
                <div class="form-row">
                    <label>Species<input name="tree_species" value="${escapeHtml(participant.tree_species || 'Tree')}" required></label>
                    <label>Trees<input name="quantity" type="number" min="1" max="1000" value="${escapeHtml(String(participant.quantity || 1))}" required></label>
                </div>
                <div class="form-row">
                    <label>Zone<input name="planting_zone" value="${escapeHtml(participant.planting_zone || 'Imported')}" required></label>
                    <label>Place<input name="manual_location_name" value="${escapeHtml(participant.manual_location_name || '')}"></label>
                </div>
                <div class="form-row">
                    <label>Lat<input name="latitude" type="number" step="any" value="${escapeHtml(String(participant.latitude || ''))}"></label>
                    <label>Lng<input name="longitude" type="number" step="any" value="${escapeHtml(String(participant.longitude || ''))}"></label>
                </div>
                <label>Status
                    <select name="status">
                        <option value="Verified" ${participant.status === 'Verified' ? 'selected' : ''}>Verified</option>
                        <option value="Pending" ${participant.status === 'Pending' ? 'selected' : ''}>Pending</option>
                        <option value="Rejected" ${participant.status === 'Rejected' ? 'selected' : ''}>Rejected</option>
                    </select>
                </label>
                <label class="admin-photo-field">Add photos
                    <input name="photos" type="file" accept="image/jpeg,image/png,image/webp" multiple>
                </label>
                <div class="actions-row">
                    <button type="submit" class="btn btn-success"><i class="fa-solid fa-floppy-disk"></i> Save Changes</button>
                    <button type="button" class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
                </div>
            </form>
        </div>
    `;
    document.body.appendChild(modal);
    const form = modal.querySelector('#editParticipantForm');
    form.addEventListener('submit', event => {
        event.preventDefault();
        fetch(`/api/participants/${id}`, {
            method: 'PUT',
            headers: csrfHeader(),
            body: new FormData(form)
        })
        .then(response => response.json().then(payload => ({ ok: response.ok, payload })))
        .then(({ ok, payload }) => {
            if (!ok || !payload.success) throw new Error(payload.error || 'Failed to update participant');
            showToast('Participant updated', 'success');
            modal.remove();
            fetchParticipants();
            fetchHubStats();
        })
        .catch(error => showToast(error.message, 'error'));
    });
}

function showParticipantModal(participant) {
    // Create and show modal with participant details
    const modal = document.createElement('div');
    const gallery = participantPhotoUrls(participant);
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
                <div class="modal-gallery">
                    ${(gallery.length ? gallery : [participantPhotoUrl(participant)]).map(url => `
                        <img src="${url}" alt="${escapeHtml(participant.full_name)}" class="modal-photo" loading="lazy" decoding="async" onerror="this.onerror=null;this.src='${PHOTO_PLACEHOLDER}'">
                    `).join('')}
                </div>
                <div class="modal-details">
                    <p><strong>Record:</strong> ${escapeHtml(participant.record_number)}</p>
                    <p><strong>Role:</strong> ${escapeHtml(participant.role)}</p>
                    <p><strong>Species:</strong> ${escapeHtml(participant.tree_species)}</p>
                    <p><strong>Quantity:</strong> ${formatNumber(participant.quantity)}</p>
                    <p><strong>Students / Planters:</strong> ${formatNumber(participant.student_count || 1)}</p>
                    <p><strong>Zone:</strong> ${escapeHtml(participant.planting_zone)}</p>
                    ${participant.manual_location_name ? `<p><strong>Selected Place:</strong> ${escapeHtml(participant.manual_location_name)}</p>` : ''}
                    ${participant.latitude && participant.longitude ? `<p><strong>Coordinates:</strong> ${Number(participant.latitude).toFixed(5)}, ${Number(participant.longitude).toFixed(5)}</p>` : ''}
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

async function createBackup() {
    const confirmed = await showConfirmDialog({
        title: 'Create Backup',
        message: 'This will create a complete backup of all data and photos.',
        confirmText: 'Create Backup'
    });
    if (!confirmed) {
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
window.unpinParticipant = unpinParticipant;
window.deleteParticipant = deleteParticipant;
window.viewParticipant = viewParticipant;
window.editParticipant = editParticipant;
window.exportData = exportData;
window.createBackup = createBackup;
