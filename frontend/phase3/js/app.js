/**
 * KYRO Risk Assessment Specialist - Main Application Controller
 * Handles routing, navigation, and application initialization
 */

const App = {
    currentPage: null,
    pages: {},
    
    init() {
        console.log("🛡️ KYRO Risk Assessment Specialist starting...");
        
        this.setupEventListeners();
        this.setupRouting();
        this.initializeModules();
        
        // Load initial page based on URL
        this.handleRoute();
        
        console.log("✅ KYRO application initialized");
    },
    
    setupEventListeners() {
        // Navigation handling
        $(document).on("click", ".nav-link[data-page]", (e) => {
            e.preventDefault();
            const page = $(e.currentTarget).data("page");
            this.navigateTo(page);
        });
        
        // Sidebar navigation
        $(document).on("click", ".sidebar .nav-link", (e) => {
            e.preventDefault();
            const href = $(e.currentTarget).attr("href");
            const page = href.substring(1); // Remove leading slash
            this.navigateTo(page);
        });
        
        // Quick action cards
        $(document).on("click", ".quick-action-card", (e) => {
            e.preventDefault();
            const href = $(e.currentTarget).attr("href");
            const page = href.substring(1); // Remove leading slash
            this.navigateTo(page);
        });
        
        // Browser back/forward handling
        $(window).on("popstate", () => {
            this.handleRoute();
        });
        
        // Global search
        $("#globalSearch").on("keypress", (e) => {
            if (e.which === 13) {
                this.handleGlobalSearch($(e.target).val());
            }
        });
        
        // Hamburger menu drawer toggle
        $(document).on("click", "#hamburgerMenuBtn", () => {
            $("#kyroMobileDrawer").addClass("open");
            $("#kyroMobileOverlay").addClass("open");
        });
        
        $(document).on("click", "#closeMobileDrawerBtn, #kyroMobileOverlay, #kyroMobileDrawer .nav-link", () => {
            $("#kyroMobileDrawer").removeClass("open");
            $("#kyroMobileOverlay").removeClass("open");
        });
        
        // Responsive navbar toggle
        $(".navbar-toggler").on("click", () => {
            new bootstrap.Offcanvas(document.getElementById("sidebar")).show();
        });
        
        // Handle connection status
        $(window).on("online", () => {
            showToast("success", "Connection restored", "Back Online");
            RealTime.reconnect();
        });
        
        $(window).on("offline", () => {
            showToast("warning", "Connection lost", "Offline Mode");
        });
        
        // Fix profile dropdown visibility
        this.setupProfileDropdown();
    },
    
    setupProfileDropdown() {
        // Let Bootstrap handle dropdown with data-bs-auto-close="true"
        const dropdownButton = document.getElementById('userMenuDropdown');
        if (dropdownButton) {
            console.log('✅ Profile dropdown initialized');
            
            const dropdownMenu = dropdownButton.nextElementSibling;
            
            // Set fixed positioning when shown
            dropdownButton.addEventListener('show.bs.dropdown', function() {
                const buttonRect = dropdownButton.getBoundingClientRect();
                dropdownMenu.style.position = 'fixed';
                dropdownMenu.style.top = (buttonRect.bottom + 8) + 'px';
                dropdownMenu.style.right = (window.innerWidth - buttonRect.right) + 'px';
                dropdownMenu.style.left = 'auto';
                dropdownMenu.style.zIndex = '9999';
            });
            
            dropdownButton.addEventListener('shown.bs.dropdown', function() {
                console.log('✅ Dropdown OPEN');
            });
            
            dropdownButton.addEventListener('hidden.bs.dropdown', function() {
                console.log('❌ Dropdown CLOSED');
            });
            
        } else {
            console.error('❌ Profile dropdown button not found');
        }
    },
    
    setupRouting() {
        // Define page handlers
        this.pages = {
            dashboard: Dashboard,
            'periodic-reviews': PeriodicReviews,
            cases: Cases,
            patterns: Patterns,
            kyrochat: KyroChat
        };
    },
    
    initializeModules() {
        // Initialize real-time updates
        if (window.RealTime) {
            RealTime.init();
        }
        
        // Initialize auth check
        if (window.Auth && !Auth.isAuthenticated()) {
            window.location.href = "/login";
            return;
        }
        
        // Setup periodic health checks
        this.startHealthMonitoring();
    },
    
    async navigateTo(pageName, params = {}) {
        if (this.currentPage === pageName) return;
        
        console.log(`📍 Navigating to: ${pageName}`);
        
        try {
            // Update navigation state
            this.updateNavigation(pageName);
            
            // Update URL
            const url = `/${pageName}${this.serializeParams(params)}`;
            window.history.pushState({ page: pageName, params }, "", url);
            
            // Load page content
            await this.loadPage(pageName, params);
            
            this.currentPage = pageName;
            
        } catch (error) {
            console.error(`Navigation error to ${pageName}:`, error);
            showToast("error", "Failed to load page", "Navigation Error");
        }
    },
    
    async loadPage(pageName, params = {}) {
        const pageHandler = this.pages[pageName];
        
        if (!pageHandler) {
            throw new Error(`Page handler not found: ${pageName}`);
        }
        
        // Show loading state
        showLoading("#mainContent", `Loading ${capitalizeFirst(pageName)}...`);
        
        try {
            // Initialize page
            if (pageHandler.init) {
                await pageHandler.init(params);
            } else if (pageHandler.loadPage) {
                await pageHandler.loadPage(params);
            } else {
                throw new Error(`Page ${pageName} has no init method`);
            }
            
        } catch (error) {
            console.error(`Page load error for ${pageName}:`, error);
            
            // Show error state
            $("#mainContent").html(`
                <div class="alert alert-danger" role="alert">
                    <h4 class="alert-heading">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        Page Load Error
                    </h4>
                    <p>Failed to load ${capitalizeFirst(pageName)} page.</p>
                    <hr>
                    <div class="d-flex gap-2">
                        <button class="btn btn-outline-danger" onclick="App.loadPage('${pageName}')">
                            <i class="fas fa-redo me-2"></i>Retry
                        </button>
                        <button class="btn btn-outline-secondary" onclick="App.navigateTo('dashboard')">
                            <i class="fas fa-home me-2"></i>Go to Dashboard
                        </button>
                    </div>
                </div>
            `);
            
            throw error;
        }
    },
    
    updateNavigation(pageName) {
        // Update sidebar navigation
        $(".sidebar .nav-link").removeClass("active");
        $(`.sidebar .nav-link[data-page="${pageName}"], .sidebar .nav-link[href="/${pageName}"]`).addClass("active");
        
        // Update navbar if present
        $(".navbar .nav-link, .kyro-navbar .nav-link").removeClass("active");
        $(`.navbar .nav-link[data-page="${pageName}"], .kyro-navbar .nav-link[data-page="${pageName}"]`).addClass("active");
        
        // Update page title
        document.title = `KYRO - ${capitalizeFirst(pageName)}`;
        
        // Close mobile menu/navbar if open
        const navbarLinksEl = document.getElementById("kyroNavbarLinks");
        if (navbarLinksEl && navbarLinksEl.classList.contains("show")) {
            const collapse = bootstrap.Collapse.getInstance(navbarLinksEl) || new bootstrap.Collapse(navbarLinksEl);
            if (collapse) {
                collapse.hide();
            }
        }

        const sidebarEl = document.getElementById("sidebar");
        if (sidebarEl) {
            const offcanvas = bootstrap.Offcanvas.getInstance(sidebarEl);
            if (offcanvas) {
                offcanvas.hide();
            }
        }
    },
    
    handleRoute() {
        const path = window.location.pathname;
        const params = this.parseParams();
        
        // Extract page name from path
        let pageName = path === "/" ? "dashboard" : path.substring(1).split("/")[0];
        
        // Handle sub-routes (e.g., /customers/123)
        const pathParts = path.substring(1).split("/");
        if (pathParts.length > 1 && pathParts[1]) {
            params.id = pathParts[1];
        }
        
        // Default to dashboard for unknown pages
        if (!this.pages[pageName]) {
            pageName = "dashboard";
        }
        
        this.loadPage(pageName, params);
    },
    
    parseParams() {
        const urlParams = new URLSearchParams(window.location.search);
        const params = {};
        for (const [key, value] of urlParams) {
            params[key] = value;
        }
        return params;
    },
    
    serializeParams(params) {
        const urlParams = new URLSearchParams();
        Object.keys(params).forEach(key => {
            if (params[key] !== null && params[key] !== undefined && params[key] !== '') {
                urlParams.set(key, params[key]);
            }
        });
        const paramString = urlParams.toString();
        return paramString ? `?${paramString}` : "";
    },
    
    async handleGlobalSearch(query) {
        if (!query || query.trim().length < 2) {
            showToast("warning", "Please enter at least 2 characters to search");
            return;
        }
        
        console.log(`🔍 Global search: ${query}`);
        
        try {
            showGlobalLoading();
            
            const results = await API.get("/search", { q: query.trim() });
            
            // Navigate to search results or specific result
            if (results.length === 1) {
                const result = results[0];
                if (result.type === "customer") {
                    this.navigateTo("customers", { id: result.id });
                } else if (result.type === "alert") {
                    this.navigateTo("alerts", { id: result.id });
                } else if (result.type === "transaction") {
                    this.navigateTo("transactions", { id: result.id });
                }
            } else {
                // Show search results page
                this.navigateTo("search", { q: query });
            }
            
        } catch (error) {
            console.error("Search error:", error);
            showToast("error", "Search failed. Please try again.");
        } finally {
            hideLoading();
            $("#globalSearch").blur();
        }
    },
    
    startHealthMonitoring() {
        // Check system health every 5 minutes
        setInterval(async () => {
            try {
                await API.get("/health");
                // System is healthy
            } catch (error) {
                if (error.status === 0) {
                    // Network error
                    showToast("warning", "Network connection issues detected", "Connection Warning");
                }
            }
        }, 300000); // 5 minutes
    },
    
    // Utility methods for other modules
    getCurrentPage() {
        return this.currentPage;
    },
    
    refreshCurrentPage() {
        if (this.currentPage && this.pages[this.currentPage]) {
            this.loadPage(this.currentPage, this.parseParams());
        }
    },
    
    showNotification(notification) {
        // Update notification badge
        const currentCount = parseInt($("#notificationBadge").text()) || 0;
        $("#notificationBadge").text(currentCount + 1);
        $("#sidebarAlertCount").text(currentCount + 1);
        
        // Add to notification dropdown
        const notificationHtml = `
            <li>
                <a class="dropdown-item d-flex align-items-start" href="/alerts/${notification.id}">
                    <div class="flex-shrink-0 me-3">
                        <i class="fas fa-exclamation-triangle text-${getRiskColor(notification.risk_score)}"></i>
                    </div>
                    <div class="flex-grow-1">
                        <div class="fw-semibold">${notification.customer_name}</div>
                        <small class="text-muted">${notification.alert_type} • ${formatRelativeTime(notification.created_at)}</small>
                    </div>
                </a>
            </li>
        `;
        
        // Remove "no notifications" message if present
        $("#notificationList").find(".dropdown-item-text").parent().remove();
        $("#notificationList").prepend(notificationHtml);
        
        // Limit to 10 notifications
        $("#notificationList li").slice(10).remove();
        
        // Show toast notification
        showToast("info", `New ${notification.alert_type} alert for ${notification.customer_name}`, "New Alert");
        
        // Play notification sound
        playNotificationSound("alert");
        
        // Update dashboard if on dashboard page
        if (this.currentPage === "dashboard" && window.Dashboard) {
            Dashboard.handleNewAlert(notification);
        }
    }
};

// Initialize application when DOM is ready
$(document).ready(function() {
    // Check if we're on the login page
    if (window.location.pathname === '/login') {
        // Initialize login form
        if (window.LoginForm) {
            LoginForm.init();
        }
        return;
    }
    
    // Initialize main application
    App.init();
});

// Handle unhandled promise rejections
window.addEventListener('unhandledrejection', function(event) {
    console.error('Unhandled promise rejection:', event.reason);
    showToast("error", "An unexpected error occurred", "System Error");
});

// Handle JavaScript errors
window.addEventListener('error', function(event) {
    console.error('JavaScript error:', event.error);
    // Don't show toast for every JS error as it might be spammy
});

// Export for use in other modules
window.App = App;