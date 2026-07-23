/**
 * KYRO Authentication System
 * Handles login, logout, token management, and session persistence
 */

console.log("🔧 KYRO Auth.js loaded - API Port: 8010");
console.log("🔧 Current location:", window.location.href);
console.log("🔧 Script version: 9999999999");

const Auth = {
    tokenKey: "access_token",
    refreshTokenKey: "refresh_token",
    userKey: "user_data",
    
    init() {
        this.setupTokenRefresh();
        this.checkAuthStatus();
    },
    
    getApiUrl(path) {
        // Always point to the API on port 8010 using whatever hostname
        // the browser is currently using. This works for localhost AND
        // external IPs / remote access without any hardcoding.
        const apiHost = window.location.hostname;
        return `http://${apiHost}:8010${path}`;
    },
    
    /**
     * Check if user is authenticated
     */
    isAuthenticated() {
        const token = this.getToken();
        if (!token) return false;
        
        // Check if token is expired
        try {
            const payload = JSON.parse(atob(token.split('.')[1]));
            const now = Date.now() / 1000;
            return payload.exp > now;
        } catch (e) {
            return false;
        }
    },
    
    /**
     * Get stored access token
     */
    getToken() {
        return localStorage.getItem(this.tokenKey);
    },
    
    /**
     * Get stored refresh token
     */
    getRefreshToken() {
        return localStorage.getItem(this.refreshTokenKey);
    },
    
    /**
     * Get stored user data
     */
    getUser() {
        try {
            const userData = localStorage.getItem(this.userKey);
            return userData ? JSON.parse(userData) : null;
        } catch (e) {
            return null;
        }
    },
    
    /**
     * Store authentication data
     */
    storeAuthData(authResponse) {
        localStorage.setItem(this.tokenKey, authResponse.access_token);
        localStorage.setItem(this.refreshTokenKey, authResponse.refresh_token);
        localStorage.setItem(this.userKey, JSON.stringify(authResponse.user));
        
        // Update UI
        this.updateUserDisplay(authResponse.user);
    },
    
    /**
     * Login with credentials
     */
    async login(credentials) {
        try {
            showGlobalLoading();
            
            console.log("Attempting login with:", credentials.username);
            
            const response = await $.ajax({
                url: this.getApiUrl("/api/v1/auth/login"),
                method: "POST",
                contentType: "application/x-www-form-urlencoded",
                data: {
                    username: credentials.username,
                    password: credentials.password
                }
            });
            
            console.log("Login successful:", response);
            this.storeAuthData(response);
            return response;
            
        } catch (error) {
            console.error("Login error details:", error);
            console.error("Status:", error.status);
            console.error("Response:", error.responseJSON);
            
            const errorMessage = error.responseJSON?.detail || 
                               error.responseJSON?.message || 
                               error.statusText ||
                               "Login failed. Please check your credentials.";
            
            throw new Error(errorMessage);
        } finally {
            hideLoading();
        }
    },
    
    /**
     * Logout user
     */
    async logout() {
        try {
            // Call logout endpoint to invalidate server-side session
            const token = this.getToken();
            if (token) {
                await $.ajax({
                    url: this.getApiUrl("/api/v1/auth/logout"),
                    method: "POST",
                    headers: {
                        "Authorization": `Bearer ${token}`,
                        "Content-Type": "application/json"
                    }
                }).catch(() => {
                    // Ignore logout API errors
                });
            }
        } catch (e) {
            // Ignore logout errors
        } finally {
            this.clearAuthData();
            window.location.href = "/";
        }
    },
    
    /**
     * Clear stored authentication data
     */
    clearAuthData() {
        localStorage.removeItem(this.tokenKey);
        localStorage.removeItem(this.refreshTokenKey);
        localStorage.removeItem(this.userKey);
    },
    
    /**
     * Refresh access token
     */
    async refreshAccessToken() {
        const refreshToken = this.getRefreshToken();
        if (!refreshToken) {
            throw new Error("No refresh token available");
        }
        
        try {
            const response = await $.ajax({
                url: this.getApiUrl("/api/v1/auth/refresh"),
                method: "POST",
                contentType: "application/json",
                data: JSON.stringify({ refresh_token: refreshToken })
            });
            
            localStorage.setItem(this.tokenKey, response.access_token);
            return response.access_token;
            
        } catch (error) {
            console.error("Token refresh error:", error);
            this.logout(); // Force logout on refresh failure
            throw error;
        }
    },
    
    /**
     * Setup automatic token refresh
     */
    setupTokenRefresh() {
        setInterval(() => {
            const token = this.getToken();
            if (token) {
                try {
                    const payload = JSON.parse(atob(token.split('.')[1]));
                    const now = Date.now() / 1000;
                    const timeUntilExpiry = payload.exp - now;
                    
                    // Refresh token if it expires in less than 5 minutes
                    if (timeUntilExpiry < 300) {
                        this.refreshAccessToken().catch(() => {
                            // Handle refresh failure
                        });
                    }
                } catch (e) {
                    console.error("Token parsing error:", e);
                }
            }
        }, 60000); // Check every minute
    },
    
    /**
     * Check authentication status on page load
     */
    checkAuthStatus() {
        const currentPath = window.location.pathname;
        const isLandingPage = currentPath === '/' || currentPath === '/landing' || currentPath.includes('landing.html');
        const isLoginPage = currentPath === '/login' || currentPath.includes('login.html');
        
        // Protected routes that require authentication
        const protectedRoutes = ['/dashboard', '/periodic-reviews', '/cases', '/patterns', '/kyrochat', '/real-time'];
        const isProtectedRoute = protectedRoutes.some(route => currentPath.includes(route)) || currentPath.includes('index.html');
        
        if (this.isAuthenticated()) {
            const user = this.getUser();
            if (user) {
                this.updateUserDisplay(user);
            }
            
            // Redirect to dashboard if on login page (but NOT landing page)
            if (isLoginPage) {
                window.location.href = '/dashboard';
            }
        } else {
            // Clear any stale auth data
            this.clearAuthData();
            
            // Redirect to login if trying to access protected route
            if (isProtectedRoute) {
                console.warn('Unauthorized access attempt to protected route:', currentPath);
                window.location.href = '/login';
                return;
            }
            
            // Allow access to landing and login pages
            if (!isLoginPage && !isLandingPage) {
                window.location.href = '/login';
            }
        }
    },
    
    /**
     * Update user display in navbar
     */
    updateUserDisplay(user) {
        if (user) {
            $("#currentUser").text(user.username || "Analyst");
            
            // Update user details if dropdown elements exist
            $("#userDropdownName").text(user.full_name || user.username || "Compliance Analyst");
            $("#userDropdownEmail").text(user.email || "analyst@kyro.com");
            $("#userDropdownRole").text((user.role || "ANALYST").toUpperCase());
            
            // Set initials
            const name = user.full_name || user.username || "A";
            const initials = name.split(" ").map(n => n[0]).join("").toUpperCase().substring(0, 2);
            $("#userInitials").text(initials);
            
            // Update user dropdown if it exists
            if (user.avatar_url) {
                $(".user-avatar").attr("src", user.avatar_url);
            }
        }
    },
    
    /**
     * Get user role
     */
    getUserRole() {
        const user = this.getUser();
        return user ? user.role : null;
    },
    
    /**
     * Check if user has permission
     */
    hasPermission(permission) {
        const user = this.getUser();
        if (!user || !user.permissions) return false;
        
        return user.permissions.includes(permission) || user.role === 'admin';
    }
};

/**
 * Login Form Handler
 */
const LoginForm = {
    init() {
        this.setupEventListeners();
        this.setupValidation();
        
        // Focus on username field
        $("#username").focus();
    },
    
    setupEventListeners() {
        // Form submission
        $("#loginForm").on("submit", (e) => {
            e.preventDefault();
            this.handleLogin();
        });
        
        // Password visibility toggle
        $("#togglePassword").on("click", () => {
            this.togglePasswordVisibility();
        });
        
        // Enter key handling
        $("#username, #password").on("keypress", (e) => {
            if (e.which === 13) {
                $("#loginForm").submit();
            }
        });
        
        // Remember me checkbox
        $("#rememberMe").on("change", (e) => {
            // Could implement extended session logic here
        });
    },
    
    setupValidation() {
        // Real-time validation
        $("#username").on("blur", () => {
            this.validateField("username");
        });
        
        $("#password").on("blur", () => {
            this.validateField("password");
        });
    },
    
    validateField(fieldName) {
        const field = $(`#${fieldName}`);
        const value = field.val().trim();
        
        field.removeClass("is-invalid is-valid");
        field.next(".invalid-feedback").remove();
        
        if (!value) {
            this.showFieldError(field, `${capitalizeFirst(fieldName)} is required`);
            return false;
        }
        
        if (fieldName === "username" && value.length < 3) {
            this.showFieldError(field, "Username must be at least 3 characters");
            return false;
        }
        
        if (fieldName === "password" && value.length < 6) {
            this.showFieldError(field, "Password must be at least 6 characters");
            return false;
        }
        
        field.addClass("is-valid");
        return true;
    },
    
    showFieldError(field, message) {
        field.addClass("is-invalid");
        field.after(`<div class="invalid-feedback">${message}</div>`);
    },
    
    async handleLogin() {
        const username = $("#username").val().trim();
        const password = $("#password").val();
        const rememberMe = $("#rememberMe").is(":checked");
        
        // Validate form
        const isUsernameValid = this.validateField("username");
        const isPasswordValid = this.validateField("password");
        
        if (!isUsernameValid || !isPasswordValid) {
            return;
        }
        
        // Disable form
        this.setFormEnabled(false);
        
        try {
            await Auth.login({
                username: username,
                password: password,
                remember_me: rememberMe
            });
            
            showToast("success", "Login successful", "Welcome back!");
            
            // Redirect to dashboard
            setTimeout(() => {
                window.location.href = "/dashboard";
            }, 1000);
            
        } catch (error) {
            console.error("Login error:", error);
            showToast("error", error.message, "Login Failed");
            this.setFormEnabled(true);
            $("#password").focus().select();
        }
    },
    
    togglePasswordVisibility() {
        const passwordField = $("#password");
        const toggleIcon = $("#togglePassword i");
        
        if (passwordField.attr("type") === "password") {
            passwordField.attr("type", "text");
            toggleIcon.removeClass("fa-eye").addClass("fa-eye-slash");
        } else {
            passwordField.attr("type", "password");
            toggleIcon.removeClass("fa-eye-slash").addClass("fa-eye");
        }
    },
    
    setFormEnabled(enabled) {
        $("#username, #password, #rememberMe, #loginBtn").prop("disabled", !enabled);
        
        if (enabled) {
            $("#loginBtn").html('<i class="fas fa-sign-in-alt me-2"></i>Sign In');
        } else {
            $("#loginBtn").html('<i class="fas fa-spinner fa-spin me-2"></i>Signing In...');
        }
    },
    
    getLoginHTML() {
        return `
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>KYRO - Login</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
                <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
                <link rel="stylesheet" href="css/custom.css">
                <style>
                    body {
                        background: linear-gradient(135deg, var(--kyro-primary) 0%, var(--kyro-secondary) 100%);
                        min-height: 100vh;
                    }
                    .login-container {
                        min-height: 100vh;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    }
                    .login-card {
                        background: white;
                        border-radius: 20px;
                        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
                        overflow: hidden;
                        max-width: 400px;
                        width: 100%;
                    }
                    .login-header {
                        background: linear-gradient(135deg, var(--kyro-primary), var(--kyro-secondary));
                        color: white;
                        padding: 2rem;
                        text-align: center;
                    }
                    .login-body {
                        padding: 2rem;
                    }
                    .brand-logo {
                        font-size: 3rem;
                        margin-bottom: 1rem;
                    }
                    .form-floating .form-control {
                        border-radius: 12px;
                    }
                    .btn-login {
                        border-radius: 12px;
                        padding: 12px;
                        font-weight: 600;
                    }
                    .password-toggle {
                        cursor: pointer;
                        position: absolute;
                        right: 12px;
                        top: 50%;
                        transform: translateY(-50%);
                        z-index: 10;
                        color: #6c757d;
                    }
                </style>
            </head>
            <body>
                <div class="login-container">
                    <div class="login-card">
                        <div class="login-header">
                            <div class="brand-logo">🛡️</div>
                            <h2 class="mb-0">KYRO</h2>
                            <p class="mb-0 opacity-75">Risk Assessment Specialist</p>
                        </div>
                        
                        <div class="login-body">
                            <form id="loginForm">
                                <div class="form-floating mb-3">
                                    <input type="text" class="form-control" id="username" placeholder="Username" required>
                                    <label for="username">
                                        <i class="fas fa-user me-2"></i>Username
                                    </label>
                                </div>
                                
                                <div class="form-floating mb-3 position-relative">
                                    <input type="password" class="form-control" id="password" placeholder="Password" required>
                                    <label for="password">
                                        <i class="fas fa-lock me-2"></i>Password
                                    </label>
                                    <span class="password-toggle" id="togglePassword">
                                        <i class="fas fa-eye"></i>
                                    </span>
                                </div>
                                
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" id="rememberMe">
                                    <label class="form-check-label" for="rememberMe">
                                        Remember me
                                    </label>
                                </div>
                                
                                <button type="submit" class="btn btn-primary w-100 btn-login" id="loginBtn">
                                    <i class="fas fa-sign-in-alt me-2"></i>Sign In
                                </button>
                            </form>
                            
                            <div class="text-center mt-3">
                                <small class="text-muted">
                                    Secure access to AML risk assessment platform
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Toast Container -->
                <div class="toast-container position-fixed top-0 end-0 p-3" id="toastContainer"></div>
                
                <!-- Loading Overlay -->
                <div class="loading-overlay d-none" id="loadingOverlay">
                    <div class="text-center">
                        <div class="spinner-border text-light mb-3" style="width: 3rem; height: 3rem;"></div>
                        <div class="text-light">Authenticating...</div>
                    </div>
                </div>
                
                <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
                <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
                <script src="js/utils.js"></script>
                <script src="js/auth.js"></script>
                <script>
                    $(document).ready(function() {
                        LoginForm.init();
                    });
                </script>
            </body>
            </html>
        `;
    }
};

// Initialize authentication on page load
$(document).ready(function() {
    Auth.init();
    
    // Setup logout handler
    $("#logoutBtn").on("click", (e) => {
        e.preventDefault();
        Auth.logout();
    });
    
    // Recheck auth on page visibility (tab focus)
    document.addEventListener('visibilitychange', function() {
        if (!document.hidden) {
            // Page is visible again, check if still authenticated
            const currentPath = window.location.pathname;
            const isLandingPage = currentPath === '/' || currentPath === '/landing' || currentPath.includes('landing.html');
            const isLoginPage = currentPath === '/login' || currentPath.includes('login.html');
            const protectedRoutes = ['/dashboard', '/periodic-reviews', '/cases', '/patterns', '/kyrochat', '/real-time'];
            const isProtectedRoute = protectedRoutes.some(route => currentPath.includes(route)) || currentPath.includes('index.html');
            
            if (isProtectedRoute && !Auth.isAuthenticated()) {
                console.warn('Session expired or invalid. Redirecting to login.');
                Auth.clearAuthData();
                window.location.href = '/login';
            }
        }
    });
    
    // Prevent back button after logout
    window.addEventListener('pageshow', function(event) {
        if (event.persisted) {
            // Page was loaded from cache
            const currentPath = window.location.pathname;
            const protectedRoutes = ['/dashboard', '/periodic-reviews', '/cases', '/patterns', '/kyrochat', '/real-time'];
            const isProtectedRoute = protectedRoutes.some(route => currentPath.includes(route)) || currentPath.includes('index.html');
            
            if (isProtectedRoute && !Auth.isAuthenticated()) {
                console.warn('Protected page loaded from cache without authentication. Redirecting.');
                window.location.href = '/login';
            }
        }
    });
});

// Export for use in other modules
window.Auth = Auth;
window.LoginForm = LoginForm;