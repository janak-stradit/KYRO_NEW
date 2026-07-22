/**
 * KYRO Risk Assessment Specialist - API Client
 * Provides authenticated API communication with error handling and retry logic
 */

const API = {
    baseUrl: (function() {
        // Always target the FastAPI backend on port 8010 using whatever
        // hostname the browser resolved — works for localhost AND external IPs.
        const host = window.location.hostname || 'localhost';
        const proto = (window.location.protocol || 'http:');
        return `${proto}//${host}:8010/api/v1`;
    })(),
    timeout: 30000,
    retryAttempts: 3,
    retryDelay: 1000,

    /**
     * Get authentication headers
     */
    getHeaders() {
        const token = localStorage.getItem("access_token");
        return {
            "Authorization": token ? `Bearer ${token}` : "",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest"
        };
    },

    /**
     * Handle API errors and authentication
     */
    handleError(xhr, endpoint) {
        console.error(`API Error [${endpoint}]:`, xhr);
        
        if (xhr.status === 401) {
            // Token expired or invalid
            Auth.logout();
            showToast("error", "Session expired. Please login again.");
            window.location.href = "/login";
            return;
        }
        
        if (xhr.status === 403) {
            showToast("error", "Access denied. Insufficient permissions.");
            return;
        }
        
        if (xhr.status === 429) {
            showToast("warning", "Too many requests. Please slow down.");
            return;
        }
        
        const errorMessage = xhr.responseJSON?.detail || 
                           xhr.responseJSON?.message || 
                           `API Error: ${xhr.status} ${xhr.statusText}`;
        
        showToast("error", errorMessage);
    },

    /**
     * Retry logic for failed requests
     */
    async retryRequest(requestFn, attempts = this.retryAttempts) {
        try {
            return await requestFn();
        } catch (error) {
            if (attempts > 1 && error.status >= 500) {
                await new Promise(resolve => setTimeout(resolve, this.retryDelay));
                return this.retryRequest(requestFn, attempts - 1);
            }
            throw error;
        }
    },

    /**
     * GET request
     */
    async get(endpoint, params = {}) {
        return this.retryRequest(() => {
            return new Promise((resolve, reject) => {
                $.ajax({
                    url: `${this.baseUrl}${endpoint}`,
                    method: "GET",
                    headers: this.getHeaders(),
                    data: params,
                    timeout: this.timeout,
                    success: resolve,
                    error: (xhr) => {
                        this.handleError(xhr, endpoint);
                        reject(xhr);
                    }
                });
            });
        });
    },

    /**
     * POST request
     */
    async post(endpoint, data = {}) {
        return this.retryRequest(() => {
            return new Promise((resolve, reject) => {
                $.ajax({
                    url: `${this.baseUrl}${endpoint}`,
                    method: "POST",
                    headers: this.getHeaders(),
                    data: JSON.stringify(data),
                    timeout: this.timeout,
                    success: resolve,
                    error: (xhr) => {
                        this.handleError(xhr, endpoint);
                        reject(xhr);
                    }
                });
            });
        });
    },

    /**
     * PUT request
     */
    async put(endpoint, data = {}) {
        return this.retryRequest(() => {
            return new Promise((resolve, reject) => {
                $.ajax({
                    url: `${this.baseUrl}${endpoint}`,
                    method: "PUT",
                    headers: this.getHeaders(),
                    data: JSON.stringify(data),
                    timeout: this.timeout,
                    success: resolve,
                    error: (xhr) => {
                        this.handleError(xhr, endpoint);
                        reject(xhr);
                    }
                });
            });
        });
    },

    /**
     * DELETE request
     */
    async delete(endpoint) {
        return this.retryRequest(() => {
            return new Promise((resolve, reject) => {
                $.ajax({
                    url: `${this.baseUrl}${endpoint}`,
                    method: "DELETE",
                    headers: this.getHeaders(),
                    timeout: this.timeout,
                    success: resolve,
                    error: (xhr) => {
                        this.handleError(xhr, endpoint);
                        reject(xhr);
                    }
                });
            });
        });
    },

    /**
     * File download
     */
    async download(endpoint, params = {}, filename = null) {
        return new Promise((resolve, reject) => {
            $.ajax({
                url: `${this.baseUrl}${endpoint}`,
                method: "GET",
                headers: this.getHeaders(),
                data: params,
                xhrFields: {
                    responseType: "blob"
                },
                success: (blob, status, xhr) => {
                    // Create download link
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    
                    // Try to get filename from Content-Disposition header
                    const contentDisposition = xhr.getResponseHeader("Content-Disposition");
                    if (contentDisposition && contentDisposition.includes("filename=")) {
                        const matches = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                        if (matches && matches[1]) {
                            a.download = matches[1].replace(/['"]/g, "");
                        }
                    } else if (filename) {
                        a.download = filename;
                    } else {
                        a.download = "download";
                    }
                    
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    window.URL.revokeObjectURL(url);
                    
                    resolve(blob);
                },
                error: (xhr) => {
                    this.handleError(xhr, endpoint);
                    reject(xhr);
                }
            });
        });
    },

    /**
     * File upload
     */
    async upload(endpoint, formData, progressCallback = null) {
        return new Promise((resolve, reject) => {
            const headers = this.getHeaders();
            delete headers["Content-Type"]; // Let browser set multipart boundary
            
            $.ajax({
                url: `${this.baseUrl}${endpoint}`,
                method: "POST",
                headers: headers,
                data: formData,
                processData: false,
                contentType: false,
                timeout: this.timeout * 3, // Longer timeout for uploads
                xhr: function() {
                    const xhr = new window.XMLHttpRequest();
                    if (progressCallback) {
                        xhr.upload.addEventListener("progress", function(evt) {
                            if (evt.lengthComputable) {
                                const percentComplete = (evt.loaded / evt.total) * 100;
                                progressCallback(percentComplete);
                            }
                        }, false);
                    }
                    return xhr;
                },
                success: resolve,
                error: (xhr) => {
                    this.handleError(xhr, endpoint);
                    reject(xhr);
                }
            });
        });
    },

    // Specific API endpoints
    endpoints: {
        // Authentication
        login: "/auth/login",
        logout: "/auth/logout",
        refresh: "/auth/refresh",
        profile: "/auth/me",

        // Dashboard
        dashboard: "/dashboard",
        kpis: "/dashboard/kpis",
        alerts_stream: "/alerts/stream",

        // Customers
        customers: "/customers",
        customer: (id) => `/customers/${id}`,
        customer_risk_history: (id) => `/customers/${id}/risk-history`,
        customer_transactions: (id) => `/customers/${id}/transactions`,

        // Transactions
        transactions: "/transactions",
        transaction: (id) => `/transactions/${id}`,
        transaction_explanation: (id) => `/transactions/${id}/explanation`,

        // Alerts
        alerts: "/alerts",
        alert: (id) => `/alerts/${id}`,
        alert_assign: "/alerts/bulk-assign",
        alert_resolve: "/alerts/bulk-resolve",

        // Cases
        cases: "/cases",
        case: (id) => `/cases/${id}`,
        case_notes: (id) => `/cases/${id}/notes`,
        case_documents: (id) => `/cases/${id}/documents`,

        // Reports
        reports: "/reports",
        report_generate: "/reports/generate",
        audit_trail: "/reports/audit-trail",
        
        // KYC Reviews (Periodic Reviews)
        kyc_reviews: "/kyc-reviews",
        kyc_review: (id) => `/kyc-reviews/${id}`,

        // Settings
        settings: "/settings",
        users: "/settings/users",
        rules: "/settings/rules",
        model_config: "/settings/model"
    }
};

// Export for use in other modules
window.API = API;