// Main JavaScript for Green Ledger

// Utility functions
function formatNumber(num) {
    return String(num ?? 0).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function formatDate(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    }[char]));
}

// Toast notifications
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = 'toast';
    
    if (type === 'success') {
        toast.style.backgroundColor = '#15803d';
    } else if (type === 'error') {
        toast.style.backgroundColor = '#dc2626';
    } else if (type === 'warning') {
        toast.style.backgroundColor = '#d97706';
    }
    
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function showConfirmDialog({
    title = 'Confirm action',
    message = '',
    confirmText = 'Continue',
    cancelText = 'Cancel',
    danger = false,
    inputLabel = '',
    requiredText = ''
} = {}) {
    return new Promise(resolve => {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay app-dialog-overlay';
        modal.innerHTML = `
            <div class="modal-content app-dialog" role="dialog" aria-modal="true" aria-labelledby="appDialogTitle">
                <div class="modal-header">
                    <h3 id="appDialogTitle">${escapeHtml(title)}</h3>
                    <button type="button" class="modal-close" aria-label="Close">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </div>
                <div class="app-dialog-body">
                    ${message ? `<p>${escapeHtml(message)}</p>` : ''}
                    ${requiredText ? `
                        <label class="field app-dialog-field">
                            <span>${escapeHtml(inputLabel || `Type ${requiredText} to continue`)}</span>
                            <input type="text" class="app-dialog-input" autocomplete="off">
                        </label>
                    ` : ''}
                    <div class="actions-row app-dialog-actions">
                        <button type="button" class="btn btn-secondary app-dialog-cancel">${escapeHtml(cancelText)}</button>
                        <button type="button" class="btn ${danger ? 'btn-danger' : 'btn-primary'} app-dialog-confirm">
                            ${escapeHtml(confirmText)}
                        </button>
                    </div>
                </div>
            </div>
        `;

        const close = value => {
            modal.remove();
            resolve(value);
        };
        const input = modal.querySelector('.app-dialog-input');
        const confirmBtn = modal.querySelector('.app-dialog-confirm');
        const validate = () => {
            if (!requiredText || !input) return;
            confirmBtn.disabled = input.value !== requiredText;
        };

        modal.querySelector('.modal-close').addEventListener('click', () => close(false));
        modal.querySelector('.app-dialog-cancel').addEventListener('click', () => close(false));
        confirmBtn.addEventListener('click', () => {
            if (requiredText && input?.value !== requiredText) return;
            close(requiredText ? input.value : true);
        });
        modal.addEventListener('click', event => {
            if (event.target === modal) close(false);
        });
        modal.addEventListener('keydown', event => {
            if (event.key === 'Escape') close(false);
            if (event.key === 'Enter' && !confirmBtn.disabled) confirmBtn.click();
        });

        document.body.appendChild(modal);
        validate();
        (input || confirmBtn).focus();
        if (input) input.addEventListener('input', validate);
    });
}

// File upload preview
function previewImage(input) {
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const preview = document.getElementById('imagePreview');
            if (preview) {
                preview.src = e.target.result;
                preview.style.display = 'block';
            }
        }
        reader.readAsDataURL(input.files[0]);
    }
}

// Form validation
function validateForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return true;
    
    const inputs = form.querySelectorAll('input[required], select[required]');
    let valid = true;
    
    inputs.forEach(input => {
        if (!input.value.trim()) {
            input.style.borderColor = '#dc2626';
            valid = false;
        } else {
            input.style.borderColor = '#d1d5db';
        }
    });
    
    return valid;
}

// Geo location
function getCurrentLocation() {
    return new Promise((resolve, reject) => {
        if (!navigator.geolocation) {
            reject('Geolocation not supported');
            return;
        }
        
        navigator.geolocation.getCurrentPosition(
            position => resolve(position),
            error => reject(error)
        );
    });
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Auto-hide flash messages
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.opacity = '0';
            setTimeout(() => message.remove(), 300);
        }, 5000);
    });
    
    // File input preview
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(input => {
        input.addEventListener('change', function() {
            previewImage(this);
        });
    });
});
