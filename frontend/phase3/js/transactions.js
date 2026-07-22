/**
 * KYRO Patterns & Transaction Monitor
 * Primary view: 6 Behavioral Pattern cards (API-backed)
 * Secondary: Transaction Ledger with filters
 */

const PATTERN_COLOR_MAP = {
    danger:    { bg: '#fef2f2', border: '#fecaca', badge: '#ef4444', icon: '#dc2626' },
    warning:   { bg: '#fffbeb', border: '#fde68a', badge: '#f59e0b', icon: '#d97706' },
    info:      { bg: '#eff6ff', border: '#bfdbfe', badge: '#3b82f6', icon: '#2563eb' },
    primary:   { bg: '#eef2ff', border: '#c7d2fe', badge: '#6366f1', icon: '#4f46e5' },
    secondary: { bg: '#f8fafc', border: '#e2e8f0', badge: '#64748b', icon: '#475569' },
    success:   { bg: '#f0fdf4', border: '#bbf7d0', badge: '#22c55e', icon: '#16a34a' },
};

const SEV_BADGE = {
    HIGH:   'bg-danger',
    MEDIUM: 'bg-warning text-dark',
    LOW:    'bg-secondary',
};

const Transactions = {
    currentPage: 1,
    pageSize: 10,
    currentFilterType: '',
    searchQuery: '',
    patternData: null,

    init(params = {}) {
        if (params.id) {
            this.loadTransactionDetails(params.id);
        } else {
            this.loadPatternsDashboard();
        }
        this.setupEventListeners();
    },

    /* ─────────────────────────────────────────────
       PATTERNS DASHBOARD
    ───────────────────────────────────────────── */
    async loadPatternsDashboard() {
        $('#mainContent').html(`
            <div class="dashboard-header">
                <div class="container-fluid d-flex justify-content-between align-items-center flex-wrap gap-2">
                    <div>
                        <h1 class="dashboard-title">Behavioral Patterns</h1>
                        <p class="dashboard-subtitle">6 canonical AML pattern detectors — live counts from the rules engine (last 30 days)</p>
                    </div>
                    <div class="d-flex gap-2">
                        <span class="badge bg-light text-dark border px-3 py-2 fw-semibold" id="patternWindowBadge">
                            <i class="fas fa-calendar-alt me-1"></i> Loading…
                        </span>
                    </div>
                </div>
            </div>

            <!-- Summary Stats Row -->
            <div class="row g-3 mb-4" id="patternSummaryRow">
                <div class="col-md-4"><div class="card border-0 shadow-sm p-3 text-center"><div class="spinner-border spinner-border-sm text-primary"></div></div></div>
                <div class="col-md-4"><div class="card border-0 shadow-sm p-3 text-center"><div class="spinner-border spinner-border-sm text-primary"></div></div></div>
                <div class="col-md-4"><div class="card border-0 shadow-sm p-3 text-center"><div class="spinner-border spinner-border-sm text-primary"></div></div></div>
            </div>

            <!-- Pattern Cards Grid -->
            <div class="row g-3 mb-5" id="patternCardsGrid">
                ${[1,2,3,4,5,6].map(() => `
                    <div class="col-lg-4 col-md-6">
                        <div class="card border-0 shadow-sm p-4" style="min-height:180px;">
                            <div class="d-flex align-items-center gap-2 mb-2">
                                <div class="rounded-circle bg-light" style="width:40px;height:40px;"></div>
                                <div class="placeholder-glow w-50"><span class="placeholder col-8"></span></div>
                            </div>
                            <div class="placeholder-glow"><span class="placeholder col-12"></span><span class="placeholder col-10 mt-1"></span></div>
                        </div>
                    </div>
                `).join('')}
            </div>

            <!-- Transaction Ledger -->
            <div class="row mb-4">
                <div class="col-12">
                    <div class="card border-0 shadow-sm">
                        <div class="card-header bg-white py-3 d-flex justify-content-between align-items-center">
                            <h5 class="card-title fw-bold mb-0"><i class="fas fa-list-ul me-2 text-muted"></i>Transaction Ledger</h5>
                            <span class="badge bg-light text-dark border" id="txnCountBadge">Loading…</span>
                        </div>
                        <div class="card-body">
                            <div class="row g-3 align-items-center mb-4">
                                <div class="col-md-5">
                                    <div class="input-group">
                                        <span class="input-group-text"><i class="fas fa-search"></i></span>
                                        <input type="text" id="txnSearch" class="form-control" placeholder="Search by customer ID or amount…">
                                    </div>
                                </div>
                                <div class="col-md-4">
                                    <select id="filterTxnType" class="form-select">
                                        <option value="">All Transaction Types</option>
                                        <option value="DEPOSIT">Deposit</option>
                                        <option value="WITHDRAWAL">Withdrawal</option>
                                        <option value="TRANSFER">Transfer</option>
                                        <option value="FX">Foreign Exchange (FX)</option>
                                        <option value="TRADE">Trade / Equity</option>
                                    </select>
                                </div>
                                <div class="col-md-3 d-grid">
                                    <button class="btn btn-primary" id="btnApplyTxnFilters">
                                        <i class="fas fa-filter me-2"></i>Filter Ledger
                                    </button>
                                </div>
                            </div>
                            <div class="table-responsive">
                                <table class="table table-hover align-middle">
                                    <thead>
                                        <tr>
                                            <th>Transaction ID</th>
                                            <th>Customer ID</th>
                                            <th>Date &amp; Time</th>
                                            <th>Type</th>
                                            <th>Amount</th>
                                            <th>Risk Score</th>
                                            <th>Source System</th>
                                            <th class="text-end">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody id="txnListBody">
                                        <tr><td colspan="8" class="text-center py-4">
                                            <div class="spinner-border spinner-border-sm text-primary me-2"></div>
                                            Reading transaction ledger…
                                        </td></tr>
                                    </tbody>
                                </table>
                            </div>
                            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mt-4">
                                <div class="text-muted" id="txnPaginationInfo">Showing page 1</div>
                                <nav><ul class="pagination mb-0" id="txnPagination">
                                    <li class="page-item disabled"><a class="page-link" href="#">Previous</a></li>
                                    <li class="page-item disabled"><a class="page-link" href="#">Next</a></li>
                                </ul></nav>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `);

        // Load both in parallel
        await Promise.all([
            this.fetchAndRenderPatterns(),
            this.fetchAndRenderTransactions(),
        ]);
    },

    async fetchAndRenderPatterns() {
        try {
            const data = await API.get('/dashboard/patterns');
            this.patternData = data;
            this.renderPatternSummary(data);
            this.renderPatternCards(data.patterns);
            $('#patternWindowBadge').html(`<i class="fas fa-calendar-alt me-1"></i> Last ${data.window_days} days`);
        } catch (err) {
            console.error('Pattern fetch error:', err);
            $('#patternCardsGrid').html(`<div class="col-12"><div class="alert alert-warning">Could not load pattern data. Is the API running?</div></div>`);
        }
    },

    renderPatternSummary(data) {
        const hitRate = data.total_transactions > 0
            ? ((data.total_pattern_hits / data.total_transactions) * 100).toFixed(1)
            : '0.0';
        $('#patternSummaryRow').html(`
            <div class="col-md-4">
                <div class="card border-0 shadow-sm p-3 text-center" style="border-left: 4px solid #6366f1 !important;">
                    <div class="text-muted small mb-1"><i class="fas fa-exchange-alt me-1"></i>Transactions (30d)</div>
                    <div class="fw-bold fs-3 text-dark">${data.total_transactions.toLocaleString()}</div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card border-0 shadow-sm p-3 text-center" style="border-left: 4px solid #ef4444 !important;">
                    <div class="text-muted small mb-1"><i class="fas fa-exclamation-triangle me-1"></i>Total Pattern Hits</div>
                    <div class="fw-bold fs-3 text-danger">${data.total_pattern_hits.toLocaleString()}</div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card border-0 shadow-sm p-3 text-center" style="border-left: 4px solid #f59e0b !important;">
                    <div class="text-muted small mb-1"><i class="fas fa-percent me-1"></i>Flag Rate</div>
                    <div class="fw-bold fs-3" style="color:#d97706;">${hitRate}%</div>
                </div>
            </div>
        `);
    },

    renderPatternCards(patterns) {
        const cards = patterns.map(p => {
            const c = PATTERN_COLOR_MAP[p.color] || PATTERN_COLOR_MAP.secondary;
            const sevClass = SEV_BADGE[p.severity] || 'bg-secondary';
            const ruleChips = p.rule_ids.length > 0
                ? p.rule_ids.map(r => `<span class="badge bg-light text-dark border me-1" style="font-size:10px;font-family:monospace;">${r}</span>`).join('')
                : `<span class="text-muted" style="font-size:11px;">Derived metric</span>`;

            return `
                <div class="col-lg-4 col-md-6">
                    <div class="card border-0 shadow-sm pattern-card h-100" style="border-top: 3px solid ${c.badge} !important; background:${c.bg};">
                        <div class="card-body p-4">
                            <div class="d-flex align-items-start justify-content-between mb-3">
                                <div class="d-flex align-items-center gap-3">
                                    <div class="rounded-3 d-flex align-items-center justify-content-center"
                                         style="width:44px;height:44px;background:${c.badge}20;border:1px solid ${c.border};">
                                        <i class="fas ${p.icon}" style="color:${c.icon};font-size:18px;"></i>
                                    </div>
                                    <div>
                                        <div class="fw-bold text-dark" style="font-size:14px;line-height:1.2;">${p.label}</div>
                                        <div class="text-muted" style="font-size:10px;font-family:monospace;letter-spacing:0.5px;">${p.id}</div>
                                    </div>
                                </div>
                                <span class="badge ${sevClass} px-2 py-1" style="font-size:10px;">${p.severity}</span>
                            </div>

                            <p class="text-muted mb-3" style="font-size:12.5px;line-height:1.5;">${p.description}</p>

                            <div class="d-flex align-items-center justify-content-between mb-3">
                                <div>
                                    <div class="text-muted" style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;">Hits (30d)</div>
                                    <div class="fw-bold" style="font-size:26px;color:${c.icon};line-height:1.1;">${p.hit_count.toLocaleString()}</div>
                                </div>
                                <div class="text-end">
                                    <div class="text-muted" style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;">Legacy ID</div>
                                    <div class="fw-semibold text-dark" style="font-size:11px;font-family:monospace;">${p.legacy_name}</div>
                                </div>
                            </div>

                            <div class="border-top pt-2 mt-1">
                                <div class="text-muted mb-1" style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px;">Mapped Rules</div>
                                <div>${ruleChips}</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
        $('#patternCardsGrid').html(cards);
    },

    /* ─────────────────────────────────────────────
       TRANSACTION LEDGER
    ───────────────────────────────────────────── */
    async fetchAndRenderTransactions() {
        try {
            const params = { page: this.currentPage, page_size: this.pageSize };
            if (this.currentFilterType) params.transaction_type = this.currentFilterType;
            if (this.searchQuery && this.searchQuery.trim().length === 36) params.customer_id = this.searchQuery.trim();

            const response = await API.get(API.endpoints.transactions, params);
            let items = response.items || [];

            if (this.searchQuery && this.searchQuery.trim().length !== 36) {
                const q = this.searchQuery.toLowerCase();
                items = items.filter(t =>
                    t.currency.toLowerCase().includes(q) ||
                    (t.source_system && t.source_system.toLowerCase().includes(q)) ||
                    t.amount.toString().includes(q)
                );
            }

            this.renderTransactionRows(items);
            this.renderPagination(response.total);
            $('#txnCountBadge').text(`${response.total.toLocaleString()} transactions`);
        } catch (err) {
            console.error('Fetch transactions error:', err);
            $('#txnListBody').html(`<tr><td colspan="8" class="text-center text-danger py-4"><i class="fas fa-exclamation-circle me-2"></i>Failed to retrieve transaction logs.</td></tr>`);
        }
    },

    renderTransactionRows(txns) {
        if (txns.length === 0) {
            $('#txnListBody').html(`<tr><td colspan="8" class="text-center py-4 text-muted">No transactions found.</td></tr>`);
            return;
        }
        const rows = txns.map(txn => {
            const rc = getRiskColor(txn.risk_score);
            const isCredit = txn.transaction_type === 'DEPOSIT';
            return `
                <tr style="cursor:pointer;" onclick="Transactions.viewTransaction('${txn.id}')">
                    <td><span class="text-muted small font-monospace">${txn.id.substring(0,8)}…</span></td>
                    <td><a href="#" onclick="event.stopPropagation();App.navigateTo('customers',{id:'${txn.customer_id}'})" class="text-kyro-primary font-monospace small">${txn.customer_id.substring(0,8)}…</a></td>
                    <td>${formatDateTime(txn.transaction_date)}</td>
                    <td><span class="badge bg-light text-dark border">${txn.transaction_type}</span></td>
                    <td><span class="fw-bold ${isCredit ? 'text-success' : 'text-danger'}">${isCredit ? '+' : '-'} ${formatCurrency(txn.amount, txn.currency)}</span></td>
                    <td><span class="badge bg-${rc}">${txn.risk_score}</span></td>
                    <td><span class="text-muted">${txn.source_system || 'N/A'}</span></td>
                    <td class="text-end" onclick="event.stopPropagation();">
                        <button class="btn btn-sm btn-outline-secondary" onclick="Transactions.viewTransaction('${txn.id}')">
                            <i class="fas fa-search me-1"></i>Analyze
                        </button>
                    </td>
                </tr>`;
        }).join('');
        $('#txnListBody').html(rows);
    },

    renderPagination(totalCount) {
        const totalPages = Math.ceil(totalCount / this.pageSize);
        const startIdx = (this.currentPage - 1) * this.pageSize + 1;
        const endIdx = Math.min(this.currentPage * this.pageSize, totalCount);
        $('#txnPaginationInfo').text(`Showing ${startIdx} to ${endIdx} of ${totalCount} Transactions`);

        let html = `<li class="page-item ${this.currentPage === 1 ? 'disabled' : ''}"><a class="page-link" href="#" onclick="Transactions.goToPage(${this.currentPage - 1})">Previous</a></li>`;
        for (let i = 1; i <= Math.min(totalPages, 5); i++) {
            html += `<li class="page-item ${this.currentPage === i ? 'active' : ''}"><a class="page-link" href="#" onclick="Transactions.goToPage(${i})">${i}</a></li>`;
        }
        if (totalPages > 5) {
            html += `<li class="page-item disabled"><span class="page-link">…</span></li>`;
            html += `<li class="page-item ${this.currentPage === totalPages ? 'active' : ''}"><a class="page-link" href="#" onclick="Transactions.goToPage(${totalPages})">${totalPages}</a></li>`;
        }
        html += `<li class="page-item ${this.currentPage === totalPages ? 'disabled' : ''}"><a class="page-link" href="#" onclick="Transactions.goToPage(${this.currentPage + 1})">Next</a></li>`;
        $('#txnPagination').html(html);
    },

    goToPage(pageNum) {
        if (pageNum < 1) return;
        this.currentPage = pageNum;
        this.fetchAndRenderTransactions();
    },

    viewTransaction(id) { App.navigateTo('transactions', { id }); },

    /* ─────────────────────────────────────────────
       TRANSACTION DETAIL VIEW
    ───────────────────────────────────────────── */
    async loadTransactionDetails(id) {
        showLoading('#mainContent', 'Ingesting transaction analytics…');
        try {
            const [txn, riskDetails, flags] = await Promise.all([
                API.get(API.endpoints.transaction(id)),
                API.get(`/transactions/${id}/risk`),
                API.get(`/transactions/${id}/flags`),
            ]);
            const rc = getRiskColor(txn.risk_score);

            // Map rule IDs back to pattern names for display
            const RULE_TO_PATTERN = {
                R001: 'THRESHOLD_BREACH', R009: 'THRESHOLD_BREACH',
                R002: 'VELOCITY_SPIKE',   R003: 'VELOCITY_SPIKE',
                R004: 'GEOGRAPHIC_SHIFT',
                R007: 'COUNTERPARTY_CHANGES',
                R008: 'COMPLEXITY_SHIFT',  R010: 'COMPLEXITY_SHIFT',
                R005: 'PEP_MATCH',  R006: 'SANCTIONS_MATCH',
            };

            const triggeredPatterns = [...new Set(
                (riskDetails.triggered_rules || []).map(r => RULE_TO_PATTERN[r] || r)
            )];

            const html = `
                <div class="dashboard-header mb-4">
                    <div class="container-fluid d-flex justify-content-between align-items-center flex-wrap gap-2">
                        <div class="d-flex align-items-center gap-3">
                            <button class="btn btn-outline-secondary btn-sm" onclick="App.navigateTo('transactions')">
                                <i class="fas fa-arrow-left me-2"></i>Back to Patterns
                            </button>
                            <div>
                                <h1 class="dashboard-title mb-0">Transaction Audit</h1>
                                <p class="dashboard-subtitle mb-0 font-monospace" style="font-size:12px;">Ref: ${txn.id}</p>
                            </div>
                        </div>
                        <button class="btn btn-primary" onclick="Transactions.runMLScoring('${txn.id}')">
                            <i class="fas fa-brain me-2"></i>Run AI Anomaly Check
                        </button>
                    </div>
                </div>

                <div class="row">
                    <div class="col-lg-6 mb-4">
                        <div class="card h-100 border-0 shadow-sm">
                            <div class="card-header bg-white py-3"><h5 class="card-title fw-bold mb-0">General Parameters</h5></div>
                            <div class="card-body">
                                <table class="table table-borderless align-middle">
                                    <tbody>
                                        <tr><td class="text-muted fw-semibold" style="width:180px;">Amount &amp; Currency</td><td class="fw-bold fs-5 text-kyro-primary">${formatCurrency(txn.amount, txn.currency)}</td></tr>
                                        <tr><td class="text-muted fw-semibold">Type</td><td><span class="badge bg-light text-dark border">${txn.transaction_type}</span></td></tr>
                                        <tr><td class="text-muted fw-semibold">Risk Score</td><td><span class="badge bg-${rc} py-2 px-3">${txn.risk_score}/100</span></td></tr>
                                        <tr><td class="text-muted fw-semibold">Customer ID</td><td><a href="#" onclick="App.navigateTo('customers',{id:'${txn.customer_id}'})" class="font-monospace fw-bold">${txn.customer_id}</a></td></tr>
                                        <tr><td class="text-muted fw-semibold">Account ID</td><td><code class="small">${txn.account_id}</code></td></tr>
                                        <tr><td class="text-muted fw-semibold">Transaction Date</td><td>${formatDateTime(txn.transaction_date)}</td></tr>
                                        <tr><td class="text-muted fw-semibold">Source System</td><td>${txn.source_system || 'CORE_BANKING'}</td></tr>
                                        <tr><td class="text-muted fw-semibold">Country</td><td>${txn.meta_country || 'N/A'}</td></tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>

                    <div class="col-lg-6 mb-4">
                        <div class="card h-100 border-0 shadow-sm">
                            <div class="card-header bg-white py-3"><h5 class="card-title fw-bold mb-0">Behavioral Patterns &amp; Risk Flags</h5></div>
                            <div class="card-body">
                                <h6 class="fw-bold text-muted border-bottom pb-2">Triggered Patterns</h6>
                                ${triggeredPatterns.length > 0 ? `
                                    <div class="d-flex flex-wrap gap-2 mb-4">
                                        ${triggeredPatterns.map(p => `<span class="badge bg-danger py-2 px-3"><i class="fas fa-exclamation-triangle me-1"></i>${p}</span>`).join('')}
                                    </div>` : `<p class="text-muted mb-4"><i class="fas fa-check-circle text-success me-2"></i>No behavioral patterns triggered.</p>`}

                                <h6 class="fw-bold text-muted border-bottom pb-2">Rules Engine Flags</h6>
                                <div class="table-responsive">
                                    <table class="table table-sm align-middle">
                                        <thead><tr><th>Severity</th><th>Rule</th><th>Description</th></tr></thead>
                                        <tbody>
                                            ${flags.length === 0
                                                ? `<tr><td colspan="3" class="text-center text-muted py-3">No compliance flags in DB.</td></tr>`
                                                : flags.map(f => `
                                                    <tr>
                                                        <td><span class="badge bg-${getRiskColor(f.flag_severity === 'CRITICAL' ? 99 : f.flag_severity === 'HIGH' ? 80 : 50)}">${f.flag_severity}</span></td>
                                                        <td><strong>${f.flag_type}</strong><br><small class="text-muted font-monospace">${RULE_TO_PATTERN[f.flag_type] || '—'}</small></td>
                                                        <td><small class="text-muted">${f.flag_description}</small></td>
                                                    </tr>`).join('')}
                                        </tbody>
                                    </table>
                                </div>
                                <div id="mlCheckResult" class="mt-4 border rounded p-3 bg-light d-none"></div>
                            </div>
                        </div>
                    </div>
                </div>`;

            $('#mainContent').html(html);
        } catch (err) {
            console.error('Load transaction details error:', err);
            showToast('error', 'Failed to retrieve transaction parameters.');
            App.navigateTo('transactions');
        }
    },

    async runMLScoring(txnId) {
        showGlobalLoading();
        $('#mlCheckResult').addClass('d-none').removeClass('d-block');
        try {
            const res = await API.post('/ml/score-transaction', { transaction_id: txnId });
            $('#mlCheckResult').html(`
                <div class="d-flex align-items-center mb-2 text-primary">
                    <i class="fas fa-brain fa-lg me-2"></i>
                    <h6 class="fw-bold mb-0">KYRO AI Classifier Analysis</h6>
                </div>
                <table class="table table-sm table-borderless mb-0">
                    <tbody>
                        <tr><td class="text-muted py-1" style="width:140px;">Anomaly Score</td><td class="fw-bold py-1">${(res.confidence * 100).toFixed(2)}% probability</td></tr>
                        <tr><td class="text-muted py-1">Risk Level</td><td class="py-1"><span class="badge bg-${getRiskColor(res.risk_score)}">${res.recommended_action}</span></td></tr>
                        <tr><td class="text-muted py-1">AI Explanation</td><td class="py-1 text-dark small">${res.ml_explanation || 'No statistical deviation detected.'}</td></tr>
                    </tbody>
                </table>
            `).removeClass('d-none').addClass('d-block');
            showToast('success', 'ML scoring completed.');
        } catch (err) {
            console.error('ML scoring error:', err);
            showToast('error', 'FastAPI ML models are still training. Please try again later.');
        } finally {
            hideLoading();
        }
    },

    setupEventListeners() {
        $(document).on('keypress', '#txnSearch', (e) => {
            if (e.which === 13) {
                this.searchQuery = $('#txnSearch').val();
                this.currentPage = 1;
                this.fetchAndRenderTransactions();
            }
        });
        $(document).off('click', '#btnApplyTxnFilters').on('click', '#btnApplyTxnFilters', () => {
            this.searchQuery = $('#txnSearch').val();
            this.currentFilterType = $('#filterTxnType').val();
            this.currentPage = 1;
            this.fetchAndRenderTransactions();
        });
    },
};

window.Transactions = Transactions;
