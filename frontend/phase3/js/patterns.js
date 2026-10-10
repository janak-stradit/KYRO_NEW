/**
 * KYRO Behavior Patterns - which behavioural patterns are firing and for whom.
 * Every number is counted from the rules that fired on alerts in the last
 * 30 days; nothing on this page is sample data.
 */

const Patterns = {
    patterns: [],
    rows: [],
    total: 0,
    page: 1,
    pageSize: 10,
    filters: { pattern: '', q: '' },
    customerCodes: {},   // customer UUID -> display code (CUST-001), as on Review Cases

    async init() {
        this.page = 1;
        this.filters = { pattern: '', q: '' };
        this.renderLayout();
        this.setupEventListeners();
        await this.loadCustomerCodes();
        await Promise.all([this.loadSummary(), this.loadRows()]);
    },

    renderLayout() {
        $("#mainContent").html(`
            <div class="kyro-page">
                <div class="kyro-page-head">
                    <div>
                        <span class="kyro-kicker">Behavior Analytics</span>
                        <h1 class="kyro-page-title">Behavior Patterns</h1>
                        <p class="kyro-page-sub">Customers whose last 30 days of transactions depart from their own previous 90 days, and how.</p>
                    </div>
                    <div class="kyro-page-actions">
                        <button class="btn btn-primary px-4" id="refreshPatternsBtn">
                            <i class="fas fa-rotate-right me-2"></i>Refresh
                        </button>
                    </div>
                </div>

                <div class="rq-tiles rq-tiles--four" id="bpTiles" aria-label="Pattern summary"></div>

                <section class="card kd-panel mb-4">
                    <header class="kd-panel__head">
                        <div>
                            <h2>Patterns</h2>
                            <p class="aml-subtitle">Each pattern compares a customer with their own history. Select one to see its customers below.</p>
                        </div>
                    </header>
                    <ul class="bp-list" id="bpList"><li class="kd-skeleton"></li><li class="kd-skeleton"></li><li class="kd-skeleton"></li></ul>
                    <p class="kx-note" id="bpNote"></p>
                </section>

                <div class="card border-0 rc-table-card">
                    <div class="rc-toolbar">
                        <div class="rc-toolbar__title">
                            <h2>Customers by pattern</h2>
                            <small class="text-muted" id="bpCount">&nbsp;</small>
                        </div>
                        <div class="rc-toolbar__controls">
                            <div class="rc-search">
                                <i class="fas fa-search"></i>
                                <input type="search" class="form-control" id="bpSearch" placeholder="Search customer name" aria-label="Search customer name">
                            </div>
                            <select class="form-select" id="bpPattern" aria-label="Filter by pattern">
                                <option value="">All patterns</option>
                            </select>
                        </div>
                    </div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0 rq-table">
                            <thead>
                                <tr>
                                    <th class="px-3 py-3">Customer</th>
                                    <th class="px-3 py-3">Pattern</th>
                                    <th class="px-3 py-3">What changed</th>
                                    <th class="px-3 py-3 text-end">Open alerts</th>
                                    <th class="px-3 py-3">Last seen</th>
                                    <th class="px-3 py-3"><span class="visually-hidden">Actions</span></th>
                                </tr>
                            </thead>
                            <tbody id="bpTableBody">${Skeleton.rows(6)}</tbody>
                        </table>
                    </div>
                    <div class="d-flex justify-content-between align-items-center p-3" style="border-top: 1px solid #f0f0f0;">
                        <span class="text-muted" id="bpPageInfo" style="font-size: 13px;"></span>
                        <div class="d-flex gap-2">
                            <button type="button" class="btn btn-sm btn-outline-primary" id="bpPrev">Previous</button>
                            <button type="button" class="btn btn-sm btn-outline-primary" id="bpNext">Next</button>
                        </div>
                    </div>
                </div>
            </div>
        `);
    },

    async loadCustomerCodes() {
        if (Object.keys(this.customerCodes).length) return;
        try {
            const response = await API.get("/customers", { page_size: 10000 });
            (response.items || []).forEach((c, idx) => {
                this.customerCodes[c.id] = `CUST-${String(idx + 1).padStart(3, '0')}`;
            });
        } catch (err) {
            console.warn("Could not load customer codes:", err);
        }
    },

    async loadSummary() {
        let data;
        try {
            data = await API.get("/dashboard/patterns");
        } catch (error) {
            $("#bpTiles").html('<div class="kd-empty kd-empty--error"><i class="fas fa-triangle-exclamation"></i>Could not load pattern activity.</div>');
            $("#bpList").empty();
            return;
        }
        this.patterns = data.patterns || [];
        const busiest = [...this.patterns].sort((a, b) => b.customers - a.customers)[0];

        const tile = (label, value, note) => `
            <div class="rq-tile rq-tile--static">
                <span class="rq-tile__label">${label}</span>
                <strong class="rq-tile__value">${value}</strong>
                <span class="rq-tile__note">${note}</span>
            </div>`;
        $("#bpTiles").html(
            tile('Customers with a behaviour change', Number(data.customers_affected || 0).toLocaleString(), `of ${Number(data.customers_active || 0).toLocaleString()} active in the last ${data.window_days} days`)
            + tile('Most common change', busiest && busiest.customers ? escapeHtml(busiest.label) : '—',
                   busiest && busiest.customers ? `${busiest.customers.toLocaleString()} customers` : 'nothing flagged')
            + tile('Customers with enough history', Number(data.customers_with_baseline || 0).toLocaleString(), 'at least 5 transactions in the previous 90 days')
            + tile('Transactions analysed', Number(data.total_transactions || 0).toLocaleString(), `last ${data.window_days} days`)
        );
        $("#bpNote").text(`A customer is compared only with their own previous ${data.baseline_days} days, so someone who has always behaved this way is not flagged. Customers without enough history are not judged.`);

        const sorted = [...this.patterns].sort((a, b) => b.customers - a.customers);
        const max = Math.max(1, ...sorted.map(p => p.customers));
        $("#bpList").html(sorted.map(p => `
            <li>
                <button type="button" class="bp-item" data-pattern="${escapeHtml(p.id)}" aria-pressed="false">
                    <span class="bp-item__main">
                        <strong>${escapeHtml(p.label)}</strong>
                        <small>${escapeHtml(p.description)}</small>
                    </span>
                    <span class="bp-item__bar"><span class="kd-bars__track"><span style="width: ${p.customers ? Math.max(2, Math.round((p.customers / max) * 100)) : 0}%"></span></span></span>
                    <span class="bp-item__num"><strong>${p.customers.toLocaleString()}</strong><small>customers</small></span>
                    <span class="bp-item__num"><strong>${p.hit_count.toLocaleString()}</strong><small>${escapeHtml(p.hit_unit)}</small></span>
                    <span class="bp-item__num"><strong>${p.open_alerts.toLocaleString()}</strong><small>open alerts</small></span>
                </button>
            </li>`).join(''));

        $("#bpPattern").html('<option value="">All patterns</option>'
            + this.patterns.map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.label)}</option>`).join(''));
        this.syncPatternSelection();
    },

    syncPatternSelection() {
        $("#bpPattern").val(this.filters.pattern);
        $(".bp-item").each((_, el) => {
            const active = $(el).data("pattern") === this.filters.pattern;
            $(el).toggleClass("is-active", active).attr("aria-pressed", String(active));
        });
    },

    async loadRows() {
        const params = { page: this.page, page_size: this.pageSize };
        if (this.filters.pattern) params.pattern = this.filters.pattern;
        if (this.filters.q) params.q = this.filters.q;
        let data;
        try {
            data = await API.get("/dashboard/patterns/customers", params);
        } catch (error) {
            $("#bpTableBody").html('<tr><td colspan="6" class="rc-empty"><i class="fas fa-triangle-exclamation"></i><strong>Could not load customers</strong><span>Select Refresh to try again.</span></td></tr>');
            return;
        }
        this.rows = data.items;
        this.total = data.total;

        const band = (score) => (score >= 80 ? 'high' : score >= 60 ? 'medium' : 'low');
        $("#bpTableBody").html(this.rows.map(r => {
            const code = this.customerCodes[r.customer_id] || '';
            const initials = r.customer_name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '?';
            return `
                <tr>
                    <td class="px-3 py-3">
                        <div class="rc-customer">
                            <span class="rc-customer__avatar" aria-hidden="true">${escapeHtml(initials)}</span>
                            <span class="rc-customer__text"><strong>${escapeHtml(r.customer_name)}</strong><small>${escapeHtml(code)}</small></span>
                        </div>
                    </td>
                    <td class="px-3 py-3"><span class="rq-rule">${escapeHtml(r.pattern_label)}</span></td>
                    <td class="px-3 py-3 bp-evidence">${escapeHtml(r.evidence)}</td>
                    <td class="px-3 py-3 text-end">${r.open_alerts ? `<strong>${r.open_alerts.toLocaleString()}</strong> <span class="rq-score rq-score--${band(r.max_risk_score)}" title="Highest open alert score">${r.max_risk_score}</span>` : '<span class="text-muted">0</span>'}</td>
                    <td class="px-3 py-3 text-nowrap">${escapeHtml(formatDate(r.last_triggered_at))}</td>
                    <td class="px-3 py-3 text-end">
                        ${code ? `<button type="button" class="btn btn-sm rc-actions__view bp-cases-btn" data-code="${escapeHtml(code)}" data-pattern="${escapeHtml(r.pattern)}">
                            <i class="fas fa-briefcase me-1"></i>Review cases
                        </button>` : ''}
                    </td>
                </tr>`;
        }).join('') || '<tr><td colspan="6" class="rc-empty"><i class="fas fa-folder-open"></i><strong>No customers match</strong><span>No customer shows this change in the last 30 days.</span></td></tr>');

        const from = this.total ? (this.page - 1) * this.pageSize + 1 : 0;
        const to = Math.min(this.page * this.pageSize, this.total);
        $("#bpCount").text(this.total ? `Showing ${from.toLocaleString()}–${to.toLocaleString()} of ${this.total.toLocaleString()} customer and pattern pairs` : 'No matching customers');
        $("#bpPageInfo").text(this.total ? `Page ${this.page} of ${Math.max(1, Math.ceil(this.total / this.pageSize))}` : '');
        $("#bpPrev").prop("disabled", this.page <= 1);
        $("#bpNext").prop("disabled", to >= this.total);
    },

    setPattern(pattern) {
        this.filters.pattern = pattern;
        this.page = 1;
        this.syncPatternSelection();
        this.loadRows();
    },

    setupEventListeners() {
        let searchTimer;
        $("#bpSearch").on("input", () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => { this.filters.q = $("#bpSearch").val().trim(); this.page = 1; this.loadRows(); }, 300);
        });
        $("#bpPattern").on("change", () => this.setPattern($("#bpPattern").val()));
        $("#bpPrev").on("click", () => { if (this.page > 1) { this.page--; this.loadRows(); } });
        $("#bpNext").on("click", () => { this.page++; this.loadRows(); });
        $("#refreshPatternsBtn").on("click", () => { this.loadSummary(); this.loadRows(); });

        $("#mainContent").off("click.patterns")
            .on("click.patterns", ".bp-item", (e) => {
                const pattern = $(e.currentTarget).data("pattern");
                this.setPattern(this.filters.pattern === pattern ? '' : pattern);
            })
            .on("click.patterns", ".bp-cases-btn", (e) => {
                const $btn = $(e.currentTarget);
                App.navigateTo('cases', { customer: $btn.data("code"), pattern: $btn.data("pattern") });
            });
    }
};

window.Patterns = Patterns;
