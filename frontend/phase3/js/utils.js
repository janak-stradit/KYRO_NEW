/**
 * KYRO Risk Assessment Specialist - Utility Functions
 * Common utility functions used throughout the application
 */

/**
 * Toast notification system - Professional and smooth
 */
const ToastManager = {
    activeToasts: new Set(),
    maxToasts: 3,
    
    show(type, message, title = null, duration = 4000) {
        // Prevent duplicate messages
        const toastKey = `${type}-${message}`;
        if (this.activeToasts.has(toastKey)) {
            return;
        }
        
        // Limit max toasts
        const existingToasts = $("#toastContainer .toast");
        if (existingToasts.length >= this.maxToasts) {
            existingToasts.first().remove();
        }
        
        const colors = {
            success: "bg-success",
            error: "bg-danger",
            warning: "bg-warning",
            info: "bg-info"
        };
        
        const icons = {
            success: "fas fa-check-circle",
            error: "fas fa-times-circle",
            warning: "fas fa-exclamation-triangle",
            info: "fas fa-info-circle"
        };
        
        const toastHtml = `
            <div class="toast align-items-center ${colors[type]} text-white border-0 shadow-lg" role="alert" aria-live="assertive" aria-atomic="true" style="min-width: 300px;">
                <div class="d-flex">
                    <div class="toast-body d-flex align-items-center" style="padding: 12px 16px;">
                        <i class="${icons[type]} me-3" style="font-size: 20px;"></i>
                        <div style="flex: 1;">
                            ${title ? `<div class="fw-bold mb-1" style="font-size: 14px;">${title}</div>` : ''}
                            <div style="font-size: 13px; line-height: 1.4;">${message}</div>
                        </div>
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close" style="font-size: 12px;"></button>
                </div>
            </div>
        `;
        
        const toastElement = $(toastHtml);
        $("#toastContainer").append(toastElement);
        
        this.activeToasts.add(toastKey);
        
        const toast = new bootstrap.Toast(toastElement[0], {
            delay: duration,
            animation: true
        });
        
        toast.show();
        
        // Auto-remove after animation
        const self = this;
        toastElement.on('hidden.bs.toast', function() {
            $(this).remove();
            self.activeToasts.delete(toastKey);
        });
        
        // Force remove after duration + 1 second
        setTimeout(() => {
            if (toastElement.length) {
                toastElement.remove();
                self.activeToasts.delete(toastKey);
            }
        }, duration + 1000);
    }
};

// Backward compatibility
function showToast(type, message, title = null, duration = 4000) {
    ToastManager.show(type, message, title, duration);
}

/**
 * Loading state management
 */
/**
 * Skeleton placeholders: grey blocks in the shape of the content that is on
 * its way, with a light sweep across them. Screen readers hear "Loading".
 */
const Skeleton = {
    line(width = '100%', height = 12) {
        return `<span class="sk" style="width:${width};height:${height}px"></span>`;
    },

    /** A few lines of text. */
    lines(count = 3) {
        const widths = ['96%', '88%', '72%', '92%', '64%', '84%'];
        return `<div class="sk-lines" aria-hidden="true">${Array.from({ length: count }, (_, i) => this.line(widths[i % widths.length])).join('')}</div>`;
    },

    /** Table rows, for a <tbody>. */
    rows(columns = 5, count = 6) {
        const widths = ['70%', '55%', '80%', '45%', '65%', '50%', '60%', '40%'];
        return Array.from({ length: count }, (_, r) => `
            <tr class="sk-row" aria-hidden="true">${Array.from({ length: columns }, (_, c) => `<td class="px-3 py-3">${this.line(widths[(r + c) % widths.length], 11)}</td>`).join('')}</tr>`).join('');
    },

    /** A row of summary tiles. */
    tiles(count = 4) {
        return `<div class="sk-tiles" aria-hidden="true">${Array.from({ length: count }, () => `
            <div class="sk-card">${this.line('45%', 10)}${this.line('30%', 22)}${this.line('60%', 10)}</div>`).join('')}</div>`;
    },

    /** Tile placeholders for a grid that already exists. */
    tileCards(count = 4) {
        return Array.from({ length: count }, () => `<div class="sk-card" aria-hidden="true">${this.line('45%', 10)}${this.line('30%', 22)}${this.line('60%', 10)}</div>`).join('');
    },

    /** A panel with a heading and some lines. */
    panel(lines = 5) {
        return `<div class="sk-card sk-card--panel" aria-hidden="true">${this.line('32%', 14)}${this.line('48%', 10)}<div class="sk-gap"></div>${this.lines(lines)}</div>`;
    },

    /** A whole page: heading band, tiles, two panels and a table. */
    page(label = 'Loading') {
        return `
            <div class="kyro-page sk-page" role="status" aria-busy="true">
                <span class="visually-hidden">${escapeHtml(label)}</span>
                <div class="kyro-page-head" aria-hidden="true"><div class="sk-head">${this.line('120px', 9)}${this.line('260px', 20)}${this.line('420px', 11)}</div></div>
                ${this.tiles(4)}
                <div class="sk-grid">${this.panel(5)}${this.panel(5)}</div>
                <div class="sk-card sk-card--panel" aria-hidden="true">${this.line('24%', 14)}<div class="sk-gap"></div>
                    <table class="table mb-0"><tbody>${this.rows(5, 5)}</tbody></table></div>
            </div>`;
    },

    /** A case page: header with facts and tabs, then panels. */
    casePage() {
        return `
            <div class="kyro-page cp sk-page" role="status" aria-busy="true">
                <span class="visually-hidden">Loading the case</span>
                <div class="cp-sticky" aria-hidden="true">
                    ${this.line('220px', 10)}
                    <div class="sk-casehead"><span class="sk sk--circle"></span><div>${this.line('240px', 20)}${this.line('120px', 12)}</div></div>
                    <div class="sk-facts">${Array.from({ length: 6 }, () => `<div>${this.line('70px', 9)}${this.line('110px', 13)}</div>`).join('')}</div>
                    ${this.line('100%', 34)}
                    <div class="sk-tabs">${this.line('70px', 12)}${this.line('70px', 12)}${this.line('90px', 12)}${this.line('90px', 12)}</div>
                </div>
                ${this.tiles(5)}
                ${this.panel(3)}
                <div class="sk-grid">${this.panel(6)}${this.panel(6)}</div>
            </div>`;
    }
};
window.Skeleton = Skeleton;

function showLoading(selector, message = "Loading...") {
    // The whole content area gets a page-shaped skeleton; a smaller area gets a few lines
    const html = selector === "#mainContent"
        ? Skeleton.page(message)
        : `<div role="status" aria-busy="true"><span class="visually-hidden">${escapeHtml(message)}</span>${Skeleton.lines(4)}</div>`;
    $(selector).html(html);
}

function hideLoading() {
    $("#loadingOverlay").addClass("d-none");
}

function showGlobalLoading() {
    $("#loadingOverlay").removeClass("d-none");
}

/**
 * Risk score utilities
 */
function getRiskLevel(score) {
    if (score <= 30) return "low";
    if (score <= 70) return "medium";
    return "high";
}

function getRiskColor(score) {
    const level = getRiskLevel(score);
    return {
        low: "success",
        medium: "warning", 
        high: "danger"
    }[level];
}

function getRiskBadge(score, includeScore = true) {
    const level = getRiskLevel(score);
    const labels = {
        low: "LOW",
        medium: "MEDIUM",
        high: "HIGH"
    };
    
    const colors = {
        low: "success",
        medium: "warning",
        high: "danger"
    };
    
    const text = includeScore ? `${labels[level]} (${score})` : labels[level];
    return `<span class="badge bg-${colors[level]}">${text}</span>`;
}

/**
 * Date and time formatting
 */
function formatDate(dateString, options = {}) {
    const date = new Date(dateString);
    const defaultOptions = {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        ...options
    };
    return date.toLocaleDateString('en-US', defaultOptions);
}

function formatDateTime(dateString, options = {}) {
    const date = new Date(dateString);
    const defaultOptions = {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        ...options
    };
    return date.toLocaleDateString('en-US', defaultOptions);
}

/**
 * Escape text for safe insertion into HTML template strings.
 */
function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function formatRelativeTime(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffInSeconds = Math.floor((now - date) / 1000);
    
    if (diffInSeconds < 60) return 'Just now';
    if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)} min ago`;
    if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)} hr ago`;
    if (diffInSeconds < 2592000) return `${Math.floor(diffInSeconds / 86400)} days ago`;
    
    return formatDate(dateString);
}

/**
 * Currency formatting
 */
function formatCurrency(amount, currency = 'USD', options = {}) {
    const defaultOptions = {
        style: 'currency',
        currency: currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
        ...options
    };
    
    return new Intl.NumberFormat('en-US', defaultOptions).format(amount);
}

/**
 * Number formatting
 */
function formatNumber(number, options = {}) {
    const defaultOptions = {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
        ...options
    };
    
    return new Intl.NumberFormat('en-US', defaultOptions).format(number);
}

function formatPercentage(value, decimals = 1) {
    return (value * 100).toFixed(decimals) + '%';
}

/**
 * String utilities
 */
function truncateText(text, maxLength = 50, suffix = '...') {
    if (!text || text.length <= maxLength) return text;
    return text.substring(0, maxLength - suffix.length) + suffix;
}

function highlightText(text, searchTerm) {
    if (!searchTerm) return text;
    const regex = new RegExp(`(${searchTerm})`, 'gi');
    return text.replace(regex, '<mark class="search-highlight">$1</mark>');
}

function capitalizeFirst(str) {
    return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
}

/**
 * Animation utilities
 */
function animateValue(element, start, end, duration = 1000, formatter = null) {
    const startTime = performance.now();
    
    function updateValue(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        
        // Easing function (ease-out)
        const easeOut = 1 - Math.pow(1 - progress, 3);
        const currentValue = start + (end - start) * easeOut;
        
        const displayValue = formatter ? formatter(currentValue) : Math.round(currentValue);
        $(element).text(displayValue);
        
        if (progress < 1) {
            requestAnimationFrame(updateValue);
        }
    }
    
    requestAnimationFrame(updateValue);
}

/**
 * URL utilities
 */
function getUrlParams() {
    const urlParams = new URLSearchParams(window.location.search);
    const params = {};
    for (const [key, value] of urlParams) {
        params[key] = value;
    }
    return params;
}

function updateUrl(params, replaceState = false) {
    const url = new URL(window.location);
    Object.keys(params).forEach(key => {
        if (params[key] !== null && params[key] !== undefined && params[key] !== '') {
            url.searchParams.set(key, params[key]);
        } else {
            url.searchParams.delete(key);
        }
    });
    
    if (replaceState) {
        window.history.replaceState({}, '', url);
    } else {
        window.history.pushState({}, '', url);
    }
}

/**
 * Validation utilities
 */
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

function validateRequired(value) {
    return value !== null && value !== undefined && value.toString().trim() !== '';
}

/**
 * Array utilities
 */
function groupBy(array, key) {
    return array.reduce((groups, item) => {
        const value = item[key];
        groups[value] = groups[value] || [];
        groups[value].push(item);
        return groups;
    }, {});
}

function sortBy(array, key, direction = 'asc') {
    return array.sort((a, b) => {
        const aVal = a[key];
        const bVal = b[key];
        
        if (direction === 'asc') {
            return aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
        } else {
            return aVal > bVal ? -1 : aVal < bVal ? 1 : 0;
        }
    });
}

/**
 * Local storage utilities
 */
function setStorage(key, value, expiry = null) {
    const item = {
        value: value,
        expiry: expiry ? Date.now() + expiry : null
    };
    localStorage.setItem(key, JSON.stringify(item));
}

function getStorage(key) {
    try {
        const itemStr = localStorage.getItem(key);
        if (!itemStr) return null;
        
        const item = JSON.parse(itemStr);
        
        if (item.expiry && Date.now() > item.expiry) {
            localStorage.removeItem(key);
            return null;
        }
        
        return item.value;
    } catch (e) {
        console.error('Error reading from localStorage:', e);
        return null;
    }
}

function removeStorage(key) {
    localStorage.removeItem(key);
}

/**
 * Clipboard utilities
 */
function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(text).then(() => {
            showToast('success', 'Copied to clipboard');
        }).catch(err => {
            console.error('Failed to copy:', err);
            showToast('error', 'Failed to copy to clipboard');
        });
    } else {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.select();
        
        try {
            document.execCommand('copy');
            showToast('success', 'Copied to clipboard');
        } catch (err) {
            console.error('Failed to copy:', err);
            showToast('error', 'Failed to copy to clipboard');
        }
        
        document.body.removeChild(textArea);
    }
}

/**
 * Debounce function for search inputs
 */
function debounce(func, wait, immediate) {
    let timeout;
    return function executedFunction() {
        const context = this;
        const args = arguments;
        
        const later = function() {
            timeout = null;
            if (!immediate) func.apply(context, args);
        };
        
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        
        if (callNow) func.apply(context, args);
    };
}

/**
 * Download blob as file
 */
function downloadBlob(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

/**
 * Generate random ID
 */
function generateId(prefix = '', length = 8) {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = prefix;
    for (let i = 0; i < length; i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
}

/**
 * Sound notification (optional)
 */
function playNotificationSound(type = 'default') {
    try {
        const audio = new Audio();
        const sounds = {
            default: 'data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmEbBy2Lze/beDEEK3/M8d6QQAoUXrTp66hVFApGn+DyvmEbBy2Lze/beDEEK3/M8d6QQAoUXrTp66hVFApGn+DyvmEbBy2Lze/beDEEK3/M8d6QQAoUXrTp66hVFApGn+DyvmEbBy2Lze/beDEEK3/M8d6QQAoUXrTp66hVFApGn+DyvmEbBy2Lze/beDEEK3/M8d6QQAoUXrTp66hVFApGn+DyvmEbBy2Lze/beDEEK3/M8d6QQAoUXrTp66hVFA==',
            alert: 'data:audio/wav;base64,UklGRp4DAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YXoDAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmEbBy2Lze/beDEEK3/M8d6QQAoUXrTp66hVFApGn+DyvmEbBy2Lze/beDEEK3/M8d6QQAoUXrTp66hVFA=='
        };
        
        audio.src = sounds[type] || sounds.default;
        audio.volume = 0.3;
        audio.play().catch(e => {
            // Ignore audio play errors (user interaction required)
        });
    } catch (e) {
        // Ignore audio errors
    }
}

/**
 * Light Theme Enforcement
 */
const ThemeManager = {
    init() {
        localStorage.setItem("theme", "light");
        document.documentElement.setAttribute("data-theme", "light");
    },
    
    setTheme() {
        localStorage.setItem("theme", "light");
        document.documentElement.setAttribute("data-theme", "light");
    },
    
    toggle() {},
    setupToggle() {}
};

// Initialize Theme Manager to ensure light theme
ThemeManager.init();
/**
 * Close a Bootstrap modal even if it is still animating open (Bootstrap
 * ignores hide() during the show transition).
 */
function closeModalSafely(modalEl) {
    const modal = bootstrap.Modal.getInstance(modalEl);
    if (!modal) return;
    if (modalEl.dataset.shown === "true") {
        modal.hide();
    } else {
        modalEl.addEventListener("shown.bs.modal", () => modal.hide(), { once: true });
    }
}

// Record when any modal has finished opening, for closeModalSafely()
document.addEventListener("shown.bs.modal", (e) => { e.target.dataset.shown = "true"; });
document.addEventListener("hidden.bs.modal", (e) => { e.target.dataset.shown = "false"; });
