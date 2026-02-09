/**
 * Toast Notification System
 * Neomorphic Design - Early Warning System
 */

class ToastNotification {
    constructor() {
        this.container = null;
        this.init();
    }

    init() {
        // Create toast container if it doesn't exist
        if (!document.querySelector('.toast-container')) {
            this.container = document.createElement('div');
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        } else {
            this.container = document.querySelector('.toast-container');
        }
    }

    show(message, type = 'success', duration = 4000) {
        const icons = {
            success: 'fa-check-circle',
            error: 'fa-exclamation-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle'
        };

        const titles = {
            success: 'Success',
            error: 'Error',
            warning: 'Warning',
            info: 'Information'
        };

        // Create toast element
        const toast = document.createElement('div');
        toast.className = `neo-toast ${type}`;
        toast.innerHTML = `
            <i class="fas ${icons[type]} neo-toast-icon"></i>
            <div class="neo-toast-content">
                <div class="neo-toast-title">${titles[type]}</div>
                <div class="neo-toast-message">${message}</div>
            </div>
            <button class="neo-toast-close" aria-label="Close notification">
                <i class="fas fa-times"></i>
            </button>
        `;

        // Add to container
        this.container.appendChild(toast);

        // Close button handler
        const closeBtn = toast.querySelector('.neo-toast-close');
        closeBtn.addEventListener('click', () => this.hide(toast));

        // Auto-hide after duration
        if (duration > 0) {
            setTimeout(() => this.hide(toast), duration);
        }

        return toast;
    }

    hide(toast) {
        toast.classList.add('hiding');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }

    success(message, duration) {
        return this.show(message, 'success', duration);
    }

    error(message, duration) {
        return this.show(message, 'error', duration);
    }

    warning(message, duration) {
        return this.show(message, 'warning', duration);
    }

    info(message, duration) {
        return this.show(message, 'info', duration);
    }
}

// Initialize global toast instance
const toast = new ToastNotification();

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ToastNotification;
}
