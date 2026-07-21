/**
 * KYRO Review Cases - Dashboard with Risk Analysis
 * Exactly matching the reference screenshot layout
 */

const Cases = {
    currentFilters: {
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
    
    init(params = {}) {
        console.log("Initializing Review Cases dashboard...", params);
        
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
        // Build filter info message
        let filterInfo = '';
        if (this.currentFilters.customer || this.currentFilters.pattern) {
            const parts = [];
            if (this.currentFilters.customer) {
                parts.push(`Customer: <strong>${this.currentFilters.customer}</strong>`);
            }
            if (this.currentFilters.pattern) {
                const patternName = this.currentFilters.pattern.replace(/_/g, ' ');
                parts.push(`Pattern: <strong>${patternName}</strong>`);
            }
            filterInfo = `
                <div class="alert alert-info d-flex justify-content-between align-items-center mb-3" role="alert">
                    <div>
                        <i class="fas fa-filter me-2"></i>
                        Filtered by: ${parts.join(' | ')}
                    </div>
                    <button class="btn btn-sm btn-outline-info" id="clearFiltersBtn">Clear Filters</button>
                </div>
            `;
        }
        
        const html = `
            <div class="container-fluid py-4" style="max-width: 1280px; margin: 0 auto;">
                <!-- Page Header -->
                <div class="mb-4">
                    <h2 class="mb-1" style="font-weight: 600; font-size: 24px;">Review Cases</h2>
                    <p class="text-muted mb-3" style="font-size: 13px;">Monitor and manage AML review case with intelligent risk assessment</p>
                    <button class="btn px-4" id="refreshCasesBtn" style="background: #FF8D28; color: white; font-size: 13px; padding: 8px 24px;">
                        Refresh
                    </button>
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
                
                <!-- Results Count -->
                <div class="mb-3">
                    <strong style="font-size: 14px; color: #374151;" id="resultsCountTop">607 Result</strong>
                </div>
                
                <!-- Filters Section -->
                <div class="card border-0 shadow-sm mb-4" style="background: #fff5f0; border-left: 4px solid #FF8D28 !important;">
                    <div class="card-body p-3">
                        <h6 class="mb-3" style="font-weight: 600; color: #FF8D28; font-size: 14px;">
                            <i class="fas fa-filter me-2"></i>Filters
                        </h6>
                        <div class="row g-3">
                            <div class="col-md-4">
                                <label class="form-label text-muted mb-1" style="font-size: 12px;">Status</label>
                                <select class="form-select" id="filterStatus" style="font-size: 13px;">
                                    <option value="all">All Status</option>
                                    <option value="OPEN">Open</option>
                                    <option value="ASSIGNED">Assigned</option>
                                    <option value="IN_REVIEW">In Review</option>
                                    <option value="ESCALATED">Escalated</option>
                                    <option value="RESOLVED">Resolved</option>
                                </select>
                            </div>
                            <div class="col-md-4">
                                <label class="form-label text-muted mb-1" style="font-size: 12px;">Risk Level</label>
                                <select class="form-select" id="filterRiskLevel" style="font-size: 13px;">
                                    <option value="all">All Risk level</option>
                                    <option value="HIGH">High</option>
                                    <option value="MEDIUM">Medium</option>
                                    <option value="LOW">Low</option>
                                </select>
                            </div>
                            <div class="col-md-4">
                                <label class="form-label text-muted mb-1" style="font-size: 12px;">Trigger Type</label>
                                <select class="form-select" id="filterTriggerType" style="font-size: 13px;">
                                    <option value="all">All Trigger Types</option>
                                    <option value="BEHAVIOR BASED">Behavior Based</option>
                                    <option value="TIME BASED">Time Based</option>
                                    <option value="RULE BASED">Rule Based</option>
                                    <option value="MANUAL">Manual</option>
                                </select>
                            </div>
                        </div>
                        <div class="mt-2">
                            <button class="btn btn-sm" id="clearFiltersBtn" style="font-size: 12px; color: #FF8D28; background: white; border: 1px solid #FF8D28;">
                                <i class="fas fa-times me-1"></i> Clear Filters
                            </button>
                        </div>
                    </div>
                </div>
                
                <!-- Review Cases Table Section -->
                <div class="card border-0 shadow-sm">
                    <div class="card-body p-0">
                        <div class="p-4 d-flex justify-content-between align-items-center" style="background: #fffbf5; border-bottom: 1px solid #f0f0f0;">
                            <div>
                                <div class="d-flex align-items-center gap-2 mb-1">
                                    <i class="fas fa-clipboard-list" style="color: #FF8D28; font-size: 16px;"></i>
                                    <h6 class="mb-0" style="font-weight: 600; font-size: 15px;">Review Cases</h6>
                                </div>
                                <small class="text-muted" id="resultsCount" style="font-size: 12px;">Showing 50 of 607 cases</small>
                            </div>
                        </div>
                        <div class="table-responsive">
                            <table class="table table-hover align-middle mb-0" style="font-size: 13px;">
                                <thead style="background: #fafafa; border-bottom: 2px solid #e5e7eb;">
                                    <tr>
                                        <th class="px-3 py-3" style="width: 100px;">
                                            <span class="text-uppercase" style="font-size: 11px; font-weight: 600; color: #6c757d;">CUSTOMER</span>
                                        </th>
                                        <th class="px-3 py-3">
                                            <span class="text-uppercase" style="font-size: 11px; font-weight: 600; color: #6c757d;">TRIGGER TYPE</span>
                                        </th>
                                        <th class="px-3 py-3">
                                            <span class="text-uppercase" style="font-size: 11px; font-weight: 600; color: #6c757d;">PRIORITY</span>
                                        </th>
                                        <th class="px-3 py-3">
                                            <span class="text-uppercase" style="font-size: 11px; font-weight: 600; color: #6c757d;">RISK ASSESSMENT</span>
                                        </th>
                                        <th class="px-3 py-3">
                                            <span class="text-uppercase" style="font-size: 11px; font-weight: 600; color: #6c757d;">STATUS</span>
                                        </th>
                                        <th class="px-3 py-3">
                                            <span class="text-uppercase" style="font-size: 11px; font-weight: 600; color: #6c757d;">CREATED AT</span>
                                        </th>
                                        <th class="px-3 py-3">
                                            <span class="text-uppercase" style="font-size: 11px; font-weight: 600; color: #6c757d;">ASSIGNED TO</span>
                                        </th>
                                        <th class="px-3 py-3">
                                            <span class="text-uppercase" style="font-size: 11px; font-weight: 600; color: #6c757d;">ACTIONS</span>
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
            await new Promise(resolve => setTimeout(resolve, 800));
            
            // Mock data with varied trigger types to demonstrate real-time data integration
            this.casesData = [
                { caseId: '6541b2c8-7044', customerId: 'CUST-044', triggerType: 'BEHAVIOR BASED', priority: 'URGENT', riskLevel: 'HIGH', status: 'OPEN', createdAt: '7/17/2026', assignedTo: 'Unassigned' },
                { caseId: '5c972006-2041', customerId: 'CUST-041', triggerType: 'TIME BASED', priority: 'URGENT', riskLevel: 'MEDIUM', status: 'OPEN', createdAt: '7/17/2026', assignedTo: 'Unassigned' },
                { caseId: '7856209f-2040', customerId: 'CUST-040', triggerType: 'BEHAVIOR BASED', priority: 'URGENT', riskLevel: 'MEDIUM', status: 'OPEN', createdAt: '7/17/2026', assignedTo: 'Unassigned' },
                { caseId: '4a9e6eb0-6039', customerId: 'CUST-039', triggerType: 'RULE BASED', priority: 'URGENT', riskLevel: 'HIGH', status: 'OPEN', createdAt: '7/17/2026', assignedTo: 'Unassigned' },
                { caseId: 'df2fd299-e038', customerId: 'CUST-038', triggerType: 'BEHAVIOR BASED', priority: 'URGENT', riskLevel: 'HIGH', status: 'OPEN', createdAt: '7/17/2026', assignedTo: 'Unassigned' },
                { caseId: '75845f89-6037', customerId: 'CUST-037', triggerType: 'MANUAL', priority: 'URGENT', riskLevel: 'HIGH', status: 'OPEN', createdAt: '7/17/2026', assignedTo: 'Unassigned' },
                { caseId: '81ab4be7-c036', customerId: 'CUST-036', triggerType: 'TIME BASED', priority: 'URGENT', riskLevel: 'HIGH', status: 'OPEN', createdAt: '7/17/2026', assignedTo: 'Unassigned' },
                { caseId: 'f4727cfd-3035', customerId: 'CUST-035', triggerType: 'BEHAVIOR BASED', priority: 'URGENT', riskLevel: 'HIGH', status: 'OPEN', createdAt: '7/17/2026', assignedTo: 'Unassigned' }
            ];
            
            this.updateDashboard();
            this.renderTable();
            
        } catch (error) {
            console.error("Error fetching cases:", error);
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
        $("#resultsCount").text(`Showing ${filtered.length} of 607 cases`);
        
        if (filtered.length === 0) {
            $("#casesTableBody").html(`
                <tr><td colspan="8" class="text-center py-5 text-muted">No cases found</td></tr>
            `);
            return;
        }
        
        const rows = filtered.map(c => {
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
            
            // Extract customer number from CUST-044
            const customerNum = c.customerId.split('-')[1];
            
            return `
                <tr style="border-bottom: 1px solid #f0f0f0;">
                    <td class="px-3 py-3">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="background: #ffe0e0; color: #dc2626; width: 28px; height: 28px; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 600;">
                                ${customerNum}
                            </span>
                            <span style="font-size: 13px; font-weight: 500;">${c.customerId}</span>
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
                        <span class="badge" style="background: #d4edda; color: #155724; font-size: 11px; font-weight: 600; padding: 5px 10px;">
                            ${c.status}
                        </span>
                    </td>
                    <td class="px-3 py-3 text-muted" style="font-size: 12px;">${c.createdAt}</td>
                    <td class="px-3 py-3 text-muted" style="font-size: 12px;">${c.assignedTo}</td>
                    <td class="px-3 py-3">
                        <div class="d-flex gap-2" style="font-size: 12px;">
                            <button class="btn btn-sm view-case-btn" data-customer="${c.customerId}" data-case="${c.caseId}" style="color: #FF8D28; background: transparent; border: none; padding: 0; text-decoration: none; display: flex; align-items: center; gap: 4px;">
                                <i class="far fa-eye"></i> View Case
                            </button>
                            <button class="btn btn-sm assign-btn" data-customer="${c.customerId}" data-case="${c.caseId}" style="color: #3b82f6; background: transparent; border: none; padding: 0; text-decoration: none; display: flex; align-items: center; gap: 4px;">
                                <i class="fas fa-user"></i> Assign
                            </button>
                            <button class="btn btn-sm export-btn" data-customer="${c.customerId}" data-case="${c.caseId}" style="color: #22c55e; background: transparent; border: none; padding: 0; text-decoration: none; display: flex; align-items: center; gap: 4px;">
                                <i class="fas fa-download"></i> Export File
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
        
        $("#casesTableBody").html(rows);
    },
    
    showCaseDetailsModal(caseData) {
        const modalHtml = `
            <div class="modal fade" id="caseDetailsModal" tabindex="-1" style="z-index: 9999;">
                <div class="modal-dialog modal-dialog-centered modal-lg">
                    <div class="modal-content" style="border-radius: 12px; border: none;">
                        <div class="modal-header" style="border-bottom: 1px solid #e5e7eb; padding: 20px 24px;">
                            <div class="d-flex align-items-center gap-2">
                                <i class="fas fa-file-alt" style="color: #FF8D28; font-size: 20px;"></i>
                                <div>
                                    <h5 class="modal-title mb-0" style="font-weight: 600; font-size: 18px;">Case Details</h5>
                                    <small class="text-muted" style="font-size: 12px;">Case ID: ${caseData.caseId}</small>
                                </div>
                            </div>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body" style="padding: 24px;">
                            <!-- Basic Information -->
                            <h6 class="mb-3" style="font-weight: 600; font-size: 15px;">Basic Information</h6>
                            <div class="row g-3 mb-4">
                                <div class="col-md-6">
                                    <label class="text-muted mb-1" style="font-size: 12px;">Customer ID</label>
                                    <div>
                                        <span class="badge" style="background: #ffe8e0; color: #FF8D28; font-size: 13px; font-weight: 600; padding: 6px 12px;">
                                            ${caseData.customerId}
                                        </span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <label class="text-muted mb-1" style="font-size: 12px;">Trigger Type</label>
                                    <div>
                                        <span class="badge" style="background: #fff5e6; color: #FF8D28; font-size: 13px; font-weight: 600; padding: 6px 12px;">
                                            ${caseData.triggerType}
                                        </span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <label class="text-muted mb-1" style="font-size: 12px;">Risk Level</label>
                                    <div>
                                        <span class="badge" style="background: ${caseData.riskLevel === 'HIGH' ? '#fef2f2' : '#fef3c7'}; color: ${caseData.riskLevel === 'HIGH' ? '#dc2626' : '#d97706'}; font-size: 13px; font-weight: 600; padding: 6px 12px;">
                                            ${caseData.riskLevel}
                                        </span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <label class="text-muted mb-1" style="font-size: 12px;">Risk Score</label>
                                    <div style="font-weight: 600; font-size: 16px;">100.00</div>
                                </div>
                                <div class="col-md-6">
                                    <label class="text-muted mb-1" style="font-size: 12px;">Status</label>
                                    <div>
                                        <span class="badge" style="background: #d4edda; color: #155724; font-size: 13px; font-weight: 600; padding: 6px 12px;">
                                            ${caseData.status}
                                        </span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <label class="text-muted mb-1" style="font-size: 12px;">Created At</label>
                                    <div style="font-size: 14px;">${caseData.createdAt}, 5:49:56 AM</div>
                                </div>
                            </div>
                            
                            <!-- Explanation -->
                            <h6 class="mb-3" style="font-weight: 600; font-size: 15px;">Explanation</h6>
                            <div class="p-3 mb-3" style="background: #f8f9fa; border-radius: 8px;">
                                <p class="mb-0" style="font-size: 13px; line-height: 1.6; color: #374151;">
                                    HIGH risk (score: 100.0) - Detected: Transaction size deviation, Geographic pattern shift, Counterparty pattern change, ML anomaly detection: MEDIUM severity. 5 behavioral anomaly(ies) detected. Review recommended to assess if account activity requires further investigation.
                                </p>
                            </div>
                        </div>
                        <div class="modal-footer" style="border-top: 1px solid #e5e7eb; padding: 16px 24px;">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal" style="font-size: 14px; padding: 8px 20px;">Close</button>
                            <button type="button" class="btn export-case-btn" data-case="${caseData.caseId}" data-customer="${caseData.customerId}" style="background: #FF8D28; color: white; font-size: 14px; padding: 8px 20px; border: none;">
                                Export Case
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Remove existing modal if any
        $("#caseDetailsModal").remove();
        
        // Append modal to body
        $("body").append(modalHtml);
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('caseDetailsModal'));
        modal.show();
        
        // Handle Export Case button in modal
        $(".export-case-btn").off("click").on("click", function() {
            const caseId = $(this).data("case");
            const customerId = $(this).data("customer");
            
            if (window.Utils && Utils.showToast) {
                Utils.showToast(`Exporting case ${caseId} for ${customerId}...`, "success");
            }
            
            modal.hide();
        });
        
        // Clean up modal after hidden
        $("#caseDetailsModal").on("hidden.bs.modal", function() {
            $(this).remove();
        });
    },
    
    getFilteredCases() {
        return this.casesData.filter(c => {
            if (this.currentFilters.riskLevel !== 'all' && c.riskLevel !== this.currentFilters.riskLevel) return false;
            if (this.currentFilters.triggerType !== 'all' && c.triggerType !== this.currentFilters.triggerType) return false;
            if (this.currentFilters.status !== 'all' && c.status !== this.currentFilters.status) return false;
            return true;
        });
    },
    
    setupEventListeners() {
        const self = this;
        
        $("#filterRiskLevel, #filterTriggerType, #filterStatus").on("change", function() {
            self.currentFilters.riskLevel = $("#filterRiskLevel").val();
            self.currentFilters.triggerType = $("#filterTriggerType").val();
            self.currentFilters.status = $("#filterStatus").val();
            self.renderTable();
        });
        
        $("#refreshCasesBtn").on("click", () => this.fetchCasesData());
        
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
        
        // Clear Filters button (from patterns page navigation)
        $("#clearFiltersBtn").on("click", () => {
            this.currentFilters.customer = null;
            this.currentFilters.pattern = null;
            Utils.showToast("Filters cleared", "success");
            this.loadDashboard();
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
    
    showExportModal(caseId, customerId) {
        // Get case data
        const caseData = this.casesData.find(c => c.caseId === caseId);
        
        // Create modal HTML
        const modalHtml = `
            <div class="modal fade" id="exportCaseModal" tabindex="-1" aria-labelledby="exportCaseModalLabel" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content" style="border-radius: 14px; border: none;">
                        <div class="modal-header" style="border-bottom: 1px solid #eceef2; padding: 20px 24px;">
                            <h5 class="modal-title" id="exportCaseModalLabel" style="font-weight: 700; color: #1c2430;">
                                <i class="fas fa-download" style="color: #22c55e; margin-right: 8px;"></i>
                                Export Case
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
                                <label for="exportFormat" class="form-label" style="font-weight: 600; font-size: 13px; color: #1c2430;">
                                    Export Format <span style="color: #e53935;">*</span>
                                </label>
                                <select class="form-select" id="exportFormat" style="border: 1px solid #d1d5db; border-radius: 8px; padding: 10px 14px;">
                                    <option value="">Select format...</option>
                                    <option value="pdf">PDF Report (Detailed)</option>
                                    <option value="excel">Excel Spreadsheet (.xlsx)</option>
                                    <option value="csv">CSV File (.csv)</option>
                                    <option value="json">JSON Data (.json)</option>
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label" style="font-weight: 600; font-size: 13px; color: #1c2430;">Include Sections</label>
                                <div style="border: 1px solid #d1d5db; border-radius: 8px; padding: 12px 14px;">
                                    <div class="form-check mb-2">
                                        <input class="form-check-input" type="checkbox" value="summary" id="includeSummary" checked>
                                        <label class="form-check-label" for="includeSummary" style="font-size: 13px;">
                                            Case Summary
                                        </label>
                                    </div>
                                    <div class="form-check mb-2">
                                        <input class="form-check-input" type="checkbox" value="transactions" id="includeTransactions" checked>
                                        <label class="form-check-label" for="includeTransactions" style="font-size: 13px;">
                                            Transaction History
                                        </label>
                                    </div>
                                    <div class="form-check mb-2">
                                        <input class="form-check-input" type="checkbox" value="risk" id="includeRisk" checked>
                                        <label class="form-check-label" for="includeRisk" style="font-size: 13px;">
                                            Risk Analysis
                                        </label>
                                    </div>
                                    <div class="form-check mb-2">
                                        <input class="form-check-input" type="checkbox" value="timeline" id="includeTimeline" checked>
                                        <label class="form-check-label" for="includeTimeline" style="font-size: 13px;">
                                            Activity Timeline
                                        </label>
                                    </div>
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" value="attachments" id="includeAttachments">
                                        <label class="form-check-label" for="includeAttachments" style="font-size: 13px;">
                                            Attachments & Documents
                                        </label>
                                    </div>
                                </div>
                            </div>
                            <div class="alert alert-success" style="background: #e4f7ee; border: 1px solid #a7f3d0; border-radius: 8px; padding: 12px; font-size: 13px; margin-bottom: 0;">
                                <i class="fas fa-info-circle" style="color: #1fb877; margin-right: 6px;"></i>
                                Export includes all case data, analysis, and selected sections.
                            </div>
                        </div>
                        <div class="modal-footer" style="border-top: 1px solid #eceef2; padding: 16px 24px; background: #f7f8fa;">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal" style="border-radius: 8px; padding: 8px 20px; font-size: 14px; font-weight: 600;">
                                Cancel
                            </button>
                            <button type="button" class="btn btn-success" id="confirmExportBtn" style="background: #22c55e; border: none; border-radius: 8px; padding: 8px 20px; font-size: 14px; font-weight: 600;">
                                <i class="fas fa-download"></i> Export Now
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Remove existing modal if any
        $('#exportCaseModal').remove();
        
        // Add modal to body
        $('body').append(modalHtml);
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('exportCaseModal'));
        modal.show();
        
        // Handle confirm button
        $('#confirmExportBtn').off('click').on('click', function() {
            const format = $('#exportFormat').val();
            
            if (!format) {
                showToast('error', 'Please select an export format');
                return;
            }
            
            // Get selected sections
            const sections = [];
            if ($('#includeSummary').is(':checked')) sections.push('summary');
            if ($('#includeTransactions').is(':checked')) sections.push('transactions');
            if ($('#includeRisk').is(':checked')) sections.push('risk');
            if ($('#includeTimeline').is(':checked')) sections.push('timeline');
            if ($('#includeAttachments').is(':checked')) sections.push('attachments');
            
            // Show loading state
            $(this).prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Exporting...');
            
            // Simulate export process
            setTimeout(() => {
                // Create export data
                const exportData = {
                    caseId: caseId,
                    customerId: customerId,
                    exportDate: new Date().toISOString(),
                    format: format,
                    sections: sections,
                    caseDetails: caseData
                };
                
                // Generate download based on format
                Cases.generateExport(exportData, format);
                
                // Close modal
                modal.hide();
                
                // Show success message
                const formatName = format.toUpperCase();
                showToast('success', `Case exported successfully as ${formatName}`);
            }, 1500);
        });
        
        // Clean up modal on hide
        $('#exportCaseModal').on('hidden.bs.modal', function() {
            $(this).remove();
        });
    },
    
    generateExport(data, format) {
        const filename = `case_${data.caseId.substring(0, 8)}_${Date.now()}`;
        
        switch(format) {
            case 'pdf':
                // Generate HTML-based PDF with print styling
                console.log('Generating PDF:', data);
                this.generateHTMLPDF(data, filename);
                break;
                
            case 'excel':
            case 'csv':
                // Generate CSV data
                const csvContent = this.generateCSVContent(data);
                const mimeType = format === 'excel' ? 'application/vnd.ms-excel' : 'text/csv';
                const ext = format === 'excel' ? '.xlsx' : '.csv';
                this.downloadFile(`${filename}${ext}`, mimeType, csvContent);
                break;
                
            case 'json':
                // Generate JSON
                const jsonContent = JSON.stringify(data, null, 2);
                this.downloadFile(`${filename}.json`, 'application/json', jsonContent);
                break;
        }
    },
    
    generateHTMLPDF(data, filename) {
        // Create a printable HTML window
        const printWindow = window.open('', '_blank');
        const htmlContent = `
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Case Report - ${data.caseId}</title>
    <style>
        @media print {
            body { margin: 0; }
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            padding: 40px;
            max-width: 800px;
            margin: 0 auto;
            color: #333;
        }
        .header {
            text-align: center;
            border-bottom: 3px solid #FF8D28;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        .header h1 {
            color: #FF8D28;
            margin: 0 0 10px 0;
            font-size: 28px;
        }
        .header p {
            color: #666;
            margin: 5px 0;
        }
        .section {
            margin: 30px 0;
            padding: 20px;
            background: #f9f9f9;
            border-radius: 8px;
            border-left: 4px solid #FF8D28;
        }
        .section h2 {
            color: #333;
            font-size: 18px;
            margin: 0 0 15px 0;
            border-bottom: 1px solid #ddd;
            padding-bottom: 10px;
        }
        .field {
            margin: 10px 0;
            display: flex;
            padding: 8px 0;
        }
        .field-label {
            font-weight: 600;
            color: #555;
            min-width: 150px;
        }
        .field-value {
            color: #333;
            flex: 1;
        }
        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge-high { background: #fef2f2; color: #dc2626; }
        .badge-medium { background: #fef3c7; color: #d97706; }
        .badge-low { background: #dcfce7; color: #16a34a; }
        .badge-urgent { background: #fff5f5; color: #dc2626; }
        .badge-open { background: #d4edda; color: #155724; }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #ddd;
            text-align: center;
            color: #999;
            font-size: 12px;
        }
        @media print {
            .no-print { display: none; }
        }
        .print-btn {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #FF8D28;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            box-shadow: 0 2px 8px rgba(255,141,40,0.3);
        }
        .print-btn:hover {
            background: #e67d1f;
        }
    </style>
</head>
<body>
    <button class="print-btn no-print" onclick="window.print()">
        🖨️ Print / Save as PDF
    </button>
    
    <div class="header">
        <h1>🛡️ KYRO Case Export Report</h1>
        <p><strong>Case ID:</strong> ${data.caseId}</p>
        <p><strong>Customer ID:</strong> ${data.customerId}</p>
        <p><strong>Export Date:</strong> ${new Date(data.exportDate).toLocaleString()}</p>
    </div>
    
    <div class="section">
        <h2>📋 Case Summary</h2>
        <div class="field">
            <div class="field-label">Status:</div>
            <div class="field-value"><span class="badge badge-open">${data.caseDetails.status}</span></div>
        </div>
        <div class="field">
            <div class="field-label">Risk Level:</div>
            <div class="field-value">
                <span class="badge badge-${data.caseDetails.riskLevel.toLowerCase()}">${data.caseDetails.riskLevel}</span>
            </div>
        </div>
        <div class="field">
            <div class="field-label">Priority:</div>
            <div class="field-value"><span class="badge badge-urgent">${data.caseDetails.priority}</span></div>
        </div>
        <div class="field">
            <div class="field-label">Trigger Type:</div>
            <div class="field-value">${data.caseDetails.triggerType}</div>
        </div>
        <div class="field">
            <div class="field-label">Created At:</div>
            <div class="field-value">${data.caseDetails.createdAt}</div>
        </div>
        <div class="field">
            <div class="field-label">Assigned To:</div>
            <div class="field-value">${data.caseDetails.assignedTo}</div>
        </div>
    </div>
    
    <div class="footer">
        <p>Generated by KYRO AML Risk Assessment System</p>
        <p>This report is confidential and intended for authorized personnel only.</p>
    </div>
</body>
</html>
        `;
        
        printWindow.document.write(htmlContent);
        printWindow.document.close();
        
        // Auto-focus print window
        setTimeout(() => {
            printWindow.focus();
        }, 250);
    },
    
    generateCSVContent(data) {
        // Generate CSV format
        const headers = ['Field', 'Value'];
        const rows = [
            ['Case ID', data.caseId],
            ['Customer ID', data.customerId],
            ['Status', data.caseDetails.status],
            ['Risk Level', data.caseDetails.riskLevel],
            ['Priority', data.caseDetails.priority],
            ['Trigger Type', data.caseDetails.triggerType],
            ['Created At', data.caseDetails.createdAt],
            ['Assigned To', data.caseDetails.assignedTo],
            ['Export Date', new Date(data.exportDate).toLocaleString()],
            ['Sections', data.sections.join('; ')]
        ];
        
        let csv = headers.join(',') + '\n';
        rows.forEach(row => {
            csv += row.map(cell => `"${cell}"`).join(',') + '\n';
        });
        
        return csv;
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
