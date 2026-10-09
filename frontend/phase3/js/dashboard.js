/**
 * KYRO Dashboard - Main Dashboard Implementation
 * Handles KPI cards, charts, real-time alerts, and system monitoring
 */

const Dashboard = {
    charts: {},
    realTimeUpdates: true,
    updateInterval: 30000, // 30 seconds
    
    init() {
        this.loadDashboard();
        this.setupEventListeners();
        this.startRealTimeUpdates();
    },
    
    async loadDashboard() {
        showLoading("#mainContent", "Loading dashboard...");
        
        try {
            // Force clear API cache to get fresh data
            if (API && API.clearCache) {
                API.clearCache();
            }
            
            const dashboardHtml = await this.getDashboardHTML();
            $("#mainContent").html(dashboardHtml);
            
            // Load data and initialize components
            await Promise.all([
                this.loadKPIs(),
                this.initializeCharts(),
                this.loadRecentAlerts(),
                this.loadReviewCounts()
            ]);
            this.markUpdated();
            
        } catch (error) {
            console.error("Dashboard load error:", error);
            $("#mainContent").html(`
                <div class="alert alert-danger" role="alert">
                    <h4 class="alert-heading">Dashboard Load Error</h4>
                    <p>Failed to load dashboard data. Please refresh the page or contact support.</p>
                    <button class="btn btn-outline-danger" onclick="Dashboard.loadDashboard()">
                        <i class="fas fa-redo me-2"></i>Retry
                    </button>
                </div>
            `);
        }
    },
    
    
    getDashboardHTML() {
        const user = (window.Auth && Auth.getUser && Auth.getUser()) || {};
        const displayName = user.full_name || user.username || "";
        const name = `<span id="kdGreetName">${displayName ? ", " + this.escapeHtml(displayName) : ""}</span>`;
        const hour = new Date().getHours();
        const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
        const today = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
        const icon = (file) => `<img src="assets/template/icons/${file}.svg" alt="" aria-hidden="true">`;

        return `
            <div class="kyro-dashboard-container kd">
                <!-- Welcome band -->
                <div class="kyro-page-head kd-welcome">
                    <div class="kd-welcome__text">
                        <span class="kyro-kicker">${today}</span>
                        <h1 class="kyro-page-title">${greeting}${name}</h1>
                        <p class="kyro-page-sub">Here is what needs your attention across cases, customer risk and behavioral signals.</p>
                        <div class="kyro-page-actions mt-4">
                            <button class="btn btn-primary px-4" onclick="App.navigateTo('cases')">
                                <i class="fas fa-briefcase me-2"></i>Review Cases
                            </button>
                            <button class="btn btn-outline-primary px-4" onclick="App.navigateTo('periodic-reviews')">
                                <i class="fas fa-calendar-plus me-2"></i>Periodic Reviews
                            </button>
                            <button class="btn kd-refresh refresh-dashboard" type="button" title="Refresh dashboard">
                                <i class="fas fa-rotate-right"></i>
                                <span>Updated <span id="kdUpdatedAt">just now</span></span>
                            </button>
                        </div>
                    </div>
                    <div class="kd-welcome__art" aria-hidden="true">
                        <img src="assets/template/icons/analyst-report.svg" alt="">
                    </div>
                </div>

                <!-- KPI row -->
                <div class="kd-kpis">
                    <a class="kd-kpi" href="/cases" data-page="cases">
                        <span class="kd-kpi__icon">${icon("investigation")}</span>
                        <span class="kd-kpi__body">
                            <span class="kd-kpi__label">Open Alerts</span>
                            <span class="kd-kpi__value" id="kpiOpenAlerts">&ndash;</span>
                            <span class="kd-kpi__meta" id="kpiFalsePositive">Awaiting review</span>
                        </span>
                    </a>
                    <a class="kd-kpi" href="/patterns" data-page="patterns">
                        <span class="kd-kpi__icon">${icon("customers")}</span>
                        <span class="kd-kpi__body">
                            <span class="kd-kpi__label">Customers Monitored</span>
                            <span class="kd-kpi__value" id="kpiCustomers">&ndash;</span>
                            <span class="kd-kpi__meta" id="kpiHighRisk">&nbsp;</span>
                        </span>
                    </a>
                    <a class="kd-kpi" href="/periodic-reviews" data-page="periodic-reviews">
                        <span class="kd-kpi__icon">${icon("review-checklist")}</span>
                        <span class="kd-kpi__body">
                            <span class="kd-kpi__label">Periodic Reviews Due</span>
                            <span class="kd-kpi__value" id="kpiReviewsDue">&ndash;</span>
                            <span class="kd-kpi__meta" id="kpiReviewsOverdue">&nbsp;</span>
                        </span>
                    </a>
                    <a class="kd-kpi" href="/patterns" data-page="patterns">
                        <span class="kd-kpi__icon">${icon("transaction-report")}</span>
                        <span class="kd-kpi__body">
                            <span class="kd-kpi__label">Transactions</span>
                            <span class="kd-kpi__value" id="kpiTransactions">&ndash;</span>
                            <span class="kd-kpi__meta" id="kpiPatternHits">&nbsp;</span>
                        </span>
                    </a>
                </div>

                <!-- Row: alerts by rule + risk profile -->
                <div class="kd-grid kd-grid--wide">
                    <section class="card kd-panel">
                        <header class="kd-panel__head">
                            <div>
                                <h2>Alerts by Rule</h2>
                                <p class="aml-subtitle" id="alertsByRuleSubtitle">Alerts created in the last 30 days, by the rule that fired</p>
                            </div>
                            <a class="kd-link" href="/cases" data-page="cases">Review cases <i class="fas fa-arrow-right"></i></a>
                        </header>
                        <div class="kd-chart-box kd-chart-box--fill" id="alertsByRuleBox">
                            <canvas id="alertsByRuleChart" aria-label="Alerts by rule" role="img"></canvas>
                        </div>
                    </section>

                    <section class="card kd-panel">
                        <header class="kd-panel__head">
                            <div>
                                <h2>Risk Profile</h2>
                                <p class="aml-subtitle">How unresolved alerts and customers split by risk</p>
                            </div>
                        </header>
                        <div class="kd-split" id="openAlertBands"></div>
                        <div class="kd-split" id="customerRiskBands"></div>
                    </section>
                </div>

                <!-- Row: daily alert volume + recent alerts -->
                <div class="kd-grid kd-grid--wide">
                    <section class="card kd-panel">
                        <header class="kd-panel__head">
                            <div>
                                <h2>Alert Volume</h2>
                                <p class="aml-subtitle">Alerts created per day, last 14 days</p>
                            </div>
                            <div class="kd-legend">
                                <span><span class="kd-swatch" style="background:#7c2d12"></span> High</span>
                                <span><span class="kd-swatch" style="background:#ea580c"></span> Medium</span>
                                <span><span class="kd-swatch" style="background:#fb923c"></span> Low</span>
                            </div>
                        </header>
                        <div class="kd-chart-box kd-chart-box--fill">
                            <canvas id="alertVolumeChart" aria-label="Alerts created per day by risk band" role="img"></canvas>
                        </div>
                    </section>

                    <section class="card kd-panel">
                        <header class="kd-panel__head">
                            <div>
                                <h2>Recent Alerts</h2>
                                <p class="aml-subtitle">Newest open alerts across all customers</p>
                            </div>
                            <a class="kd-link" href="/cases" data-page="cases">View all <i class="fas fa-arrow-right"></i></a>
                        </header>
                        <ul class="kd-alerts" id="kdRecentAlerts">
                            <li class="kd-skeleton"></li><li class="kd-skeleton"></li><li class="kd-skeleton"></li><li class="kd-skeleton"></li>
                        </ul>
                    </section>
                </div>

                <!-- Row: case status, behavioral flags, transactions -->
                <div class="kd-grid kd-grid--thirds">
                    <section class="card kd-panel">
                        <header class="kd-panel__head">
                            <div>
                                <h2>Case Status Overview</h2>
                                <p class="aml-subtitle">All alerts by workflow status</p>
                            </div>
                        </header>
                        <div class="kd-split" id="caseStatusSplit"></div>
                    </section>

                    <section class="card kd-panel">
                        <header class="kd-panel__head">
                            <div>
                                <h2>Behavioral Flags</h2>
                                <p class="aml-subtitle">Customers whose last 30 days differ from their own previous 90</p>
                            </div>
                            <a class="kd-link" href="/patterns" data-page="patterns">Details <i class="fas fa-arrow-right"></i></a>
                        </header>
                        <ul class="kd-bars" id="behavioralFlagsList">
                            <li class="kd-skeleton"></li><li class="kd-skeleton"></li><li class="kd-skeleton"></li><li class="kd-skeleton"></li>
                        </ul>
                    </section>

                    <section class="card kd-panel kd-panel--dark" style="background: #1a1a1a;">
                        <header class="kd-panel__head">
                            <div>
                                <h2 style="color: #FF8D28 !important;">Transaction Overview</h2>
                                <p class="aml-subtitle" style="color: #9ca3af !important;">All transactions to date</p>
                            </div>
                        </header>
                        <ul class="kd-tx">
                            <li>
                                <span class="kd-tx__icon"><i class="fas fa-receipt"></i></span>
                                <span><small>Total Transactions</small><strong id="txOverviewCount">&ndash;</strong></span>
                            </li>
                            <li>
                                <span class="kd-tx__icon"><i class="fas fa-coins"></i></span>
                                <span><small>Total Volume</small><strong id="txOverviewVolume">&ndash;</strong></span>
                            </li>
                            <li>
                                <span class="kd-tx__icon"><i class="fas fa-scale-balanced"></i></span>
                                <span><small>Average Amount</small><strong id="txOverviewAverage">&ndash;</strong></span>
                            </li>
                        </ul>
                        <p class="kd-tx__note"><i class="fas fa-circle-info me-1"></i>Amounts are summed across currencies, not converted.</p>
                    </section>
                </div>

                <!-- Take Action -->
                <div class="kyro-section-head">
                    <h2 class="kyro-section-title">Take Action</h2>
                    <p class="kyro-section-desc">Jump straight into the review workflows, with live counts of what needs attention.</p>
                </div>
                <div class="kd-grid kd-grid--thirds kd-actions">
                    <div class="kt-service-card" role="link" tabindex="0" onclick="App.navigateTo('cases')" onkeydown="if (event.key === 'Enter') App.navigateTo('cases')">
                        <div class="kt-service-card__icon kt-service-card__icon--img">${icon("investigation")}</div>
                        <h3 class="kt-service-card__title">Review Cases</h3>
                        <p class="kt-service-card__text">Process and resolve all flagged cases, from triage to final disposition.</p>
                        <div class="kt-service-card__footer">
                            <span class="kt-service-card__link">View Details <i class="fas fa-arrow-right"></i></span>
                            <span class="kt-service-card__count" id="takeActionCasesVal">&ndash;</span>
                        </div>
                    </div>
                    <div class="kt-service-card kt-service-card--dark" role="link" tabindex="0" onclick="App.navigateTo('periodic-reviews')" onkeydown="if (event.key === 'Enter') App.navigateTo('periodic-reviews')">
                        <div class="kt-service-card__icon kt-service-card__icon--img">${icon("review-checklist")}</div>
                        <h3 class="kt-service-card__title">Periodic Reviews</h3>
                        <p class="kt-service-card__text">Schedule and manage time-based customer reviews before they fall due.</p>
                        <div class="kt-service-card__footer">
                            <span class="kt-service-card__link">View Details <i class="fas fa-arrow-right"></i></span>
                            <span class="kt-service-card__count" id="takeActionReviewsVal">&ndash;</span>
                        </div>
                    </div>
                    <div class="kt-service-card" role="link" tabindex="0" onclick="App.navigateTo('patterns')" onkeydown="if (event.key === 'Enter') App.navigateTo('patterns')">
                        <div class="kt-service-card__icon kt-service-card__icon--img">${icon("analytics-search")}</div>
                        <h3 class="kt-service-card__title">Behavioral Patterns</h3>
                        <p class="kt-service-card__text">Analyze and investigate behavioral anomalies against customer baselines.</p>
                        <div class="kt-service-card__footer">
                            <span class="kt-service-card__link">View Details <i class="fas fa-arrow-right"></i></span>
                            <span class="kt-service-card__count" id="takeActionPatternsVal">&ndash;</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    },

    escapeHtml(value) {
        return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    },

    humanize(code) {
        return String(code || "")
            .toLowerCase()
            .replace(/_/g, " ")
            .replace(/\b\w/g, (c) => c.toUpperCase());
    },

    compactNumber(value) {
        return Number(value || 0).toLocaleString(undefined, { notation: "compact", maximumFractionDigits: 1 });
    },

    markUpdated() {
        $("#kdUpdatedAt").text(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    },

    async loadRecentAlerts() {
        const $list = $("#kdRecentAlerts");
        if (!$list.length) return;
        if (!Auth.can('cases.view')) {
            $list.html(`<li class="kd-empty">Individual alerts are not shown for your role.</li>`);
            return;
        }
        try {
            const alerts = (await API.get("/dashboard/recent-alerts")) || [];
            if (!alerts.length) {
                $list.html(`<li class="kd-empty"><i class="fas fa-circle-check"></i>No alerts right now. You're all caught up.</li>`);
                return;
            }
            const riskClass = (score) => (score >= 70 ? "high" : score >= 40 ? "medium" : "low");
            $list.html(alerts.slice(0, 6).map((a) => `
                <li>
                    <a class="kd-alert" href="/cases" data-page="cases">
                        <span class="kd-alert__score kd-alert__score--${riskClass(a.risk_score)}" title="Risk score">${Number(a.risk_score || 0)}</span>
                        <span class="kd-alert__body">
                            <strong>${this.escapeHtml(a.customer_name || "Unknown customer")}</strong>
                            <small>${this.escapeHtml(this.humanize(a.alert_type))} &middot; ${this.escapeHtml(this.humanize(a.status))}</small>
                        </span>
                        <span class="kd-alert__time">${typeof formatRelativeTime === "function" ? formatRelativeTime(a.created_at) : ""}</span>
                    </a>
                </li>
            `).join(""));
        } catch (error) {
            console.error("Recent alerts load error:", error);
            $list.html(`<li class="kd-empty kd-empty--error"><i class="fas fa-triangle-exclamation"></i>Couldn't load recent alerts.</li>`);
        }
    },

    async loadReviewCounts() {
        if (!Auth.can('cases.view')) return;
        try {
            const [scheduled, overdue] = await Promise.all([
                API.get("/kyc-reviews", { review_status: "SCHEDULED", page_size: 1 }),
                API.get("/kyc-reviews", { review_status: "OVERDUE", page_size: 1 })
            ]);
            const scheduledCount = (scheduled && scheduled.total) || 0;
            const overdueCount = (overdue && overdue.total) || 0;
            const due = scheduledCount + overdueCount;
            $("#kpiReviewsDue").text(due.toLocaleString());
            $("#kpiReviewsOverdue")
                .text(overdueCount ? `${overdueCount.toLocaleString()} overdue` : "None overdue")
                .toggleClass("kd-kpi__meta--alert", overdueCount > 0);
            $("#takeActionReviewsVal").text(`${due.toLocaleString()} Due`);
        } catch (error) {
            console.error("Review counts load error:", error);
            $("#kpiReviewsDue").text("–");
            $("#takeActionReviewsVal").text("View");
        }
    },

    async loadKPIs() {
            try {
                // Show loading state
                this.showKPILoading();

                console.log("📊 Fetching KPIs and patterns from API in parallel...");

                // Fetch KPIs and patterns in parallel for better performance
                const [kpisResult, patternsResult] = await Promise.allSettled([
                    API.get(API.endpoints.kpis),
                    API.get("/dashboard/patterns")
                ]);

                // Hide loading state
                this.hideKPILoading();

                // Process KPIs data
                if (kpisResult.status === 'fulfilled') {
                    const data = kpisResult.value;
                    console.log("✅ KPI Data received:", data);

                    // Keep the header bell in step with the dashboard
                    if (window.Notifications) {
                        Notifications.setCount(data.pending_alerts);
                    }

                    // KPI row
                    const pending = Number(data.pending_alerts || 0);
                    const highRisk = Number(data.high_risk_customers || 0);
                    $("#kpiOpenAlerts").text(pending.toLocaleString());
                    $("#kpiFalsePositive").text(`False-positive rate ${Number(data.false_positive_rate || 0).toFixed(1)}%`);
                    $("#kpiCustomers").text(Number(data.total_customers || 0).toLocaleString());
                    $("#kpiHighRisk")
                        .text(`${highRisk.toLocaleString()} high risk`)
                        .toggleClass("kd-kpi__meta--alert", highRisk > 0);
                    $("#kpiTransactions").text(Number(data.total_transactions || 0).toLocaleString());

                    // Transaction Overview card. Amounts span several currencies and
                    // aren't converted, so no currency symbol is shown.
                    const formattedTotalTx = Number(data.total_transactions || 0).toLocaleString();
                    const formattedTotalVol = this.compactNumber(data.total_volume);
                    const formattedAvgAmt = Number(data.avg_amount || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});

                    console.log("💰 Transaction Stats:", { formattedTotalTx, formattedTotalVol, formattedAvgAmt });

                    $("#txOverviewCount").text(formattedTotalTx);
                    $("#txOverviewVolume").text(formattedTotalVol);
                    $("#txOverviewAverage").text(formattedAvgAmt);

                    // Take Action counts (periodic reviews come from loadReviewCounts)
                    $("#takeActionCasesVal").text(`${pending.toLocaleString()} Active`);
                } else {
                    console.error("Failed to load KPIs:", kpisResult.reason);
                }

                // Process patterns data
                if (patternsResult.status === 'fulfilled') {
                    const patternData = patternsResult.value;
                    console.log("✅ Pattern Data received:", patternData);

                    if (patternData) {
                        // Update Behavioral Patterns Take Action count
                        const flagged = Number(patternData.customers_affected || 0);
                        $("#takeActionPatternsVal").text(`${flagged.toLocaleString()} Customers`);
                        $("#kpiPatternHits").text(`${flagged.toLocaleString()} customers with a behaviour change`);

                        // One bar per pattern: how many customers show it
                        if (patternData.patterns) {
                            const patterns = [...patternData.patterns].sort((x, y) => (y.customers || 0) - (x.customers || 0));
                            const max = Math.max(1, ...patterns.map(p => p.customers || 0));
                            const html = patterns.map(p => `
                                <li title="${this.escapeHtml(p.description)}">
                                    <div class="kd-bars__row">
                                        <span>${this.escapeHtml(p.label)}</span>
                                        <strong>${Number(p.customers || 0).toLocaleString()} <small class="text-muted fw-normal">customer${p.customers === 1 ? '' : 's'}</small></strong>
                                    </div>
                                    <div class="kd-bars__track"><span style="width: ${Math.round(((p.customers || 0) / max) * 100)}%"></span></div>
                                </li>
                            `).join('');
                            $("#behavioralFlagsList").html(html || `<li class="kd-empty">No behaviour changes in this window.</li>`);
                        }
                    }
                } else {
                    console.error("Failed to load patterns:", patternsResult.reason);
                }

            } catch (error) {
                console.error("KPI load error:", error);
            }
        }
,
    
    getChartThemeColors() {
        const isDark = document.documentElement.getAttribute("data-theme") === "dark";
        return {
            textColor: isDark ? "#94a3b8" : "#7b8794",
            gridColor: isDark ? "rgba(255, 255, 255, 0.06)" : "rgba(0, 0, 0, 0.05)",
            labelColor: isDark ? "#e2e8f0" : "#1c2430",
            surfaceColor: isDark ? "#1e293b" : "#ffffff",
            accentColor: "#FF8D28",
            fillColor: isDark ? "rgba(255, 141, 40, 0.08)" : "rgba(255, 141, 40, 0.05)"
        };
    },

    updateChartColors() {
        // Handled via dashboard redraws on theme change
    },

    async initializeCharts() {
        try {
            // Show loading overlays
            this.showChartLoading();
            
            console.log("📈 Fetching chart data from API...");
            // Force fresh data with version timestamp
            const chartData = await API.get("/dashboard/charts", { v: Date.now() });
            console.log("✅ Chart Data received:", chartData);
            
            // Hide loading overlays
            this.hideChartLoading();
            
            this.renderRiskProfile(chartData);
            this.renderCaseStatus(chartData);
            await this.renderOtherCharts(chartData);
            
        } catch (error) {
            console.error("Charts initialization error:", error);
            this.hideChartLoading();
            this.renderFallbackCharts();
        }
    },
    
    // Risk bands are an ordered scale, so they share one hue (darker = higher risk).
    // Case statuses are states, so each has its own colour, always shown with a label.
    RISK_COLORS: { high: '#7c2d12', medium: '#ea580c', low: '#fb923c' },
    STATUS_COLORS: { RESOLVED: '#0ca30c', OPEN: '#2a78d6', IN_REVIEW: '#c98500', ESCALATED: '#d03b3b' },

    /**
     * Part-to-whole as one stacked bar plus a labelled row per part, so the
     * numbers are readable without relying on colour.
     */
    renderSplit(selector, title, parts, emptyText) {
        const total = parts.reduce((sum, p) => sum + p.value, 0);
        const share = (v) => (total ? (v / total) * 100 : 0);
        const pct = (v) => {
            const s = share(v);
            return s > 0 && s < 0.1 ? '<0.1%' : `${s.toFixed(1)}%`;
        };
        const segments = parts.filter(p => p.value > 0).map(p => `
            <span class="kd-stack__seg" style="flex: ${p.value} 1 0; background: ${p.color};"
                  title="${this.escapeHtml(p.label)}: ${p.value.toLocaleString()} (${pct(p.value)})"></span>`).join('');
        const rows = parts.map(p => `
            <li>
                <span><span class="kd-swatch" style="background:${p.color}"></span>${this.escapeHtml(p.label)}</span>
                <span class="kd-split__value"><strong>${p.value.toLocaleString()}</strong><small>${pct(p.value)}</small></span>
            </li>`).join('');
        $(selector).html(`
            <div class="kd-split__head"><span>${this.escapeHtml(title)}</span><strong>${total.toLocaleString()}</strong></div>
            ${total ? `<div class="kd-stack" role="img" aria-label="${this.escapeHtml(title)}">${segments}</div>`
                    : `<p class="kd-split__empty">${this.escapeHtml(emptyText)}</p>`}
            <ul class="kd-list kd-list--tight">${rows}</ul>`);
    },

    renderRiskProfile(chartData) {
        const bands = chartData.open_alert_bands || {};
        const customers = chartData.risk_counts || {};
        const c = this.RISK_COLORS;
        this.renderSplit('#openAlertBands', 'Unresolved alerts by risk score', [
            { label: 'High (80+)', value: Number(bands.high || 0), color: c.high },
            { label: 'Medium (60–79)', value: Number(bands.medium || 0), color: c.medium },
            { label: 'Low (under 60)', value: Number(bands.low || 0), color: c.low }
        ], 'No unresolved alerts.');
        this.renderSplit('#customerRiskBands', 'Customers by risk rating', [
            { label: 'High', value: Number(customers.HIGH || 0), color: c.high },
            { label: 'Medium', value: Number(customers.MEDIUM || 0), color: c.medium },
            { label: 'Low', value: Number(customers.LOW || 0), color: c.low }
        ], 'No customers yet.');
    },

    renderCaseStatus(chartData) {
        const s = chartData.status_counts || chartData.status_distribution || {};
        const c = this.STATUS_COLORS;
        this.renderSplit('#caseStatusSplit', 'All alerts', [
            { label: 'Open', value: Number(s.OPEN || 0), color: c.OPEN },
            { label: 'In review', value: Number(s.IN_REVIEW || 0), color: c.IN_REVIEW },
            { label: 'Escalated', value: Number(s.ESCALATED || 0), color: c.ESCALATED },
            { label: 'Resolved', value: Number(s.RESOLVED || 0), color: c.RESOLVED }
        ], 'No alerts yet.');
    },

    renderFallbackCharts() {
        // Show an explicit "unavailable" state rather than placeholder numbers.
        const message = `<div class="kd-empty kd-empty--error"><i class="fas fa-triangle-exclamation"></i>Chart data unavailable. Try refreshing.</div>`;
        $("#alertsByRuleBox, #openAlertBands, #caseStatusSplit").html(message);
        $("#customerRiskBands").empty();
    },

    tooltipStyle() {
        return {
            backgroundColor: '#ffffff', borderColor: '#e5e7eb', borderWidth: 1,
            titleColor: '#1c2430', bodyColor: '#4b5563', padding: 10, cornerRadius: 8,
            boxWidth: 10, boxHeight: 10, boxPadding: 4, usePointStyle: false
        };
    },

    async renderOtherCharts(chartData) {
        try {
            const theme = this.getChartThemeColors();
            const tick = { color: theme.textColor, font: { size: 12, family: 'Roboto' } };

            // Chart 1: alerts by rule, largest first. One measure, so one colour.
            const ruleCanvas = document.getElementById('alertsByRuleChart');
            const byRule = (chartData.alerts_by_rule && chartData.alerts_by_rule.rules) || [];
            if (this.charts.alertsByRule) this.charts.alertsByRule.destroy();
            if (ruleCanvas && !byRule.length) {
                $("#alertsByRuleBox").html(`<div class="kd-empty"><i class="fas fa-circle-check"></i>No alerts in the last 30 days.</div>`);
            } else if (ruleCanvas) {
                const ruleNames = typeof Cases !== 'undefined' && Cases.RULES ? Cases.RULES : {};
                const rules = byRule.slice(0, 10);
                const labels = rules.map(r => (ruleNames[r.rule] ? `${r.rule}  ${ruleNames[r.rule][0]}` : (r.rule === 'NO_RULE' ? 'No rule recorded' : r.rule)));
                $("#alertsByRuleBox").css('height', `${Math.max(220, rules.length * 38 + 30)}px`);

                this.charts.alertsByRule = new Chart(ruleCanvas, {
                    type: 'bar',
                    data: {
                        labels,
                        datasets: [{
                            label: 'Alerts',
                            data: rules.map(r => r.alerts),
                            backgroundColor: this.RISK_COLORS.medium,
                            borderRadius: { topRight: 4, bottomRight: 4, topLeft: 0, bottomLeft: 0 },
                            borderSkipped: false,
                            barThickness: 16
                        }]
                    },
                    options: {
                        indexAxis: 'y',
                        responsive: true,
                        maintainAspectRatio: false,
                        layout: { padding: { right: 56 } },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                ...this.tooltipStyle(),
                                displayColors: false,
                                callbacks: {
                                    label: (ctx) => {
                                        const r = rules[ctx.dataIndex];
                                        const fp = r.false_positive_rate == null
                                            ? 'no outcomes recorded yet'
                                            : `${(r.false_positive_rate * 100).toFixed(0)}% false positive`;
                                        return [`${r.alerts.toLocaleString()} alerts`, `${r.resolved.toLocaleString()} resolved, ${fp}`];
                                    }
                                }
                            }
                        },
                        scales: {
                            x: { beginAtZero: true, grid: { color: theme.gridColor }, border: { display: false },
                                 ticks: { ...tick, maxTicksLimit: 6, callback: (v) => Number(v).toLocaleString() } },
                            y: { grid: { display: false }, border: { display: false }, ticks: { ...tick, color: theme.labelColor } }
                        }
                    },
                    // Value at the tip of each bar
                    plugins: [{
                        id: 'barEndLabels',
                        afterDatasetsDraw: (chart) => {
                            const { ctx } = chart;
                            ctx.save();
                            ctx.font = '600 12px Roboto, sans-serif';
                            ctx.fillStyle = theme.labelColor;
                            ctx.textBaseline = 'middle';
                            chart.getDatasetMeta(0).data.forEach((bar, i) => {
                                ctx.fillText(rules[i].alerts.toLocaleString(), bar.x + 8, bar.y);
                            });
                            ctx.restore();
                        }
                    }]
                });
            }

            // Chart 2: alerts created per day, stacked by risk band
            const volumeCanvas = document.getElementById('alertVolumeChart');
            if (volumeCanvas) {
                if (this.charts.alertVolume) this.charts.alertVolume.destroy();
                const daily = chartData.alert_volume_daily || { dates: [], high: [], medium: [], low: [] };
                const dayLabels = daily.dates.map(d => {
                    const date = new Date(`${d}T00:00:00`);
                    return isNaN(date) ? d : date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
                });
                const series = (label, key) => ({
                    label, data: daily[key], backgroundColor: this.RISK_COLORS[key],
                    borderColor: theme.surfaceColor, borderWidth: { top: 2, right: 0, bottom: 0, left: 0 },
                    maxBarThickness: 24, borderRadius: 0
                });

                this.charts.alertVolume = new Chart(volumeCanvas, {
                    type: 'bar',
                    data: { labels: dayLabels, datasets: [series('Low', 'low'), series('Medium', 'medium'), series('High', 'high')] },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: { mode: 'index', intersect: false },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                ...this.tooltipStyle(),
                                itemSort: (a, b) => b.datasetIndex - a.datasetIndex,
                                callbacks: {
                                    label: (ctx) => ` ${ctx.dataset.label}: ${Number(ctx.parsed.y).toLocaleString()}`,
                                    footer: (items) => `Total: ${items.reduce((sum, i) => sum + i.parsed.y, 0).toLocaleString()}`
                                }
                            }
                        },
                        scales: {
                            x: { stacked: true, grid: { display: false }, border: { display: false }, ticks: { ...tick, maxRotation: 0, autoSkipPadding: 12 } },
                            y: { stacked: true, beginAtZero: true, grid: { color: theme.gridColor }, border: { display: false },
                                 ticks: { ...tick, maxTicksLimit: 6, precision: 0, callback: (v) => Number(v).toLocaleString() } }
                        }
                    }
                });
            }
        } catch (error) {
            console.error("Chart initialization error:", error);
            showToast("error", "Failed to load charts");
        }
    },

    setupEventListeners() {
        // Fill in the greeting once the user profile arrives
        $(document).on("kyro:user", (e, user) => {
            const displayName = (user && (user.full_name || user.username)) || "";
            if (displayName) $("#kdGreetName").text(", " + displayName);
        });

        // Refresh button
        $(document).on("click", ".refresh-dashboard", () => {
            this.loadDashboard();
        });

        // Dashboard cards/links navigate inside the app instead of reloading
        $(document).on("click", ".kd a[data-page]", (e) => {
            e.preventDefault();
            App.navigateTo($(e.currentTarget).data("page"));
        });
        
        // Chart resize handling
        $(window).on("resize", debounce(() => {
            Object.values(this.charts).forEach(chart => {
                if (chart && chart.resize) {
                    chart.resize();
                }
            });
        }, 250));
    },
    
    startRealTimeUpdates() {
            // Update KPIs and Charts periodically every 30 seconds (reduced frequency)
            let cycle = 0;
            setInterval(async () => {
                // Only refresh while the dashboard is on screen
                if (this.realTimeUpdates && $(".kd").length) {
                    cycle += 1;
                    await Promise.all([this.loadKPIs(), this.loadRecentAlerts(), this.loadReviewCounts()]);
                    // Charts refresh every other cycle
                    if (cycle % 2 === 0) {
                        await this.initializeCharts();
                    }
                    this.markUpdated();
                }
            }, 30000);
        }
,
    
    async handleNewAlert(alert) {
        // Instantly update KPIs and Charts on new alert events
        await this.loadKPIs();
        await this.initializeCharts();
    },
    
    // Loading State Handlers
    showKPILoading() {
        // Add pulse animation to KPI cards
        $('.figma-card').addClass('loading-pulse');
    },
    
    hideKPILoading() {
        $('.figma-card').removeClass('loading-pulse');
    },
    
    showChartLoading() {
        // Add loading overlays to chart containers
        $('.chart-container, .bar-chart-kyro-container, .kyro-donut-container').each(function() {
            if (!$(this).find('.chart-loading-overlay').length) {
                $(this).css('position', 'relative').append(`
                    <div class="chart-loading-overlay">
                        <div>
                            <div class="chart-spinner"></div>
                            <div class="loading-text">Loading chart data...</div>
                        </div>
                    </div>
                `);
            }
        });
    },
    
    hideChartLoading() {
        $('.chart-loading-overlay').fadeOut(300, function() {
            $(this).remove();
        });
    }
};

// Export for use in other modules
window.Dashboard = Dashboard;