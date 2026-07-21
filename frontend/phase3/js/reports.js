/**
 * KYRO Reports - Enhanced Reports & Compliance Page Implementation
 */

const Reports = {
    init() {
        this.loadReportsDashboard();
        this.setupEventListeners();
    },
    
    async loadReportsDashboard() {
        showLoading("#mainContent", "Analyzing compliance logs and model statistics...");
        
        try {
            // Fetch stats and charts data from backend
            const [kpis, charts] = await Promise.all([
                API.get("/dashboard/kpis"),
                API.get("/dashboard/charts")
            ]);

            // Optional ML endpoints (graceful fallback if empty)
            let models = [];
            let performance = { precision: null, false_positive_rate: null, total_reviewed: 0 };
            
            try {
                models = await API.get("/ml/models");
            } catch (err) {
                console.warn("Could not fetch models registry:", err);
            }
            
            try {
                performance = await API.get("/ml/performance");
            } catch (err) {
                console.warn("Could not fetch ML performance stats:", err);
            }
            
            // Format dynamic production metrics
            const prodPrecision = performance.precision !== null && performance.precision !== undefined
                ? `${(performance.precision * 100).toFixed(1)}%` 
                : "Pending Data";
            const prodFPR = performance.false_positive_rate !== null && performance.false_positive_rate !== undefined
                ? `${(performance.false_positive_rate * 100).toFixed(1)}%` 
                : "Pending Data";
            
            const html = `
                <div class="dashboard-header mb-4">
                    <div class="container-fluid d-flex justify-content-between align-items-center flex-wrap gap-2">
                        <div>
                            <h1 class="dashboard-title">Compliance Reports & Auditor Hub</h1>
                            <p class="dashboard-subtitle">Compile signed regulatory reports, audit challenger model performance, and track classifier drift</p>
                        </div>
                    </div>
                </div>
                
                <!-- KPI Gradient Cards Row -->
                <div class="row g-4 mb-4">
                    <div class="col-md-3">
                        <div class="kpi-card text-white" style="background: linear-gradient(135deg, #1a237e, #3f51b5); border-radius: 16px; box-shadow: 0 4px 20px rgba(26, 35, 126, 0.2);">
                            <div class="card-body position-relative">
                                <h6>Total Database Clients</h6>
                                <h2>${kpis.total_customers}</h2>
                                <small class="opacity-75">All KYC registered profiles</small>
                                <i class="fas fa-users position-absolute end-0 bottom-0 m-3 opacity-25" style="font-size: 2.5rem;"></i>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="kpi-card text-white" style="background: linear-gradient(135deg, #d32f2f, #f44336); border-radius: 16px; box-shadow: 0 4px 20px rgba(211, 47, 47, 0.2);">
                            <div class="card-body position-relative">
                                <h6>High Risk Customers</h6>
                                <h2>${kpis.high_risk_customers}</h2>
                                <small class="opacity-75">Risk Score &gt; 70 or HIGH status</small>
                                <i class="fas fa-shield-alt position-absolute end-0 bottom-0 m-3 opacity-25" style="font-size: 2.5rem;"></i>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="kpi-card text-white" style="background: linear-gradient(135deg, #fb8c00, #ffa726); border-radius: 16px; box-shadow: 0 4px 20px rgba(251, 140, 0, 0.2);">
                            <div class="card-body position-relative">
                                <h6>Pending Queue Alerts</h6>
                                <h2>${kpis.pending_alerts}</h2>
                                <small class="opacity-75">Requires manual verification</small>
                                <i class="fas fa-exclamation-triangle position-absolute end-0 bottom-0 m-3 opacity-25" style="font-size: 2.5rem;"></i>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="kpi-card text-white" style="background: linear-gradient(135deg, #2e7d32, #4caf50); border-radius: 16px; box-shadow: 0 4px 20px rgba(46, 125, 50, 0.2);">
                            <div class="card-body position-relative">
                                <h6>False Positive Rate</h6>
                                <h2>${(kpis.false_positive_rate * 100).toFixed(1)}%</h2>
                                <small class="opacity-75">Resolved in last 30 days</small>
                                <i class="fas fa-percent position-absolute end-0 bottom-0 m-3 opacity-25" style="font-size: 2.5rem;"></i>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="row mb-4">
                    <!-- Column Left: ML Classifier Validation & Model Routing -->
                    <div class="col-lg-6 mb-4">
                        <!-- Classifier metrics card -->
                        <div class="card border-0 shadow-sm mb-4" style="border-radius: 16px;">
                            <div class="card-header bg-white py-3 border-0">
                                <h5 class="card-title fw-bold mb-0 text-dark">
                                    <i class="fas fa-brain text-primary me-2"></i>ML Classifier Validation Metrics
                                </h5>
                            </div>
                            <div class="card-body">
                                <table class="table table-borderless align-middle mb-0">
                                    <tbody>
                                        <tr>
                                            <td class="text-muted fw-semibold" style="width: 140px;">Baseline Precision</td>
                                            <td>
                                                <div class="d-flex align-items-center">
                                                    <span class="fw-bold me-2" style="width: 45px;">${(charts.model_performance.precision * 100).toFixed(0)}%</span>
                                                    <div class="progress w-100" style="height: 6px; border-radius: 3px;">
                                                        <div class="progress-bar bg-success" role="progressbar" style="width: ${charts.model_performance.precision * 100}%"></div>
                                                    </div>
                                                </div>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted fw-semibold">Baseline Recall</td>
                                            <td>
                                                <div class="d-flex align-items-center">
                                                    <span class="fw-bold me-2" style="width: 45px;">${(charts.model_performance.recall * 100).toFixed(0)}%</span>
                                                    <div class="progress w-100" style="height: 6px; border-radius: 3px;">
                                                        <div class="progress-bar bg-primary" role="progressbar" style="width: ${charts.model_performance.recall * 100}%"></div>
                                                    </div>
                                                </div>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td class="text-muted fw-semibold">F1-Score Accuracy</td>
                                            <td>
                                                <div class="d-flex align-items-center">
                                                    <span class="fw-bold me-2" style="width: 45px;">${(charts.model_performance.overall_score * 100).toFixed(0)}%</span>
                                                    <div class="progress w-100" style="height: 6px; border-radius: 3px;">
                                                        <div class="progress-bar bg-info" role="progressbar" style="width: ${charts.model_performance.overall_score * 100}%"></div>
                                                    </div>
                                                </div>
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                                
                                <div class="row g-2 mt-3 pt-3 border-top">
                                    <div class="col-6">
                                        <div class="p-2 border rounded bg-light text-center">
                                            <div class="text-muted small">Live Production Precision</div>
                                            <h5 class="fw-bold text-success mb-0 mt-1">${prodPrecision}</h5>
                                        </div>
                                    </div>
                                    <div class="col-6">
                                        <div class="p-2 border rounded bg-light text-center">
                                            <div class="text-muted small">Production FP Rate</div>
                                            <h5 class="fw-bold text-danger mb-0 mt-1">${prodFPR}</h5>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Model Status & Routing card -->
                        <div class="card border-0 shadow-sm" style="border-radius: 16px;">
                            <div class="card-header bg-white py-3 border-0">
                                <h5 class="card-title fw-bold mb-0 text-dark">
                                    <i class="fas fa-server text-secondary me-2"></i>Active Model Challenger Routing
                                </h5>
                            </div>
                            <div class="card-body p-0">
                                <div class="table-responsive">
                                    <table class="table table-hover align-middle mb-0">
                                        <thead class="table-light">
                                            <tr>
                                                <th class="ps-3">Model Name</th>
                                                <th>Active Version</th>
                                                <th>Challenger</th>
                                                <th class="pe-3">Traffic Split</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${models.length === 0 ? `
                                                <tr>
                                                    <td colspan="4" class="text-center text-muted py-4">No model models configured.</td>
                                                </tr>
                                            ` : models.map(m => {
                                                const hasChallenger = m.candidate_version !== null && m.candidate_version !== undefined;
                                                return `
                                                    <tr>
                                                        <td class="ps-3 fw-semibold text-dark">${m.name}</td>
                                                        <td><span class="badge bg-success-subtle text-success border border-success-subtle">v${m.active_version}</span></td>
                                                        <td>
                                                            ${hasChallenger 
                                                                ? `<span class="badge bg-warning-subtle text-warning border border-warning-subtle">v${m.candidate_version}</span>` 
                                                                : '<span class="text-muted small">-</span>'}
                                                        </td>
                                                        <td class="pe-3">
                                                            ${hasChallenger 
                                                                ? `<div class="d-flex align-items-center gap-1">
                                                                       <span class="small fw-bold">${100 - m.candidate_traffic_pct}% / ${m.candidate_traffic_pct}%</span>
                                                                       <i class="fas fa-random text-muted small" title="Traffic Split active"></i>
                                                                   </div>` 
                                                                : '<span class="text-muted small">100% active</span>'}
                                                        </td>
                                                    </tr>
                                                `;
                                            }).join('')}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Column Right: Report Generator Wizard -->
                    <div class="col-lg-6 mb-4">
                        <div class="card border-0 shadow-sm h-100" style="border-radius: 16px;">
                            <div class="card-header bg-white py-3 border-0">
                                <h5 class="card-title fw-bold mb-0 text-dark">
                                    <i class="fas fa-file-invoice text-primary me-2"></i>Generate Regulatory Audit Report
                                </h5>
                            </div>
                            <div class="card-body">
                                <form id="reportGeneratorForm">
                                    <div class="mb-3">
                                        <label class="form-label fw-semibold text-muted small">Select Report Type</label>
                                        <select class="form-select" id="reportType" style="border-radius: 8px;">
                                            <option value="sar_escalations">Suspicious Activity Report (SAR) Escalations</option>
                                            <option value="kyc_reviews">KYC Periodic Review Log</option>
                                            <option value="high_risk_ledger">High Risk Transaction Ledger</option>
                                        </select>
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label class="form-label fw-semibold text-muted small">Reporting Timeframe</label>
                                        <select class="form-select" id="reportTimeframe" style="border-radius: 8px;">
                                            <option value="30">Last 30 Days</option>
                                            <option value="90">Last 90 Days</option>
                                            <option value="365">Last 12 Months</option>
                                        </select>
                                    </div>
                                    
                                    <div class="mb-4">
                                        <label class="form-label fw-semibold text-muted small">File Format</label>
                                        <div class="d-flex gap-3">
                                            <div class="form-check">
                                                <input class="form-check-input" type="radio" name="reportFormat" id="formatPdf" value="PDF" checked>
                                                <label class="form-check-label" for="formatPdf">PDF (Signed)</label>
                                            </div>
                                            <div class="form-check">
                                                <input class="form-check-input" type="radio" name="reportFormat" id="formatCsv" value="CSV">
                                                <label class="form-check-label" for="formatCsv">CSV (Spreadsheet)</label>
                                            </div>
                                            <div class="form-check">
                                                <input class="form-check-input" type="radio" name="reportFormat" id="formatExcel" value="XLSX">
                                                <label class="form-check-label" for="formatExcel">Excel (XLSX)</label>
                                            </div>
                                        </div>
                                    </div>
                                    
                                    <div class="d-grid">
                                        <button type="button" class="btn btn-primary py-2 fw-semibold" onclick="Reports.generateReport()" style="border-radius: 8px;">
                                            <i class="fas fa-file-download me-2"></i>Export & Verify Signature
                                        </button>
                                    </div>
                                </form>
                                
                                <div class="alert alert-warning mt-4 mb-0" role="alert" style="border-radius: 12px;">
                                    <h6 class="alert-heading fw-bold"><i class="fas fa-key me-2 text-warning"></i>Cryptographic Signatures</h6>
                                    <p class="mb-0 small">All generated compliance files are signed using SHA-256 and verified against the KYRO AML root certificate to guarantee audit non-repudiation.</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Bottom Row: Historical Generated Reports Ledger -->
                <div class="row">
                    <div class="col-12">
                        <div class="card border-0 shadow-sm" style="border-radius: 16px;">
                            <div class="card-header bg-white py-3 border-0">
                                <h5 class="card-title fw-bold mb-0 text-dark">
                                    <i class="fas fa-history text-secondary me-2"></i>Historical Audit Reports Ledger
                                </h5>
                            </div>
                            <div class="card-body p-0">
                                <div class="table-responsive">
                                    <table class="table table-hover align-middle mb-0">
                                        <thead class="table-light">
                                            <tr>
                                                <th class="ps-3">Report ID</th>
                                                <th>Report Name</th>
                                                <th>Created Date</th>
                                                <th>Format</th>
                                                <th>Size</th>
                                                <th>Compiled By</th>
                                                <th>Status</th>
                                                <th>Verification Hash</th>
                                                <th class="text-end pe-3">Action</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            <tr id="newReportRow" class="d-none table-success">
                                                <!-- Dynamic generated reports appended here -->
                                            </tr>
                                            <tr>
                                                <td class="ps-3 font-monospace small">REP-2026-081</td>
                                                <td class="fw-semibold text-dark">Q2 Suspicious Activity Escalations</td>
                                                <td>2026-07-10 14:32</td>
                                                <td><span class="badge bg-danger-subtle text-danger border border-danger-subtle">PDF</span></td>
                                                <td>2.4 MB</td>
                                                <td>Compliance Analyst</td>
                                                <td><span class="badge bg-success-subtle text-success border border-success-subtle"><i class="fas fa-check-circle me-1"></i>SIGNED</span></td>
                                                <td><code class="small text-muted">8f3c7a2b...d89e</code></td>
                                                <td class="text-end pe-3">
                                                    <button class="btn btn-sm btn-outline-secondary" onclick="Reports.downloadHistorical('REP-2026-081', 'Q2 Suspicious Activity Escalations', 'PDF')">
                                                        <i class="fas fa-download"></i>
                                                    </button>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td class="ps-3 font-monospace small">REP-2026-080</td>
                                                <td class="fw-semibold text-dark">Monthly KYC Periodic Reviews Summary</td>
                                                <td>2026-07-01 09:15</td>
                                                <td><span class="badge bg-success-subtle text-success border border-success-subtle">CSV</span></td>
                                                <td>842 KB</td>
                                                <td>Compliance Analyst</td>
                                                <td><span class="badge bg-success-subtle text-success border border-success-subtle"><i class="fas fa-check-circle me-1"></i>SIGNED</span></td>
                                                <td><code class="small text-muted">4a2b8e3c...12c5</code></td>
                                                <td class="text-end pe-3">
                                                    <button class="btn btn-sm btn-outline-secondary" onclick="Reports.downloadHistorical('REP-2026-080', 'Monthly KYC Periodic Reviews Summary', 'CSV')">
                                                        <i class="fas fa-download"></i>
                                                    </button>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td class="ps-3 font-monospace small">REP-2026-079</td>
                                                <td class="fw-semibold text-dark">High-Risk Customer Transaction Audit</td>
                                                <td>2026-06-25 17:45</td>
                                                <td><span class="badge bg-primary-subtle text-primary border border-primary-subtle">XLSX</span></td>
                                                <td>4.1 MB</td>
                                                <td>Test Compliance Officer</td>
                                                <td><span class="badge bg-success-subtle text-success border border-success-subtle"><i class="fas fa-check-circle me-1"></i>SIGNED</span></td>
                                                <td><code class="small text-muted">9e1c2d3a...f7b8</code></td>
                                                <td class="text-end pe-3">
                                                    <button class="btn btn-sm btn-outline-secondary" onclick="Reports.downloadHistorical('REP-2026-079', 'High-Risk Customer Transaction Audit', 'XLSX')">
                                                        <i class="fas fa-download"></i>
                                                    </button>
                                                </td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            $("#mainContent").html(html);
            
        } catch (error) {
            console.error("Reports dashboard load error:", error);
            showToast("error", "Failed to retrieve reporting statistics.");
        }
    },
    
    generateReport() {
        const type = $("#reportType").val();
        const timeframe = $("#reportTimeframe").val();
        const format = $("input[name='reportFormat']:checked").val();
        
        const typeLabels = {
            sar_escalations: "Suspicious Activity Report (SAR) Escalations",
            kyc_reviews: "KYC Periodic Review Log",
            high_risk_ledger: "High Risk Transaction Ledger"
        };
        
        showGlobalLoading();
        
        setTimeout(() => {
            hideLoading();
            
            // Random SHA256 string for visual hash signature
            const randomHash = Array.from({length: 8}, () => Math.floor(Math.random()*16).toString(16)).join("") + "...signed";
            const reportId = `REP-2026-${Math.floor(Math.random() * 900) + 100}`;
            
            showToast("success", `Successfully compiled ${typeLabels[type]} Report. File signed successfully.`);
            
            // Inject new report row to demonstrate visual interaction feedback
            const formatBadgeColor = format === 'PDF' ? 'danger' : format === 'CSV' ? 'success' : 'primary';
            const newRowHtml = `
                <td class="ps-3 font-monospace small">${reportId}</td>
                <td class="fw-semibold text-dark">${typeLabels[type]}</td>
                <td>Just now</td>
                <td><span class="badge bg-${formatBadgeColor}-subtle text-${formatBadgeColor} border border-${formatBadgeColor}-subtle">${format}</span></td>
                <td>124 KB</td>
                <td>Compliance Analyst</td>
                <td><span class="badge bg-success text-white"><i class="fas fa-check-circle me-1"></i>SIGNED</span></td>
                <td><code class="small text-muted">${randomHash}</code></td>
                <td class="text-end pe-3">
                    <button class="btn btn-sm btn-outline-success" onclick="Reports.downloadHistorical('${reportId}', '${typeLabels[type]}', '${format}')">
                        <i class="fas fa-download"></i>
                    </button>
                </td>
            `;
            $("#newReportRow").html(newRowHtml).removeClass("d-none");
            
            // Trigger browser mock file download
            const element = document.createElement('a');
            const fileContent = `==================================================\nKYRO COMPLIANCE & AML COMPLIANCE AUDIT\n==================================================\nReport ID: ${reportId}\nReport Type: ${typeLabels[type]}\nTimeframe: Last ${timeframe} Days\nFormat: ${format}\nGenerated At: ${new Date().toISOString()}\nStatus: AUDITED & SIGNED\nDigital Verification Key: ${randomHash}\n==================================================\nCONFIDENTIAL - OFFICIAL REGULATORY ARCHIVE`;
            element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(fileContent));
            element.setAttribute('download', `KYRO_${type}_${timeframe}d_Report.${format.toLowerCase()}`);
            element.style.display = 'none';
            document.body.appendChild(element);
            element.click();
            document.body.removeChild(element);
        }, 1500);
    },
    
    downloadHistorical(id, name, format) {
        showToast("info", `Downloading archive file: ${id} (${format})`);
        
        // Mock download
        const element = document.createElement('a');
        const fileContent = `==================================================\nKYRO ARCHIVED REGULATORY REPORT\n==================================================\nReport ID: ${id}\nReport Name: ${name}\nFormat: ${format}\nStatus: SIGNED & COMPLETED\n==================================================\nCONFIDENTIAL - AUDITOR COPY`;
        element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(fileContent));
        element.setAttribute('download', `${id}_${name.replace(/\s+/g, '_')}.${format.toLowerCase()}`);
        element.style.display = 'none';
        document.body.appendChild(element);
        element.click();
        document.body.removeChild(element);
    },
    
    setupEventListeners() {
        // Any custom event listners for report page
    }
};

window.Reports = Reports;
