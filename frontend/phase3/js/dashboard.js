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

                <!-- Row: case volume + customer risk -->
                <div class="kd-grid kd-grid--wide">
                    <section class="aml-card kd-panel">
                        <header class="kd-panel__head">
                            <div>
                                <h2>Review Case Volume</h2>
                                <p class="aml-subtitle">Reviewed vs. flagged, last 7 days</p>
                            </div>
                            <div class="aml-legend aml-chart-legend kd-legend">
                                <span><span class="aml-dot dark"></span> Reviewed</span>
                                <span><span class="aml-dot orange"></span> Flagged</span>
                                <span class="kd-chip" id="caseVolumePeriodText">&ndash;</span>
                            </div>
                        </header>
                        <div class="aml-chart">
                            <div class="aml-gridline"><span>100</span></div>
                            <div class="aml-gridline"><span>75</span></div>
                            <div class="aml-gridline"><span>50</span></div>
                            <div class="aml-gridline"><span>25</span></div>
                            <div class="aml-gridline"><span>0</span></div>
                            <div class="aml-bars" id="volumeBars"></div>
                        </div>
                    </section>

                    <section class="aml-card aml-donut-card kd-panel">
                        <header class="kd-panel__head">
                            <div>
                                <h2>Customer Risk Profile</h2>
                                <p class="aml-subtitle">Share of customers by risk rating</p>
                            </div>
                        </header>
                        <div class="aml-donut-wrap">
                            <div class="aml-donut" id="riskDonut" role="img" aria-label="Customer risk distribution"></div>
                        </div>
                        <div class="aml-donut-legend">
                            <span class="aml-legend"><span class="aml-dot orange"></span> <span id="highRiskLegend">High Risk</span></span>
                            <span class="aml-legend"><span class="aml-dot dark"></span> <span id="lowMidLegend">Low/Mid</span></span>
                        </div>
                    </section>
                </div>

                <!-- Row: behavior trends + recent alerts -->
                <div class="kd-grid kd-grid--wide">
                    <section class="card kd-panel">
                        <header class="kd-panel__head">
                            <div>
                                <h2>Behavior Pattern Trends</h2>
                                <p class="aml-subtitle">Detected vs. flagged patterns by month</p>
                            </div>
                            <div class="kd-legend">
                                <span><span class="kd-line kd-line--dark"></span> Detected</span>
                                <span><span class="kd-line kd-line--orange"></span> Flagged</span>
                            </div>
                        </header>
                        <div class="kd-chart-box kd-chart-box--fill">
                            <canvas id="behaviorTrendsChart" aria-label="Behavior pattern trends chart" role="img"></canvas>
                        </div>
                    </section>

                    <section class="card kd-panel">
                        <header class="kd-panel__head">
                            <div>
                                <h2>Recent Alerts</h2>
                                <p class="aml-subtitle">Newest alerts across all customers</p>
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
                        <div class="kd-chart-box" style="height: 180px;">
                            <canvas id="caseStatusChart" aria-label="Case status chart" role="img"></canvas>
                        </div>
                        <ul class="kd-list mt-3">
                            <li><span><span class="kd-dot" style="background:#06B6D4"></span>Open</span><strong id="caseStatusOpen">0</strong></li>
                            <li><span><span class="kd-dot" style="background:#F59E0B"></span>In Review</span><strong id="caseStatusReview">0</strong></li>
                            <li><span><span class="kd-dot" style="background:#10B981"></span>Resolved</span><strong id="caseStatusResolved">0</strong></li>
                            <li><span><span class="kd-dot" style="background:#EF4444"></span>Escalated</span><strong id="caseStatusEscalated">0</strong></li>
                        </ul>
                    </section>

                    <section class="card kd-panel">
                        <header class="kd-panel__head">
                            <div>
                                <h2>Behavioral Flags</h2>
                                <p class="aml-subtitle">Pattern hits, last 30 days</p>
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
                        const hits = Number(patternData.total_pattern_hits || 0);
                        $("#takeActionPatternsVal").text(`${hits.toLocaleString()} Detected`);
                        $("#kpiPatternHits").text(`${hits.toLocaleString()} pattern hits in ${patternData.window_days || 30} days`);

                        // Behavioral flags as proportional bars
                        if (patternData.patterns) {
                            const patterns = [...patternData.patterns].sort((x, y) => (y.hit_count || 0) - (x.hit_count || 0));
                            const max = Math.max(1, ...patterns.map(p => p.hit_count || 0));
                            const html = patterns.map(p => `
                                <li>
                                    <div class="kd-bars__row">
                                        <span>${this.escapeHtml(p.label)}</span>
                                        <strong>${Number(p.hit_count || 0).toLocaleString()}</strong>
                                    </div>
                                    <div class="kd-bars__track"><span style="width: ${Math.round(((p.hit_count || 0) / max) * 100)}%"></span></div>
                                </li>
                            `).join('');
                            $("#behavioralFlagsList").html(html || `<li class="kd-empty">No pattern hits in this window.</li>`);
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
            
            // Generate bar chart with real CSS data
            this.renderCSSBarChart(chartData);
            
            // Generate donut chart with real CSS data
            this.renderCSSDonutChart(chartData);
            
            // Keep existing Chart.js charts for other sections
            await this.renderOtherCharts(chartData);
            
        } catch (error) {
            console.error("Charts initialization error:", error);
            this.hideChartLoading();
            this.renderFallbackCharts();
        }
    },
    
    renderCSSBarChart(chartData) {
        console.log("📊 Rendering Review Case Volume Chart with data:", chartData);
        
        const alertVolume = chartData.alert_volume || { dates: [], counts: [], flags: [], total_period: 0 };
        const dates = alertVolume.dates || [];
        const openCounts = alertVolume.counts || [];
        const flagCounts = alertVolume.flags || [];

        console.log("📊 Chart values - Dates:", dates.length, "Counts:", openCounts, "Flags:", flagCounts);

        const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
        const labels = dates.map(d => {
            const date = new Date(d);
            return isNaN(date.getDay()) ? d : dayNames[date.getDay()];
        });

        const totalLastPeriod = alertVolume.total_period !== undefined ? alertVolume.total_period : openCounts.reduce((a, b) => a + b, 0);
        console.log("📊 Total Last Period:", totalLastPeriod);
        $("#caseVolumePeriodText").text(`${totalLastPeriod.toLocaleString()} this period`);

        // Calculate max value for Y-axis scaling
        const maxVal = Math.max(...openCounts, ...flagCounts, 10);
        console.log("📊 Max value for scaling:", maxVal);
        
        // Dynamically update Y-axis gridline labels for case volume chart
        const step = Math.ceil(maxVal / 4);
        const gridlines = $("#volumeBars").closest(".aml-card").find(".aml-gridline span");
        console.log("📊 Y-axis step:", step, "Gridlines found:", gridlines.length);
        
        if (gridlines.length >= 5) {
            gridlines.eq(0).text(step * 4);
            gridlines.eq(1).text(step * 3);
            gridlines.eq(2).text(step * 2);
            gridlines.eq(3).text(step * 1);
            gridlines.eq(4).text(0);
        }

        // Generate bars with proper scaling
        const barsHtml = openCounts.map((openCnt, i) => {
            const darkVal = flagCounts[i] !== undefined ? flagCounts[i] : Math.round(openCnt * 0.7);
            const orangeVal = openCnt;
            
            // Calculate heights as percentage of max value
            const darkHeight = Math.min(Math.max(Math.round((darkVal / (step * 4)) * 100), 8), 95);
            const orangeHeight = Math.min(Math.max(Math.round((orangeVal / (step * 4)) * 100), 12), 95);
            
            return `
                <div class="aml-bar-group" title="Date: ${dates[i]} | Reviewed: ${darkVal.toLocaleString()} | Flagged: ${orangeVal.toLocaleString()}">
                    <div class="aml-bar dark" style="height: ${darkHeight}%;"></div>
                    <div class="aml-bar orange" style="height: ${orangeHeight}%;"></div>
                    <span class="aml-x-label">${labels[i]}</span>
                </div>
            `;
        }).join('');
        
        $("#volumeBars").html(barsHtml);
        console.log("✅ Review Case Volume Chart rendered successfully");
    },
    
    renderCSSDonutChart(chartData) {
        console.log("🍩 Rendering Customer Risk Profile Chart with data:", chartData);
        
        const riskCounts = chartData.risk_counts || { LOW: 0, MEDIUM: 0, HIGH: 0 };
        const lowCount = riskCounts.LOW !== undefined ? riskCounts.LOW : (chartData.risk_distribution ? chartData.risk_distribution[0] : 0);
        const mediumCount = riskCounts.MEDIUM !== undefined ? riskCounts.MEDIUM : (chartData.risk_distribution ? chartData.risk_distribution[1] : 0);
        const highCount = riskCounts.HIGH !== undefined ? riskCounts.HIGH : (chartData.risk_distribution ? chartData.risk_distribution[2] : 0);
        
        console.log("🍩 Risk counts - Low:", lowCount, "Medium:", mediumCount, "High:", highCount);
        
        const totalRisk = lowCount + mediumCount + highCount;
        const highRiskPercentage = totalRisk > 0 ? ((highCount / totalRisk) * 100).toFixed(1) : "0.0";
        const lowMidPercentage = (100 - parseFloat(highRiskPercentage)).toFixed(1);
        
        console.log("🍩 Percentages - High Risk:", highRiskPercentage + "%", "Low/Mid:", lowMidPercentage + "%");
        
        // Update legend text dynamically with live counts
        $("#highRiskLegend").text(`High Risk - ${highCount.toLocaleString()} (${highRiskPercentage}%)`);
        $("#lowMidLegend").text(`Low/Mid - ${(lowCount + mediumCount).toLocaleString()} (${lowMidPercentage}%)`);
        
        const lowMidTurn = parseFloat(lowMidPercentage) / 100;
        
        const donutStyle = `
            background: conic-gradient(
                var(--aml-dark) 0turn ${lowMidTurn}turn,
                var(--aml-orange) ${lowMidTurn}turn 1turn
            );
        `;
        
        $("#riskDonut").attr("style", donutStyle);
        console.log("✅ Customer Risk Profile Chart rendered successfully");
    },
    
    renderFallbackCharts() {
        // Show an explicit "unavailable" state rather than placeholder numbers.
        $("#volumeBars").html(`<div class="kd-empty kd-empty--error"><i class="fas fa-triangle-exclamation"></i>Chart data unavailable. Try refreshing.</div>`);
        $("#caseVolumePeriodText").text("No data");
        $("#riskDonut").attr("style", "background: #f3f4f6;");
        $("#highRiskLegend").text("High Risk: unavailable");
        $("#lowMidLegend").text("Low/Mid: unavailable");
    },

    async renderOtherCharts(chartData) {
        try {
            // Chart 1: Behavior Trends
            const behaviorCanvas = document.getElementById('behaviorTrendsChart');
            if (behaviorCanvas) {
                if (this.charts.behaviorTrends) {
                    this.charts.behaviorTrends.destroy();
                }

                const behaviorTrends = chartData.behavior_trends || { labels: [], detected: [], flagged: [] };
                const trendLabels = behaviorTrends.labels && behaviorTrends.labels.length > 0 ? behaviorTrends.labels : ['Feb','Mar','Apr','May','Jun','Jul'];
                const detectedData = behaviorTrends.detected || [0, 0, 0, 0, 0, 0];
                const flaggedData = behaviorTrends.flagged || [0, 0, 0, 0, 0, 0];

                this.charts.behaviorTrends = new Chart(behaviorCanvas, {
                    type: 'line',
                    data: {
                        labels: trendLabels,
                        datasets: [
                            {
                                label: 'Detected',
                                data: detectedData,
                                borderColor: '#1F2937',
                                borderWidth: 3,
                                pointBackgroundColor: '#1F2937',
                                pointRadius: 4,
                                fill: false,
                                tension: 0.3
                            },
                            {
                                label: 'Flagged',
                                data: flaggedData,
                                borderColor: '#FF8C42',
                                borderWidth: 3,
                                pointBackgroundColor: '#FF8C42',
                                pointRadius: 4,
                                fill: false,
                                tension: 0.3
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: {
                                grid: { display: false },
                                border: { display: false },
                                ticks: { color: '#9CA3AF', font: { size: 12, family: 'Roboto' } }
                            },
                            y: {
                                grid: { color: '#f0f0f0', drawBorder: false },
                                border: { display: false },
                                ticks: { color: '#9CA3AF', font: { size: 12, family: 'Roboto' } }
                            }
                        }
                    }
                });
            }

            // Chart 2: Case Status
            const caseStatusCanvas = document.getElementById('caseStatusChart');
            if (caseStatusCanvas) {
                const statusDist = chartData.status_distribution || { OPEN: 0, IN_REVIEW: 0, RESOLVED: 0, ESCALATED: 0 };
                const openVal = statusDist.OPEN || 0;
                const reviewVal = statusDist.IN_REVIEW || 0;
                const resolvedVal = statusDist.RESOLVED || 0;
                const escalatedVal = statusDist.ESCALATED || 0;

                $("#caseStatusOpen").text(openVal);
                $("#caseStatusReview").text(reviewVal);
                $("#caseStatusResolved").text(resolvedVal);
                $("#caseStatusEscalated").text(escalatedVal);

                if (this.charts.caseStatus) {
                    this.charts.caseStatus.destroy();
                }

                this.charts.caseStatus = new Chart(caseStatusCanvas, {
                    type: 'bar',
                    data: {
                        labels: ['Open', 'Review', 'Resolved', 'Escalated'],
                        datasets: [{
                            data: [openVal, reviewVal, resolvedVal, escalatedVal],
                            backgroundColor: ['#06B6D4', '#F59E0B', '#10B981', '#EF4444'],
                            borderRadius: 6,
                            barThickness: 30,
                            maxBarThickness: 40
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                backgroundColor: '#ffffff',
                                borderColor: '#e5e7eb',
                                borderWidth: 1,
                                titleColor: '#1F2937',
                                bodyColor: '#1F2937',
                                padding: 8,
                                cornerRadius: 6,
                                callbacks: { label: (context) => `Count: ${context.parsed.y}` }
                            }
                        },
                        scales: {
                            x: {
                                grid: { display: false },
                                border: { display: false },
                                ticks: { display: true, color: '#9CA3AF', font: { size: 10, family: 'Roboto' } }
                            },
                            y: {
                                grid: { display: true, color: '#f0f0f0', drawBorder: false },
                                border: { display: false },
                                ticks: { display: true, color: '#9CA3AF', font: { size: 10, family: 'Roboto' } }
                            }
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