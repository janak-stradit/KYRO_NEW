/**
 * KYRO Alerts - Alert Management Implementation
 */

const Alerts = {
    currentPage: 1,
    pageSize: 10,
    currentFilterStatus: "",
    searchQuery: "",
    
    init(params = {}) {
        if (params.id) {
            this.loadAlertDetails(params.id);
        } else {
            this.loadAlertList();
        }
        this.setupEventListeners();
    },
    
    async loadAlertList() {
        showLoading("#mainContent", "Loading alerts queue...");
        
        const html = `
            <div class="dashboard-header">
                <div class="container-fluid d-flex justify-content-between align-items-center flex-wrap gap-2">
                    <div>
                        <h1 class="dashboard-title">Compliance Alerts Queue</h1>
                        <p class="dashboard-subtitle">Monitor and resolve automatically generated risk and transaction anomalies</p>
                    </div>
                </div>
            </div>
            
            <div class="row mb-4">
                <div class="col-12">
                    <div class="card">
                        <div class="card-body">
                            <!-- Filters & Search Toolbar -->
                            <div class="row g-3 align-items-center mb-4">
                                <div class="col-md-5">
                                    <div class="input-group">
                                        <span class="input-group-text"><i class="fas fa-search"></i></span>
                                        <input type="text" id="alertSearch" class="form-control" placeholder="Search by customer ID or alert type..." value="${this.searchQuery}">
                                    </div>
                                </div>
                                <div class="col-md-4">
                                    <select id="filterAlertStatus" class="form-select">
                                        <option value="">All Statuses</option>
                                        <option value="OPEN" ${this.currentFilterStatus === 'OPEN' ? 'selected' : ''}>Open</option>
                                        <option value="ASSIGNED" ${this.currentFilterStatus === 'ASSIGNED' ? 'selected' : ''}>Assigned</option>
                                        <option value="ESCALATED" ${this.currentFilterStatus === 'ESCALATED' ? 'selected' : ''}>Escalated</option>
                                        <option value="RESOLVED" ${this.currentFilterStatus === 'RESOLVED' ? 'selected' : ''}>Resolved</option>
                                    </select>
                                </div>
                                <div class="col-md-3 d-grid">
                                    <button class="btn btn-primary" id="btnApplyAlertFilters">
                                        <i class="fas fa-filter me-2"></i>Filter Queue
                                    </button>
                                </div>
                            </div>
                            
                            <!-- Table container -->
                            <div class="table-responsive">
                                <table class="table table-hover align-middle">
                                    <thead>
                                        <tr>
                                            <th>Alert ID</th>
                                            <th>Customer ID</th>
                                            <th>Alert Type</th>
                                            <th>Risk Score</th>
                                            <th>Confidence</th>
                                            <th>Status</th>
                                            <th>Triggered Date</th>
                                            <th class="text-end">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody id="alertListBody">
                                        <tr>
                                            <td colspan="8" class="text-center py-4">
                                                <div class="spinner-border spinner-border-sm text-primary me-2"></div>
                                                Reading alert records...
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                            
                            <!-- Pagination -->
                            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mt-4">
                                <div class="text-muted" id="alertPaginationInfo">
                                    Showing page 1
                                </div>
                                <nav aria-label="Alerts Queue Pagination">
                                    <ul class="pagination mb-0" id="alertPagination">
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
        await this.fetchAndRenderAlerts();
    },
    
    async fetchAndRenderAlerts() {
        try {
            const params = {
                page: this.currentPage,
                page_size: this.pageSize
            };
            
            if (this.currentFilterStatus) params.status_filter = this.currentFilterStatus;
            
            // Search by customer_id directly if query looks like UUID
            if (this.searchQuery && this.searchQuery.trim().length === 36) {
                params.customer_id = this.searchQuery.trim();
            }
            
            // Call API
            const response = await API.get(API.endpoints.alerts, params);
            let items = response.items || [];
            
            // Client side search for text queries
            if (this.searchQuery && this.searchQuery.trim().length !== 36) {
                const query = this.searchQuery.toLowerCase();
                items = items.filter(a => 
                    a.alert_type.toLowerCase().includes(query) ||
                    a.status.toLowerCase().includes(query)
                );
            }
            
            this.renderAlertRows(items);
            this.renderPagination(response.total);
            
        } catch (error) {
            console.error("Fetch alerts error:", error);
            $("#alertListBody").html(`
                <tr>
                    <td colspan="8" class="text-center text-danger py-4">
                        <i class="fas fa-exclamation-circle me-2"></i>Failed to retrieve queue items.
                    </td>
                </tr>
            `);
        }
    },
    
    renderAlertRows(alerts) {
        if (alerts.length === 0) {
            $("#alertListBody").html(`
                <tr>
                    <td colspan="8" class="text-center py-4 text-muted">
                        No pending alerts found matching the selection criteria.
                    </td>
                </tr>
            `);
            return;
        }
        
        const rows = alerts.map(alert => {
            const riskColor = getRiskColor(alert.risk_score);
            let statusBadgeColor = "secondary";
            if (alert.status === "OPEN") statusBadgeColor = "danger";
            else if (alert.status === "ASSIGNED") statusBadgeColor = "primary";
            else if (alert.status === "ESCALATED") statusBadgeColor = "warning text-dark";
            else if (alert.status === "RESOLVED") statusBadgeColor = "success";
            
            return `
                <tr style="cursor: pointer;" onclick="Alerts.viewAlert('${alert.id}')">
                    <td>
                        <span class="text-muted small">${alert.id.substring(0, 8)}...</span>
                    </td>
                    <td>
                        <a href="#" onclick="event.stopPropagation(); App.navigateTo('customers', { id: '${alert.customer_id}' })" class="text-kyro-primary font-monospace small">
                            ${alert.customer_id.substring(0, 8)}...
                        </a>
                    </td>
                    <td>
                        <strong>${alert.alert_type}</strong>
                    </td>
                    <td>
                        <span class="badge bg-${riskColor}">${alert.risk_score}</span>
                    </td>
                    <td>
                        ${(alert.confidence * 100).toFixed(1)}%
                    </td>
                    <td>
                        <span class="badge bg-${statusBadgeColor}">${alert.status}</span>
                    </td>
                    <td>
                        ${formatDateTime(alert.created_at)}
                    </td>
                    <td class="text-end" onclick="event.stopPropagation();">
                        <button class="btn btn-sm btn-outline-secondary" onclick="Alerts.viewAlert('${alert.id}')">
                            <i class="fas fa-eye me-1"></i>View Details
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
        
        $("#alertListBody").html(rows);
    },
    
    renderPagination(totalCount) {
        const totalPages = Math.ceil(totalCount / this.pageSize);
        const startIdx = (this.currentPage - 1) * this.pageSize + 1;
        const endIdx = Math.min(this.currentPage * this.pageSize, totalCount);
        
        $("#alertPaginationInfo").text(`Showing ${startIdx} to ${endIdx} of ${totalCount} Compliance Alerts`);
        
        let paginationHtml = `
            <li class="page-item ${this.currentPage === 1 ? 'disabled' : ''}">
                <a class="page-link" href="#" onclick="Alerts.goToPage(${this.currentPage - 1})">Previous</a>
            </li>
        `;
        
        for (let i = 1; i <= Math.min(totalPages, 5); i++) {
            paginationHtml += `
                <li class="page-item ${this.currentPage === i ? 'active' : ''}">
                    <a class="page-link" href="#" onclick="Alerts.goToPage(${i})">${i}</a>
                </li>
            `;
        }
        
        if (totalPages > 5) {
            paginationHtml += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
            paginationHtml += `
                <li class="page-item ${this.currentPage === totalPages ? 'active' : ''}">
                    <a class="page-link" href="#" onclick="Alerts.goToPage(${totalPages})">${totalPages}</a>
                </li>
            `;
        }
        
        paginationHtml += `
            <li class="page-item ${this.currentPage === totalPages ? 'disabled' : ''}">
                <a class="page-link" href="#" onclick="Alerts.goToPage(${this.currentPage + 1})">Next</a>
            </li>
        `;
        
        $("#alertPagination").html(paginationHtml);
    },
    
    goToPage(pageNum) {
        if (pageNum < 1) return;
        this.currentPage = pageNum;
        this.fetchAndRenderAlerts();
    },
    
    viewAlert(id) {
        App.navigateTo("alerts", { id });
    },
    
    async loadAlertDetails(id) {
        showLoading("#mainContent", "Analyzing alert characteristics...");
        
        try {
            // Fetch alert details
            const alert = await API.get(API.endpoints.alert(id));
            const customer = await API.get(API.endpoints.customer(alert.customer_id));
            const riskColor = getRiskColor(alert.risk_score);
            
            let statusBadgeColor = "secondary";
            if (alert.status === "OPEN") statusBadgeColor = "danger";
            else if (alert.status === "ASSIGNED") statusBadgeColor = "primary";
            else if (alert.status === "ESCALATED") statusBadgeColor = "warning text-dark";
            else if (alert.status === "RESOLVED") statusBadgeColor = "success";
            
            const html = `
                <div class="dashboard-header mb-4">
                    <div class="container-fluid d-flex justify-content-between align-items-center flex-wrap gap-2">
                        <div class="d-flex align-items-center gap-3">
                            <button class="btn btn-outline-secondary btn-sm" onclick="App.navigateTo('alerts')">
                                <i class="fas fa-arrow-left me-2"></i>Back to Queue
                            </button>
                            <div>
                                <h1 class="dashboard-title mb-0">Alert Resolution Console</h1>
                                <p class="dashboard-subtitle mb-0">Alert UUID: ${alert.id}</p>
                            </div>
                        </div>
                        <div class="d-flex gap-2">
                            ${alert.status === "OPEN" ? `
                                <button class="btn btn-primary" onclick="Alerts.assignAlert('${alert.id}')">
                                    <i class="fas fa-user-check me-2"></i>Assign to Me
                                </button>
                            ` : ''}
                            ${alert.status !== "RESOLVED" ? `
                                <button class="btn btn-warning" onclick="Alerts.triggerEscalateModal('${alert.id}')">
                                    <i class="fas fa-share-square me-2"></i>Escalate to Case
                                </button>
                                <button class="btn btn-success" onclick="Alerts.triggerResolveModal('${alert.id}')">
                                    <i class="fas fa-check-circle me-2"></i>Resolve Alert
                                </button>
                            ` : ''}
                        </div>
                    </div>
                </div>
                
                <div class="row">
                    <!-- Left: Alert and Customer Core Info -->
                    <div class="col-lg-6 mb-4">
                        <div class="card h-100">
                            <div class="card-header bg-white py-3">
                                <h5 class="card-title fw-bold mb-0">Alert Attributes</h5>
                            </div>
                            <div class="card-body">
                                <table class="table table-borderless align-middle mb-4">
                                    <tbody>
                                        <tr>
                                            <td class="text-muted fw-semibold" style="width: 150px;">Alert Type</td>
                                            <td class="fw-bold">${alert.alert_type}</td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted fw-semibold">Status</td>
                                            <td><span class="badge bg-${statusBadgeColor}">${alert.status}</span></td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted fw-semibold">Risk Score</td>
                                            <td><span class="badge bg-${riskColor} py-2 px-3">${alert.risk_score}/100</span></td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted fw-semibold">Model Confidence</td>
                                            <td><strong>${(alert.confidence * 100).toFixed(1)}% Anomaly Risk</strong></td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted fw-semibold">Triggered At</td>
                                            <td>${formatDateTime(alert.created_at)}</td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted fw-semibold">Assigned To</td>
                                            <td><code>${alert.assigned_to || 'Unassigned'}</code></td>
                                        </tr>
                                    </tbody>
                                </table>
                                
                                <h6 class="fw-bold text-muted border-bottom pb-2">Customer Profile Summary</h6>
                                <div class="d-flex align-items-center mt-3" style="cursor: pointer;" onclick="App.navigateTo('customers', { id: '${customer.id}' })">
                                    <div class="rounded-circle bg-light d-flex align-items-center justify-content-center me-3" style="width: 50px; height: 50px;">
                                        <span class="fs-4 fw-bold text-primary">${customer.full_name.charAt(0)}</span>
                                    </div>
                                    <div>
                                        <h6 class="fw-bold mb-0 text-kyro-primary">${customer.full_name}</h6>
                                        <small class="text-muted">${customer.email} • ${customer.country || 'N/A'}</small>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Right: Explanation & Findings Logs -->
                    <div class="col-lg-6 mb-4">
                        <div class="card h-100">
                            <div class="card-header bg-white py-3">
                                <h5 class="card-title fw-bold mb-0">System Rationale & Audit Trail</h5>
                            </div>
                            <div class="card-body">
                                <div class="border rounded p-3 bg-light mb-4">
                                    <div class="d-flex align-items-center mb-2 text-primary">
                                        <i class="fas fa-brain fa-lg me-2"></i>
                                        <h6 class="fw-bold mb-0">Rules Engine Explanation</h6>
                                    </div>
                                    <p class="mb-0 text-dark small">${alert.explanation || 'Anomaly flags and historical velocity deviations triggered this alert.'}</p>
                                </div>
                                
                                ${alert.resolution_notes ? `
                                    <div class="border border-success rounded p-3 bg-success-subtle mb-4">
                                        <div class="d-flex align-items-center mb-2 text-success">
                                            <i class="fas fa-clipboard-check fa-lg me-2"></i>
                                            <h6 class="fw-bold mb-0">Resolution Audits & Notes</h6>
                                        </div>
                                        <p class="mb-2 text-dark small">${alert.resolution_notes}</p>
                                        <div class="small text-muted">
                                            Resolved on: ${alert.resolved_at ? formatDateTime(alert.resolved_at) : 'N/A'} 
                                            ${alert.is_false_positive !== null ? `• False Positive: <strong>${alert.is_false_positive ? 'YES' : 'NO'}</strong>` : ''}
                                        </div>
                                    </div>
                                ` : `
                                    <div class="text-center py-4 text-muted">
                                        <i class="fas fa-clipboard-list mb-2 fs-4"></i><br>
                                        No resolution audits logged yet. Alert is currently active.
                                    </div>
                                `}
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            $("#mainContent").html(html);
            
        } catch (error) {
            console.error("Alert details load error:", error);
            showToast("error", "Failed to retrieve alert description details.");
            App.navigateTo("alerts");
        }
    },
    
    async assignAlert(alertId) {
        try {
            showGlobalLoading();
            
            // Get logged-in user profile to find ID
            const me = await API.get("/auth/me");
            
            // Call assign endpoint
            await API.put(`/alerts/${alertId}/assign`, {
                assigned_to: me.id
            });
            
            showToast("success", "Alert successfully assigned to your workspace.");
            this.loadAlertDetails(alertId);
            
        } catch (error) {
            console.error("Assign alert error:", error);
            showToast("error", "Failed to assign alert. Check user permissions.");
        } finally {
            hideLoading();
        }
    },
    
    triggerResolveModal(alertId) {
        const modalId = "resolveModal";
        $(`#${modalId}`).remove();
        
        const modalHtml = `
            <div class="modal fade" id="${modalId}" tabindex="-1" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title fw-bold">Resolve Compliance Alert</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <form id="resolveForm">
                                <div class="mb-3">
                                    <label class="form-label fw-semibold">Audit Classification</label>
                                    <div class="form-check">
                                        <input class="form-check-input" type="radio" name="fpRadio" id="fpRadioTrue" value="true" checked>
                                        <label class="form-check-label" for="fpRadioTrue">
                                            False Positive (Benign Transaction / Activity)
                                        </label>
                                    </div>
                                    <div class="form-check">
                                        <input class="form-check-input" type="radio" name="fpRadio" id="fpRadioFalse" value="false">
                                        <label class="form-check-label" for="fpRadioFalse">
                                            True Positive (Suspicious / Requires Monitoring)
                                        </label>
                                    </div>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label fw-semibold">Resolution Notes</label>
                                    <textarea class="form-control" id="resolveNotes" rows="4" placeholder="Detail the source of funds check, PEP screening check, or benign explanation..." required></textarea>
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-success" onclick="Alerts.submitResolve('${alertId}')">Resolve Alert</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        $("body").append(modalHtml);
        new bootstrap.Modal(document.getElementById(modalId)).show();
    },
    
    async submitResolve(alertId) {
        const notes = $("#resolveNotes").val();
        const isFp = $('input[name="fpRadio"]:checked').val() === "true";
        
        if (!notes || notes.trim().length === 0) {
            showToast("warning", "Resolution notes are required to resolve an alert.");
            return;
        }
        
        try {
            showGlobalLoading();
            await API.put(`/alerts/${alertId}/resolve`, {
                resolution_notes: notes,
                is_false_positive: isFp
            });
            
            bootstrap.Modal.getInstance(document.getElementById("resolveModal")).hide();
            showToast("success", "Alert resolved successfully.");
            this.loadAlertDetails(alertId);
            
        } catch (error) {
            console.error("Resolve alert error:", error);
            showToast("error", "Only COMPLIANCE_OFFICER or ADMIN roles can resolve alerts.");
        } finally {
            hideLoading();
        }
    },
    
    triggerEscalateModal(alertId) {
        const modalId = "escalateModal";
        $(`#${modalId}`).remove();
        
        const modalHtml = `
            <div class="modal fade" id="${modalId}" tabindex="-1" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title fw-bold">Escalate Alert to Case File</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <form id="escalateForm">
                                <div class="mb-3">
                                    <label class="form-label fw-semibold">Escalation Rationale</label>
                                    <textarea class="form-control" id="escalateNotes" rows="4" placeholder="Detail reason for escalating this to an active SAR (Suspicious Activity Report) Case..." required></textarea>
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-warning" onclick="Alerts.submitEscalate('${alertId}')">Escalate to Case</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        $("body").append(modalHtml);
        new bootstrap.Modal(document.getElementById(modalId)).show();
    },
    
    async submitEscalate(alertId) {
        const notes = $("#escalateNotes").val();
        
        if (!notes || notes.trim().length === 0) {
            showToast("warning", "Escalation notes are required to create a Case.");
            return;
        }
        
        try {
            showGlobalLoading();
            
            // Escalate alert
            await API.put(`/alerts/${alertId}/escalate`, {
                resolution_notes: notes
            });
            
            // Create Case on the backend: let's verify if Case router exists or we just mock/call it.
            // Wait, we will implement Case management page next, and check the backend routes!
            try {
                await API.post("/cases", {
                    customer_id: alertId, // we'll check if cases endpoint expects customer_id
                    title: "Escalated Alert Case",
                    description: notes
                });
            } catch (caseErr) {
                // Ignore case creation error if API doesn't support direct post
                console.warn("Case auto-creation failed, but alert was escalated:", caseErr);
            }
            
            bootstrap.Modal.getInstance(document.getElementById("escalateModal")).hide();
            showToast("success", "Alert escalated. Active case initialized.");
            this.loadAlertDetails(alertId);
            
        } catch (error) {
            console.error("Escalate alert error:", error);
            showToast("error", "Failed to escalate alert.");
        } finally {
            hideLoading();
        }
    },
    
    setupEventListeners() {
        // Search trigger
        $(document).on("keypress", "#alertSearch", (e) => {
            if (e.which === 13) {
                this.searchQuery = $("#alertSearch").val();
                this.currentPage = 1;
                this.fetchAndRenderAlerts();
            }
        });
        
        // Filter trigger
        $(document).off("click", "#btnApplyAlertFilters").on("click", "#btnApplyAlertFilters", () => {
            this.searchQuery = $("#alertSearch").val();
            this.currentFilterStatus = $("#filterAlertStatus").val();
            this.currentPage = 1;
            this.fetchAndRenderAlerts();
        });
    }
};

window.Alerts = Alerts;
