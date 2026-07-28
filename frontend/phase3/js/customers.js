/**
 * KYRO Customers - Customer Management Page Implementation
 */

const Customers = {
    currentPage: 1,
    pageSize: 10,
    currentFilterKYC: "",
    currentFilterRisk: "",
    searchQuery: "",
    
    init(params = {}) {
        if (params.id) {
            this.loadCustomerDetails(params.id);
        } else {
            this.loadCustomerList();
        }
        this.setupEventListeners();
    },
    
    async loadCustomerList() {
        showLoading("#mainContent", "Loading customers...");
        
        const html = `
            <div class="dashboard-header">
                <div class="container-fluid d-flex justify-content-between align-items-center flex-wrap gap-2">
                    <div>
                        <h1 class="dashboard-title">Customer Risk Directory</h1>
                        <p class="dashboard-subtitle">Manage customer risk profiles and KYC compliance reviews</p>
                    </div>
                </div>
            </div>
            
            <div class="row mb-4">
                <div class="col-12">
                    <div class="card">
                        <div class="card-body">
                            <!-- Filters & Search Toolbar -->
                            <div class="row g-3 align-items-center mb-4">
                                <div class="col-md-4">
                                    <div class="input-group">
                                        <span class="input-group-text"><i class="fas fa-search"></i></span>
                                        <input type="text" id="customerSearch" class="form-control" placeholder="Search by name, email..." value="${this.searchQuery}">
                                    </div>
                                </div>
                                <div class="col-md-3">
                                    <select id="filterRisk" class="form-select">
                                        <option value="">All Risk Levels</option>
                                        <option value="LOW" ${this.currentFilterRisk === 'LOW' ? 'selected' : ''}>Low Risk</option>
                                        <option value="MEDIUM" ${this.currentFilterRisk === 'MEDIUM' ? 'selected' : ''}>Medium Risk</option>
                                        <option value="HIGH" ${this.currentFilterRisk === 'HIGH' ? 'selected' : ''}>High Risk</option>
                                    </select>
                                </div>
                                <div class="col-md-3">
                                    <select id="filterKYC" class="form-select">
                                        <option value="">All KYC Statuses</option>
                                        <option value="VERIFIED" ${this.currentFilterKYC === 'VERIFIED' ? 'selected' : ''}>Verified</option>
                                        <option value="PENDING" ${this.currentFilterKYC === 'PENDING' ? 'selected' : ''}>Pending</option>
                                        <option value="UNDER_REVIEW" ${this.currentFilterKYC === 'UNDER_REVIEW' ? 'selected' : ''}>Under Review</option>
                                        <option value="REJECTED" ${this.currentFilterKYC === 'REJECTED' ? 'selected' : ''}>Rejected</option>
                                    </select>
                                </div>
                                <div class="col-md-2 d-grid">
                                    <button class="btn btn-primary" id="btnApplyFilters">
                                        <i class="fas fa-filter me-2"></i>Filter
                                    </button>
                                </div>
                            </div>
                            
                            <!-- Table container -->
                            <div class="table-responsive">
                                <table class="table table-hover align-middle" id="customersTable">
                                    <thead>
                                        <tr>
                                            <th>Name</th>
                                            <th>Contact / Details</th>
                                            <th>Type</th>
                                            <th>KYC Status</th>
                                            <th>Risk Level</th>
                                            <th>Risk Score</th>
                                            <th>Created Date</th>
                                            <th class="text-end">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody id="customerListBody">
                                        <tr>
                                            <td colspan="8" class="text-center py-4">
                                                <div class="spinner-border spinner-border-sm text-primary me-2"></div>
                                                Loading customer database...
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                            
                            <!-- Pagination -->
                            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mt-4">
                                <div class="text-muted" id="customerPaginationInfo">
                                    Showing page 1
                                </div>
                                <nav aria-label="Customer Pagination">
                                    <ul class="pagination mb-0" id="customerPagination">
                                        <li class="page-item disabled"><a class="page-link" href="#">Previous</a></li>
                                        <li class="page-item disabled"><a class="page-link" href="#">Next</a></li>
                                    </ul>
                                </nav>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        $("#mainContent").html(html);
        await this.fetchAndRenderCustomers();
    },
    
    async fetchAndRenderCustomers() {
        try {
            const params = {
                page: this.currentPage,
                page_size: this.pageSize
            };
            
            if (this.currentFilterKYC) params.kyc_status = this.currentFilterKYC;
            if (this.currentFilterRisk) params.risk_level = this.currentFilterRisk;
            
            // Call API
            const response = await API.get(API.endpoints.customers, params);
            let items = response.items || [];
            
            // Client-side search filtering (since backend /customers currently doesn't implement query filter directly in list route)
            if (this.searchQuery) {
                const query = this.searchQuery.toLowerCase();
                items = items.filter(c => 
                    c.full_name.toLowerCase().includes(query) || 
                    c.email.toLowerCase().includes(query) ||
                    (c.phone && c.phone.includes(query))
                );
            }
            
            this.renderCustomerRows(items);
            this.renderPagination(response.total);
            
        } catch (error) {
            console.error("Fetch customers error:", error);
            $("#customerListBody").html(`
                <tr>
                    <td colspan="8" class="text-center text-danger py-4">
                        <i class="fas fa-exclamation-circle me-2"></i>Failed to retrieve customer profiles.
                    </td>
                </tr>
            `);
        }
    },
    
    renderCustomerRows(customers) {
        if (customers.length === 0) {
            $("#customerListBody").html(`
                <tr>
                    <td colspan="8" class="text-center py-4 text-muted">
                        No customers match the active filters.
                    </td>
                </tr>
            `);
            return;
        }
        
        const rows = customers.map(customer => {
            const riskColor = getRiskColor(customer.risk_score);
            let kycBadgeColor = "secondary";
            if (customer.kyc_status === "VERIFIED") kycBadgeColor = "success";
            else if (customer.kyc_status === "UNDER_REVIEW") kycBadgeColor = "warning";
            else if (customer.kyc_status === "REJECTED") kycBadgeColor = "danger";
            
            return `
                <tr style="cursor: pointer;" onclick="Customers.viewCustomer('${customer.id}')">
                    <td>
                        <div class="fw-semibold text-kyro-primary">${customer.full_name}</div>
                        <small class="text-muted">${customer.country || 'N/A'}</small>
                    </td>
                    <td>
                        <div>${customer.email}</div>
                        <small class="text-muted">${customer.phone || 'No phone'}</small>
                    </td>
                    <td>
                        <span class="badge bg-light text-dark border">${customer.customer_type || 'INDIVIDUAL'}</span>
                    </td>
                    <td>
                        <span class="badge bg-${kycBadgeColor}">${customer.kyc_status}</span>
                    </td>
                    <td>
                        <span class="badge bg-${riskColor}">${customer.risk_level}</span>
                    </td>
                    <td>
                        <div class="d-flex align-items-center">
                            <span class="fw-bold me-2">${customer.risk_score}</span>
                            <div class="progress" style="width: 60px; height: 6px;">
                                <div class="progress-bar bg-${riskColor}" role="progressbar" style="width: ${customer.risk_score}%"></div>
                            </div>
                        </div>
                    </td>
                    <td>
                        ${formatDate(customer.created_at)}
                    </td>
                    <td class="text-end" onclick="event.stopPropagation();">
                        <div class="dropdown">
                            <button class="btn btn-sm btn-outline-secondary" type="button" data-bs-toggle="dropdown">
                                <i class="fas fa-ellipsis-v"></i>
                            </button>
                            <ul class="dropdown-menu dropdown-menu-end">
                                <li><a class="dropdown-item" href="#" onclick="Customers.viewCustomer('${customer.id}')"><i class="fas fa-eye me-2 text-primary"></i>Profile Details</a></li>
                                <li><a class="dropdown-item" href="#" onclick="Customers.triggerKYCModal('${customer.id}', '${customer.full_name}')"><i class="fas fa-check-double me-2 text-warning"></i>KYC Review</a></li>
                                <li><hr class="dropdown-divider"></li>
                                <li><a class="dropdown-item text-danger" href="#" onclick="Customers.deleteCustomer('${customer.id}', '${customer.full_name}')"><i class="fas fa-trash-alt me-2"></i>Blacklist / Delete</a></li>
                            </ul>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
        
        $("#customerListBody").html(rows);
    },
    
    renderPagination(totalCount) {
        const totalPages = Math.ceil(totalCount / this.pageSize);
        const startIdx = (this.currentPage - 1) * this.pageSize + 1;
        const endIdx = Math.min(this.currentPage * this.pageSize, totalCount);
        
        $("#customerPaginationInfo").text(`Showing ${startIdx} to ${endIdx} of ${totalCount} Customer Profiles`);
        
        let paginationHtml = `
            <li class="page-item ${this.currentPage === 1 ? 'disabled' : ''}">
                <a class="page-link" href="#" onclick="Customers.goToPage(${this.currentPage - 1})">Previous</a>
            </li>
        `;
        
        for (let i = 1; i <= Math.min(totalPages, 5); i++) {
            paginationHtml += `
                <li class="page-item ${this.currentPage === i ? 'active' : ''}">
                    <a class="page-link" href="#" onclick="Customers.goToPage(${i})">${i}</a>
                </li>
            `;
        }
        
        if (totalPages > 5) {
            paginationHtml += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
            paginationHtml += `
                <li class="page-item ${this.currentPage === totalPages ? 'active' : ''}">
                    <a class="page-link" href="#" onclick="Customers.goToPage(${totalPages})">${totalPages}</a>
                </li>
            `;
        }
        
        paginationHtml += `
            <li class="page-item ${this.currentPage === totalPages ? 'disabled' : ''}">
                <a class="page-link" href="#" onclick="Customers.goToPage(${this.currentPage + 1})">Next</a>
            </li>
        `;
        
        $("#customerPagination").html(paginationHtml);
    },
    
    goToPage(pageNum) {
        if (pageNum < 1) return;
        this.currentPage = pageNum;
        this.fetchAndRenderCustomers();
    },
    
    viewCustomer(id) {
        App.navigateTo("customers", { id });
    },
    
    async loadCustomerDetails(id) {
        showLoading("#mainContent", "Fetching customer compliance profile...");
        
        try {
            // Fetch multiple related items in parallel
            const [customer, riskHistory, kycReviews, screening, transactions] = await Promise.all([
                API.get(API.endpoints.customer(id)),
                API.get(API.endpoints.customer_risk_history(id)),
                API.get(`/customers/${id}/kyc-reviews`),
                API.get(`/customers/${id}/screening`),
                API.get("/transactions", { customer_id: id })
            ]);
            
            const riskColor = getRiskColor(customer.risk_score);
            let kycBadgeColor = "secondary";
            if (customer.kyc_status === "VERIFIED") kycBadgeColor = "success";
            else if (customer.kyc_status === "UNDER_REVIEW") kycBadgeColor = "warning";
            else if (customer.kyc_status === "REJECTED") kycBadgeColor = "danger";
            
            const txnList = transactions.items || [];
            
            const html = `
                <div class="dashboard-header mb-4">
                    <div class="container-fluid d-flex justify-content-between align-items-center flex-wrap gap-2">
                        <div class="d-flex align-items-center gap-3">
                            <button class="btn btn-outline-secondary btn-sm" onclick="App.navigateTo('customers')">
                                <i class="fas fa-arrow-left me-2"></i>Back to List
                            </button>
                            <div>
                                <h1 class="dashboard-title mb-0">${customer.full_name}</h1>
                                <p class="dashboard-subtitle mb-0">Customer ID: ${customer.id}</p>
                            </div>
                        </div>
                        <div class="d-flex gap-2">
                            <button class="btn btn-outline-warning" onclick="Customers.triggerKYCModal('${customer.id}', '${customer.full_name}')">
                                <i class="fas fa-check-double me-2"></i>Perform KYC Review
                            </button>
                            <button class="btn btn-danger" onclick="Customers.deleteCustomer('${customer.id}', '${customer.full_name}')">
                                <i class="fas fa-ban me-2"></i>Block Customer
                            </button>
                        </div>
                    </div>
                </div>
                
                <div class="row">
                    <!-- Sidebar Info Profile -->
                    <div class="col-lg-4 mb-4">
                        <div class="card mb-4 h-100">
                            <div class="card-body text-center py-5">
                                <div class="rounded-circle bg-light d-flex align-items-center justify-content-center mx-auto mb-4" style="width: 100px; height: 100px; border: 3px solid var(--kyro-primary);">
                                    <span class="fs-1 fw-bold text-kyro-primary">${customer.full_name.charAt(0)}</span>
                                </div>
                                <h4 class="fw-bold mb-2">${customer.full_name}</h4>
                                <span class="badge bg-light text-dark border mb-3">${customer.customer_type || 'INDIVIDUAL'}</span>
                                
                                <div class="d-flex justify-content-center gap-2 mb-4">
                                    <span class="badge bg-${kycBadgeColor} py-2 px-3">KYC: ${customer.kyc_status}</span>
                                    <span class="badge bg-${riskColor} py-2 px-3">RISK: ${customer.risk_level} (${customer.risk_score})</span>
                                </div>
                                
                                <hr>
                                
                                <div class="text-start mt-4 px-3">
                                    <div class="mb-3">
                                        <label class="text-muted small fw-semibold">Email Address</label>
                                        <div class="fw-medium">${customer.email}</div>
                                    </div>
                                    <div class="mb-3">
                                        <label class="text-muted small fw-semibold">Phone Number</label>
                                        <div class="fw-medium">${customer.phone || 'Not provided'}</div>
                                    </div>
                                    <div class="mb-3">
                                        <label class="text-muted small fw-semibold">Country of Incorporation</label>
                                        <div class="fw-medium">${customer.country || 'Not provided'}</div>
                                    </div>
                                    <div class="mb-3">
                                        <label class="text-muted small fw-semibold">Date of Birth</label>
                                        <div class="fw-medium">${customer.date_of_birth ? formatDate(customer.date_of_birth) : 'Not provided'}</div>
                                    </div>
                                    <div class="mb-3">
                                        <label class="text-muted small fw-semibold">Created Timestamp</label>
                                        <div class="fw-medium">${formatDateTime(customer.created_at)}</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Tabs Content Area -->
                    <div class="col-lg-8 mb-4">
                        <div class="card h-100">
                            <div class="card-header bg-white border-bottom py-3">
                                <ul class="nav nav-tabs card-header-tabs" id="profileTabs" role="tablist">
                                    <li class="nav-item">
                                        <button class="nav-link active fw-bold text-kyro-primary" id="watchlist-tab" data-bs-toggle="tab" data-bs-target="#watchlist" type="button" role="tab">Compliance Flags</button>
                                    </li>
                                    <li class="nav-item">
                                        <button class="nav-link fw-bold" id="risk-tab" data-bs-toggle="tab" data-bs-target="#risk" type="button" role="tab">Risk Assessment</button>
                                    </li>
                                    <li class="nav-item">
                                        <button class="nav-link fw-bold" id="kyc-tab" data-bs-toggle="tab" data-bs-target="#kyc" type="button" role="tab">KYC History (${kycReviews.length})</button>
                                    </li>
                                    <li class="nav-item">
                                        <button class="nav-link fw-bold" id="txns-tab" data-bs-toggle="tab" data-bs-target="#txns" type="button" role="tab">Transactions (${txnList.length})</button>
                                    </li>
                                </ul>
                            </div>
                            
                            <div class="card-body">
                                <div class="tab-content" id="profileTabsContent">
                                    
                                    <!-- TAB 1: Compliance Flags -->
                                    <div class="tab-pane fade show active" id="watchlist" role="tabpanel">
                                        <h5 class="card-title fw-bold mb-4">Sanctions, PEP, and Screening Info</h5>
                                        <div class="row g-3 mb-4">
                                            <div class="col-md-4">
                                                <div class="border rounded p-3 text-center ${customer.pep_flag ? 'bg-danger-subtle border-danger text-danger' : 'bg-success-subtle border-success text-success'}">
                                                    <i class="fas fa-user-shield fa-2x mb-2"></i>
                                                    <div class="fw-bold">PEP Status</div>
                                                    <div>${customer.pep_flag ? "Politically Exposed" : "Clean Profile"}</div>
                                                </div>
                                            </div>
                                            <div class="col-md-4">
                                                <div class="border rounded p-3 text-center ${customer.sanctions_flag ? 'bg-danger-subtle border-danger text-danger' : 'bg-success-subtle border-success text-success'}">
                                                    <i class="fas fa-globe-americas fa-2x mb-2"></i>
                                                    <div class="fw-bold">Sanctions Watchlist</div>
                                                    <div>${customer.sanctions_flag ? "MATCH DETECTED" : "Clear / Free"}</div>
                                                </div>
                                            </div>
                                            <div class="col-md-4">
                                                <div class="border rounded p-3 text-center ${customer.adverse_media_flag ? 'bg-warning-subtle border-warning text-warning' : 'bg-success-subtle border-success text-success'}">
                                                    <i class="fas fa-newspaper fa-2x mb-2"></i>
                                                    <div class="fw-bold">Adverse Media</div>
                                                    <div>${customer.adverse_media_flag ? "FLAGGED NEWS" : "Clean Records"}</div>
                                                </div>
                                            </div>
                                        </div>
                                        
                                        <h6 class="fw-bold border-bottom pb-2">PEPs & Watchlist Screening Logs</h6>
                                        <div class="table-responsive">
                                            <table class="table table-sm align-middle">
                                                <thead>
                                                    <tr>
                                                        <th>Type</th>
                                                        <th>Status</th>
                                                        <th>Screened At</th>
                                                        <th>Details</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    ${screening.length === 0 ? `
                                                        <tr><td colspan="4" class="text-center text-muted py-3">No screening logs found for this customer.</td></tr>
                                                    ` : screening.map(log => `
                                                        <tr>
                                                            <td><span class="badge bg-secondary">${log.screening_type || 'PEP & Sanctions'}</span></td>
                                                            <td>
                                                                <span class="badge bg-${log.match_status === 'MATCH' ? 'danger' : 'success'}">
                                                                    ${log.match_status}
                                                                </span>
                                                            </td>
                                                            <td>${formatDateTime(log.screened_at)}</td>
                                                            <td><small>${JSON.stringify(log.match_details || {})}</small></td>
                                                        </tr>
                                                    `).join('')}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                    
                                    <!-- TAB 2: Risk Assessment -->
                                    <div class="tab-pane fade" id="risk" role="tabpanel">
                                        <h5 class="card-title fw-bold mb-4">ML & Rules Based Risk Profile</h5>
                                        <div class="d-flex align-items-center mb-4 border rounded p-3 bg-light">
                                            <div class="me-4 text-center">
                                                <div class="fs-1 fw-bold text-${riskColor}">${customer.risk_score}</div>
                                                <small class="text-muted">Overall Risk</small>
                                            </div>
                                            <div>
                                                <h6 class="fw-bold text-${riskColor}">${customer.risk_level} RISK PROFILE</h6>
                                                <p class="mb-0 text-muted">This profile is recalculated dynamically based on cash-flow velocities, transaction frequency, and identity screening results.</p>
                                            </div>
                                        </div>
                                        
                                        <h6 class="fw-bold border-bottom pb-2">Identified Risk Factors</h6>
                                        <div class="table-responsive">
                                            <table class="table table-sm align-middle">
                                                <thead>
                                                    <tr>
                                                        <th>Category</th>
                                                        <th>Factor / Trigger</th>
                                                        <th>Assessed At</th>
                                                        <th>Assessed By</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    ${riskHistory.length === 0 ? `
                                                        <tr><td colspan="4" class="text-center text-muted py-3">No risk history assessments available.</td></tr>
                                                    ` : riskHistory.map(rf => `
                                                        <tr>
                                                            <td><span class="badge bg-warning text-dark">${rf.risk_category || 'General'}</span></td>
                                                            <td>${rf.risk_factor || 'N/A'}</td>
                                                            <td>${formatDateTime(rf.assessed_at)}</td>
                                                            <td><small class="text-muted">${rf.assessed_by || 'system'}</small></td>
                                                        </tr>
                                                    `).join('')}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                    
                                    <!-- TAB 3: KYC Reviews -->
                                    <div class="tab-pane fade" id="kyc" role="tabpanel">
                                        <div class="d-flex justify-content-between align-items-center mb-3">
                                            <h5 class="card-title fw-bold mb-0">KYC Review & Compliance Audits</h5>
                                        </div>
                                        
                                        <div class="timeline">
                                            ${kycReviews.length === 0 ? `
                                                <p class="text-muted text-center py-4">No KYC review records exist yet.</p>
                                            ` : kycReviews.map(review => `
                                                <div class="border rounded p-3 mb-3 bg-light">
                                                    <div class="d-flex justify-content-between mb-2">
                                                        <span class="badge bg-kyro-primary">${review.review_type}</span>
                                                        <span class="badge bg-success">${review.review_status}</span>
                                                    </div>
                                                    <div class="mb-2"><strong>Findings:</strong> ${review.findings || 'No notes provided.'}</div>
                                                    <div class="row g-2 small text-muted">
                                                        <div class="col-sm-6">Reviewed On: ${formatDateTime(review.created_at)}</div>
                                                        <div class="col-sm-6">Risk Level After: <strong>${review.risk_level_after || 'No change'}</strong></div>
                                                    </div>
                                                </div>
                                            `).join('')}
                                        </div>
                                    </div>
                                    
                                    <!-- TAB 4: Transactions -->
                                    <div class="tab-pane fade" id="txns" role="tabpanel">
                                        <h5 class="card-title fw-bold mb-4">Transaction History</h5>
                                        <div class="table-responsive">
                                            <table class="table table-sm table-striped">
                                                <thead>
                                                    <tr>
                                                        <th>Date</th>
                                                        <th>Type</th>
                                                        <th>Direction</th>
                                                        <th>Amount</th>
                                                        <th>Status</th>
                                                        <th>Risk Score</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    ${txnList.length === 0 ? `
                                                        <tr><td colspan="6" class="text-center text-muted py-3">No transactions found for this customer.</td></tr>
                                                    ` : txnList.map(txn => {
                                                        const txnRiskColor = getRiskColor(txn.risk_score);
                                                        return `
                                                            <tr style="cursor: pointer;" onclick="App.navigateTo('transactions', { id: '${txn.id}' })">
                                                                <td>${formatDateTime(txn.transaction_date)}</td>
                                                                <td><span class="badge bg-light text-dark border">${txn.transaction_type}</span></td>
                                                                <td>
                                                                    <span class="badge bg-${txn.direction === 'CREDIT' ? 'success-subtle text-success' : 'warning-subtle text-warning'}">
                                                                        ${txn.direction}
                                                                    </span>
                                                                </td>
                                                                <td class="fw-bold">${formatCurrency(txn.amount, txn.currency)}</td>
                                                                <td><span class="badge bg-light text-dark">${txn.status}</span></td>
                                                                <td><span class="badge bg-${txnRiskColor}">${txn.risk_score}</span></td>
                                                            </tr>
                                                        `;
                                                    }).join('')}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                    
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            $("#mainContent").html(html);
            
            // Re-bind click listeners on tabs
            $('#profileTabs button').on('click', function (e) {
                e.preventDefault();
                $(this).tab('show');
            });
            
        } catch (error) {
            console.error("Customer details error:", error);
            showToast("error", "Failed to retrieve customer full profile.");
            App.navigateTo("customers");
        }
    },
    
    setupEventListeners() {
        // Search trigger
        $(document).on("keypress", "#customerSearch", (e) => {
            if (e.which === 13) {
                this.searchQuery = $("#customerSearch").val();
                this.currentPage = 1;
                this.fetchAndRenderCustomers();
            }
        });
        
        // Apply filters
        $(document).off("click", "#btnApplyFilters").on("click", "#btnApplyFilters", () => {
            this.searchQuery = $("#customerSearch").val();
            this.currentFilterKYC = $("#filterKYC").val();
            this.currentFilterRisk = $("#filterRisk").val();
            this.currentPage = 1;
            this.fetchAndRenderCustomers();
        });
    },
    
    triggerKYCModal(customerId, customerName) {
        // Create Modal dynamically
        const modalId = "kycModal";
        $(`#${modalId}`).remove(); // remove old instances
        
        const modalHtml = `
            <div class="modal fade" id="${modalId}" tabindex="-1" aria-labelledby="${modalId}Label" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title fw-bold" id="${modalId}Label">KYC Compliance Review</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <p class="text-muted">Performing ad-hoc review for <strong>${customerName}</strong></p>
                            <form id="kycReviewForm">
                                <div class="mb-3">
                                    <label class="form-label fw-semibold">Review Type</label>
                                    <select class="form-select" id="kycReviewType">
                                        <option value="ADHOC">Ad-hoc Review</option>
                                        <option value="PERIODIC">Periodic Audit</option>
                                        <option value="TRIGGERED">Triggered Risk Alert</option>
                                    </select>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label fw-semibold">Post-Review Risk Recommendation</label>
                                    <select class="form-select" id="kycRiskLevelAfter">
                                        <option value="LOW">LOW Risk</option>
                                        <option value="MEDIUM">MEDIUM Risk</option>
                                        <option value="HIGH">HIGH Risk</option>
                                    </select>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label fw-semibold">Audit Findings & Notes</label>
                                    <textarea class="form-control" id="kycFindings" rows="4" placeholder="Enter findings, checked database reports, watchlist screen results..." required></textarea>
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Close</button>
                            <button type="button" class="btn btn-primary" onclick="Customers.submitKYCReview('${customerId}')">Submit Review</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        $("body").append(modalHtml);
        const modal = new bootstrap.Modal(document.getElementById(modalId));
        modal.show();
    },
    
    async submitKYCReview(customerId) {
        const reviewType = $("#kycReviewType").val();
        const findings = $("#kycFindings").val();
        const riskLevelAfter = $("#kycRiskLevelAfter").val();
        
        if (!findings || findings.trim().length === 0) {
            showToast("warning", "Findings notes are required to resolve a KYC audit.");
            return;
        }
        
        try {
            showGlobalLoading();
            
            // Post review to backend API
            await API.post(`/customers/${customerId}/kyc-reviews`, {
                review_type: reviewType,
                findings: findings
            });
            
            // Also update customer details risk level and status as appropriate
            await API.put(`/customers/${customerId}`, {
                kyc_status: "VERIFIED",
                risk_level: riskLevelAfter
            });
            
            bootstrap.Modal.getInstance(document.getElementById("kycModal")).hide();
            showToast("success", "KYC Review logged successfully. Customer verified.");
            
            // Refresh customer view
            if (App.getCurrentPage() === "customers") {
                Customers.loadCustomerDetails(customerId);
            }
            
        } catch (error) {
            console.error("Submit KYC review error:", error);
            showToast("error", "Failed to log KYC review.");
        } finally {
            hideLoading();
        }
    },
    
    async deleteCustomer(id, name) {
        if (confirm(`Are you sure you want to BLACKLIST and reject the customer ${name}?`)) {
            try {
                showGlobalLoading();
                await API.delete(`/customers/${id}`);
                showToast("success", `${name} has been rejected / deleted.`);
                App.navigateTo("customers");
            } catch (error) {
                console.error("Delete customer error:", error);
                showToast("error", "Failed to blacklist customer.");
            } finally {
                hideLoading();
            }
        }
    }
};

window.Customers = Customers;
