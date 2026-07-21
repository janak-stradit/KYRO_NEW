/**
 * KYRO Risk Assessment Specialist - Utility Functions
 * Common utility functions used throughout the application
 */

/**
 * Toast notification system
 */
function showToast(type, message, title = null, duration = 5000) {
    const colors = {
        success: "bg-success",
        error: "bg-danger",
        warning: "bg-warning",
        info: "bg-info"
    };
    
    const icons = {
        success: "fas fa-check-circle",
        error: "fas fa-exclamation-triangle",
        warning: "fas fa-exclamation-circle",
        info: "fas fa-info-circle"
    };
    
    const toastHtml = `
        <div class="toast align-items-center ${colors[type]} text-white" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body d-flex align-items-center">
                    <i class="${icons[type]} me-2"></i>
                    <div>
                        ${title ? `<div class="fw-bold">${title}</div>` : ''}
                        ${message}
                    </div>
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    
    const toastElement = $(toastHtml);
    $("#toastContainer").append(toastElement);
    
    const toast = new bootstrap.Toast(toastElement[0], {
        delay: duration
    });
    
    toast.show();
    
    // Auto-remove after animation
    toastElement.on('hidden.bs.toast', function() {
        $(this).remove();
    });
}

/**
 * Loading state management
 */
function showLoading(selector, message = "Loading...") {
    const loadingHtml = `
        <div class="d-flex justify-content-center align-items-center py-5">
            <div class="text-center">
                <div class="spinner-border text-primary mb-3" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="text-muted">${message}</p>
            </div>
        </div>
    `;
    $(selector).html(loadingHtml);
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