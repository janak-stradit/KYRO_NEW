/**
 * KYRO Review Cases - the compliance work queue.
 * Highest-risk, oldest alerts first; filter by risk, rule, status and owner;
 * assign, resolve and export from each row.
 */

const Cases = {
    // Server-side filters for the queue
    filters: { q: '', status: 'UNRESOLVED', risk: '', rule: '', assignment: '', customerId: null, sort: 'priority' },
    // Set when arriving from the Patterns page with a customer selected
    currentFilters: { customer: null, pattern: null },

    casesData: [],
    totalCases: 0,
    summary: null,
    customerCodes: {},   // customer UUID -> display code (CUST-001)
    customerIds: {},     // display code -> customer UUID

    // Pagination settings
    pagination: {
        currentPage: 1,
        pageSize: 10,
        pageSizeOptions: [10, 25, 50, 100]
    },

    init(params = {}) {
        // Each visit starts on the default queue; only a customer passed from
        // the Patterns page carries over.
        this.filters = { q: '', status: 'UNRESOLVED', risk: '', rule: '', assignment: '', customerId: null, sort: 'priority' };
        this.currentFilters = { customer: params.customer || null, pattern: params.pattern || null };
        this.pagination.currentPage = 1;
        this.afterChange = null;
        this.loadDashboard();
    },

    human(value) {
        return value ? String(value).replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase()) : '—';
    },

    /** Called after an alert is assigned or resolved. The case page sets `afterChange` to refresh itself. */
    refreshAfterChange() {
        if (typeof this.afterChange === 'function') { this.afterChange(); return; }
        this.loadSummary();
        this.fetchCasesData();
        this.loadBaseline();
    },

    /** "3 h", "2 d": how long an alert has been waiting. */
    age(dateString) {
        const hours = (Date.now() - new Date(dateString).getTime()) / 3600000;
        if (!isFinite(hours) || hours < 0) return '—';
        if (hours < 1) return '< 1 h';
        return hours < 48 ? `${Math.floor(hours)} h` : `${Math.floor(hours / 24)} d`;
    },

    async loadDashboard() {
        $("#mainContent").html(`
            <div class="kyro-page">
                <div class="kyro-page-head">
                    <div>
                        <span class="kyro-kicker">Case Management</span>
                        <h1 class="kyro-page-title">Review Cases</h1>
                        <p class="kyro-page-sub">Your work queue: the highest-risk, longest-waiting alerts come first.</p>
                    </div>
                    <div class="kyro-page-actions">
                        <button class="btn btn-primary px-4" id="refreshCasesBtn">
                            <i class="fas fa-rotate-right me-2"></i>Refresh
                        </button>
                    </div>
                </div>

                <div id="customerFilterChip"></div>

                <!-- What is waiting: each tile is also a one-click filter -->
                <div class="rq-tiles" id="rqTiles" aria-label="Queue summary"></div>

                <!-- Where the work concentrates -->
                <div class="kd-grid kd-grid--halves mb-4">
                    <section class="card kd-panel">
                        <header class="kd-panel__head">
                            <div>
                                <h2>Customers with the most open alerts</h2>
                                <p class="aml-subtitle">Reviewing one customer can clear many alerts at once</p>
                            </div>
                        </header>
                        <ul class="kd-bars" id="rqTopCustomers"><li class="kd-skeleton"></li><li class="kd-skeleton"></li><li class="kd-skeleton"></li></ul>
                    </section>
                    <section class="card kd-panel">
                        <header class="kd-panel__head">
                            <div>
                                <h2>Open alerts by rule</h2>
                                <p class="aml-subtitle">Select a rule to see only its alerts</p>
                            </div>
                        </header>
                        <ul class="kd-bars" id="rqByRule"><li class="kd-skeleton"></li><li class="kd-skeleton"></li><li class="kd-skeleton"></li></ul>
                    </section>
                </div>

                <!-- The queue -->
                <div class="card border-0 rc-table-card">
                    <div class="rc-toolbar">
                        <div class="rc-toolbar__title">
                            <h2>Work queue</h2>
                            <small class="text-muted" id="resultsCount">&nbsp;</small>
                        </div>
                        <div class="rc-toolbar__controls">
                            <div class="rc-search">
                                <i class="fas fa-search"></i>
                                <input type="search" class="form-control" id="caseSearch" placeholder="Search customer name" aria-label="Search customer name">
                            </div>
                            <select class="form-select" id="filterStatus" aria-label="Filter by status">
                                <option value="UNRESOLVED">Unresolved</option>
                                <option value="OPEN">Open</option>
                                <option value="ASSIGNED">Assigned</option>
                                <option value="IN_REVIEW">In review</option>
                                <option value="ESCALATED">Escalated</option>
                                <option value="RESOLVED">Resolved</option>
                                ${Auth.can('alerts.qa') ? `
                                <option value="AWAITING_QA">Resolved, awaiting quality check</option>
                                <option value="QA_FAILED">Failed quality check</option>` : ''}
                                <option value="ALL">All statuses</option>
                            </select>
                            <select class="form-select" id="filterRisk" aria-label="Filter by risk">
                                <option value="">All risk levels</option>
                                <option value="high">High (80+)</option>
                                <option value="medium">Medium (60–79)</option>
                                <option value="low">Low (under 60)</option>
                            </select>
                            <select class="form-select" id="filterRule" aria-label="Filter by rule">
                                <option value="">All rules</option>
                                ${Object.entries(this.RULES).map(([code, r]) => `<option value="${code}">${code} ${escapeHtml(r[0])}</option>`).join('')}
                            </select>
                            <select class="form-select" id="filterAssignment" aria-label="Filter by owner">
                                <option value="">Any owner</option>
                                <option value="unassigned">Unassigned</option>
                                <option value="mine">Assigned to me</option>
                            </select>
                            <select class="form-select" id="filterSort" aria-label="Sort order">
                                <option value="priority">Highest risk first</option>
                                <option value="oldest">Oldest first</option>
                                <option value="newest">Newest first</option>
                            </select>
                            <button type="button" class="btn rc-clear d-none" id="clearFiltersBtn">
                                <i class="fas fa-xmark me-1"></i>Clear
                            </button>
                        </div>
                    </div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0 rq-table">
                            <thead>
                                <tr>
                                    <th class="px-3 py-3">Risk</th>
                                    <th class="px-3 py-3">Customer</th>
                                    <th class="px-3 py-3">Why it was flagged</th>
                                    <th class="px-3 py-3">Status</th>
                                    <th class="px-3 py-3">Waiting</th>
                                    <th class="px-3 py-3">Owner</th>
                                    <th class="px-3 py-3"><span class="visually-hidden">Actions</span></th>
                                </tr>
                            </thead>
                            <tbody id="casesTableBody">
                                <tr><td colspan="7" class="rc-empty">Loading the queue...</td></tr>
                            </tbody>
                        </table>
                    </div>
                    <div class="d-flex justify-content-between align-items-center p-3" style="border-top: 1px solid #f0f0f0;">
                        <div class="d-flex align-items-center gap-2">
                            <span class="text-muted" style="font-size: 13px;">Rows per page:</span>
                            <select class="form-select form-select-sm" id="pageSizeSelect" style="width: 80px; font-size: 13px;">
                                ${this.pagination.pageSizeOptions.map(n => `<option value="${n}">${n}</option>`).join('')}
                            </select>
                            <span class="text-muted ms-3" id="paginationInfo" style="font-size: 13px;"></span>
                        </div>
                        <div class="d-flex gap-2">
                            <button type="button" class="btn btn-sm btn-outline-primary" id="prevPage">Previous</button>
                            <button type="button" class="btn btn-sm btn-outline-primary" id="nextPage">Next</button>
                        </div>
                    </div>
                </div>

                <!-- False-positive baseline per rule (compliance officers and admins) -->
                <div id="fpBaselineCard" class="mt-4"></div>
            </div>
        `);

        this.setupEventListeners();
        await this.loadCustomerCodes();
        this.applyCustomerFromPatterns();
        await Promise.all([this.loadSummary(), this.fetchCasesData()]);
        this.loadBaseline();
    },

    /** Display codes (CUST-001) follow the customer list order, as on the Patterns page. */
    async loadCustomerCodes() {
        if (Object.keys(this.customerCodes).length) return;
        try {
            const response = await API.get("/customers", { page_size: 10000 });
            (response.items || []).forEach((c, idx) => {
                const code = `CUST-${String(idx + 1).padStart(3, '0')}`;
                this.customerCodes[c.id] = code;
                this.customerIds[code] = c.id;
            });
        } catch (err) {
            console.warn("Could not load customer codes:", err);
        }
    },

    applyCustomerFromPatterns() {
        const code = this.currentFilters.customer;
        if (!code) { $("#customerFilterChip").empty(); return; }
        this.filters.customerId = this.customerIds[code] || null;
        this.renderCustomerChip(code, this.currentFilters.pattern);
    },

    renderCustomerChip(label, pattern) {
        const from = pattern ? ` &middot; from pattern <strong>${escapeHtml(String(pattern).replace(/_/g, ' '))}</strong>` : '';
        $("#customerFilterChip").html(`
            <div class="rc-filter-chip" role="status">
                <i class="fas fa-filter"></i>
                <span>Showing cases for customer <strong>${escapeHtml(label)}</strong>${from}</span>
                <button type="button" class="rc-filter-chip__clear" id="clearCustomerFilterBtn" aria-label="Show all customers">
                    <i class="fas fa-xmark"></i>
                </button>
            </div>`);
    },

    // False-positive rate and time-to-disposition per rule, from recorded outcomes
    async loadBaseline() {
        if (!Auth.can('alerts.baseline')) return;

        let data;
        try {
            data = await API.get('/alerts/disposition-baseline', { days: 90 });
        } catch (error) {
            return; // the baseline is supplementary; the case list still works without it
        }
        const pct = (v) => (v == null ? '—' : `${(v * 100).toFixed(0)}%`);
        const hours = (v) => (v == null ? '—' : v < 48 ? `${v.toFixed(1)} h` : `${(v / 24).toFixed(1)} d`);
        const fpClass = (v) => (v == null ? '' : v >= 0.7 ? 'high' : v >= 0.4 ? 'medium' : 'low');
        const topReason = (reasons) => {
            const first = Object.entries(reasons || {})[0];
            return first ? `${first[0].replace(/_/g, ' ').toLowerCase()} (${first[1]})` : '—';
        };
        const o = data.overall;

        const rows = data.by_rule.map(r => {
            const rule = this.RULES[r.rule];
            return `
                <tr>
                    <td class="px-3 py-2"><strong>${escapeHtml(r.rule)}</strong> <span class="text-muted">${escapeHtml(rule ? rule[0] : '')}</span></td>
                    <td class="px-3 py-2 text-end">${r.alerts}</td>
                    <td class="px-3 py-2 text-end">${r.resolved}</td>
                    <td class="px-3 py-2 text-end">${r.false_positive_rate == null ? '—' : `<span class="cd-chip cd-chip--${fpClass(r.false_positive_rate)}">${pct(r.false_positive_rate)}</span>`}</td>
                    <td class="px-3 py-2 text-end">${r.sar_filed}</td>
                    <td class="px-3 py-2 text-end">${hours(r.median_hours_to_disposition)}</td>
                    <td class="px-3 py-2 text-muted">${escapeHtml(topReason(r.reasons))}</td>
                </tr>`;
        }).join('');

        $("#fpBaselineCard").html(`
            <div class="card border-0 rc-table-card mb-4">
                <div class="rc-toolbar">
                    <div class="rc-toolbar__title">
                        <h2>False-positive baseline</h2>
                        <small class="text-muted">Alerts created in the last ${data.window_days} days, by triggered rule</small>
                    </div>
                    <div class="fp-summary">
                        <div><span>Alerts</span><strong>${o.alerts}</strong></div>
                        <div><span>Resolved</span><strong>${o.resolved}</strong></div>
                        <div><span>False-positive rate</span><strong>${pct(o.false_positive_rate)}</strong></div>
                        <div><span>Median time to resolve</span><strong>${hours(o.median_hours_to_disposition)}</strong></div>
                    </div>
                </div>
                ${o.resolved === 0 ? `
                    <p class="fp-empty">No cases have been resolved yet. Rates appear here once outcomes are recorded with the Resolve action.</p>` : ''}
                <div class="table-responsive">
                    <table class="table table-hover mb-0 fp-table">
                        <thead>
                            <tr>
                                <th class="px-3 py-2">Rule</th>
                                <th class="px-3 py-2 text-end">Alerts</th>
                                <th class="px-3 py-2 text-end">Resolved</th>
                                <th class="px-3 py-2 text-end">False-positive rate</th>
                                <th class="px-3 py-2 text-end">SAR filed</th>
                                <th class="px-3 py-2 text-end">Median time to resolve</th>
                                <th class="px-3 py-2">Most common reason</th>
                            </tr>
                        </thead>
                        <tbody>${rows || '<tr><td colspan="7" class="rc-empty">No alerts in this period.</td></tr>'}</tbody>
                    </table>
                </div>
            </div>
        `);
    },
    
    async loadSummary() {
        let s;
        try {
            s = await API.get('/alerts/queue/summary');
        } catch (error) {
            $("#rqTiles").html('<div class="kd-empty kd-empty--error"><i class="fas fa-triangle-exclamation"></i>Could not load the queue summary.</div>');
            $("#rqTopCustomers, #rqByRule").empty();
            return;
        }
        this.summary = s;

        const tile = (key, label, value, note, alertClass = '') => `
            <button type="button" class="rq-tile ${alertClass}" data-tile="${key}">
                <span class="rq-tile__label">${label}</span>
                <strong class="rq-tile__value">${value}</strong>
                <span class="rq-tile__note">${note}</span>
            </button>`;
        $("#rqTiles").html(
            tile('all', 'Unresolved', s.unresolved.toLocaleString(), `across ${s.customers_with_alerts.toLocaleString()} customers`)
            + tile('high', 'High risk', s.high_risk.toLocaleString(), 'risk score 80 or more', s.high_risk ? 'rq-tile--alert' : '')
            + tile('unassigned', 'Unassigned', s.unassigned.toLocaleString(), 'no owner yet', s.unassigned ? 'rq-tile--warn' : '')
            + tile('mine', 'Assigned to me', s.assigned_to_me.toLocaleString(), 'in your name')
            + tile('escalated', 'Escalated', s.escalated.toLocaleString(), 'awaiting a senior decision')
            + tile('oldest', 'Longest waiting', s.oldest_created_at ? this.age(s.oldest_created_at) : '—', 'oldest unresolved alert')
        );

        const bars = (items, attrs, label, value, max) => items.map(item => `
            <li>
                <button type="button" class="rq-bar" ${attrs(item)}>
                    <div class="kd-bars__row"><span>${label(item)}</span><strong>${value(item).toLocaleString()}</strong></div>
                    <div class="kd-bars__track"><span style="width: ${Math.max(2, Math.round((value(item) / max) * 100))}%"></span></div>
                </button>
            </li>`).join('');

        const maxCustomer = Math.max(1, ...s.top_customers.map(c => c.open_alerts));
        $("#rqTopCustomers").html(bars(
            s.top_customers,
            c => `data-customer="${escapeHtml(c.customer_id)}" data-name="${escapeHtml(c.customer_name)}"`,
            c => `${escapeHtml(c.customer_name)} <small class="text-muted">highest score ${c.max_risk_score}</small>`,
            c => c.open_alerts, maxCustomer
        ) || '<li class="kd-empty">No open alerts.</li>');

        const rules = s.by_rule.slice(0, 5);
        const maxRule = Math.max(1, ...rules.map(r => r.alerts));
        $("#rqByRule").html(bars(
            rules,
            r => `data-rule="${escapeHtml(r.rule)}"`,
            r => `${escapeHtml(r.rule)} <small class="text-muted">${escapeHtml((this.RULES[r.rule] || [''])[0])}</small>`,
            r => r.alerts, maxRule
        ) || '<li class="kd-empty">No open alerts.</li>');
    },

    async fetchCasesData() {
        const f = this.filters;
        const params = { page: this.pagination.currentPage, page_size: this.pagination.pageSize, status_filter: f.status, sort: f.sort };
        if (f.q) params.q = f.q;
        if (f.risk) params.risk = f.risk;
        if (f.rule) params.rule = f.rule;
        if (f.assignment) params.assignment = f.assignment;
        if (f.customerId) params.customer_id = f.customerId;

        let data;
        try {
            data = await API.get('/alerts/queue', params);
        } catch (error) {
            // Never substitute sample data: an empty or wrong queue is worse than an honest error
            this.casesData = [];
            this.totalCases = 0;
            $("#casesTableBody").html('<tr><td colspan="7" class="rc-empty"><i class="fas fa-triangle-exclamation"></i><strong>Could not load the queue</strong><span>Check your connection and select Refresh.</span></td></tr>');
            $("#resultsCount").text('');
            this.renderPaginationControls();
            return;
        }

        this.totalCases = data.total;
        this.casesData = data.items.map(alert => {
            const score = Number(alert.risk_score);
            const riskLevel = score >= 80 ? 'HIGH' : score >= 60 ? 'MEDIUM' : 'LOW';
            return {
                caseId: alert.id,
                customerId: this.customerCodes[alert.customer_id] || '—',
                customerName: alert.customer_name || '',
                rawCustomerId: alert.customer_id,
                triggerType: 'RULE BASED',
                priority: riskLevel === 'HIGH' ? 'URGENT' : riskLevel === 'MEDIUM' ? 'HIGH' : 'LOW',
                riskLevel,
                status: alert.status || 'OPEN',
                createdAt: new Date(alert.created_at).toLocaleDateString(),
                assignedTo: alert.assigned_to_name || (alert.assigned_to ? 'Assigned' : 'Unassigned'),
                fullData: alert
            };
        });
        this.renderTable();
    },

    // Kept for callers that refresh the page after a change
    updateDashboard() {
        this.loadSummary();
    },

    renderTable() {
        const total = this.totalCases;
        const start = total ? (this.pagination.currentPage - 1) * this.pagination.pageSize + 1 : 0;
        const end = Math.min(this.pagination.currentPage * this.pagination.pageSize, total);
        $("#resultsCount").text(total ? `Showing ${start.toLocaleString()}–${end.toLocaleString()} of ${total.toLocaleString()} alerts` : 'No matching alerts');
        this.renderPaginationControls();

        if (!this.casesData.length) {
            $("#casesTableBody").html('<tr><td colspan="7" class="rc-empty"><i class="fas fa-folder-open"></i><strong>No alerts match these filters</strong><span>Try clearing the search or filters.</span></td></tr>');
            return;
        }

        const statusColors = {
            OPEN: ['#e0f2fe', '#0369a1'], ASSIGNED: ['#ede9fe', '#6d28d9'], IN_REVIEW: ['#fef3c7', '#b45309'],
            ESCALATED: ['#fee2e2', '#b91c1c'], RESOLVED: ['#dcfce7', '#15803d']
        };
        const canAct = (c) => c.status !== 'RESOLVED';
        const mayAssign = Auth.can('alerts.assign');
        const mayResolve = this.canDecide();

        $("#casesTableBody").html(this.casesData.map(c => {
            const a = c.fullData;
            const displayName = c.customerName || c.customerId;
            const initials = displayName.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '?';
            const band = c.riskLevel.toLowerCase();
            const codes = (a.triggered_rules && (a.triggered_rules.rules || a.triggered_rules)) || [];
            const rules = (Array.isArray(codes) ? codes : []).map(code => ({ code, name: (this.RULES[code] || [code])[0] }));
            const [statusBg, statusFg] = statusColors[c.status] || statusColors.OPEN;
            const others = (a.customer_open_alerts || 0) - (canAct(c) ? 1 : 0);

            return `
                <tr>
                    <td class="px-3 py-3">
                        <span class="rq-score rq-score--${band}" title="${escapeHtml(this.human(c.riskLevel))} risk">${isFinite(Number(a.risk_score)) ? Number(a.risk_score) : '—'}</span>
                    </td>
                    <td class="px-3 py-3">
                        <div class="rc-customer">
                            <span class="rc-customer__avatar" aria-hidden="true">${escapeHtml(initials)}</span>
                            <span class="rc-customer__text">
                                <strong>${escapeHtml(displayName)}</strong>
                                <small>${escapeHtml(c.customerId)}${a.customer_sanctions ? ' <span class="cd-chip cd-chip--high">Sanctions</span>' : ''}${a.customer_pep ? ' <span class="cd-chip cd-chip--medium">PEP</span>' : ''}</small>
                                ${others > 0 ? `<button type="button" class="rq-more" data-customer="${escapeHtml(c.rawCustomerId)}" data-name="${escapeHtml(displayName)}">+${others.toLocaleString()} other open alert${others === 1 ? '' : 's'}</button>` : ''}
                            </span>
                        </div>
                    </td>
                    <td class="px-3 py-3">
                        <div class="rq-rules">
                            ${rules.slice(0, 3).map(r => `<span class="rq-rule" title="${escapeHtml(r.code)}">${escapeHtml(r.name)}</span>`).join('')}
                            ${rules.length > 3 ? `<span class="rq-rule rq-rule--more">+${rules.length - 3}</span>` : ''}
                            ${rules.length ? '' : '<span class="text-muted">No rule recorded</span>'}
                        </div>
                    </td>
                    <td class="px-3 py-3"><span class="badge" style="background:${statusBg};color:${statusFg};font-size:11px;font-weight:600;padding:5px 10px;">${escapeHtml(this.human(c.status))}</span></td>
                    <td class="px-3 py-3 text-nowrap" title="Created ${escapeHtml(new Date(a.created_at).toLocaleString())}">${canAct(c) ? escapeHtml(this.age(a.created_at)) : '—'}</td>
                    <td class="px-3 py-3 ${a.assigned_to ? '' : 'text-muted'}">${escapeHtml(c.assignedTo)}</td>
                    <td class="px-3 py-3">
                        <div class="rc-actions">
                            <button type="button" class="btn btn-sm rc-actions__view view-case-btn" data-case="${escapeHtml(c.caseId)}">
                                <i class="far fa-eye me-1"></i>View
                            </button>
                            ${canAct(c) && mayAssign ? `
                            <button type="button" class="btn btn-sm rc-actions__icon assign-btn" data-case="${escapeHtml(c.caseId)}" title="Assign" aria-label="Assign alert for ${escapeHtml(displayName)}">
                                <i class="fas fa-user-plus"></i>
                            </button>` : ''}
                            ${canAct(c) && mayResolve ? `
                            <button type="button" class="btn btn-sm rc-actions__icon resolve-btn" data-case="${escapeHtml(c.caseId)}" title="Resolve" aria-label="Resolve alert for ${escapeHtml(displayName)}">
                                <i class="fas fa-check-double"></i>
                            </button>` : ''}
                            <button type="button" class="btn btn-sm rc-actions__icon export-btn" data-customer="${escapeHtml(c.customerId)}" data-case="${escapeHtml(c.caseId)}" title="Export case report" aria-label="Export case report for ${escapeHtml(displayName)}">
                                <i class="fas fa-file-arrow-down"></i>
                            </button>
                        </div>
                    </td>
                </tr>`;
        }).join(''));
    },

    renderPaginationControls() {
        const total = this.totalCases;
        const pages = Math.max(1, Math.ceil(total / this.pagination.pageSize));
        $("#pageSizeSelect").val(this.pagination.pageSize);
        $("#paginationInfo").text(total ? `Page ${this.pagination.currentPage.toLocaleString()} of ${pages.toLocaleString()}` : '');
        $("#prevPage").prop("disabled", this.pagination.currentPage <= 1);
        $("#nextPage").prop("disabled", this.pagination.currentPage >= pages);
    },

    // Records the disposition (outcome + reason codes + notes) for a case.
    // "Escalated" goes to /escalate; the other outcomes close the alert.
    // Each outcome is a separate decision with its own permission
    OUTCOME_PERMISSION: {
        FALSE_POSITIVE: 'alerts.close_false_positive',
        TRUE_POSITIVE_NO_SAR: 'alerts.close',
        SAR_FILED: 'sar.approve',
        ESCALATED: 'alerts.escalate'
    },

    canDecide() {
        return Auth.can(...Object.values(this.OUTCOME_PERMISSION));
    },

    async showResolveModal(caseData) {
        let options;
        try {
            options = await API.get('/alerts/resolution-options');
        } catch (error) {
            showToast('error', 'Could not load resolution options. Please try again.');
            return;
        }
        options.outcomes = options.outcomes.filter(o => Auth.can(this.OUTCOME_PERMISSION[o.code]));
        if (!options.outcomes.length) {
            showToast('error', 'Your role cannot record an outcome on this case.');
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
                closeModalSafely(modalEl);
                showToast('success', outcome === 'ESCALATED' ? 'Case escalated.' : 'Case resolved.');
                this.refreshAfterChange();
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

    /** Push the current filters into the controls, then reload page one. */
    applyFilters() {
        const f = this.filters;
        $("#caseSearch").val(f.q);
        $("#filterStatus").val(f.status);
        $("#filterRisk").val(f.risk);
        $("#filterRule").val(f.rule);
        $("#filterAssignment").val(f.assignment);
        $("#filterSort").val(f.sort);
        const changed = f.q || f.risk || f.rule || f.assignment || f.status !== 'UNRESOLVED' || f.sort !== 'priority';
        $("#clearFiltersBtn").toggleClass("d-none", !changed);
        this.pagination.currentPage = 1;
        this.fetchCasesData();
    },

    resetFilters(overrides = {}) {
        Object.assign(this.filters, { q: '', status: 'UNRESOLVED', risk: '', rule: '', assignment: '', sort: 'priority' }, overrides);
        this.applyFilters();
    },

    setupEventListeners() {
        const self = this;
        const find = (el) => self.casesData.find(c => c.caseId === $(el).data("case"));

        let searchTimer;
        $("#caseSearch").on("input", function() {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => { self.filters.q = $(this).val().trim(); self.applyFilters(); }, 300);
        });
        $("#filterStatus, #filterRisk, #filterRule, #filterAssignment, #filterSort").on("change", () => {
            Object.assign(self.filters, {
                status: $("#filterStatus").val(), risk: $("#filterRisk").val(), rule: $("#filterRule").val(),
                assignment: $("#filterAssignment").val(), sort: $("#filterSort").val()
            });
            self.applyFilters();
        });
        $("#clearFiltersBtn").on("click", () => self.resetFilters());

        $("#refreshCasesBtn").on("click", () => { self.loadSummary(); self.fetchCasesData(); self.loadBaseline(); });

        $("#pageSizeSelect").on("change", function() {
            self.pagination.pageSize = parseInt($(this).val(), 10);
            self.pagination.currentPage = 1;
            self.fetchCasesData();
        });
        $("#prevPage").on("click", () => { if (self.pagination.currentPage > 1) { self.pagination.currentPage--; self.fetchCasesData(); } });
        $("#nextPage").on("click", () => { self.pagination.currentPage++; self.fetchCasesData(); });

        const filterByCustomer = (el) => {
            self.filters.customerId = $(el).data("customer");
            self.renderCustomerChip($(el).data("name"), null);
            self.resetFilters();
        };

        $("#mainContent").off("click.cases")
            // Summary tiles are one-click filters
            .on("click.cases", ".rq-tile", function() {
                const presets = {
                    all: {}, high: { risk: 'high' }, unassigned: { assignment: 'unassigned' }, mine: { assignment: 'mine' },
                    escalated: { status: 'ESCALATED' }, oldest: { sort: 'oldest' }
                };
                self.resetFilters(presets[$(this).data("tile")] || {});
            })
            .on("click.cases", ".rq-bar[data-rule]", function() { self.resetFilters({ rule: $(this).data("rule") }); })
            .on("click.cases", ".rq-bar[data-customer], .rq-more", function() { filterByCustomer(this); })
            .on("click.cases", "#clearCustomerFilterBtn", () => {
                self.filters.customerId = null;
                self.currentFilters = { customer: null, pattern: null };
                $("#customerFilterChip").empty();
                self.applyFilters();
            })
            .on("click.cases", ".view-case-btn", function() { App.navigateTo('case', { id: $(this).data("case") }); })
            .on("click.cases", ".assign-btn", function() { const c = find(this); if (c) self.showAssignModal(c); })
            .on("click.cases", ".resolve-btn", function() { const c = find(this); if (c) self.showResolveModal(c); })
            .on("click.cases", ".export-btn", function() { self.showExportModal($(this).data("case"), $(this).data("customer")); });
    },

    /** Assign an alert to a real user (or to yourself). */
    async showAssignModal(caseData) {
        let assignees;
        try {
            assignees = await API.get('/alerts/assignees');
        } catch (error) {
            showToast('error', 'Could not load the list of users.');
            return;
        }
        const me = Auth.getUser() || {};
        const displayName = caseData.customerName || caseData.customerId;

        $("#assignCaseModal").remove();
        $("body").append(`
            <div class="modal fade" id="assignCaseModal" tabindex="-1" aria-labelledby="assignCaseTitle" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content kx-modal">
                        <div class="modal-header">
                            <div>
                                <h5 class="modal-title" id="assignCaseTitle">Assign alert</h5>
                                <small class="text-muted">${escapeHtml(displayName)} &middot; risk score ${escapeHtml(String(caseData.fullData.risk_score))}</small>
                            </div>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <label class="kx-label" for="assignToUser">Owner</label>
                            <select class="form-select" id="assignToUser">
                                <option value="">Select a person...</option>
                                ${assignees.map(u => `<option value="${escapeHtml(u.id)}" ${u.id === caseData.fullData.assigned_to ? 'selected' : ''}>${escapeHtml(u.name)} (${escapeHtml(this.human(u.role))})${u.id === me.id ? ' — me' : ''}</option>`).join('')}
                            </select>
                            <p class="kx-note">The owner is recorded on the alert and in the audit log.</p>
                            <div class="text-danger small mt-2 d-none" id="assignError" role="alert"></div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-primary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-primary" id="confirmAssignBtn">Assign</button>
                        </div>
                    </div>
                </div>
            </div>`);
        const modalEl = document.getElementById('assignCaseModal');
        new bootstrap.Modal(modalEl).show();

        $("#confirmAssignBtn").on("click", async () => {
            const userId = $("#assignToUser").val();
            if (!userId) { $("#assignError").text('Select who should own this alert.').removeClass("d-none"); return; }
            const $btn = $("#confirmAssignBtn").prop("disabled", true);
            try {
                await API.put(`/alerts/${caseData.caseId}/assign`, { assigned_to: userId });
                closeModalSafely(modalEl);
                showToast('success', 'Alert assigned.');
                this.refreshAfterChange();
            } catch (xhr) {
                const detail = xhr && xhr.responseJSON && xhr.responseJSON.detail;
                $("#assignError").text(typeof detail === 'string' ? detail : 'Could not assign the alert.').removeClass("d-none");
                $btn.prop("disabled", false);
            }
        });
        $(modalEl).on("hidden.bs.modal", function() { setTimeout(() => $(this).remove(), 0); });
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
                                    <label class="form-check"><input class="form-check-input" type="checkbox" id="includeDocuments" checked><span class="form-check-label">Documents reviewed</span></label>
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
            if ($('#includeDocuments').is(':checked')) sections.push('documents');
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

        let documents = [];
        if (rawCustomerId) {
            try {
                const list = await API.get('/documents', { customer_id: rawCustomerId });
                documents = (await Promise.all(list.slice(0, 20).map(d => API.get(`/documents/${d.id}`).catch(() => null)))).filter(Boolean)
                    .map(({ pages, ...rest }) => rest);  // the report cites pages; it does not reproduce the document text
            } catch (err) {
                console.warn("Could not load documents for the report:", err);
            }
        }

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
            kycReviews: value(4) || [],
            documents
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
        if (has('documents')) {
            const docTypes = (typeof Documents !== 'undefined' && Documents.TYPES) || {};
            const checkLabel = { MATCH: 'Matches record', MISMATCH: 'Differs from record', NOT_ON_RECORD: 'Not on record', EXPIRED: 'Expired', NOT_CHECKED: 'Not checked' };
            section('Documents Reviewed', `${(data.documents || []).length} on file`);
            if (!(data.documents || []).length) {
                text('No documents have been uploaded for this customer.', M, y + 2, { size: 9, color: C.muted });
                y += 8;
            }
            (data.documents || []).forEach(d => {
                ensure(20);
                text(`${d.filename}  ·  ${docTypes[d.doc_type] || human(d.doc_type)}  ·  uploaded ${fmtDate(d.uploaded_at)}${d.alert_id === data.caseId ? '  ·  for this case' : ''}`, M, y, { size: 9, bold: true, color: C.ink });
                y += 5;
                if (d.text_status !== 'EXTRACTED') {
                    text(d.text_status === 'NEEDS_OCR' ? 'Scanned document: could not be read automatically.' : 'The text of this document could not be read.', M, y, { size: 8.5, color: C.muted });
                    y += 7;
                    return;
                }
                table(
                    ['Field', 'Value', 'Check', 'On record', 'Page', 'Decision'],
                    d.extractions.map(e => [
                        human(e.field), e.value + (e.quote_verified ? '' : '  (not found in document)'),
                        checkLabel[e.check_status] || human(e.check_status), e.record_value || '—', e.page_number || '—',
                        human(e.status === 'PROPOSED' ? 'not reviewed' : e.status) + (e.applied_to_record ? ', record updated' : '')
                    ]),
                    { empty: d.extracted_at ? 'None of the expected fields were found.' : 'Fields have not been read from this document.' }
                );
                if (d.extracted_by === 'mock' && d.extractions.length) {
                    text('Fields were read by the mock reader, not an AI model.', M, y - 2, { size: 7.5, color: C.muted });
                    y += 4;
                }
            });
        }

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
            ...(data.documents || []).flatMap(d => d.extractions.map(e => [
                `Document ${d.filename}: ${e.field}`,
                `${e.value} [${e.check_status}${e.record_value ? `, on record ${e.record_value}` : ''}; ${e.status}; page ${e.page_number || '-'}]`
            ])),
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
