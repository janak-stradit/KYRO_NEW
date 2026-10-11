/**
 * KYRO Risk Assessment Specialist - Main Application Controller
 * Handles routing, navigation, and application initialization
 */

const App = {
    currentPage: null,
    pages: {},
    
    async init() {
        console.log("🛡️ KYRO Risk Assessment Specialist starting...");
        
        this.setupEventListeners();
        this.setupRouting();
        
        // Pages show or hide actions by permission, so load the profile first
        await Auth.ensureUser();
        Auth.applyNavPermissions();
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
        
        // User menu
        $(document).on("click", ".dropdown-item[data-page]", (e) => {
            e.preventDefault();
            this.navigateTo($(e.currentTarget).data("page"));
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
        
        this.setupSearch();
        
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
            
            // Function to position dropdown
            const positionDropdown = () => {
                const buttonRect = dropdownButton.getBoundingClientRect();
                dropdownMenu.style.position = 'fixed';
                dropdownMenu.style.top = (buttonRect.bottom + 8) + 'px';
                dropdownMenu.style.right = (window.innerWidth - buttonRect.right) + 'px';
                dropdownMenu.style.left = 'auto';
                dropdownMenu.style.zIndex = '9999';
            };
            
            // Set fixed positioning when shown
            dropdownButton.addEventListener('show.bs.dropdown', function() {
                positionDropdown();
            });
            
            // Reposition on scroll while dropdown is open
            let isDropdownOpen = false;
            
            dropdownButton.addEventListener('shown.bs.dropdown', function() {
                console.log('✅ Dropdown OPEN');
                isDropdownOpen = true;
                
                // Add scroll listener
                window.addEventListener('scroll', handleScroll, true);
                window.addEventListener('resize', handleScroll);
            });
            
            dropdownButton.addEventListener('hidden.bs.dropdown', function() {
                console.log('❌ Dropdown CLOSED');
                isDropdownOpen = false;
                
                // Remove scroll listener
                window.removeEventListener('scroll', handleScroll, true);
                window.removeEventListener('resize', handleScroll);
            });
            
            // Handler to reposition dropdown on scroll
            const handleScroll = () => {
                if (isDropdownOpen) {
                    positionDropdown();
                }
            };
            
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
            case: CaseDetail,
            patterns: Patterns,
            regulations: Regulations,
            rules: Rules,
            process: Process,
            feeds: Feeds,
            admin: Admin,
            profile: Profile
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
        if (this.currentPage === pageName) {
            console.log(`Already on ${pageName}, skipping navigation`);
            return;
        }
        
        console.log(`📍 Navigating to: ${pageName}`);
        
        try {
            if (this.pages[pageName] && !Auth.canOpen(pageName)) {
                showToast("error", "Your role does not have access to that page.");
                return;
            }
            // Validate page exists
            if (!this.pages[pageName]) {
                console.error(`❌ Invalid page: ${pageName}`);
                showToast("error", `Page not found: ${pageName}`, "Navigation Error");
                // Fallback to dashboard
                if (pageName !== 'dashboard') {
                    this.navigateTo('dashboard');
                }
                return;
            }
            
            // Update navigation state
            this.updateNavigation(pageName);
            
            // Update URL
            const url = `/${pageName}${this.serializeParams(params)}`;
            window.history.pushState({ page: pageName, params }, "", url);
            
            // Load page content
            await this.loadPage(pageName, params);
            
            this.currentPage = pageName;
            console.log(`✅ Navigation complete: ${pageName}`);
            
        } catch (error) {
            console.error(`❌ Navigation error to ${pageName}:`, error);
            console.error("Error details:", error.stack);
            
            // Show user-friendly error without breaking the app
            showToast("error", "Navigation failed. Please try again.", "Navigation Error");
            
            // If not on dashboard and navigation fails, try to go to dashboard
            if (pageName !== 'dashboard' && this.currentPage !== 'dashboard') {
                console.log("⚠️ Falling back to dashboard");
                setTimeout(() => this.navigateTo('dashboard'), 500);
            }
        }
    },
    
    async loadPage(pageName, params = {}) {
        const pageHandler = this.pages[pageName];
        
        if (!pageHandler) {
            console.error(`❌ Page handler not found: ${pageName}`);
            console.error("Available pages:", Object.keys(this.pages));
            throw new Error(`Page handler not found: ${pageName}`);
        }
        
        // Also on a direct visit or a reload, which do not pass through updateNavigation()
        document.title = `${this.PAGE_TITLES[pageName] || capitalizeFirst(pageName)} · KYRO`;

        // Show loading state
        showLoading("#mainContent", `Loading ${this.PAGE_TITLES[pageName] || capitalizeFirst(pageName)}...`);
        
        try {
            console.log(`📄 Loading page: ${pageName}`, pageHandler);
            
            // Initialize page with proper method detection
            if (typeof pageHandler.init === 'function') {
                console.log(`✅ Calling ${pageName}.init()`);
                await pageHandler.init(params);
            } else if (typeof pageHandler.loadDashboard === 'function') {
                console.log(`✅ Calling ${pageName}.loadDashboard()`);
                await pageHandler.loadDashboard(params);
            } else if (typeof pageHandler.loadPage === 'function') {
                console.log(`✅ Calling ${pageName}.loadPage()`);
                await pageHandler.loadPage(params);
            } else if (typeof pageHandler.load === 'function') {
                console.log(`✅ Calling ${pageName}.load()`);
                await pageHandler.load(params);
            } else {
                console.error(`❌ No init method found for ${pageName}`, pageHandler);
                throw new Error(`Page ${pageName} has no init/load method`);
            }
            
            console.log(`✅ Page loaded successfully: ${pageName}`);
            
        } catch (error) {
            console.error(`❌ Page load error for ${pageName}:`, error);
            console.error("Error stack:", error.stack);
            
            // Show error state without throwing
            $("#mainContent").html(`
                <div class="alert alert-danger" role="alert">
                    <h4 class="alert-heading">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        Navigation Error
                    </h4>
                    <p>Failed to load ${capitalizeFirst(pageName)} page.</p>
                    <p class="small text-muted mb-0">${error.message}</p>
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
            
            // Don't throw, just log - this prevents navigation from completely breaking
            return;
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
        document.title = `${this.PAGE_TITLES[pageName] || capitalizeFirst(pageName)} · KYRO`;
        
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
        
        // Default to dashboard for unknown pages, and for pages this role cannot open
        if (!this.pages[pageName] || !Auth.canOpen(pageName)) {
            pageName = "dashboard";
        }
        
        // Keep navigateTo's "already on this page" check right after back/forward
        this.currentPage = pageName;
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
    
    PAGE_TITLES: {
        dashboard: 'Dashboard', 'periodic-reviews': 'Periodic Reviews', cases: 'Review Cases', case: 'Case', patterns: 'Behavior Patterns',
        regulations: 'Regulations', rules: 'Rules', process: 'How KYRO works', feeds: 'Data Feeds', admin: 'Users and Access', profile: 'My Profile'
    },

    // ── Header search: customers by name or CUST code ──────────────────────
    search: { items: [], active: -1, timer: null, seq: 0 },

    setupSearch() {
        const $input = $("#globalSearch");
        if (!$input.length) return;
        $input.on("input", () => {
            clearTimeout(this.search.timer);
            this.search.timer = setTimeout(() => this.runSearch($input.val()), 220);
        });
        $input.on("focus", () => { if (this.search.items.length) this.showSearch(true); });
        $input.on("keydown", (e) => {
            const n = this.search.items.length;
            if (e.key === 'ArrowDown' && n) { e.preventDefault(); this.setActiveResult((this.search.active + 1) % n); }
            else if (e.key === 'ArrowUp' && n) { e.preventDefault(); this.setActiveResult((this.search.active - 1 + n) % n); }
            else if (e.key === 'Enter') { e.preventDefault(); if (n) this.openSearchResult(this.search.items[Math.max(0, this.search.active)]); }
            else if (e.key === 'Escape') { this.showSearch(false); $input.trigger("blur"); }
        });
        $("#kyroSearchResults").on("mousedown", ".ks__item", (e) => {
            e.preventDefault();  // keep focus in the box until the result opens
            this.openSearchResult(this.search.items[$(e.currentTarget).data("index")]);
        });
        $(document).on("mousedown", (e) => { if (!$(e.target).closest("#kyroSearch").length) this.showSearch(false); });
        // "/" jumps to the search box, as long as the user is not typing somewhere else
        $(document).on("keydown", (e) => {
            if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
            if ($(e.target).is("input, textarea, select, [contenteditable=true]")) return;
            e.preventDefault();
            $input.trigger("focus").trigger("select");
        });
    },

    showSearch(open) {
        $("#kyroSearchResults").toggleClass("d-none", !open);
        $("#globalSearch").attr("aria-expanded", String(open));
    },

    setActiveResult(index) {
        this.search.active = index;
        $("#kyroSearchResults .ks__item").each((i, el) => $(el).toggleClass("is-active", i === index).attr("aria-selected", String(i === index)));
    },

    async runSearch(raw) {
        const query = (raw || '').trim();
        const seq = ++this.search.seq;
        if (query.length < 2) { this.search.items = []; this.showSearch(false); return; }
        if (!Auth.can('cases.view')) {
            $("#kyroSearchResults").html('<p class="ks__empty">Your role does not open customer records.</p>');
            this.showSearch(true);
            return;
        }
        // A customer code (CUST-012) is looked up directly; anything else searches names
        const params = { q: query };
        const code = query.toUpperCase().replace(/^CUST[\s-]?(\d+)$/, (m, n) => `CUST-${n.padStart(3, '0')}`);
        if (/^CUST-\d+$/.test(code) && window.Cases) {
            await Cases.loadCustomerCodes();
            if (Cases.customerIds[code]) { delete params.q; params.customer_id = Cases.customerIds[code]; }
        }
        let items;
        try {
            items = await API.get('/search', params);
        } catch (error) {
            if (seq !== this.search.seq) return;
            $("#kyroSearchResults").html('<p class="ks__empty">Search is not available right now.</p>');
            this.showSearch(true);
            return;
        }
        if (seq !== this.search.seq) return;  // a newer search has started
        if (window.Cases) await Cases.loadCustomerCodes();
        this.search.items = items;
        this.search.active = items.length ? 0 : -1;
        const band = (score) => (score >= 80 ? 'high' : score >= 60 ? 'medium' : 'low');
        $("#kyroSearchResults").html(items.length ? items.map((c, i) => `
            <button type="button" class="ks__item${i === 0 ? ' is-active' : ''}" role="option" aria-selected="${i === 0}" data-index="${i}">
                <span class="ks__avatar" aria-hidden="true">${escapeHtml(c.name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '?')}</span>
                <span class="ks__text">
                    <strong>${escapeHtml(c.name)}</strong>
                    <small>${escapeHtml((window.Cases && Cases.customerCodes[c.customer_id]) || '')}${c.customer_type ? ` &middot; ${escapeHtml(c.customer_type.charAt(0) + c.customer_type.slice(1).toLowerCase())}` : ''}${c.country ? ` &middot; ${escapeHtml(c.country)}` : ''}</small>
                </span>
                <span class="ks__meta">
                    ${c.sanctions ? '<span class="cd-chip cd-chip--high">Sanctions</span>' : ''}${c.pep ? '<span class="cd-chip cd-chip--medium">PEP</span>' : ''}
                    ${c.open_alerts ? `<span class="rq-score rq-score--${band(c.max_risk_score)}">${c.max_risk_score}</span><small>${c.open_alerts} open</small>` : '<small>no open alerts</small>'}
                </span>
            </button>`).join('') + '<p class="ks__hint">Enter opens the highest-risk open case</p>'
            : `<p class="ks__empty">No customer matches "${escapeHtml(query)}".</p>`);
        this.showSearch(true);
    },

    openSearchResult(item) {
        if (!item) return;
        this.showSearch(false);
        $("#globalSearch").val('').trigger("blur");
        this.search.items = [];
        if (item.top_alert_id) {
            // The case page is one route for every case, so tell it directly when it is already open
            if (this.currentPage === 'case') CaseDetail.open(item.top_alert_id);
            else this.navigateTo('case', { id: item.top_alert_id });
            return;
        }
        // No open alert: show the customer's alerts of any status in the queue
        const params = { customerId: item.customer_id, customerName: item.name };
        if (this.currentPage === 'cases') Cases.init(params);
        else this.navigateTo('cases', params);
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
        // Badge and dropdown are owned by notifications.js
        if (window.Notifications) {
            Notifications.add(notification);
        }
        
        // Show toast notification
        showToast("info", `New ${Notifications.humanize(notification.alert_type)} alert for ${Notifications.escape(notification.customer_name)}`, "New Alert");
        
        // Play notification sound
        playNotificationSound("alert");
        
        // Update dashboard if on dashboard page
        if (this.currentPage === "dashboard" && window.Dashboard) {
            Dashboard.handleNewAlert(notification);
        }
    }
};

// Template artwork for each page's heading band, keyed by route. The dashboard
// renders its own; pages not listed here get none.
const PAGE_HEAD_ART = {
    cases: "investigation",
    "periodic-reviews": "review-checklist",
    patterns: "analytics-search"
};

function decoratePageHeads() {
    const page = window.location.pathname.replace(/^\/+/, "").split("/")[0];
    const art = PAGE_HEAD_ART[page];
    if (!art) return;
    document.querySelectorAll("#mainContent .kyro-page-head:not(.has-art)").forEach((head) => {
        head.classList.add("has-art");
        head.insertAdjacentHTML(
            "beforeend",
            `<div class="kyro-page-art" aria-hidden="true"><img src="assets/template/icons/${art}.svg" alt=""></div>`
        );
    });
}

$(function() {
    const main = document.getElementById("mainContent");
    if (main) {
        new MutationObserver(decoratePageHeads).observe(main, { childList: true, subtree: true });
    }
});

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