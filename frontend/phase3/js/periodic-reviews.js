/**
 * KYRO Periodic Reviews - Automatic AML Review Scheduling
 * Manage automatic periodic AML review schedules with intelligent monitoring
 */

const PeriodicReviews = {
    reviewsData: [],
    
    // Pagination settings
    filters: { search: '', risk: 'all', urgency: 'all', status: 'all' },
    loadError: false,
    pagination: {
        currentPage: 1,
        pageSize: 10,
        pageSizeOptions: [10, 25, 50, 100]
    },
    
    async init(params = {}) {
        try {
            console.log("=== Periodic Reviews Init ===");
            console.log("Params:", params);
            await this.loadDashboard();
        } catch (error) {
            console.error("Periodic Reviews init error:", error);
            $("#mainContent").html(`
                <div class="alert alert-danger m-4" role="alert">
                    <h4 class="alert-heading">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        Failed to Load Periodic Reviews
                    </h4>
                    <p>Error: ${error.message || 'Unknown error'}</p>
                    <hr>
                    <div class="d-flex gap-2">
                        <button class="btn btn-outline-danger" onclick="PeriodicReviews.init()">
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
    
    // Alias for compatibility
    async loadPage(params = {}) {
        return await this.init(params);
    },
    
    async fetchReviewsData() {
        try {
            console.log("Fetching reviews from API...");
            
            // Customer codes/names, numbered the same way as Review Cases and Patterns
            const customerMap = {};
            try {
                const custResponse = await API.get("/customers", { page_size: 10000 });
                (custResponse?.items || []).forEach((c, idx) => {
                    customerMap[c.id] = {
                        code: `CUST-${String(idx + 1).padStart(3, '0')}`,
                        name: c.full_name || '',
                        lastReview: c.kyc_last_review || null
                    };
                });
            } catch (err) {
                console.warn("Could not load customer names for reviews:", err);
            }

            // Fetch KYC reviews from backend
            const response = await API.get("/kyc-reviews", { page_size: 5000 });
            
            console.log("API response:", response);
            
            if (response && response.items && response.items.length > 0) {
                console.log("Got", response.items.length, "reviews from API");
                this.reviewsData = response.items.map((review, idx) => {
                    const nextReviewDate = new Date(review.scheduled_date || review.created_at);
                    const dueInDays = Math.floor((nextReviewDate - new Date()) / (1000 * 60 * 60 * 24));
                    
                    const lookup = customerMap[review.customer_id];
                    let displayCode = lookup?.code;
                    let displayName = lookup?.name;

                    if (!displayCode) {
                        if (typeof review.customer_id === 'string' && review.customer_id.startsWith('CUST-')) {
                            displayCode = review.customer_id;
                        } else {
                            const num = (idx % 1000) + 1;
                            displayCode = `CUST-${String(num).padStart(3, '0')}`;
                        }
                    }

                    // Review cycle follows the customer's risk rating
                    const riskForCycle = review.risk_level_after || 'MEDIUM';
                    const frequency = review.review_type === 'PERIODIC'
                        ? ({ HIGH: '3 months', MEDIUM: '6 months', LOW: '12 months' }[riskForCycle] || '12 months')
                        : 'Ad-hoc';

                    return {
                        id: review.id,
                        customerId: displayCode,
                        customerName: displayName,
                        riskLevel: review.risk_level_after || 'MEDIUM',
                        lastReview: (review.completed_date || lookup?.lastReview)
                            ? new Date(review.completed_date || lookup.lastReview).toLocaleDateString()
                            : 'Never',
                        nextReview: nextReviewDate.toLocaleDateString(),
                        dueIn: Math.abs(dueInDays),
                        overdue: dueInDays < 0,
                        frequency: frequency,
                        // A schedule is active until its review is completed
                        status: review.review_status === 'COMPLETED' ? 'Inactive' : 'Active'
                    };
                });
            } else {
                // Nothing scheduled yet: show the empty state, never invented data
                this.reviewsData = [];
            }
            this.loadError = false;
        } catch (error) {
            console.error("Error fetching reviews:", error);
            this.reviewsData = [];
            this.loadError = true;
        }
    },

    async loadDashboard() {
        try {
            this.filters = { search: '', risk: 'all', urgency: 'all', status: 'all' };
            this.pagination.currentPage = 1;
            console.log("=== Loading Dashboard ===");
            
            // Fetch real data first
            await this.fetchReviewsData();
            
            console.log("Reviews data loaded:", this.reviewsData.length, "items");
        
        const html = `
            <div class="kyro-page">
                <!-- Page Header -->
                <div class="kyro-page-head">
                    <div>
                        <span class="kyro-kicker">Ongoing Due Diligence</span>
                        <h1 class="kyro-page-title">Periodic Reviews</h1>
                        <p class="kyro-page-sub">Manage automatic periodic AML review schedules with intelligent monitoring.</p>
                    </div>
                    
                    <div class="kyro-page-actions">
                        <button class="aml-btn aml-btn-secondary" id="refreshReviewsBtn">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>
                            </svg>
                            Refresh
                        </button>
                        <button class="aml-btn aml-btn-primary" id="scheduleReviewBtn">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                                <path d="M12 5v14M5 12h14"/>
                            </svg>
                            Schedule Review
                        </button>
                    </div>
                </div>
                
                <!-- Cards -->
                <div class="aml-pr-cards">
                    <!-- Review Frequency -->
                    <section class="aml-pr-card">
                        <div class="aml-pr-card-head">
                            <span class="aml-icon-chip blue">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                                    <path d="M8 20V12M12 20V6M16 20v-4"/><rect x="3" y="3" width="18" height="18" rx="2" stroke-width="1.6"/>
                                </svg>
                            </span>
                            <h2>Review Frequency</h2>
                        </div>
                        
                        <div class="aml-freq-chart">
                            <!-- Y-axis labels -->
                            <span class="aml-freq-y" id="freqYAxis0" style="top: 0%;">16</span>
                            <span class="aml-freq-y" id="freqYAxis25" style="top: 25%;">12</span>
                            <span class="aml-freq-y" id="freqYAxis50" style="top: 50%;">8</span>
                            <span class="aml-freq-y" id="freqYAxis75" style="top: 75%;">4</span>
                            <span class="aml-freq-y" style="top: 100%;">0</span>
                            
                            <!-- Horizontal grid lines -->
                            <div class="aml-freq-h" style="top: 0%;"></div>
                            <div class="aml-freq-h" style="top: 25%;"></div>
                            <div class="aml-freq-h" style="top: 50%;"></div>
                            <div class="aml-freq-h" style="top: 75%;"></div>
                            
                            <!-- Vertical grid lines -->
                            <div class="aml-freq-v" style="left: 20%;"></div>
                            <div class="aml-freq-v" style="left: 53%;"></div>
                            <div class="aml-freq-v" style="left: 86%;"></div>
                            
                            <!-- X-axis labels -->
                            <span class="aml-freq-x" style="left: 20%;">3 Months</span>
                            <span class="aml-freq-x" style="left: 53%;">6 Months</span>
                            <span class="aml-freq-x" style="left: 86%;">12 Months</span>
                            
                            <!-- Bar chart bars - dynamically updated with animation -->
                            <div id="freqBar3M" class="freq-bar-animated" style="position: absolute; bottom: 0; left: 13%; width: 14%; height: 0%; background: #ee4444; border-radius: 6px 6px 0 0; transition: height 0.8s cubic-bezier(0.4, 0, 0.2, 1);"></div>
                            <div id="freqBar6M" class="freq-bar-animated" style="position: absolute; bottom: 0; left: 46%; width: 14%; height: 0%; background: #f5a623; border-radius: 6px 6px 0 0; transition: height 0.8s cubic-bezier(0.4, 0, 0.2, 1) 0.15s;"></div>
                            <div id="freqBar12M" class="freq-bar-animated" style="position: absolute; bottom: 0; left: 79%; width: 14%; height: 0%; background: #1fb877; border-radius: 6px 6px 0 0; transition: height 0.8s cubic-bezier(0.4, 0, 0.2, 1) 0.3s;"></div>
                        </div>
                    </section>
                    
                    <!-- Schedule Status -->
                    <section class="aml-pr-card">
                        <div class="aml-pr-card-head">
                            <span class="aml-icon-chip green">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.5 2.5 4.5-5"/>
                                </svg>
                            </span>
                            <h2>Schedule Status</h2>
                        </div>
                        
                        <div class="aml-pr-donut-wrap">
                            <div class="aml-pr-donut donut-animated" id="scheduleDonut" role="img" aria-label="Active schedules"></div>
                        </div>
                        
                        <div class="aml-pr-status-legend">
                            <div class="aml-pr-status-item">
                                <span class="aml-pr-dot green" style="background-color: #1fb877;"></span>
                                <div><b style="color: #1fb877; font-weight: 700;">Active</b><span id="activePercent" style="color: #10b981; font-weight: 600;">0 (0%)</span></div>
                            </div>
                            <div class="aml-pr-status-item">
                                <span class="aml-pr-dot gray" style="background-color: #9ca3af;"></span>
                                <div><b style="color: #6b7280; font-weight: 700;">Inactive</b><span id="inactivePercent" style="color: #6b7280; font-weight: 600;">0 (0%)</span></div>
                            </div>
                        </div>
                    </section>
                    
                    <!-- Review Urgency -->
                    <section class="aml-pr-card">
                        <div class="aml-pr-card-head">
                            <span class="aml-icon-chip amber">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                                    <circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>
                                </svg>
                            </span>
                            <h2>Review Urgency</h2>
                        </div>
                        
                        <div class="aml-pr-urgency-list">
                            <div class="aml-pr-urgency-row">
                                <span class="aml-pr-dot red" style="background-color: #ef4444;"></span> Overdue
                                <span class="aml-pr-count red" id="overdueCount" style="color: #ef4444; background: #fee2e2;">0</span>
                            </div>
                            <div class="aml-pr-urgency-row">
                                <span class="aml-pr-dot amber"></span> Due Soon (7 days)
                                <span class="aml-pr-count amber" id="dueSoonCount">0</span>
                            </div>
                            <div class="aml-pr-urgency-row">
                                <span class="aml-pr-dot green"></span> Future
                                <span class="aml-pr-count green" id="futureCount">0</span>
                            </div>
                        </div>
                    </section>
                </div>
                
                <!-- Scheduled Reviews Table -->
                <div class="card rc-table-card" style="margin-top: 28px;">
                    <div class="rc-toolbar">
                        <div class="rc-toolbar__title">
                            <h2>Scheduled Reviews</h2>
                            <small class="text-muted" id="reviewsCount">Loading schedules...</small>
                        </div>
                        <div class="rc-toolbar__controls">
                            <div class="rc-search">
                                <i class="fas fa-magnifying-glass" aria-hidden="true"></i>
                                <input type="search" class="form-control" id="reviewSearch" placeholder="Search customer" aria-label="Search reviews" autocomplete="off">
                            </div>
                            <select class="form-select" id="filterReviewUrgency" aria-label="Filter by urgency">
                                <option value="all">Any due date</option>
                                <option value="overdue">Overdue</option>
                                <option value="soon">Due in 7 days</option>
                                <option value="future">Later</option>
                            </select>
                            <select class="form-select" id="filterReviewRisk" aria-label="Filter by risk level">
                                <option value="all">All risk levels</option>
                                <option value="HIGH">High</option>
                                <option value="MEDIUM">Medium</option>
                                <option value="LOW">Low</option>
                            </select>
                            <select class="form-select" id="filterReviewStatus" aria-label="Filter by schedule status">
                                <option value="all">All schedules</option>
                                <option value="Active">Active</option>
                                <option value="Inactive">Completed</option>
                            </select>
                            <button type="button" class="btn rc-clear d-none" id="clearReviewFiltersBtn">
                                <i class="fas fa-xmark me-1"></i>Clear
                            </button>
                        </div>
                    </div>

                    <!-- Table -->
                    <table class="table table-hover mb-0" id="reviewsTable" style="margin: 0;">
                        <thead style="background: transparent; border-bottom: 1px solid var(--aml-border);">
                            <tr>
                                <th style="padding: 14px 28px; font-size: 12px; font-weight: 600; color: var(--aml-muted); border: none; text-transform: uppercase; letter-spacing: 0.3px;">
                                    <div style="display: flex; align-items: center; gap: 6px;">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                                        Customer ID
                                    </div>
                                </th>
                                <th style="padding: 14px 20px; font-size: 12px; font-weight: 600; color: var(--aml-muted); border: none; text-transform: uppercase; letter-spacing: 0.3px;">
                                    <div style="display: flex; align-items: center; gap: 6px;">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
                                        Risk Level
                                    </div>
                                </th>
                                <th style="padding: 14px 20px; font-size: 12px; font-weight: 600; color: var(--aml-muted); border: none; text-transform: uppercase; letter-spacing: 0.3px;">
                                    <div style="display: flex; align-items: center; gap: 6px;">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
                                        Last KYC Review
                                    </div>
                                </th>
                                <th style="padding: 14px 20px; font-size: 12px; font-weight: 600; color: var(--aml-muted); border: none; text-transform: uppercase; letter-spacing: 0.3px;">
                                    <div style="display: flex; align-items: center; gap: 6px;">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                                        Next Review
                                    </div>
                                </th>
                                <th style="padding: 14px 20px; font-size: 12px; font-weight: 600; color: var(--aml-muted); border: none; text-transform: uppercase; letter-spacing: 0.3px;">
                                    <div style="display: flex; align-items: center; gap: 6px;">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                                        Due In
                                    </div>
                                </th>
                                <th style="padding: 14px 20px; font-size: 12px; font-weight: 600; color: var(--aml-muted); border: none; text-transform: uppercase; letter-spacing: 0.3px;">
                                    <div style="display: flex; align-items: center; gap: 6px;">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
                                        Frequency
                                    </div>
                                </th>
                                <th style="padding: 14px 20px; font-size: 12px; font-weight: 600; color: var(--aml-muted); border: none; text-transform: uppercase; letter-spacing: 0.3px;">
                                    <div style="display: flex; align-items: center; gap: 6px;">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
                                        Status
                                    </div>
                                </th>
                                <th style="padding: 14px 28px; font-size: 12px; font-weight: 600; color: var(--aml-muted); border: none; text-align: center; text-transform: uppercase; letter-spacing: 0.3px;">Actions</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                    
                    <!-- Pagination Controls -->
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 16px 28px; border-top: 1px solid var(--aml-border);">
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <span style="font-size: 13px; color: var(--aml-muted);">Rows per page:</span>
                            <select class="form-select form-select-sm" id="pageSizeSelect" style="width: 80px; font-size: 13px; border: 1px solid var(--aml-border); border-radius: 6px;">
                                <option value="10">10</option>
                                <option value="25">25</option>
                                <option value="50">50</option>
                                <option value="100">100</option>
                            </select>
                            <span style="font-size: 13px; color: var(--aml-text); margin-left: 12px;" id="paginationInfo">1-10 of 50</span>
                        </div>
                        <nav aria-label="Table pagination">
                            <ul class="pagination pagination-sm mb-0" id="paginationControls" style="gap: 4px;">
                                <li class="page-item disabled">
                                    <a class="page-link" href="#" id="prevPage" style="border-radius: 6px;">
                                        <i class="fas fa-chevron-left"></i>
                                    </a>
                                </li>
                                <li class="page-item active"><a class="page-link" href="#" style="border-radius: 6px;">1</a></li>
                                <li class="page-item">
                                    <a class="page-link" href="#" id="nextPage" style="border-radius: 6px;">
                                        <i class="fas fa-chevron-right"></i>
                                    </a>
                                </li>
                            </ul>
                        </nav>
                    </div>
                </div>
            </div>
        `;
        
        console.log("Rendering HTML to #mainContent");
        $("#mainContent").html(html);
        
        console.log("Updating stats...");
        // Update stats with actual data
        this.updateStats();
        
        console.log("Rendering reviews table...");
        // Render table rows
        this.initializeTable();
        
        console.log("Rendering donut chart...");
        // Render donut chart with CSS
        this.renderScheduleDonut();
        
        console.log("Initializing table...");
        // Initialize DataTable
        this.initializeTable();
        
        console.log("Setting up event listeners...");
        // Setup event listeners
        this.setupEventListeners();
        
        console.log("=== Dashboard loaded successfully ===");
        } catch (error) {
            console.error("Load Dashboard Error:", error);
            throw error;
        }
    },
    
    updateStats() {
        const overdue = this.reviewsData.filter(r => r.overdue).length;
        const dueSoon = this.reviewsData.filter(r => !r.overdue && r.dueIn <= 7).length;
        const future = this.reviewsData.filter(r => !r.overdue && r.dueIn > 7).length;
        
        // Animate count updates
        this.animateCount("#overdueCount", 0, overdue, 600);
        this.animateCount("#dueSoonCount", 0, dueSoon, 600);
        this.animateCount("#futureCount", 0, future, 600);
        
        const active = this.reviewsData.filter(r => r.status === 'Active').length;
        const inactive = this.reviewsData.filter(r => r.status === 'Inactive').length;
        const total = this.reviewsData.length;
        
        const activePercent = total > 0 ? ((active / total) * 100).toFixed(0) : 0;
        const inactivePercent = total > 0 ? ((inactive / total) * 100).toFixed(0) : 0;
        
        $("#activePercent").text(`${active} (${activePercent}%)`);
        $("#inactivePercent").text(`${inactive} (${inactivePercent}%)`);
        
        // Update subtitle to reflect real accurate count
        
        // Update bar chart based on frequency data
        this.updateFrequencyChart();
    },
    
    animateCount(selector, start, end, duration) {
        const $el = $(selector);
        const range = end - start;
        const increment = range / (duration / 16); // 60fps
        let current = start;
        
        const timer = setInterval(() => {
            current += increment;
            if ((increment > 0 && current >= end) || (increment < 0 && current <= end)) {
                current = end;
                clearInterval(timer);
            }
            $el.text(Math.floor(current));
        }, 16);
    },
    
    updateFrequencyChart() {
        // Count reviews by frequency
        const freq3Months = this.reviewsData.filter(r => r.frequency === '3 months').length;
        const freq6Months = this.reviewsData.filter(r => r.frequency === '6 months').length;
        const freq12Months = this.reviewsData.filter(r => r.frequency === '12 months').length;
        
        // Find max for scaling dynamically
        const maxVal = Math.max(freq3Months, freq6Months, freq12Months, 1);
        const scale = maxVal <= 16 ? 16 : Math.ceil(maxVal / 10) * 10;
        
        // Calculate heights as percentages (bounded strictly 0-100%)
        const height3M = Math.min(100, Math.max(0, (freq3Months / scale) * 100));
        const height6M = Math.min(100, Math.max(0, (freq6Months / scale) * 100));
        const height12M = Math.min(100, Math.max(0, (freq12Months / scale) * 100));
        
        // Update Y-axis labels
        $("#freqYAxis0").text(Math.round(scale));
        $("#freqYAxis25").text(Math.round(scale * 0.75));
        $("#freqYAxis50").text(Math.round(scale * 0.5));
        $("#freqYAxis75").text(Math.round(scale * 0.25));
        
        // Reset heights to 0 first for animation
        $("#freqBar3M").css('height', '0%');
        $("#freqBar6M").css('height', '0%');
        $("#freqBar12M").css('height', '0%');
        
        // Trigger animation after a small delay
        setTimeout(() => {
            $("#freqBar3M").css('height', `${height3M}%`);
            $("#freqBar6M").css('height', `${height6M}%`);
            $("#freqBar12M").css('height', `${height12M}%`);
        }, 100);
    },
    
    renderScheduleDonut() {
        const active = this.reviewsData.filter(r => r.status === 'Active').length;
        const inactive = this.reviewsData.filter(r => r.status === 'Inactive').length;
        const total = this.reviewsData.length || 1;
        
        const activeTurn = active / total;
        
        console.log("Donut data:", { active, inactive, total, activeTurn });
        
        // Green (#1fb877) for Active, Grey (#9ca3af) for Inactive
        let donutStyle = '';
        if (active === 0 && inactive === 0) {
            donutStyle = 'background: #e5e7eb;'; // no schedules yet
        } else if (inactive === 0) {
            donutStyle = 'background: #1fb877;';
        } else if (active === 0) {
            donutStyle = 'background: #9ca3af;';
        } else {
            donutStyle = `
                background: conic-gradient(
                    #1fb877 0turn ${activeTurn.toFixed(3)}turn,
                    #9ca3af ${activeTurn.toFixed(3)}turn 1turn
                );
            `;
        }
        
        console.log("Applying donut style:", donutStyle);
        
        // Reset and animate
        const $donut = $("#scheduleDonut");
        $donut.css({
            'transform': 'scale(0)',
            'opacity': '0'
        });
        
        setTimeout(() => {
            $donut.attr("style", donutStyle + " transition: transform 0.6s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.6s ease; transform: scale(1); opacity: 1;");
        }, 200);
    },
    
    getFilteredReviews() {
        const f = this.filters;
        const q = (f.search || '').trim().toLowerCase();
        return this.reviewsData.filter(r => {
            if (q && !`${r.customerName || ''} ${r.customerId}`.toLowerCase().includes(q)) return false;
            if (f.risk !== 'all' && r.riskLevel !== f.risk) return false;
            if (f.status !== 'all' && r.status !== f.status) return false;
            if (f.urgency === 'overdue' && !r.overdue) return false;
            if (f.urgency === 'soon' && (r.overdue || r.dueIn > 7)) return false;
            if (f.urgency === 'future' && (r.overdue || r.dueIn <= 7)) return false;
            return true;
        });
    },

    emptyRow() {
        if (this.loadError) {
            return `<tr><td colspan="8" class="rc-empty"><i class="fas fa-triangle-exclamation"></i><strong>Couldn't load review schedules</strong><span>Check the connection and use Refresh to try again.</span></td></tr>`;
        }
        if (!this.reviewsData.length) {
            return `<tr><td colspan="8" class="rc-empty"><i class="fas fa-calendar-plus"></i><strong>No periodic reviews scheduled yet</strong><span>Use <em>Schedule Review</em> to set up a customer's first review cycle.</span></td></tr>`;
        }
        return `<tr><td colspan="8" class="rc-empty"><i class="fas fa-filter"></i><strong>No reviews match these filters</strong><span>Try clearing the search or filters.</span></td></tr>`;
    },

    initializeTable() {
        const filtered = this.getFilteredReviews();
        const total = filtered.length;
        
        // Calculate pagination
        const startIdx = (this.pagination.currentPage - 1) * this.pagination.pageSize;
        const endIdx = Math.min(startIdx + this.pagination.pageSize, total);
        const paginatedReviews = filtered.slice(startIdx, endIdx);
        
        const tableBody = paginatedReviews.map(review => {
            // Determine status badge color based on overdue/due soon
            let dueStatus = '';
            let dueColor = '';
            if (review.overdue) {
                dueStatus = `${review.dueIn} days overdue`;
                dueColor = 'background: #fee; color: #c44; border: 1px solid #fcc;';
            } else if (review.dueIn <= 7) {
                dueStatus = `${review.dueIn} days`;
                dueColor = 'background: #fff7ed; color: #c2410c; border: 1px solid #fed7aa;';
            } else {
                dueStatus = `${review.dueIn} days`;
                dueColor = 'background: #ecfdf5; color: #059669; border: 1px solid #a7f3d0;';
            }
            
            // Risk level colors
            const riskColors = {
                'LOW': 'background: #dcfce7; color: #166534; border: 1px solid #bbf7d0;',
                'MEDIUM': 'background: #fef3c7; color: #d97706; border: 1px solid #fde68a;',
                'HIGH': 'background: #fee2e2; color: #dc2626; border: 1px solid #fecaca;'
            };
            
            // Status colors  
            const statusColors = {
                'Active': 'background: #a7f3d0; color: #065f46; border: 1px solid #6ee7b7;',
                'Inactive': 'background: #f3f4f6; color: #4b5563; border: 1px solid #e5e7eb;'
            };
            
            const displayCode = review.customerId || '';
            const displayName = review.customerName || displayCode;
            const initials = displayName.split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase();

            return `
            <tr>
                <td class="px-3 py-3">
                    <div class="rc-customer">
                        <span class="rc-customer__avatar" aria-hidden="true">${escapeHtml(initials)}</span>
                        <span class="rc-customer__text">
                            <strong>${escapeHtml(displayName)}</strong>
                            <small>${escapeHtml(displayCode)}</small>
                        </span>
                    </div>
                </td>
                <td style="padding: 14px 20px;">
                    <span style="font-size: 13px; padding: 5px 11px; border-radius: 8px; font-weight: 600; display: inline-block; ${riskColors[review.riskLevel]}">
                        ${review.riskLevel}
                    </span>
                </td>
                <td style="padding: 14px 20px; font-size: 14px; color: var(--aml-text);">${review.lastReview}</td>
                <td style="padding: 14px 20px;">
                    <div style="font-size: 14px; color: var(--aml-text); font-weight: 500;">${review.nextReview}</div>
                    <div style="font-size: 12px; color: #ef4444; margin-top: 2px;">${review.overdue ? '○ Overdue' : ''}</div>
                </td>
                <td style="padding: 14px 20px;">
                    <span style="font-size: 13px; padding: 5px 11px; border-radius: 8px; font-weight: 600; display: inline-block; ${dueColor}">
                        ${dueStatus}
                    </span>
                </td>
                <td style="padding: 14px 20px;">
                    <span style="font-size: 13px; padding: 5px 11px; border-radius: 8px; font-weight: 600; display: inline-block; background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd;">
                        ${review.frequency}
                    </span>
                </td>
                <td style="padding: 14px 20px;">
                    <span style="font-size: 13px; padding: 5px 11px; border-radius: 8px; font-weight: 600; display: inline-block; ${statusColors[review.status]}">
                        ${review.status === 'Inactive' ? 'Completed' : 'Active'}
                    </span>
                </td>
                <td class="px-3 py-3">
                    <div class="rc-actions">
                        <button type="button" class="btn btn-sm rc-actions__view trigger-review-btn" data-customer="${review.customerId}">
                            <i class="fas fa-play me-1"></i>Trigger
                        </button>
                        <button type="button" class="btn btn-sm rc-actions__icon edit-schedule-btn" data-customer="${review.customerId}" title="Edit schedule" aria-label="Edit review schedule for ${escapeHtml(displayName)}">
                            <i class="fas fa-pen"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `}).join('');
        
        $("#reviewsTable tbody").html(tableBody || this.emptyRow());

        // Update counts
        $("#reviewsCount").text(total
            ? `Showing ${startIdx + 1}-${endIdx} of ${total} review${total !== 1 ? 's' : ''}`
            : (this.reviewsData.length ? 'No matching reviews' : 'No reviews scheduled'));
        
        // Render pagination controls
        this.renderPaginationControls(total, startIdx, endIdx);
        
        console.log(`Table rendered with ${paginatedReviews.length} of ${total} rows (page ${this.pagination.currentPage})`);
    },
    
    renderPaginationControls(total, startIdx, endIdx) {
        // Update pagination info
        if (total === 0) {
            $("#paginationInfo").text("0 reviews");
        } else {
            $("#paginationInfo").text(`${startIdx + 1}-${endIdx} of ${total}`);
        }
        
        // Update page size selector
        $("#pageSizeSelect").val(this.pagination.pageSize);
        
        // Calculate total pages
        const totalPages = Math.ceil(total / this.pagination.pageSize);
        
        if (totalPages <= 1) {
            $("#paginationControls").html(`
                <li class="page-item disabled">
                    <a class="page-link" href="#" id="prevPage" style="border-radius: 6px;">
                        <i class="fas fa-chevron-left"></i>
                    </a>
                </li>
                <li class="page-item active"><a class="page-link" href="#" style="border-radius: 6px;">1</a></li>
                <li class="page-item disabled">
                    <a class="page-link" href="#" id="nextPage" style="border-radius: 6px;">
                        <i class="fas fa-chevron-right"></i>
                    </a>
                </li>
            `);
            return;
        }
        
        // Build pagination buttons
        let paginationHTML = '';
        
        // Previous button
        paginationHTML += `
            <li class="page-item ${this.pagination.currentPage === 1 ? 'disabled' : ''}">
                <a class="page-link" href="#" id="prevPage" style="border-radius: 6px;">
                    <i class="fas fa-chevron-left"></i>
                </a>
            </li>
        `;
        
        // Page numbers
        const maxVisiblePages = 5;
        let startPage = Math.max(1, this.pagination.currentPage - Math.floor(maxVisiblePages / 2));
        let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
        
        // Adjust start if we're at the end
        if (endPage - startPage < maxVisiblePages - 1) {
            startPage = Math.max(1, endPage - maxVisiblePages + 1);
        }
        
        // First page
        if (startPage > 1) {
            paginationHTML += `
                <li class="page-item">
                    <a class="page-link page-num-btn" href="#" data-page="1" style="border-radius: 6px;">1</a>
                </li>
            `;
            if (startPage > 2) {
                paginationHTML += `<li class="page-item disabled"><a class="page-link" style="border-radius: 6px;">...</a></li>`;
            }
        }
        
        // Page numbers
        for (let i = startPage; i <= endPage; i++) {
            paginationHTML += `
                <li class="page-item ${i === this.pagination.currentPage ? 'active' : ''}">
                    <a class="page-link page-num-btn" href="#" data-page="${i}" style="border-radius: 6px;">${i}</a>
                </li>
            `;
        }
        
        // Last page
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) {
                paginationHTML += `<li class="page-item disabled"><a class="page-link" style="border-radius: 6px;">...</a></li>`;
            }
            paginationHTML += `
                <li class="page-item">
                    <a class="page-link page-num-btn" href="#" data-page="${totalPages}" style="border-radius: 6px;">${totalPages}</a>
                </li>
            `;
        }
        
        // Next button
        paginationHTML += `
            <li class="page-item ${this.pagination.currentPage === totalPages ? 'disabled' : ''}">
                <a class="page-link" href="#" id="nextPage" style="border-radius: 6px;">
                    <i class="fas fa-chevron-right"></i>
                </a>
            </li>
        `;
        
        $("#paginationControls").html(paginationHTML);
    },
    
    async showScheduleReviewModal() {
        try {
            // Fetch real customers from API
            const customersResponse = await API.get("/customers", { page_size: 10000 });
            const customers = customersResponse.items || [];
            
            const customerOptions = customers.map((cust, idx) => {
                const code = `CUST-${String(idx + 1).padStart(3, '0')}`;
                return `<option value="${cust.id}">${code} - ${cust.full_name} (${cust.email})</option>`;
            }).join('');
            
            const modalHtml = `
                <div class="modal fade" id="scheduleReviewModal" tabindex="-1" style="z-index: 9999;">
                    <div class="modal-dialog modal-dialog-centered kyro-modal-dialog">
                        <div class="modal-content kyro-modal-content">
                            <div class="modal-header kyro-modal-header">
                                <div style="display: flex; align-items: center; gap: 14px;">
                                    <div class="kyro-modal-header-icon">
                                        <i class="fas fa-calendar-plus"></i>
                                    </div>
                                    <div>
                                        <h5 class="kyro-modal-title">Schedule New Review</h5>
                                        <p class="kyro-modal-subtitle">Create a periodic KYC compliance review schedule</p>
                                    </div>
                                </div>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close" style="font-size: 12px;"></button>
                            </div>
                            <div class="modal-body kyro-modal-body">
                                <form id="scheduleReviewForm">
                                    <!-- CUST ID -->
                                    <div class="kyro-form-group">
                                        <label class="kyro-form-label">
                                            <i class="fas fa-id-card" style="color: #FF8D28;"></i>
                                            <span>CUST ID</span>
                                        </label>
                                        <select class="kyro-form-select" id="scheduleCustomerId" required>
                                            <option value="">Select CUST ID</option>
                                            ${customerOptions}
                                        </select>
                                    </div>
                                    
                                    <!-- Review Frequency (Months) -->
                                    <div class="kyro-form-group">
                                        <label class="kyro-form-label">
                                            <i class="fas fa-clock" style="color: #FF8D28;"></i>
                                            <span>Review Frequency (Months)</span>
                                        </label>
                                        <select class="kyro-form-select" id="scheduleFrequency" required>
                                            <option value="">Select Frequency</option>
                                            <option value="3">3 Months</option>
                                            <option value="6">6 Months</option>
                                            <option value="12">12 Months</option>
                                        </select>
                                    </div>
                                </form>
                            </div>
                            <div class="modal-footer kyro-modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal" style="font-size: 14px; padding: 10px 20px; border-radius: 10px; font-weight: 500;">
                                    Cancel
                                </button>
                                <button type="button" class="btn" id="confirmScheduleBtn" style="background: #FF8D28; color: white; font-size: 14px; padding: 10px 24px; border-radius: 10px; font-weight: 600; box-shadow: 0 4px 14px rgba(255, 141, 40, 0.35); transition: transform 0.15s, background 0.15s;">
                                    <i class="fas fa-calendar-check me-2"></i>Schedule Review
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            // Remove existing modal if any
            $("#scheduleReviewModal").remove();
            
            // Append and show modal
            $("body").append(modalHtml);
            const modal = new bootstrap.Modal(document.getElementById('scheduleReviewModal'));
            modal.show();
            
            // Handle form submission
            $("#confirmScheduleBtn").on("click", () => {
                this.handleScheduleSubmit(modal);
            });
        } catch (error) {
            console.error("Error loading customers:", error);
            showToast("error", "Failed to load customers. Please try again.");
        }
    },
    
    async handleScheduleSubmit(modal) {
        const customerId = $("#scheduleCustomerId").val();
        const customerName = $("#scheduleCustomerId option:selected").text();
        const frequency = $("#scheduleFrequency").val();
        
        // Validate
        if (!customerId || !frequency) {
            showToast("warning", "Please select CUST ID and Review Frequency");
            return;
        }

        // Calculate next review date automatically based on frequency in months
        const months = parseInt(frequency, 10) || 12;
        const nextReviewDate = new Date();
        nextReviewDate.setMonth(nextReviewDate.getMonth() + months);
        
        try {
            // Show loading
            $("#confirmScheduleBtn").prop("disabled", true).html('<i class="fas fa-spinner fa-spin me-2"></i>Scheduling...');
            
            // Call API with customer_id as query parameter
            const response = await API.post(`/kyc-reviews?customer_id=${customerId}&review_type=PERIODIC`);
            
            if (response && response.id) {
                showToast("success", `Review scheduled successfully for ${customerName}`);
                modal.hide();
                
                const today = new Date();
                const dueInDays = Math.floor((nextReviewDate - today) / (1000 * 60 * 60 * 24));
                const custCode = customerName.split(' - ')[0] || 'CUST-000';
                
                this.reviewsData.unshift({
                    id: response.id,
                    rawCustomerId: customerId,
                    customerId: custCode,
                    customerName: customerName,
                    riskLevel: response.risk_level || 'MEDIUM',
                    lastReview: 'Never',
                    nextReview: nextReviewDate.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric', year: 'numeric' }),
                    dueIn: Math.abs(dueInDays),
                    overdue: dueInDays < 0,
                    frequency: `${frequency} months`,
                    status: 'Active'
                });
                
                // Refresh the dashboard
                this.updateStats();
                this.renderScheduleDonut();
                this.initializeTable();
            } else {
                showToast("error", "Failed to schedule review");
            }
        } catch (error) {
            console.error("Error scheduling review:", error);
            const errorMsg = error.responseJSON?.detail || error.responseJSON?.message || "Failed to schedule review. Please try again.";
            showToast("error", errorMsg);
        } finally {
            $("#confirmScheduleBtn").prop("disabled", false).html('<i class="fas fa-check me-2"></i>Schedule Review');
        }
    },
    
    setupEventListeners() {
        const self = this;
        
        // Refresh button
        $("#refreshReviewsBtn").on("click", () => {
            this.loadDashboard();
            showToast("success", "Reviews refreshed");
        });
        
        // Schedule Review button
        $("#scheduleReviewBtn").on("click", () => {
            this.showScheduleReviewModal();
        });
        
        // Search + filters
        const applyFilters = () => {
            self.filters.search = $("#reviewSearch").val() || '';
            self.filters.risk = $("#filterReviewRisk").val();
            self.filters.urgency = $("#filterReviewUrgency").val();
            self.filters.status = $("#filterReviewStatus").val();
            const active = self.filters.search.trim() !== '' ||
                ['risk', 'urgency', 'status'].some(k => self.filters[k] !== 'all');
            $("#clearReviewFiltersBtn").toggleClass("d-none", !active);
            self.pagination.currentPage = 1;
            self.initializeTable();
        };
        $("#filterReviewRisk, #filterReviewUrgency, #filterReviewStatus").on("change", applyFilters);
        $("#reviewSearch").on("input", debounce(applyFilters, 200));
        $("#clearReviewFiltersBtn").on("click", () => {
            $("#reviewSearch").val('');
            $("#filterReviewRisk, #filterReviewUrgency, #filterReviewStatus").val('all');
            applyFilters();
        });

        // Page size selector
        $("body").off("change", "#pageSizeSelect").on("change", "#pageSizeSelect", function(e) {
            self.pagination.pageSize = parseInt($(this).val());
            self.pagination.currentPage = 1; // Reset to first page
            self.initializeTable();
        });
        
        // Previous page button
        $("body").off("click", "#prevPage").on("click", "#prevPage", function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            if (!$(this).parent().hasClass('disabled') && self.pagination.currentPage > 1) {
                self.pagination.currentPage--;
                self.initializeTable();
                
                // Scroll to top of table
                $("#reviewsTable").get(0)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
        
        // Next page button
        $("body").off("click", "#nextPage").on("click", "#nextPage", function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const totalPages = Math.ceil(self.getFilteredReviews().length / self.pagination.pageSize);
            
            if (!$(this).parent().hasClass('disabled') && self.pagination.currentPage < totalPages) {
                self.pagination.currentPage++;
                self.initializeTable();
                
                // Scroll to top of table
                $("#reviewsTable").get(0)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
        
        // Page number buttons
        $("body").off("click", ".page-num-btn").on("click", ".page-num-btn", function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const page = parseInt($(this).data("page"));
            if (page && page !== self.pagination.currentPage) {
                self.pagination.currentPage = page;
                self.initializeTable();
                
                // Scroll to top of table
                $("#reviewsTable").get(0)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
        
        // Trigger review button
        $(document).on("click", ".trigger-review-btn", function() {
            const customerId = $(this).data("customer");
            showToast("info", `Triggering review for ${customerId}`);
        });
        
        // Edit schedule button
        $(document).on("click", ".edit-schedule-btn", function() {
            const customerId = $(this).data("customer");
            showToast("info", `Edit schedule for ${customerId}`);
        });
    }
};

// Export for use
window.PeriodicReviews = PeriodicReviews;
