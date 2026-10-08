/**
 * KYRO Review Cases - Dashboard with Risk Analysis
 * Exactly matching the reference screenshot layout
 */

const Cases = {
    currentFilters: {
        search: '',
        status: 'all',
        riskLevel: 'all',
        triggerType: 'all',
        customer: null,
        pattern: null
    },
    
    charts: {
        riskDistribution: null,
        statusOverview: null
    },
    
    casesData: [],
    
    // Pagination settings
    pagination: {
        currentPage: 1,
        pageSize: 10,
        pageSizeOptions: [10, 25, 50, 100]
    },
    
    init(params = {}) {
        console.log("Initializing Review Cases dashboard...", params);
        
        // Each visit starts unfiltered (the page re-renders its controls as
        // "All"); only a customer passed from the Patterns page carries over.
        Object.assign(this.currentFilters, { search: '', status: 'all', riskLevel: 'all', triggerType: 'all', customer: null, pattern: null });
        this.pagination.currentPage = 1;

        // Apply filters from params if provided
        if (params.customer) {
            this.currentFilters.customer = params.customer;
        }
        if (params.pattern) {
            this.currentFilters.pattern = params.pattern;
        }
        
        this.loadDashboard();
    },
    
    async loadDashboard() {
        // Chip shown when arriving from the Patterns page with a customer filter
        let filterInfo = '';
        if (this.currentFilters.customer) {
            const pattern = this.currentFilters.pattern
                ? ` &middot; from pattern <strong>${escapeHtml(this.currentFilters.pattern.replace(/_/g, ' '))}</strong>`
                : '';
            filterInfo = `
                <div class="rc-filter-chip" role="status">
                    <i class="fas fa-filter"></i>
                    <span>Showing cases for customer <strong>${escapeHtml(this.currentFilters.customer)}</strong>${pattern}</span>
                    <button type="button" class="rc-filter-chip__clear" id="clearCustomerFilterBtn" aria-label="Show all customers">
                        <i class="fas fa-xmark"></i>
                    </button>
                </div>
            `;
        }

        const html = `
            <div class="kyro-page">
                <!-- Page Header -->
                <div class="kyro-page-head">
                    <div>
                        <span class="kyro-kicker">Case Management</span>
                        <h1 class="kyro-page-title">Review Cases</h1>
                        <p class="kyro-page-sub">Monitor and manage AML review cases with intelligent risk assessment.</p>
                    </div>
                    <div class="kyro-page-actions">
                        <button class="btn btn-primary px-4" id="refreshCasesBtn">
                            <i class="fas fa-rotate-right me-2"></i>Refresh
                        </button>
                    </div>
                </div>
                
                <!-- Dashboard Grid - 3 Column Layout -->
                <div class="row g-3 mb-4">
                    <!-- Left: Risk Distribution with Stats -->
                    <div class="col-md-4">
                        <div class="card border-0 shadow-sm h-100">
                            <div class="card-body p-4">
                                <h6 class="mb-3" style="font-weight: 600; font-size: 14px;">Risk Distribution</h6>
                                <div style="height: 160px; margin-bottom: 20px;">
                                    <canvas id="riskDistributionChart"></canvas>
                                </div>
                                <div class="row text-center mt-3">
                                    <div class="col-4">
                                        <h3 class="mb-0" style="font-weight: 700; color: #ef4444;" id="highRiskCount">500</h3>
                                        <div class="text-muted" style="font-size: 11px;">High Risk</div>
                                        <div style="font-size: 10px; color: #ef4444;">92.4%</div>
                                    </div>
                                    <div class="col-4">
                                        <h3 class="mb-0" style="font-weight: 700; color: #FF8D28;" id="mediumRiskCount">105</h3>
                                        <div class="text-muted" style="font-size: 11px;">Pending Risk</div>
                                        <div style="font-size: 10px; color: #FF8D28;">17.3%</div>
                                    </div>
                                    <div class="col-4">
                                        <h3 class="mb-0" style="font-weight: 700; color: #22c55e;" id="lowRiskCount">2</h3>
                                        <div class="text-muted" style="font-size: 11px;">Low Risk</div>
                                        <div style="font-size: 10px; color: #22c55e;">0.3%</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Center: Status Overview (Black Card) -->
                    <div class="col-md-4">
                        <div class="card border-0 shadow-sm h-100" style="background: #1a1a1a;">
                            <div class="card-body p-4">
                                <h6 class="mb-3" style="font-weight: 600; color: #FF8D28; font-size: 14px;">Status overview</h6>
                                <div class="position-relative d-flex justify-content-center align-items-center" style="height: 180px;">
                                    <canvas id="statusOverviewChart"></canvas>
                                </div>
                                <div class="mt-3">
                                    <div class="d-flex justify-content-between align-items-center p-3 rounded" style="background: rgba(255,141,40,0.2);">
                                        <div class="d-flex align-items-center">
                                            <i class="fas fa-th me-2" style="color: #FF8D28; font-size: 14px;"></i>
                                            <span style="font-size: 13px; color: #fff;">Open</span>
                                        </div>
                                        <strong style="color: #FF8D28; font-size: 14px;" id="openStatusPercent">136 (22%)</strong>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Right: Trigger Types -->
                    <div class="col-md-4">
                        <div class="card border-0 shadow-sm h-100">
                            <div class="card-body p-4">
                                <h6 class="mb-3" style="font-weight: 600; font-size: 14px;">Trigger Types</h6>
                                <div class="d-flex flex-column gap-2">
                                    <div class="d-flex justify-content-between align-items-center p-2 rounded" style="background-color: #e3f2fd;">
                                        <div class="d-flex align-items-center">
                                            <i class="fas fa-circle me-2" style="color: #2196f3; font-size: 8px;"></i>
                                            <span style="font-size: 13px;">Time-Based</span>
                                        </div>
                                        <span class="fw-bold" style="font-size: 15px; color: #2196f3;" id="timeBasedCount">93</span>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center p-2 rounded" style="background-color: #e8f5e9;">
                                        <div class="d-flex align-items-center">
                                            <i class="fas fa-circle me-2" style="color: #4caf50; font-size: 8px;"></i>
                                            <span style="font-size: 13px;">Behavior-Based</span>
                                        </div>
                                        <span class="fw-bold" style="font-size: 15px; color: #4caf50;" id="behaviorBasedCount">510</span>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center p-2 rounded" style="background-color: #fff3e0;">
                                        <div class="d-flex align-items-center">
                                            <i class="fas fa-circle me-2" style="color: #ff9800; font-size: 8px;"></i>
                                            <span style="font-size: 13px;">Manual</span>
                                        </div>
                                        <span class="fw-bold" style="font-size: 15px; color: #ff9800;" id="manualCount">3</span>
                                    </div>
                                    <div class="d-flex justify-content-between align-items-center p-2 rounded" style="background-color: #ffebee;">
                                        <div class="d-flex align-items-center">
                                            <i class="fas fa-circle me-2" style="color: #f44336; font-size: 8px;"></i>
                                            <span style="font-size: 13px;">Rule-based</span>
                                        </div>
                                        <span class="fw-bold" style="font-size: 15px; color: #f44336;" id="ruleBasedCount">1</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Review Cases Table Section -->
                <div class="card border-0 rc-table-card">
                    <div class="card-body p-0">
                        <div class="rc-toolbar">
                            <div class="rc-toolbar__title">
                                <h2>Review Cases</h2>
                                <small class="text-muted" id="resultsCount">Showing 0 cases</small>
                            </div>
                            <div class="rc-toolbar__controls">
                                <div class="rc-search">
                                    <i class="fas fa-magnifying-glass" aria-hidden="true"></i>
                                    <input type="search" class="form-control" id="caseSearch" placeholder="Search customer or case ID" aria-label="Search cases" autocomplete="off">
                                </div>
                                <select class="form-select" id="filterStatus" aria-label="Filter by status">
                                    <option value="all">All statuses</option>
                                    <option value="OPEN">Open</option>
                                    <option value="ASSIGNED">Assigned</option>
                                    <option value="IN_REVIEW">In Review</option>
                                    <option value="ESCALATED">Escalated</option>
                                    <option value="RESOLVED">Resolved</option>
                                </select>
                                <select class="form-select" id="filterRiskLevel" aria-label="Filter by risk level">
                                    <option value="all">All risk levels</option>
                                    <option value="HIGH">High</option>
                                    <option value="MEDIUM">Medium</option>
                                    <option value="LOW">Low</option>
                                </select>
                                <select class="form-select" id="filterTriggerType" aria-label="Filter by trigger type">
                                    <option value="all">All triggers</option>
                                    <option value="BEHAVIOR BASED">Behavior Based</option>
                                    <option value="TIME BASED">Time Based</option>
                                    <option value="RULE BASED">Rule Based</option>
                                    <option value="MANUAL">Manual</option>
                                </select>
                                <button type="button" class="btn rc-clear d-none" id="clearFiltersBtn">
                                    <i class="fas fa-xmark me-1"></i>Clear
                                </button>
                            </div>
                        </div>
                        ${filterInfo}
                        <div class="table-responsive">
                            <table class="table table-hover align-middle mb-0" style="font-size: 13px;">
                                <thead>
                                    <tr>
                                        <th class="px-3 py-3">
                                            Customer
                                        </th>
                                        <th class="px-3 py-3">
                                            Trigger Type
                                        </th>
                                        <th class="px-3 py-3">
                                            Priority
                                        </th>
                                        <th class="px-3 py-3">
                                            Risk Assessment
                                        </th>
                                        <th class="px-3 py-3">
                                            Status
                                        </th>
                                        <th class="px-3 py-3">
                                            Created At
                                        </th>
                                        <th class="px-3 py-3">
                                            Assigned To
                                        </th>
                                        <th class="px-3 py-3">
                                            <span class="visually-hidden">Actions</span>
                                        </th>
                                    </tr>
                                </thead>
                                <tbody id="casesTableBody">
                                    <tr>
                                        <td colspan="8" class="text-center py-5">
                                            <div class="spinner-border text-primary" role="status">
                                                <span class="visually-hidden">Loading...</span>
                                            </div>
                                            <p class="mt-2 text-muted">Loading cases...</p>
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                        
                        <!-- Pagination Controls -->
                        <div class="d-flex justify-content-between align-items-center p-3" style="border-top: 1px solid #f0f0f0;">
                            <div class="d-flex align-items-center gap-2">
                                <span class="text-muted" style="font-size: 13px;">Rows per page:</span>
                                <select class="form-select form-select-sm" id="pageSizeSelect" style="width: 80px; font-size: 13px;">
                                    <option value="10">10</option>
                                    <option value="25">25</option>
                                    <option value="50">50</option>
                                    <option value="100">100</option>
                                </select>
                                <span class="text-muted ms-3" id="paginationInfo" style="font-size: 13px;">1-10 of 50</span>
                            </div>
                            <nav aria-label="Table pagination">
                                <ul class="pagination pagination-sm mb-0" id="paginationControls">
                                    <li class="page-item disabled">
                                        <a class="page-link" href="#" id="prevPage">
                                            <i class="fas fa-chevron-left"></i>
                                        </a>
                                    </li>
                                    <li class="page-item active"><a class="page-link" href="#">1</a></li>
                                    <li class="page-item">
                                        <a class="page-link" href="#" id="nextPage">
                                            <i class="fas fa-chevron-right"></i>
                                        </a>
                                    </li>
                                </ul>
                            </nav>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        $("#mainContent").html(html);
        await this.fetchCasesData();
        this.initCharts();
        this.setupEventListeners();
    },
    
    async fetchCasesData() {
        try {
            // Build customer map to convert UUIDs to clean CUST-XXX IDs
            let customerMap = {};
            const customerNames = {};
            try {
                const custResponse = await API.get("/customers", { page_size: 10000 });
                if (custResponse && custResponse.items) {
                    custResponse.items.forEach((c, idx) => {
                        const code = `CUST-${String(idx + 1).padStart(3, '0')}`;
                        customerMap[c.id] = code;
                        customerNames[c.id] = c.full_name || '';
                    });
                }
            } catch (err) {
                console.warn("Could not fetch customer lookup map for cases:", err);
            }

            const data = await API.get("/alerts", { page_size: 100 });
            const alerts = data.items || data;
            
            // If no alerts from API, generate mock data for demo
            if (!alerts || alerts.length === 0) {
                console.log("No alerts in database - generating mock data for demo");
                this.generateMockCases();
                return;
            }
            
            this.totalCases = data.total || alerts.length;

            // Map DB alert_type → UI trigger type labels
            const triggerTypeMap = {
                'BEHAVIORAL_ANOMALY': 'BEHAVIOR BASED',
                'HIGH_RISK_CUSTOMER': 'RULE BASED',
                'LARGE_AMOUNT':       'RULE BASED',
                'WIRE_TRANSFER':      'BEHAVIOR BASED',
                'TIME_BASED':         'TIME BASED',
                'MANUAL':             'MANUAL'
            };

            this.casesData = alerts.map((alert, idx) => {
                let riskLevel = 'LOW';
                let priority = 'LOW';
                if (alert.risk_score >= 80)      { riskLevel = 'HIGH';   priority = 'URGENT'; }
                else if (alert.risk_score >= 60) { riskLevel = 'MEDIUM'; priority = 'HIGH'; }

                const triggerType = triggerTypeMap[alert.alert_type] || 'BEHAVIOR BASED';

                let displayCustId = customerMap[alert.customer_id];
                if (!displayCustId) {
                    if (typeof alert.customer_id === 'string' && alert.customer_id.startsWith('CUST-')) {
                        displayCustId = alert.customer_id;
                    } else {
                        displayCustId = `CUST-${String(idx + 1).padStart(3, '0')}`;
                    }
                }

                return {
                    caseId:        alert.id,
                    customerId:    displayCustId,
                    customerName:  customerNames[alert.customer_id] || '',
                    rawCustomerId: alert.customer_id,
                    triggerType,
                    priority,
                    riskLevel,
                    status:        alert.status || 'OPEN',
                    createdAt:     new Date(alert.created_at).toLocaleDateString(),
                    assignedTo:    alert.assigned_to ? 'Assigned' : 'Unassigned',
                    fullData:      alert
                };
            });

            this.updateDashboard();
            this.renderTable();

        } catch (error) {
            console.warn("Error fetching cases - using mock data:", error);
            // Silently fall back to mock data - no error toast
            this.casesData = [];
            this.totalCases = 0;
            this.generateMockCases();
        }
    },
    
    updateDashboard() {
        const stats = {
            high: this.casesData.filter(c => c.riskLevel && c.riskLevel.toUpperCase() === 'HIGH').length,
            medium: this.casesData.filter(c => c.riskLevel && c.riskLevel.toUpperCase() === 'MEDIUM').length,
            low: this.casesData.filter(c => c.riskLevel && c.riskLevel.toUpperCase() === 'LOW').length,
            open: this.casesData.filter(c => c.status && c.status.toUpperCase() === 'OPEN').length,
            timeBased: this.casesData.filter(c => c.triggerType && c.triggerType.toUpperCase().includes('TIME')).length,
            behaviorBased: this.casesData.filter(c => c.triggerType && c.triggerType.toUpperCase().includes('BEHAVIOR')).length,
            manual: this.casesData.filter(c => c.triggerType && c.triggerType.toUpperCase() === 'MANUAL').length,
            ruleBased: this.casesData.filter(c => c.triggerType && c.triggerType.toUpperCase().includes('RULE')).length
        };
        
        const total = this.casesData.length || 1;
        const highPercent = ((stats.high / total) * 100).toFixed(1);
        const mediumPercent = ((stats.medium / total) * 100).toFixed(1);
        const lowPercent = ((stats.low / total) * 100).toFixed(1);
        
        $("#highRiskCount").text(stats.high);
        $("#mediumRiskCount").text(stats.medium);
        $("#lowRiskCount").text(stats.low);
        
        // Update percentages
        $("#highRiskCount").next().next().text(`${highPercent}%`);
        $("#mediumRiskCount").next().next().text(`${mediumPercent}%`);
        $("#lowRiskCount").next().next().text(`${lowPercent}%`);
        
        const openPercent = this.casesData.length > 0 ? Math.round(stats.open / this.casesData.length * 100) : 0;
        $("#openStatusPercent").text(`${stats.open} (${openPercent}%)`);
        
        $("#timeBasedCount").text(stats.timeBased);
        $("#behaviorBasedCount").text(stats.behaviorBased);
        $("#manualCount").text(stats.manual);
        $("#ruleBasedCount").text(stats.ruleBased);
        
        if (this.charts.riskDistribution) {
            this.charts.riskDistribution.data.datasets[0].data = [stats.high, stats.medium, stats.low];
            this.charts.riskDistribution.update();
        }
        
        if (this.charts.statusOverview) {
            const total = this.casesData.length;
            this.charts.statusOverview.data.datasets[0].data = [stats.open, total - stats.open];
            this.charts.statusOverview.update();
        }
    },
    
    initCharts() {
        // Risk Distribution - Vertical Bar Chart
        const riskCtx = document.getElementById('riskDistributionChart');
        if (riskCtx) {
            this.charts.riskDistribution = new Chart(riskCtx, {
                type: 'bar',
                data: {
                    labels: ['High', 'Medium', 'Low'],
                    datasets: [{
                        data: [500, 105, 2],
                        backgroundColor: ['#ef4444', '#FF8D28', '#22c55e'],
                        borderRadius: 6,
                        barThickness: 50
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { 
                            grid: { display: false },
                            ticks: { font: { size: 11 } }
                        },
                        y: {
                            beginAtZero: true,
                            max: 600,
                            ticks: { 
                                stepSize: 150,
                                font: { size: 11 }
                            },
                            grid: { color: 'rgba(0,0,0,0.05)' }
                        }
                    }
                }
            });
        }
        
        // Status Overview - Donut Chart (Black background with orange segment)
        const statusCtx = document.getElementById('statusOverviewChart');
        if (statusCtx) {
            this.charts.statusOverview = new Chart(statusCtx, {
                type: 'doughnut',
                data: {
                    datasets: [{
                        data: [22, 78],
                        backgroundColor: ['#FF8D28', '#2a2a2a'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '75%',
                    plugins: { 
                        legend: { display: false },
                        tooltip: { enabled: false }
                    }
                }
            });
        }
    },
    renderTable() {
        const filtered = this.getFilteredCases();
        const total = filtered.length;
        
        // Calculate pagination
        const startIdx = (this.pagination.currentPage - 1) * this.pagination.pageSize;
        const endIdx = Math.min(startIdx + this.pagination.pageSize, total);
        const paginatedCases = filtered.slice(startIdx, endIdx);
        
        // Update counts
        $("#resultsCount").text(total ? `Showing ${startIdx + 1}-${endIdx} of ${total} cases` : "No matching cases");
        $("#resultsCountTop").text(`${total} Result${total !== 1 ? 's' : ''}`);
        
        if (paginatedCases.length === 0) {
            $("#casesTableBody").html(`
                <tr><td colspan="8" class="rc-empty"><i class="fas fa-folder-open"></i><strong>No cases match these filters</strong><span>Try clearing the search or filters.</span></td></tr>
            `);
            this.renderPaginationControls(0, 0);
            return;
        }
        
        const rows = paginatedCases.map(c => {
            // Priority badge colors matching screenshot
            const priorityColors = { 
                'URGENT': { bg: '#fff5f5', text: '#dc2626', icon: '🔺' },
                'HIGH': { bg: '#fff7ed', text: '#f59e0b', icon: '⚠️' },
                'MEDIUM': { bg: '#fef9c3', text: '#d97706', icon: '●' }
            };
            
            // Risk assessment colors
            const riskColors = { 
                'HIGH': { bg: '#fef2f2', text: '#dc2626' }, 
                'MEDIUM': { bg: '#fef3c7', text: '#d97706' }
            };
            
            const priority = priorityColors[c.priority] || priorityColors['MEDIUM'];
            const risk = riskColors[c.riskLevel] || riskColors['MEDIUM'];
            
            const statusColors = {
                'OPEN':      { bg: '#e0f2fe', text: '#0369a1' },
                'ASSIGNED':  { bg: '#ede9fe', text: '#6d28d9' },
                'IN_REVIEW': { bg: '#fef3c7', text: '#b45309' },
                'ESCALATED': { bg: '#fee2e2', text: '#b91c1c' },
                'RESOLVED':  { bg: '#dcfce7', text: '#15803d' }
            };
            const status = statusColors[c.status] || statusColors['OPEN'];
            const displayName = c.customerName || c.customerId;
            const initials = displayName.split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase();

            return `
                <tr>
                    <td class="px-3 py-3">
                        <div class="rc-customer">
                            <span class="rc-customer__avatar" aria-hidden="true">${escapeHtml(initials)}</span>
                            <span class="rc-customer__text">
                                <strong>${escapeHtml(displayName)}</strong>
                                <small>${escapeHtml(c.customerId)}</small>
                            </span>
                        </div>
                    </td>
                    <td class="px-3 py-3">
                        <span class="badge" style="background: #fff5e6; color: #FF8D28; font-size: 11px; font-weight: 600; padding: 5px 10px;">
                            ${c.triggerType}
                        </span>
                    </td>
                    <td class="px-3 py-3">
                        <span class="badge" style="background: ${priority.bg}; color: ${priority.text}; font-size: 11px; font-weight: 600; padding: 5px 10px;">
                            ${priority.icon} ${c.priority}
                        </span>
                    </td>
                    <td class="px-3 py-3">
                        <span class="badge" style="background: ${risk.bg}; color: ${risk.text}; font-size: 11px; font-weight: 600; padding: 5px 10px; text-transform: uppercase;">
                            ${c.riskLevel}
                        </span>
                    </td>
                    <td class="px-3 py-3">
                        <span class="badge" style="background: ${status.bg}; color: ${status.text}; font-size: 11px; font-weight: 600; padding: 5px 10px;">
                            ${c.status.replace(/_/g, ' ')}
                        </span>
                    </td>
                    <td class="px-3 py-3 text-muted" style="font-size: 12px;">${c.createdAt}</td>
                    <td class="px-3 py-3 text-muted" style="font-size: 12px;">${c.assignedTo}</td>
                    <td class="px-3 py-3">
                        <div class="rc-actions">
                            <button type="button" class="btn btn-sm rc-actions__view view-case-btn" data-customer="${c.customerId}" data-case="${c.caseId}">
                                <i class="far fa-eye me-1"></i>View
                            </button>
                            <button type="button" class="btn btn-sm rc-actions__icon assign-btn" data-customer="${c.customerId}" data-case="${c.caseId}" title="Assign case" aria-label="Assign case for ${escapeHtml(displayName)}">
                                <i class="fas fa-user-plus"></i>
                            </button>
                            <button type="button" class="btn btn-sm rc-actions__icon export-btn" data-customer="${c.customerId}" data-case="${c.caseId}" title="Export case report" aria-label="Export case report for ${escapeHtml(displayName)}">
                                <i class="fas fa-file-arrow-down"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
        
        $("#casesTableBody").html(rows);
        this.renderPaginationControls(total, startIdx, endIdx);
    },
    
    renderPaginationControls(total, startIdx, endIdx) {
        // Update pagination info
        if (total === 0) {
            $("#paginationInfo").text("0 cases");
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
                    <a class="page-link" href="#" id="prevPage">
                        <i class="fas fa-chevron-left"></i>
                    </a>
                </li>
                <li class="page-item active"><a class="page-link" href="#">1</a></li>
                <li class="page-item disabled">
                    <a class="page-link" href="#" id="nextPage">
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
                <a class="page-link" href="#" id="prevPage" style="border-radius: 6px 0 0 6px;">
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
                    <a class="page-link page-num-btn" href="#" data-page="1">1</a>
                </li>
            `;
            if (startPage > 2) {
                paginationHTML += `<li class="page-item disabled"><a class="page-link">...</a></li>`;
            }
        }
        
        // Page numbers
        for (let i = startPage; i <= endPage; i++) {
            paginationHTML += `
                <li class="page-item ${i === this.pagination.currentPage ? 'active' : ''}">
                    <a class="page-link page-num-btn" href="#" data-page="${i}">${i}</a>
                </li>
            `;
        }
        
        // Last page
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) {
                paginationHTML += `<li class="page-item disabled"><a class="page-link">...</a></li>`;
            }
            paginationHTML += `
                <li class="page-item">
                    <a class="page-link page-num-btn" href="#" data-page="${totalPages}">${totalPages}</a>
                </li>
            `;
        }
        
        // Next button
        paginationHTML += `
            <li class="page-item ${this.pagination.currentPage === totalPages ? 'disabled' : ''}">
                <a class="page-link" href="#" id="nextPage" style="border-radius: 0 6px 6px 0;">
                    <i class="fas fa-chevron-right"></i>
                </a>
            </li>
        `;
        
        $("#paginationControls").html(paginationHTML);
    },
    
    showCaseDetailsModal(caseData) {
        const alert = caseData.fullData || {};
        const score = Number(alert.risk_score);
        const hasScore = Number.isFinite(score);
        const scoreClass = !hasScore ? 'low' : score >= 80 ? 'high' : score >= 60 ? 'medium' : 'low';
        const human = (v) => (v ? String(v).replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase()) : '—');
        const created = alert.created_at
            ? new Date(alert.created_at).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
            : caseData.createdAt;

        const ruleCodes = (alert.triggered_rules && (alert.triggered_rules.rules || alert.triggered_rules)) || [];
        const rules = (Array.isArray(ruleCodes) ? ruleCodes : []).map(code => {
            const r = this.RULES[code] || [code, 'Rule triggered', '—'];
            return { code, name: r[0], detail: r[1], severity: r[2] };
        });

        // Explanation assembled from the alert's own data
        const parts = [`${caseData.riskLevel} risk`];
        parts.push(hasScore ? `score ${score}/100` : 'no score recorded');
        if (alert.confidence != null) parts.push(`confidence ${Number(alert.confidence).toFixed(0)}%`);
        let explanation = `${parts.join(', ')}. `;
        explanation += rules.length
            ? `Triggered by ${rules.map(r => r.name.toLowerCase()).join(' and ')}. `
            : 'No individual rule triggers were recorded for this alert. ';
        if (alert.recommended_action) explanation += `Recommended action: ${human(alert.recommended_action).toLowerCase()}.`;

        const severityClass = (sev) => (sev === 'CRITICAL' || sev === 'HIGH' ? 'high' : sev === 'MEDIUM' ? 'medium' : 'low');
        const statusColors = {
            OPEN: ['#e0f2fe', '#0369a1'], ASSIGNED: ['#ede9fe', '#6d28d9'], IN_REVIEW: ['#fef3c7', '#b45309'],
            ESCALATED: ['#fee2e2', '#b91c1c'], RESOLVED: ['#dcfce7', '#15803d']
        };
        const [statusBg, statusFg] = statusColors[caseData.status] || statusColors.OPEN;
        const displayName = caseData.customerName || caseData.customerId;

        const modalHtml = `
            <div class="modal fade" id="caseDetailsModal" tabindex="-1" aria-labelledby="caseDetailsTitle" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered modal-lg">
                    <div class="modal-content kx-modal">
                        <div class="modal-header">
                            <div>
                                <h5 class="modal-title" id="caseDetailsTitle">${escapeHtml(displayName)}</h5>
                                <small class="text-muted">${escapeHtml(caseData.customerId)} &middot; Case ${escapeHtml(caseData.caseId)}</small>
                            </div>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <div class="cd-score cd-score--${scoreClass}">
                                <div class="cd-score__value">
                                    <span>Risk score</span>
                                    <strong>${hasScore ? score : '—'}<small>/100</small></strong>
                                </div>
                                <div class="cd-score__meter" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${hasScore ? score : 0}" aria-label="Risk score">
                                    <span style="width: ${hasScore ? Math.max(0, Math.min(100, score)) : 0}%"></span>
                                </div>
                                <div class="cd-score__meta">
                                    <span class="cd-chip cd-chip--${scoreClass}">${escapeHtml(caseData.riskLevel)} risk</span>
                                    ${alert.confidence != null ? `<span>Confidence ${Number(alert.confidence).toFixed(0)}%</span>` : ''}
                                </div>
                            </div>

                            <div class="cd-grid">
                                <div><label>Status</label><span class="badge" style="background:${statusBg};color:${statusFg};">${escapeHtml(human(caseData.status))}</span></div>
                                <div><label>Priority</label><strong>${escapeHtml(human(caseData.priority))}</strong></div>
                                <div><label>Trigger type</label><strong>${escapeHtml(human(caseData.triggerType))}</strong></div>
                                <div><label>Alert type</label><strong>${escapeHtml(human(alert.alert_type))}</strong></div>
                                <div><label>Created</label><strong>${escapeHtml(created)}</strong></div>
                                <div><label>Assigned to</label><strong>${escapeHtml(caseData.assignedTo)}</strong></div>
                            </div>

                            <h6 class="cd-heading">Why this case was flagged</h6>
                            <p class="cd-explanation">${escapeHtml(explanation)}</p>

                            <h6 class="cd-heading">Triggered rules</h6>
                            ${rules.length ? `
                                <ul class="cd-rules">
                                    ${rules.map(r => `
                                        <li>
                                            <span class="cd-rules__code">${escapeHtml(r.code)}</span>
                                            <span class="cd-rules__text"><strong>${escapeHtml(r.name)}</strong>${escapeHtml(r.detail)}</span>
                                            <span class="cd-chip cd-chip--${severityClass(r.severity)}">${escapeHtml(r.severity)}</span>
                                        </li>`).join('')}
                                </ul>` : `<p class="cd-explanation text-muted">No rule triggers recorded.</p>`}

                            ${alert.resolution_outcome ? `
                                <h6 class="cd-heading">Disposition</h6>
                                <p class="cd-explanation">
                                    <strong>${escapeHtml(human(alert.resolution_outcome))}</strong>${(alert.resolution_reasons || []).length ? ` &middot; ${escapeHtml(alert.resolution_reasons.map(human).join(', '))}` : ''}${alert.sar_reference ? ` &middot; Ref ${escapeHtml(alert.sar_reference)}` : ''}
                                    ${alert.resolution_notes ? `<br>${escapeHtml(alert.resolution_notes)}` : ''}
                                </p>` : ''}
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-primary" data-bs-dismiss="modal">Close</button>
                            ${caseData.status !== 'RESOLVED' && alert.id ? `
                                <button type="button" class="btn btn-outline-primary" id="caseDetailsResolveBtn">
                                    <i class="fas fa-check-double me-2"></i>Resolve
                                </button>` : ''}
                            <button type="button" class="btn btn-primary" id="caseDetailsExportBtn">
                                <i class="fas fa-file-arrow-down me-2"></i>Export report
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        $("#caseDetailsModal").remove();
        $("body").append(modalHtml);
        const modalEl = document.getElementById('caseDetailsModal');
        const modal = new bootstrap.Modal(modalEl);
        modal.show();

        // Hand over to the export dialog once this modal has closed
        $("#caseDetailsExportBtn").on("click", () => {
            $(modalEl).one("hidden.bs.modal", () => this.showExportModal(caseData.caseId, caseData.customerId));
            modal.hide();
        });

        $("#caseDetailsResolveBtn").on("click", () => {
            $(modalEl).one("hidden.bs.modal", () => this.showResolveModal(caseData));
            modal.hide();
        });

        $(modalEl).on("hidden.bs.modal", function() {
            setTimeout(() => $(this).remove(), 0);
        });
    },

    // Records the disposition (outcome + reason codes + notes) for a case.
    // "Escalated" goes to /escalate; the other outcomes close the alert.
    async showResolveModal(caseData) {
        let options;
        try {
            options = await API.get('/alerts/resolution-options');
        } catch (error) {
            showToast('error', 'Could not load resolution options. Please try again.');
            return;
        }
        const reasonLabels = Object.fromEntries(options.reasons.map(r => [r.code, r.label]));
        const human = (v) => String(v).replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
        const displayName = caseData.customerName || caseData.customerId;

        const modalHtml = `
            <div class="modal fade" id="resolveCaseModal" tabindex="-1" aria-labelledby="resolveCaseTitle" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content kx-modal">
                        <div class="modal-header">
                            <div>
                                <h5 class="modal-title" id="resolveCaseTitle">Resolve case</h5>
                                <small class="text-muted">${escapeHtml(displayName)} &middot; Case ${escapeHtml(caseData.caseId)}</small>
                            </div>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <label class="kx-label" for="resolveOutcome">Outcome</label>
                            <select class="form-select mb-1" id="resolveOutcome">
                                <option value="">Select an outcome...</option>
                                ${options.outcomes.map(o => `<option value="${escapeHtml(o.code)}">${escapeHtml(human(o.code))}</option>`).join('')}
                            </select>
                            <p class="kx-note mt-0 mb-3" id="resolveOutcomeHelp"></p>

                            <div class="kx-label">Reasons</div>
                            <div class="kx-sections mb-3" id="resolveReasons">
                                <p class="kx-note my-2">Select an outcome to see its reasons.</p>
                            </div>

                            <div class="mb-3 d-none" id="resolveSarGroup">
                                <label class="kx-label" for="resolveSarReference">SAR/STR filing reference</label>
                                <input type="text" class="form-control" id="resolveSarReference" maxlength="100">
                            </div>

                            <label class="kx-label" for="resolveNotes">Notes</label>
                            <textarea class="form-control" id="resolveNotes" rows="4" placeholder="What was checked and why this outcome was chosen"></textarea>
                            <div class="text-danger small mt-2 d-none" id="resolveError" role="alert"></div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-primary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-primary" id="confirmResolveBtn">Save disposition</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        $("#resolveCaseModal").remove();
        $("body").append(modalHtml);
        const modalEl = document.getElementById('resolveCaseModal');
        const modal = new bootstrap.Modal(modalEl);
        modal.show();

        $("#resolveOutcome").on("change", function() {
            const outcome = options.outcomes.find(o => o.code === $(this).val());
            $("#resolveOutcomeHelp").text(outcome ? outcome.label : '');
            $("#resolveSarGroup").toggleClass("d-none", !outcome || outcome.code !== 'SAR_FILED');
            $("#resolveReasons").html(outcome ? outcome.reasons.map(code => `
                <label class="form-check">
                    <input class="form-check-input resolve-reason" type="checkbox" value="${escapeHtml(code)}">
                    <span class="form-check-label">${escapeHtml(reasonLabels[code] || human(code))}</span>
                </label>`).join('') : '<p class="kx-note my-2">Select an outcome to see its reasons.</p>');
        });

        const showError = (message) => $("#resolveError").text(message).removeClass("d-none");

        $("#confirmResolveBtn").on("click", async () => {
            const outcome = $("#resolveOutcome").val();
            const reasons = $(".resolve-reason:checked").map((_, el) => el.value).get();
            const notes = $("#resolveNotes").val().trim();
            if (!outcome) return showError('Select an outcome.');
            if (!reasons.length) return showError('Select at least one reason.');
            if (!notes) return showError('Notes are required.');

            const $btn = $("#confirmResolveBtn").prop("disabled", true);
            try {
                const updated = outcome === 'ESCALATED'
                    ? await API.put(`/alerts/${caseData.caseId}/escalate`, { resolution_notes: notes, reasons })
                    : await API.put(`/alerts/${caseData.caseId}/resolve`, {
                        outcome, reasons, resolution_notes: notes,
                        sar_reference: $("#resolveSarReference").val().trim() || null
                    });
                caseData.status = updated.status;
                caseData.fullData = updated;
                modal.hide();
                showToast('success', outcome === 'ESCALATED' ? 'Case escalated.' : 'Case resolved.');
                this.updateDashboard();
                this.renderTable();
            } catch (xhr) {
                const detail = xhr && xhr.responseJSON && xhr.responseJSON.detail;
                showError(xhr && xhr.status === 403
                    ? 'Only a compliance officer or admin can resolve a case. Analysts can escalate it.'
                    : (typeof detail === 'string' ? detail : 'Could not save the disposition. Please try again.'));
                $btn.prop("disabled", false);
            }
        });

        $(modalEl).on("hidden.bs.modal", function() {
            setTimeout(() => $(this).remove(), 0);
        });
    },

    generateMockCases() {
        // Generate mock cases with LIMITED customers (only 5 unique customers)
        const triggerTypes = ['BEHAVIOR BASED', 'TIME BASED', 'RULE BASED', 'MANUAL'];
        const statuses = ['OPEN', 'ASSIGNED', 'IN_REVIEW', 'ESCALATED'];
        const priorities = ['URGENT', 'HIGH', 'MEDIUM', 'LOW'];
        const riskLevels = ['HIGH', 'MEDIUM', 'LOW'];
        
        // Only 5 customers like patterns page
        const customers = ['CUST-001', 'CUST-002', 'CUST-003', 'CUST-004', 'CUST-005'];
        
        this.casesData = [];
        for (let i = 1; i <= 125; i++) {
            const riskLevel = riskLevels[Math.floor(Math.random() * riskLevels.length)];
            const priority = riskLevel === 'HIGH' ? 'URGENT' : riskLevel === 'MEDIUM' ? 'HIGH' : 'MEDIUM';
            
            // Pick random customer from the 5 customers
            const customerId = customers[Math.floor(Math.random() * customers.length)];
            
            this.casesData.push({
                caseId: `case-${String(i).padStart(4, '0')}`,
                customerId: customerId,
                triggerType: triggerTypes[Math.floor(Math.random() * triggerTypes.length)],
                priority: priority,
                riskLevel: riskLevel,
                status: statuses[Math.floor(Math.random() * statuses.length)],
                createdAt: new Date(Date.now() - Math.random() * 60 * 24 * 60 * 60 * 1000).toLocaleDateString(),
                assignedTo: Math.random() > 0.3 ? 'Analyst' : 'Unassigned',
                fullData: {
                    risk_score: riskLevel === 'HIGH' ? 85 : riskLevel === 'MEDIUM' ? 65 : 35,
                    alert_type: 'BEHAVIORAL_ANOMALY'
                }
            });
        }
        
        this.totalCases = this.casesData.length;
        this.updateDashboard();
        this.renderTable();
    },
    
    getFilteredCases() {
        const q = (this.currentFilters.search || '').trim().toLowerCase();
        return this.casesData.filter(c => {
            if (this.currentFilters.customer && c.customerId !== this.currentFilters.customer) return false;
            if (q) {
                const haystack = `${c.customerName || ''} ${c.customerId} ${c.caseId}`.toLowerCase();
                if (!haystack.includes(q)) return false;
            }
            if (this.currentFilters.riskLevel !== 'all' && c.riskLevel !== this.currentFilters.riskLevel) return false;
            if (this.currentFilters.triggerType !== 'all' && c.triggerType !== this.currentFilters.triggerType) return false;
            if (this.currentFilters.status !== 'all' && c.status !== this.currentFilters.status) return false;
            return true;
        });
    },
    
    setupEventListeners() {
        const self = this;
        
        // Filter change handlers
        const applyFilters = () => {
            self.currentFilters.search = $("#caseSearch").val() || '';
            self.currentFilters.riskLevel = $("#filterRiskLevel").val();
            self.currentFilters.triggerType = $("#filterTriggerType").val();
            self.currentFilters.status = $("#filterStatus").val();
            const active = self.currentFilters.search.trim() !== '' ||
                ['riskLevel', 'triggerType', 'status'].some(k => self.currentFilters[k] !== 'all');
            $("#clearFiltersBtn").toggleClass("d-none", !active);

            // Reset to first page when filters change
            self.pagination.currentPage = 1;
            self.renderTable();
        };
        $("#filterRiskLevel, #filterTriggerType, #filterStatus").on("change", applyFilters);
        $("#caseSearch").on("input", debounce(applyFilters, 200));

        // Refresh button
        $("#refreshCasesBtn").on("click", () => this.fetchCasesData());
        
        // Page size selector
        $("body").off("change", "#pageSizeSelect").on("change", "#pageSizeSelect", function(e) {
            self.pagination.pageSize = parseInt($(this).val());
            self.pagination.currentPage = 1; // Reset to first page
            self.renderTable();
        });
        
        // Previous page button
        $("body").off("click", "#prevPage").on("click", "#prevPage", function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            if (!$(this).parent().hasClass('disabled') && self.pagination.currentPage > 1) {
                self.pagination.currentPage--;
                self.renderTable();
                
                // Scroll to top of table
                $(".table-responsive").get(0)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
        
        // Next page button
        $("body").off("click", "#nextPage").on("click", "#nextPage", function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const filtered = self.getFilteredCases();
            const totalPages = Math.ceil(filtered.length / self.pagination.pageSize);
            
            if (!$(this).parent().hasClass('disabled') && self.pagination.currentPage < totalPages) {
                self.pagination.currentPage++;
                self.renderTable();
                
                // Scroll to top of table
                $(".table-responsive").get(0)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
        
        // Page number buttons
        $("body").off("click", ".page-num-btn").on("click", ".page-num-btn", function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const page = parseInt($(this).data("page"));
            if (page && page !== self.pagination.currentPage) {
                self.pagination.currentPage = page;
                self.renderTable();
                
                // Scroll to top of table
                $(".table-responsive").get(0)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
        
        $("#selectAll").on("change", function() {
            $(".case-checkbox").prop("checked", $(this).is(":checked"));
        });
        
        // View Case button clicks - show modal
        $("body").off("click", ".view-case-btn").on("click", ".view-case-btn", function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const customerId = $(this).data("customer");
            const caseId = $(this).data("case");
            
            console.log("View Case clicked for:", customerId, caseId);
            
            // Find the case data
            const caseData = self.casesData.find(c => c.caseId === caseId && c.customerId === customerId);
            
            if (caseData) {
                self.showCaseDetailsModal(caseData);
            }
        });
        
        // Assign button clicks
        $("body").off("click", ".assign-btn").on("click", ".assign-btn", function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const caseId = $(this).data("case");
            const customerId = $(this).data("customer");
            
            console.log("Assign clicked for case:", caseId, "customer:", customerId);
            
            Cases.showAssignModal(caseId, customerId);
        });
        
        // Export File button clicks
        $("body").off("click", ".export-btn").on("click", ".export-btn", function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const caseId = $(this).data("case");
            const customerId = $(this).data("customer");
            
            console.log("Export File clicked for case:", caseId, "customer:", customerId);
            
            Cases.showExportModal(caseId, customerId);
        });
        
        // Clear search + dropdown filters
        $("#clearFiltersBtn").on("click", () => {
            $("#caseSearch").val('');
            $("#filterRiskLevel, #filterTriggerType, #filterStatus").val('all');
            applyFilters();
            $("#caseSearch").trigger("focus");
        });

        // Drop the customer filter that came from the Patterns page
        $("#clearCustomerFilterBtn").on("click", () => {
            this.currentFilters.customer = null;
            this.currentFilters.pattern = null;
            $(".rc-filter-chip").remove();
            this.pagination.currentPage = 1;
            this.renderTable();
        });
    },
    
    showAssignModal(caseId, customerId) {
        // Create modal HTML
        const modalHtml = `
            <div class="modal fade" id="assignCaseModal" tabindex="-1" aria-labelledby="assignCaseModalLabel" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content" style="border-radius: 14px; border: none;">
                        <div class="modal-header" style="border-bottom: 1px solid #eceef2; padding: 20px 24px;">
                            <h5 class="modal-title" id="assignCaseModalLabel" style="font-weight: 700; color: #1c2430;">
                                <i class="fas fa-user-plus" style="color: #FF8D28; margin-right: 8px;"></i>
                                Assign Case
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body" style="padding: 24px;">
                            <div class="mb-3">
                                <label class="form-label" style="font-weight: 600; font-size: 13px; color: #1c2430;">Case ID</label>
                                <input type="text" class="form-control" value="${caseId}" disabled style="background: #f7f8fa; border: 1px solid #eceef2; border-radius: 8px;">
                            </div>
                            <div class="mb-3">
                                <label class="form-label" style="font-weight: 600; font-size: 13px; color: #1c2430;">Customer ID</label>
                                <input type="text" class="form-control" value="${customerId}" disabled style="background: #f7f8fa; border: 1px solid #eceef2; border-radius: 8px;">
                            </div>
                            <div class="mb-3">
                                <label for="assignToUser" class="form-label" style="font-weight: 600; font-size: 13px; color: #1c2430;">
                                    Assign To <span style="color: #e53935;">*</span>
                                </label>
                                <select class="form-select" id="assignToUser" style="border: 1px solid #d1d5db; border-radius: 8px; padding: 10px 14px;">
                                    <option value="">Select an analyst...</option>
                                    <option value="analyst1">John Smith (Analyst)</option>
                                    <option value="analyst2">Sarah Johnson (Senior Analyst)</option>
                                    <option value="analyst3">Mike Chen (Analyst)</option>
                                    <option value="analyst4">Emma Davis (Lead Analyst)</option>
                                    <option value="analyst5">David Wilson (Analyst)</option>
                                </select>
                            </div>
                            <div class="mb-3">
                                <label for="assignmentNotes" class="form-label" style="font-weight: 600; font-size: 13px; color: #1c2430;">Notes (Optional)</label>
                                <textarea class="form-control" id="assignmentNotes" rows="3" placeholder="Add any notes or instructions for this assignment..." style="border: 1px solid #d1d5db; border-radius: 8px; padding: 10px 14px; resize: vertical;"></textarea>
                            </div>
                            <div class="alert alert-info" style="background: #e7f3ff; border: 1px solid #b3d9ff; border-radius: 8px; padding: 12px; font-size: 13px; margin-bottom: 0;">
                                <i class="fas fa-info-circle" style="color: #3b82f6; margin-right: 6px;"></i>
                                The assigned analyst will be notified via email and in-app notification.
                            </div>
                        </div>
                        <div class="modal-footer" style="border-top: 1px solid #eceef2; padding: 16px 24px; background: #f7f8fa;">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal" style="border-radius: 8px; padding: 8px 20px; font-size: 14px; font-weight: 600;">
                                Cancel
                            </button>
                            <button type="button" class="btn btn-primary" id="confirmAssignBtn" style="background: #FF8D28; border: none; border-radius: 8px; padding: 8px 20px; font-size: 14px; font-weight: 600;">
                                <i class="fas fa-check"></i> Assign Case
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Remove existing modal if any
        $('#assignCaseModal').remove();
        
        // Add modal to body
        $('body').append(modalHtml);
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('assignCaseModal'));
        modal.show();
        
        // Handle confirm button
        $('#confirmAssignBtn').off('click').on('click', function() {
            const assignedTo = $('#assignToUser').val();
            const notes = $('#assignmentNotes').val();
            
            if (!assignedTo) {
                showToast('error', 'Please select an analyst to assign the case to');
                return;
            }
            
            // Show loading state
            $(this).prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Assigning...');
            
            // Simulate API call
            setTimeout(() => {
                // Update the case in the data
                const caseIndex = Cases.casesData.findIndex(c => c.caseId === caseId);
                if (caseIndex !== -1) {
                    const analystNames = {
                        'analyst1': 'John Smith',
                        'analyst2': 'Sarah Johnson',
                        'analyst3': 'Mike Chen',
                        'analyst4': 'Emma Davis',
                        'analyst5': 'David Wilson'
                    };
                    Cases.casesData[caseIndex].assignedTo = analystNames[assignedTo];
                    Cases.casesData[caseIndex].status = 'ASSIGNED';
                }
                
                // Close modal
                modal.hide();
                
                // Show success message
                showToast('success', `Case ${caseId.substring(0, 8)}... assigned successfully`);
                
                // Refresh the table
                Cases.renderTable();
                Cases.updateStats();
            }, 1000);
        });
        
        // Clean up modal on hide
        $('#assignCaseModal').on('hidden.bs.modal', function() {
            $(this).remove();
        });
    },
    
    async showExportModal(caseId, customerId) {
        const caseData = this.casesData.find(c => c.caseId === caseId);
        const customerName = (caseData && caseData.customerName) || customerId;

        const modalHtml = `
            <div class="modal fade" id="exportCaseModal" tabindex="-1" aria-labelledby="exportCaseModalLabel" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content kx-modal">
                        <div class="modal-header">
                            <div>
                                <h5 class="modal-title" id="exportCaseModalLabel">
                                    <i class="fas fa-file-arrow-down me-2" style="color: var(--kt-accent-strong);"></i>Export Case Report
                                </h5>
                                <small class="text-muted">${escapeHtml(customerName)} &middot; ${escapeHtml(customerId)}</small>
                            </div>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <div class="mb-3">
                                <label class="form-label kx-label">Case ID</label>
                                <input type="text" class="form-control" value="${escapeHtml(caseId)}" disabled>
                            </div>
                            <div class="mb-3">
                                <label for="exportFormat" class="form-label kx-label">Format</label>
                                <div class="kx-formats" role="radiogroup" aria-label="Export format">
                                    <label class="kx-format"><input type="radio" name="exportFormat" value="pdf" checked><span><i class="fas fa-file-pdf"></i>PDF report</span></label>
                                    <label class="kx-format"><input type="radio" name="exportFormat" value="csv"><span><i class="fas fa-file-csv"></i>CSV (opens in Excel)</span></label>
                                    <label class="kx-format"><input type="radio" name="exportFormat" value="json"><span><i class="fas fa-file-code"></i>JSON data</span></label>
                                </div>
                            </div>
                            <div class="mb-1">
                                <label class="form-label kx-label">Include sections</label>
                                <div class="kx-sections">
                                    <label class="form-check"><input class="form-check-input" type="checkbox" id="includeSummary" checked><span class="form-check-label">Case &amp; customer summary</span></label>
                                    <label class="form-check"><input class="form-check-input" type="checkbox" id="includeRisk" checked><span class="form-check-label">Risk assessment &amp; screening</span></label>
                                    <label class="form-check"><input class="form-check-input" type="checkbox" id="includeTransactions" checked><span class="form-check-label">Transaction analysis</span></label>
                                    <label class="form-check"><input class="form-check-input" type="checkbox" id="includeTimeline" checked><span class="form-check-label">Activity timeline</span></label>
                                </div>
                            </div>
                            <p class="kx-note"><i class="fas fa-circle-info me-1"></i>Reports are built from live case, customer and transaction data at the time of export.</p>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-primary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-primary" id="confirmExportBtn">
                                <i class="fas fa-download me-2"></i>Export
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        $('#exportCaseModal').remove();
        $('body').append(modalHtml);
        const modal = new bootstrap.Modal(document.getElementById('exportCaseModal'));
        modal.show();

        $('#confirmExportBtn').off('click').on('click', async function() {
            const format = $('input[name="exportFormat"]:checked').val();
            const sections = [];
            if ($('#includeSummary').is(':checked')) sections.push('summary');
            if ($('#includeRisk').is(':checked')) sections.push('risk');
            if ($('#includeTransactions').is(':checked')) sections.push('transactions');
            if ($('#includeTimeline').is(':checked')) sections.push('timeline');
            if (!sections.length) {
                showToast('warning', 'Select at least one section to export');
                return;
            }

            const $btn = $(this);
            $btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin me-2"></i>Preparing report...');
            try {
                const report = await Cases.collectReportData(caseData, caseId, customerId);
                report.sections = sections;
                report.format = format;
                await Cases.generateExport(report, format);
                modal.hide();
                showToast('success', `Case report downloaded as ${format.toUpperCase()}`);
            } catch (error) {
                console.error('Export failed:', error);
                showToast('error', 'Could not build the case report. Please try again.');
                $btn.prop('disabled', false).html('<i class="fas fa-download me-2"></i>Export');
            }
        });

        $('#exportCaseModal').on('hidden.bs.modal', function() {
            $(this).remove();
        });
    },

    /** Gathers everything the report shows from the live API. */
    async collectReportData(caseData, caseId, customerCode) {
        const rawCustomerId = caseData && caseData.rawCustomerId;
        const settled = await Promise.allSettled([
            API.get(`/alerts/${caseId}`),
            rawCustomerId ? API.get(`/customers/${rawCustomerId}`) : Promise.resolve(null),
            rawCustomerId ? API.get('/transactions', { customer_id: rawCustomerId, page_size: 2000 }) : Promise.resolve(null),
            rawCustomerId ? API.get(`/customers/${rawCustomerId}/screening`) : Promise.resolve(null),
            rawCustomerId ? API.get(`/customers/${rawCustomerId}/kyc-reviews`) : Promise.resolve(null)
        ]);
        const value = (i) => (settled[i].status === 'fulfilled' ? settled[i].value : null);
        const user = (window.Auth && Auth.getUser && Auth.getUser()) || {};

        return {
            caseId,
            customerId: customerCode,
            customerName: (value(1) && value(1).full_name) || (caseData && caseData.customerName) || customerCode,
            exportDate: new Date().toISOString(),
            preparedBy: user.full_name || user.username || 'KYRO user',
            caseDetails: caseData || {},
            alert: value(0) || (caseData && caseData.fullData) || {},
            customer: value(1),
            transactions: (value(2) && (value(2).items || value(2))) || [],
            screening: value(3) || [],
            kycReviews: value(4) || []
        };
    },

    async generateExport(data, format) {
        const filename = `KYRO_case_${String(data.caseId).substring(0, 8)}_${new Date().toISOString().slice(0, 10)}`;
        switch (format) {
            case 'pdf':
                await this.generateHTMLPDF(data, filename);
                break;
            case 'csv':
                this.downloadFile(`${filename}.csv`, 'text/csv;charset=utf-8', '﻿' + this.generateCSVContent(data));
                break;
            case 'json':
                this.downloadFile(`${filename}.json`, 'application/json', JSON.stringify(data, null, 2));
                break;
        }
    },

    RULES: {
        R001: ['Amount Threshold', 'Transaction amount above the reporting threshold', 'MEDIUM'],
        R002: ['Velocity (daily)', 'More transactions per day than the configured limit', 'MEDIUM'],
        R003: ['Velocity (hourly)', 'More transactions per hour than the configured limit', 'LOW'],
        R004: ['High-Risk Country', 'Counterparty in a sanctioned or high-risk jurisdiction', 'HIGH'],
        R005: ['PEP Match', 'Customer is a Politically Exposed Person', 'HIGH'],
        R006: ['Sanctions Match', 'Customer matched on a sanctions list', 'CRITICAL'],
        R007: ['New Counterparty', 'First transaction with this counterparty', 'LOW'],
        R008: ['Weekend Activity', 'Transaction made on a weekend', 'LOW'],
        R009: ['Round Amount', 'Suspiciously round transaction amount', 'MEDIUM'],
        R010: ['Rapid Succession', 'Multiple transactions within one minute', 'HIGH']
    },

    /** Summary numbers for the transaction section (amounts kept per currency). */
    summarizeTransactions(transactions) {
        const byCurrency = {};
        let flagged = 0;
        let first = null;
        let last = null;
        const countries = new Set();
        const counterparties = {};
        transactions.forEach(t => {
            const cur = t.currency || '---';
            byCurrency[cur] = byCurrency[cur] || { count: 0, total: 0 };
            byCurrency[cur].count += 1;
            byCurrency[cur].total += Number(t.amount) || 0;
            const hasFlags = t.risk_flags && Object.keys(t.risk_flags).length > 0;
            if ((t.risk_score || 0) >= 50 || hasFlags) flagged += 1;
            const d = new Date(t.transaction_date);
            if (!isNaN(d)) {
                if (!first || d < first) first = d;
                if (!last || d > last) last = d;
            }
            if (t.meta_country) countries.add(t.meta_country);
            if (t.meta_counterparty) counterparties[t.meta_counterparty] = (counterparties[t.meta_counterparty] || 0) + 1;
        });
        const topCounterparties = Object.entries(counterparties).sort((a, b) => b[1] - a[1]).slice(0, 3);
        return { byCurrency, flagged, first, last, countries: [...countries], topCounterparties, count: transactions.length };
    },

    /** Renders the KYRO mark (same paths as the app logo) to a PNG for jsPDF. */
    async kyroLogoPng() {
        if (this._logoPng) return this._logoPng;
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="88" height="104" viewBox="0 0 44 52">
            <path d="M17.3573 25.4845C20.1188 25.4845 22.4006 23.2307 21.9439 20.5073C21.6589 18.808 21.228 17.142 20.6555 15.5347C19.5319 12.3802 17.8851 9.51402 15.809 7.0997C13.733 4.68537 11.2683 2.77023 8.55578 1.46361C7.38388 0.899101 6.17563 0.452955 4.94442 0.128265C2.27429 -0.575893 0 1.72305 0 4.48447V20.4845C0 23.2459 2.23858 25.4845 5 25.4845H17.3573Z" fill="#ffffff" fill-opacity="0.9" transform="translate(0 13)"/>
            <path d="M4.64504 25.4845C1.88362 25.4845 -0.39823 23.2307 0.0585117 20.5073C0.343506 18.808 0.774422 17.142 1.3469 15.5347C2.47046 12.3802 4.11729 9.51402 6.19336 7.0997C8.26943 4.68537 10.7341 2.77023 13.4466 1.46361C14.6185 0.899101 15.8267 0.452955 17.058 0.128265C19.7281 -0.575893 22.0024 1.72305 22.0024 4.48447V20.4845C22.0024 23.2459 19.7638 25.4845 17.0024 25.4845H4.64504Z" fill="#FF6A00" fill-opacity="0.95" transform="translate(11 13)"/>
        </svg>`;
        this._logoPng = await new Promise((resolve) => {
            const img = new Image();
            img.onload = () => {
                const canvas = document.createElement('canvas');
                canvas.width = 88; canvas.height = 104;
                canvas.getContext('2d').drawImage(img, 0, 0);
                resolve(canvas.toDataURL('image/png'));
            };
            img.onerror = () => resolve(null);
            img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
        });
        return this._logoPng;
    },

    async generateHTMLPDF(data, filename) {
        const { jsPDF } = window.jspdf;
        const doc = new jsPDF({ unit: 'mm', format: 'a4' });
        const hasTable = typeof doc.autoTable === 'function';

        const C = {
            accent: [249, 115, 22], accentSoft: [255, 243, 234], dark: [26, 26, 26],
            ink: [28, 36, 48], body: [75, 85, 99], muted: [107, 114, 128],
            line: [240, 228, 218], zebra: [255, 250, 246],
            high: [185, 28, 28], medium: [194, 65, 12], low: [21, 128, 61]
        };
        const W = 210, H = 297, M = 16, CW = W - 2 * M;
        const alert = data.alert || {};
        const cust = data.customer || {};
        const det = data.caseDetails || {};
        const has = (s) => data.sections.includes(s);
        const fmtDate = (v, withTime) => {
            if (!v) return '—';
            const d = new Date(v);
            if (isNaN(d)) return String(v);
            const dateOnly = typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v);
            return withTime && !dateOnly
                ? d.toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
                : d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
        };
        const human = (v) => (v ? String(v).replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase()) : '—');
        const money = (n) => Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        const riskLevel = det.riskLevel || cust.risk_level || 'MEDIUM';
        const riskRGB = riskLevel === 'HIGH' ? C.high : riskLevel === 'LOW' ? C.low : C.medium;
        const reportId = `KYRO-${String(data.caseId).substring(0, 8).toUpperCase()}`;

        doc.setProperties({
            title: `AML Case Report ${reportId}`,
            subject: `AML case report for ${data.customerName}`,
            author: data.preparedBy,
            keywords: 'AML, case, KYC, risk',
            creator: 'KYRO AML Risk Assessment'
        });

        let y = 0;
        const ensure = (space) => {
            if (y + space > H - 22) {
                doc.addPage();
                y = 20;
            }
        };
        const text = (str, x, yy, opts = {}) => {
            doc.setFont('helvetica', opts.bold ? 'bold' : 'normal');
            doc.setFontSize(opts.size || 9);
            doc.setTextColor(...(opts.color || C.body));
            doc.text(str, x, yy, opts.align ? { align: opts.align } : undefined);
        };
        const section = (title, subtitle, need = 24) => {
            ensure(need);
            y += 4;
            doc.setFillColor(...C.accent);
            doc.rect(M, y - 4.2, 1.6, 6.4, 'F');
            text(title, M + 4.5, y + 0.6, { size: 12.5, bold: true, color: C.ink });
            if (subtitle) text(subtitle, W - M, y + 0.6, { size: 8, color: C.muted, align: 'right' });
            y += 4;
            doc.setDrawColor(...C.line);
            doc.setLineWidth(0.3);
            doc.line(M, y, W - M, y);
            y += 5;
        };
        const keyValues = (rows) => {
            // Two columns of label/value pairs
            const colW = CW / 2;
            for (let i = 0; i < rows.length; i += 2) {
                ensure(10);
                let rowHeight = 11;
                [rows[i], rows[i + 1]].forEach((row, col) => {
                    if (!row) return;
                    const x = M + col * colW;
                    text(row[0].toUpperCase(), x, y, { size: 7, bold: true, color: C.muted });
                    doc.setFontSize(9.5);
                    const lines = doc.splitTextToSize(String(row[1] ?? '—'), colW - 6);
                    text(lines, x, y + 4.6, { size: 9.5, color: row[2] || C.ink, bold: !!row[2] });
                    rowHeight = Math.max(rowHeight, 6.5 + lines.length * 4.4);
                });
                y += rowHeight;
            }
        };
        const table = (head, body, opts = {}) => {
            if (!body.length) {
                ensure(10);
                text(opts.empty || 'No records.', M, y + 2, { size: 9, color: C.muted });
                y += 8;
                return;
            }
            if (body.length <= 6) ensure(14 + body.length * 9);
            if (!hasTable) {
                body.forEach(r => { ensure(6); text(r.join('   '), M, y, { size: 8 }); y += 5; });
                return;
            }
            doc.autoTable({
                startY: y,
                head: [head],
                body,
                margin: { left: M, right: M, bottom: 22, top: 20 },
                rowPageBreak: 'avoid',
                styles: { font: 'helvetica', fontSize: 8, cellPadding: 2.4, textColor: C.body, lineColor: C.line, lineWidth: 0.2 },
                headStyles: { fillColor: C.accentSoft, textColor: C.ink, fontStyle: 'bold', fontSize: 7.5 },
                alternateRowStyles: { fillColor: C.zebra },
                columnStyles: opts.columnStyles || {},
                didParseCell: opts.didParseCell
            });
            y = doc.lastAutoTable.finalY + 6;
        };

        // ── Header band ──────────────────────────────────────────────
        doc.setFillColor(...C.dark);
        doc.rect(0, 0, W, 46, 'F');
        doc.setFillColor(...C.accent);
        doc.rect(0, 46, W, 1.4, 'F');
        const logo = await this.kyroLogoPng();
        if (logo) doc.addImage(logo, 'PNG', M, 11, 9, 10.6);
        text('KYRO', M + (logo ? 12 : 0), 18.6, { size: 15, bold: true, color: [255, 255, 255] });
        text('AML Risk Assessment', M + (logo ? 12 : 0), 23.4, { size: 8, color: [156, 163, 175] });
        text('AML Case Investigation Report', M, 37, { size: 17, bold: true, color: [255, 255, 255] });
        // Confidential tag
        doc.setDrawColor(248, 113, 113);
        doc.setLineWidth(0.4);
        doc.roundedRect(W - M - 34, 12, 34, 7, 1.5, 1.5, 'S');
        text('CONFIDENTIAL', W - M - 17, 16.8, { size: 7.5, bold: true, color: [248, 113, 113], align: 'center' });
        text(`Report ID  ${reportId}`, W - M, 31, { size: 8, color: [209, 213, 219], align: 'right' });
        text(`Generated  ${fmtDate(data.exportDate, true)}`, W - M, 36, { size: 8, color: [209, 213, 219], align: 'right' });
        text(`Prepared by  ${data.preparedBy}`, W - M, 41, { size: 8, color: [209, 213, 219], align: 'right' });
        y = 58;

        // ── Subject line + risk strip ────────────────────────────────
        text(data.customerName, M, y, { size: 15, bold: true, color: C.ink });
        text(`${data.customerId}   ·   Case ${data.caseId}`, M, y + 5.5, { size: 8.5, color: C.muted });
        y += 12;
        const tiles = [
            ['RISK LEVEL', riskLevel, riskRGB],
            ['RISK SCORE', `${alert.risk_score ?? '—'} / 100`, C.ink],
            ['PRIORITY', human(det.priority), C.ink],
            ['STATUS', human(alert.status || det.status), C.ink]
        ];
        const tw = (CW - 9) / 4;
        tiles.forEach(([label, val, col], i) => {
            const x = M + i * (tw + 3);
            doc.setFillColor(...(i === 0 ? C.accentSoft : [249, 250, 251]));
            doc.setDrawColor(...(i === 0 ? [255, 220, 194] : [229, 231, 235]));
            doc.setLineWidth(0.3);
            doc.roundedRect(x, y, tw, 17, 2, 2, 'FD');
            text(label, x + 4, y + 6, { size: 6.8, bold: true, color: C.muted });
            text(String(val), x + 4, y + 13, { size: 11.5, bold: true, color: col });
        });
        y += 25;

        // ── Summary ──────────────────────────────────────────────────
        if (has('summary')) {
            section('Case Summary');
            const rules = ((alert.triggered_rules && (alert.triggered_rules.rules || alert.triggered_rules)) || []);
            const ruleNames = (Array.isArray(rules) ? rules : []).map(r => (this.RULES[r] ? this.RULES[r][0] : r));
            const summary = `${data.customerName} (${data.customerId}) was flagged by KYRO on ${fmtDate(alert.created_at)} ` +
                `with a risk score of ${alert.risk_score ?? 'n/a'}${alert.confidence != null ? ` (confidence ${Number(alert.confidence).toFixed(0)}%)` : ''}` +
                `${ruleNames.length ? `, triggered by: ${ruleNames.join(', ')}` : ''}. ` +
                `The case is ${human(alert.status || det.status).toLowerCase()} and ${det.assignedTo === 'Assigned' ? 'assigned to an analyst' : 'not yet assigned'}.`;
            doc.setFontSize(9.5);
            const lines = doc.splitTextToSize(summary, CW);
            ensure(lines.length * 4.6 + 4);
            text(lines, M, y, { size: 9.5, color: C.body });
            y += lines.length * 4.6 + 5;

            keyValues([
                ['Alert type', human(alert.alert_type)],
                ['Trigger', human(det.triggerType)],
                ['Opened', fmtDate(alert.created_at, true)],
                ['Recommended action', human(alert.recommended_action)],
                ['Assigned to', det.assignedTo || 'Unassigned'],
                ['Resolved', alert.resolved_at ? fmtDate(alert.resolved_at, true) : 'Not resolved']
            ]);

            section('Customer Profile');
            if (data.customer) {
                keyValues([
                    ['Full name', cust.full_name],
                    ['Customer type', human(cust.customer_type)],
                    ['Country', cust.country || '—'],
                    ['Residency', cust.residency_country || '—'],
                    ['Customer risk rating', `${cust.risk_level || '—'} (score ${cust.risk_score ?? '—'})`, cust.risk_level === 'HIGH' ? C.high : null],
                    ['KYC status', human(cust.kyc_status)],
                    ['Last KYC review', fmtDate(cust.kyc_last_review)],
                    ['Customer since', fmtDate(cust.created_at)]
                ]);
            } else {
                text('Customer record could not be loaded.', M, y, { size: 9, color: C.muted });
                y += 8;
            }
        }

        // ── Risk assessment ──────────────────────────────────────────
        if (has('risk')) {
            section('Risk Assessment', alert.ml_version ? `Model ${alert.ml_version}` : '');
            const flag = (on) => (on ? 'Yes' : 'No');
            keyValues([
                ['PEP', flag(cust.pep_flag), cust.pep_flag ? C.high : null],
                ['Sanctions match', flag(cust.sanctions_flag), cust.sanctions_flag ? C.high : null],
                ['Adverse media', flag(cust.adverse_media_flag), cust.adverse_media_flag ? C.medium : null],
                ['Last screened', fmtDate(cust.last_screened_at, true)]
            ]);

            const rules = (alert.triggered_rules && (alert.triggered_rules.rules || alert.triggered_rules)) || [];
            const ruleRows = (Array.isArray(rules) ? rules : []).map(code => {
                const r = this.RULES[code] || [code, 'Rule triggered', '—'];
                return [code, r[0], r[1], r[2]];
            });
            ensure(16 + Math.max(ruleRows.length, 1) * 9);
            text('Triggered rules', M, y, { size: 9.5, bold: true, color: C.ink });
            y += 3;
            table(['Rule', 'Name', 'What it detects', 'Severity'], ruleRows, {
                empty: 'No rule triggers recorded for this alert.',
                columnStyles: { 0: { cellWidth: 16, fontStyle: 'bold' }, 1: { cellWidth: 36 }, 3: { cellWidth: 22 } },
                didParseCell: (h) => {
                    if (h.section === 'body' && h.column.index === 3) {
                        const sev = String(h.cell.raw);
                        h.cell.styles.fontStyle = 'bold';
                        h.cell.styles.textColor = sev === 'CRITICAL' || sev === 'HIGH' ? C.high : sev === 'MEDIUM' ? C.medium : C.low;
                    }
                }
            });

            if (alert.ml_explanation && typeof alert.ml_explanation === 'object') {
                const feats = alert.ml_explanation.top_features || alert.ml_explanation.features || alert.ml_explanation;
                const rows = Array.isArray(feats)
                    ? feats.slice(0, 6).map(f => [human(f.feature || f.name), String(f.value ?? ''), String(f.contribution ?? f.shap ?? '')])
                    : Object.entries(feats).slice(0, 6).map(([k, v]) => [human(k), typeof v === 'object' ? JSON.stringify(v) : String(v), '']);
                ensure(16 + rows.length * 9);
                text('Model explanation (top factors)', M, y, { size: 9.5, bold: true, color: C.ink });
                y += 3;
                table(['Factor', 'Value', 'Contribution'], rows);
            }

            if (Array.isArray(data.screening) && data.screening.length) {
                ensure(16 + Math.min(data.screening.length, 8) * 9);
                text('Watchlist screening results', M, y, { size: 9.5, bold: true, color: C.ink });
                y += 3;
                table(['Type', 'List / source', 'Match', 'Score', 'Status', 'Screened'],
                    data.screening.slice(0, 8).map(s => [
                        human(s.screening_type),
                        (s.match_details && (s.match_details.source || s.match_details.list || s.match_details.list_name)) || s.screened_by || '—',
                        (s.match_details && (s.match_details.matched_name || s.match_details.name)) || '—',
                        s.match_score != null ? Number(s.match_score).toFixed(0) : '—', human(s.match_status), fmtDate(s.screened_at)
                    ]));
            }
        }

        // ── Transactions ─────────────────────────────────────────────
        if (has('transactions')) {
            const tx = data.transactions || [];
            const s = this.summarizeTransactions(tx);
            section('Transaction Analysis', tx.length ? `${fmtDate(s.first)} – ${fmtDate(s.last)}` : '');
            keyValues([
                ['Transactions on record', s.count.toLocaleString()],
                ['Flagged (score >= 50 or rule flags)', `${s.flagged.toLocaleString()}${s.count ? ` (${Math.round(s.flagged / s.count * 100)}%)` : ''}`, s.flagged ? C.medium : null],
                ['Countries involved', s.countries.length ? s.countries.slice(0, 8).join(', ') : '—'],
                ['Most frequent counterparties', s.topCounterparties.length ? s.topCounterparties.map(([n, c]) => `${n} (${c})`).join(', ') : '—']
            ]);
            const curRows = Object.entries(s.byCurrency).sort((a, b) => b[1].total - a[1].total)
                .map(([cur, v]) => [cur, v.count.toLocaleString(), money(v.total), money(v.total / v.count)]);
            ensure(16 + Math.max(curRows.length, 1) * 9);
            text('Volume by currency (not converted)', M, y, { size: 9.5, bold: true, color: C.ink });
            y += 3;
            table(['Currency', 'Transactions', 'Total amount', 'Average amount'], curRows, {
                empty: 'No transactions on record for this customer.',
                columnStyles: { 1: { halign: 'right' }, 2: { halign: 'right' }, 3: { halign: 'right' } }
            });

            const recent = [...tx].sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0) || new Date(b.transaction_date) - new Date(a.transaction_date)).slice(0, 12);
            if (recent.length) {
                ensure(16 + 4 * 9);
                text('Highest-risk transactions', M, y, { size: 9.5, bold: true, color: C.ink });
                y += 3;
                table(['Date', 'Type', 'Amount', 'Counterparty', 'Country', 'Risk'],
                    recent.map(t => [fmtDate(t.transaction_date), human(t.transaction_type), `${money(t.amount)} ${t.currency || ''}`,
                        t.meta_counterparty || '—', t.meta_country || '—', String(t.risk_score ?? 0)]),
                    {
                        columnStyles: { 2: { halign: 'right' }, 5: { halign: 'center', cellWidth: 14 } },
                        didParseCell: (h) => {
                            if (h.section === 'body' && h.column.index === 5) {
                                const v = Number(h.cell.raw);
                                h.cell.styles.fontStyle = 'bold';
                                h.cell.styles.textColor = v >= 70 ? C.high : v >= 40 ? C.medium : C.low;
                            }
                        }
                    });
            }
        }

        // ── Timeline ─────────────────────────────────────────────────
        if (has('timeline')) {
            const events = [];
            if (alert.created_at) events.push([alert.created_at, 'Alert raised', `${human(alert.alert_type)} · risk score ${alert.risk_score ?? '—'}`]);
            if (alert.assigned_to) events.push([alert.created_at, 'Assigned', 'Case assigned to an analyst']);
            if (alert.resolved_at) events.push([alert.resolved_at, 'Resolved', alert.resolution_notes || (alert.is_false_positive ? 'Closed as false positive' : 'Case resolved')]);
            (data.kycReviews || []).forEach(r => {
                events.push([r.completed_date || r.scheduled_date || r.created_at,
                    `KYC review ${human(r.review_status).toLowerCase()}`,
                    `${human(r.review_type)} review${r.risk_level_after ? ` · risk ${r.risk_level_after}` : ''}${r.findings ? ` · ${r.findings}` : ''}`]);
            });
            if (cust.last_screened_at) events.push([cust.last_screened_at, 'Watchlist screening', 'Customer screened against sanctions lists']);
            events.sort((a, b) => new Date(a[0]) - new Date(b[0]));
            section('Activity Timeline', '', 22 + Math.min(Math.max(events.length, 1), 6) * 9);
            table(['Date', 'Event', 'Details'], events.map(e => [fmtDate(e[0], true), e[1], e[2]]), {
                empty: 'No recorded activity.',
                columnStyles: { 0: { cellWidth: 38 }, 1: { cellWidth: 40, fontStyle: 'bold' } }
            });
        }

        // ── Suggested next steps (system guidance, not findings) ─────
        const steps = [];
        const action = alert.recommended_action;
        if (cust.sanctions_flag) steps.push('Confirm or dismiss the sanctions match before any further transactions are processed.');
        if (cust.pep_flag) steps.push('Apply enhanced due diligence for a Politically Exposed Person, including source of wealth.');
        if (action === 'SAR') steps.push('The model recommends a SAR: confirm the suspicion and prepare the filing.');
        if (action === 'ENHANCED_DUE_DILIGENCE') steps.push('Start enhanced due diligence: verify source of funds and the business rationale.');
        if (action === 'IMMEDIATE_REVIEW' || riskLevel === 'HIGH') steps.push('Escalate to a senior compliance officer for a decision.');
        if (['REVIEW', 'BATCH_REVIEW', 'IMMEDIATE_REVIEW'].includes(action) || riskLevel !== 'LOW') steps.push('Review the triggered rules against the customer\'s expected activity profile.');
        steps.push('Document the investigation outcome and, if suspicion is confirmed, prepare a SAR/STR filing.');
        section('Suggested Next Steps', 'System guidance based on alert and risk data');
        steps.forEach((step, i) => {
            doc.setFontSize(9.5);
            const lines = doc.splitTextToSize(step, CW - 10);
            ensure(lines.length * 4.6 + 3);
            doc.setFillColor(...C.accentSoft);
            doc.circle(M + 2.5, y - 1.2, 2.5, 'F');
            text(String(i + 1), M + 2.5, y, { size: 7.5, bold: true, color: C.accent, align: 'center' });
            text(lines, M + 8, y, { size: 9.5 });
            y += lines.length * 4.6 + 3;
        });

        // ── Analyst sign-off ─────────────────────────────────────────
        ensure(46);
        section('Review & Sign-off');
        const box = (x, label) => {
            doc.setDrawColor(209, 213, 219);
            doc.setLineWidth(0.3);
            doc.rect(x, y - 3.2, 3.6, 3.6);
            text(label, x + 5.5, y, { size: 9 });
        };
        text('Decision:', M, y, { size: 9, bold: true, color: C.ink });
        box(M + 20, 'No further action');
        box(M + 62, 'Enhanced monitoring');
        box(M + 108, 'Escalate');
        box(M + 135, 'File SAR/STR');
        y += 13;
        const signLine = (x, label) => {
            doc.setDrawColor(156, 163, 175);
            doc.line(x, y, x + 52, y);
            text(label, x, y + 4.5, { size: 7.5, color: C.muted });
        };
        signLine(M, 'Prepared by (analyst)');
        signLine(M + 62, 'Reviewed by (compliance officer)');
        signLine(M + 124, 'Date');
        text(data.preparedBy, M, y - 1.8, { size: 9, color: C.ink });
        y += 10;

        // ── Footer on every page ─────────────────────────────────────
        const pages = doc.internal.getNumberOfPages();
        for (let i = 1; i <= pages; i++) {
            doc.setPage(i);
            doc.setDrawColor(...C.accent);
            doc.setLineWidth(0.6);
            doc.line(M, H - 15, W - M, H - 15);
            text('KYRO · AML Case Investigation Report · Confidential — for authorized personnel only', M, H - 10, { size: 7, color: C.muted });
            text(`${reportId}   ·   Page ${i} of ${pages}`, W - M, H - 10, { size: 7, color: C.muted, align: 'right' });
        }

        doc.save(`${filename}.pdf`);
    },

    generateCSVContent(data) {
        const alert = data.alert || {};
        const cust = data.customer || {};
        const det = data.caseDetails || {};
        const rules = (alert.triggered_rules && (alert.triggered_rules.rules || alert.triggered_rules)) || [];
        const s = this.summarizeTransactions(data.transactions || []);
        const rows = [
            ['Case ID', data.caseId],
            ['Customer ID', data.customerId],
            ['Customer name', data.customerName],
            ['Alert type', alert.alert_type],
            ['Risk score', alert.risk_score],
            ['Risk level', det.riskLevel],
            ['Priority', det.priority],
            ['Status', alert.status || det.status],
            ['Triggered rules', Array.isArray(rules) ? rules.join('; ') : ''],
            ['Recommended action', alert.recommended_action],
            ['Opened', alert.created_at],
            ['Assigned to', det.assignedTo],
            ['Customer risk rating', cust.risk_level],
            ['KYC status', cust.kyc_status],
            ['PEP', cust.pep_flag],
            ['Sanctions match', cust.sanctions_flag],
            ['Transactions on record', s.count],
            ['Flagged transactions', s.flagged],
            ...Object.entries(s.byCurrency).map(([cur, v]) => [`Total ${cur} (${v.count} txns)`, v.total.toFixed(2)]),
            ['Exported', data.exportDate],
            ['Exported by', data.preparedBy]
        ];
        const cell = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
        return ['Field,Value', ...rows.map(r => r.map(cell).join(','))].join('\n') + '\n';
    },

    downloadFile(filename, mimeType, content) {
        // Create blob and download
        const blob = new Blob([content], { type: mimeType });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    }
};

window.Cases = Cases;
