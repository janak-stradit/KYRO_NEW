/**
 * KYRO Regulations - loaded regulatory sources and the obligations register.
 * The AI proposes obligations from section text; a compliance officer
 * confirms, edits or rejects each one here.
 */

const Regulations = {
    sources: [],
    obligations: [],
    total: 0,
    page: 1,
    pageSize: 15,
    filters: { status: 'PROPOSED', category: '', q: '' },

    CATEGORIES: ['REPORTING', 'RECORDKEEPING', 'CUSTOMER_IDENTIFICATION', 'PROGRAM', 'MONITORING', 'OTHER'],
    STATUS_CHIP: { PROPOSED: 'medium', CONFIRMED: 'low', REJECTED: 'high', SUPERSEDED: 'muted' },

    human(value) {
        return value ? String(value).replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase()) : '—';
    },

    canReview(permission) {
        return Auth.can(permission);
    },

    async init() {
        this.page = 1;
        this.filters = { status: 'PROPOSED', category: '', q: '' };
        this.renderLayout();
        this.setupListeners();
        await Promise.all([this.loadSources(), this.loadSummary(), this.loadObligations(), this.loadTraceability(), this.loadChanges(), this.loadRuleChanges(), this.loadNotices()]);
    },

    renderLayout() {
        const reviewer = this.canReview('regulatory.ingest');
        $("#mainContent").html(`
            <div class="kyro-page">
                <div class="kyro-page-head">
                    <div>
                        <span class="kyro-kicker">Regulatory</span>
                        <h1 class="kyro-page-title">Regulations</h1>
                        <p class="kyro-page-sub">Regulation text loaded into KYRO and the obligations drawn from it. Every obligation links back to the sentence it came from.</p>
                    </div>
                    ${reviewer ? `
                    <div class="kyro-page-actions">
                        <button class="btn btn-primary px-4" id="regRefreshBtn">
                            <i class="fas fa-rotate-right me-2"></i>Check for updates
                        </button>
                    </div>` : ''}
                </div>

                <div class="card border-0 rc-table-card mb-4">
                    <div class="rc-toolbar">
                        <div class="rc-toolbar__title">
                            <h2>Sources</h2>
                            <small class="text-muted">Pulled from eCFR; changed sections are kept as new versions</small>
                        </div>
                    </div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0 fp-table">
                            <thead>
                                <tr>
                                    <th class="px-3 py-2">Source</th>
                                    <th class="px-3 py-2 text-end">Sections</th>
                                    <th class="px-3 py-2">Last checked</th>
                                    <th class="px-3 py-2"><span class="visually-hidden">Actions</span></th>
                                </tr>
                            </thead>
                            <tbody id="regSourcesBody"><tr><td colspan="4" class="rc-empty">Loading sources...</td></tr></tbody>
                        </table>
                    </div>
                </div>

                <div class="card border-0 rc-table-card mb-4">
                    <div class="rc-toolbar">
                        <div class="rc-toolbar__title">
                            <h2>Rulemaking to watch</h2>
                            <small class="text-muted">Rules and proposed rules in the Federal Register that amend a loaded part, newest first</small>
                        </div>
                        <div class="rc-toolbar__controls">
                            <select class="form-select" id="regNoticeStatus" aria-label="Filter notices by status">
                                <option value="NEW">Not yet assessed</option>
                                <option value="ACTION_REQUIRED">Action required</option>
                                <option value="NO_ACTION">No action needed</option>
                                <option value="">All</option>
                            </select>
                        </div>
                    </div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0 fp-table reg-table">
                            <thead>
                                <tr>
                                    <th class="px-3 py-2">Published</th>
                                    <th class="px-3 py-2">Notice</th>
                                    <th class="px-3 py-2">Type</th>
                                    <th class="px-3 py-2">Key dates</th>
                                    <th class="px-3 py-2">Amends</th>
                                    <th class="px-3 py-2"><span class="visually-hidden">Actions</span></th>
                                </tr>
                            </thead>
                            <tbody id="regNoticesBody"><tr><td colspan="6" class="rc-empty">Loading...</td></tr></tbody>
                        </table>
                    </div>
                </div>

                <div class="card border-0 rc-table-card mb-4">
                    <div class="rc-toolbar">
                        <div class="rc-toolbar__title">
                            <h2>Regulatory changes</h2>
                            <small class="text-muted">Sections added, amended or removed since they were first loaded, with what each one affects</small>
                        </div>
                    </div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0 fp-table reg-table">
                            <thead>
                                <tr>
                                    <th class="px-3 py-2">Detected</th>
                                    <th class="px-3 py-2">Section</th>
                                    <th class="px-3 py-2">Change</th>
                                    <th class="px-3 py-2">Affects</th>
                                    <th class="px-3 py-2">Status</th>
                                    <th class="px-3 py-2"><span class="visually-hidden">Actions</span></th>
                                </tr>
                            </thead>
                            <tbody id="regChangesBody"><tr><td colspan="6" class="rc-empty">Loading...</td></tr></tbody>
                        </table>
                    </div>
                </div>

                <div class="card border-0 rc-table-card mb-4">
                    <div class="rc-toolbar">
                        <div class="rc-toolbar__title">
                            <h2>Rule changes</h2>
                            <small class="text-muted">A threshold change takes effect only after a second person approves it, on its effective date</small>
                        </div>
                        ${this.canReview('rules.propose') ? `
                        <div class="rc-toolbar__controls">
                            <button type="button" class="btn btn-sm rc-actions__view" id="regProposeRuleChange">
                                <i class="fas fa-plus me-1"></i>Propose a change
                            </button>
                        </div>` : ''}
                    </div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0 fp-table reg-table">
                            <thead>
                                <tr>
                                    <th class="px-3 py-2">Setting</th>
                                    <th class="px-3 py-2">Change</th>
                                    <th class="px-3 py-2">Effective</th>
                                    <th class="px-3 py-2">Impact over 90 days</th>
                                    <th class="px-3 py-2">Proposed by</th>
                                    <th class="px-3 py-2">Status</th>
                                    <th class="px-3 py-2"><span class="visually-hidden">Actions</span></th>
                                </tr>
                            </thead>
                            <tbody id="regRuleChangesBody"><tr><td colspan="7" class="rc-empty">Loading...</td></tr></tbody>
                        </table>
                    </div>
                </div>

                <div class="card border-0 rc-table-card">
                    <div class="rc-toolbar">
                        <div class="rc-toolbar__title">
                            <h2>Obligations register</h2>
                            <small class="text-muted" id="regCountLabel">&nbsp;</small>
                        </div>
                        <div class="rc-toolbar__controls">
                            <div class="rc-search">
                                <i class="fas fa-search"></i>
                                <input type="search" class="form-control" id="regSearch" placeholder="Search obligations or section" aria-label="Search obligations">
                            </div>
                            <select class="form-select" id="regStatus" aria-label="Filter by status">
                                <option value="PROPOSED">Awaiting review</option>
                                <option value="CONFIRMED">Confirmed</option>
                                <option value="REJECTED">Rejected</option>
                                <option value="SUPERSEDED">Superseded</option>
                                <option value="">All statuses</option>
                            </select>
                            <select class="form-select" id="regCategory" aria-label="Filter by category">
                                <option value="">All categories</option>
                                ${this.CATEGORIES.map(c => `<option value="${c}">${escapeHtml(this.human(c))}</option>`).join('')}
                            </select>
                        </div>
                    </div>
                    <div id="regSummary"></div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0 fp-table reg-table">
                            <thead>
                                <tr>
                                    <th class="px-3 py-2">Section</th>
                                    <th class="px-3 py-2">Who</th>
                                    <th class="px-3 py-2">Must</th>
                                    <th class="px-3 py-2">By when</th>
                                    <th class="px-3 py-2">Category</th>
                                    <th class="px-3 py-2">Status</th>
                                    <th class="px-3 py-2"><span class="visually-hidden">Actions</span></th>
                                </tr>
                            </thead>
                            <tbody id="regObligationsBody"><tr><td colspan="7" class="rc-empty">Loading obligations...</td></tr></tbody>
                        </table>
                    </div>
                    <div class="d-flex justify-content-between align-items-center p-3" style="border-top: 1px solid #f0f0f0;">
                        <span class="text-muted" id="regPageInfo" style="font-size: 13px;"></span>
                        <div class="d-flex gap-2">
                            <button type="button" class="btn btn-sm btn-outline-primary" id="regPrev">Previous</button>
                            <button type="button" class="btn btn-sm btn-outline-primary" id="regNext">Next</button>
                        </div>
                    </div>
                </div>

                <div class="card border-0 rc-table-card mt-4">
                    <div class="rc-toolbar">
                        <div class="rc-toolbar__title">
                            <h2>Coverage and traceability</h2>
                            <small class="text-muted">Confirmed obligations, the KYRO control that meets each one, and its live setting</small>
                        </div>
                        <div class="rc-toolbar__controls">
                            ${this.canReview('mappings.manage') ? `
                            <button type="button" class="btn btn-sm rc-actions__view" id="regProposeMappings">
                                <i class="fas fa-wand-magic-sparkles me-1"></i>Propose mappings
                            </button>` : ''}
                            <button type="button" class="btn btn-sm rc-actions__view" id="regExportTrace">
                                <i class="fas fa-file-arrow-down me-1"></i>Export CSV
                            </button>
                        </div>
                    </div>
                    <div id="regTraceSummary"></div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0 fp-table reg-table">
                            <thead>
                                <tr>
                                    <th class="px-3 py-2">Section</th>
                                    <th class="px-3 py-2">Obligation</th>
                                    <th class="px-3 py-2">Control</th>
                                    <th class="px-3 py-2">Live setting</th>
                                    <th class="px-3 py-2 text-end">Alerts</th>
                                    <th class="px-3 py-2">Status</th>
                                    <th class="px-3 py-2"><span class="visually-hidden">Actions</span></th>
                                </tr>
                            </thead>
                            <tbody id="regTraceBody"><tr><td colspan="7" class="rc-empty">Loading...</td></tr></tbody>
                        </table>
                    </div>
                </div>
            </div>
        `);
    },

    setupListeners() {
        let searchTimer;
        $("#regSearch").on("input", () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => { this.filters.q = $("#regSearch").val().trim(); this.page = 1; this.loadObligations(); }, 300);
        });
        $("#regStatus, #regCategory").on("change", () => {
            this.filters.status = $("#regStatus").val();
            this.filters.category = $("#regCategory").val();
            this.page = 1;
            this.loadObligations();
        });
        $("#regPrev").on("click", () => { if (this.page > 1) { this.page--; this.loadObligations(); } });
        $("#regNext").on("click", () => { if (this.page * this.pageSize < this.total) { this.page++; this.loadObligations(); } });

        $("#regRefreshBtn").on("click", async (e) => {
            const $btn = $(e.currentTarget).prop("disabled", true);
            try {
                const [runs, notices] = await Promise.all([
                    API.post('/regulatory/ingest'),
                    API.post('/changes/notices/sync').catch(() => null)
                ]);
                const changed = runs.reduce((n, r) => n + r.sections_added + r.sections_changed + r.sections_removed, 0);
                const failed = runs.filter(r => r.status === 'FAILED').length;
                showToast(failed ? 'warning' : 'success', failed
                    ? `${failed} source(s) could not be reached; existing text was kept.`
                    : changed ? `${changed} section(s) added or changed.` : 'All sources are up to date.');
                if (notices && notices.notices_added) showToast('info', `${notices.notices_added} new Federal Register notice(s).`);
                this.loadNotices();
                await Promise.all([this.loadSources(), this.loadSummary(), this.loadObligations(), this.loadChanges(), this.loadTraceability()]);
            } catch (xhr) { /* API layer already reported it */ }
            $btn.prop("disabled", false);
        });

        $("#regProposeMappings").on("click", async (e) => {
            const $btn = $(e.currentTarget).prop("disabled", true);
            try {
                const r = await API.post('/regulatory/mappings/propose');
                showToast('success', r.obligations_processed
                    ? `${r.mappings_proposed} mapping(s) proposed for ${r.obligations_processed} obligation(s).`
                    : 'Every confirmed obligation already has a mapping or a proposal.');
                await this.loadTraceability();
            } catch (xhr) { /* API layer already reported it */ }
            $btn.prop("disabled", false);
        });

        $("#regExportTrace").on("click", async () => {
            try {
                const response = await fetch(`${API.baseUrl}/regulatory/traceability?format=csv`, { headers: API.getHeaders() });
                if (!response.ok) throw new Error(response.status);
                downloadBlob(await response.blob(), 'kyro-traceability-matrix.csv');
            } catch (error) {
                showToast('error', 'Could not export the traceability matrix.');
            }
        });

        $("#regProposeRuleChange").on("click", () => this.showProposeModal());
        $("#regNoticeStatus").on("change", () => this.loadNotices());

        $("#mainContent").off("click.reg")
            .on("click.reg", ".reg-notice-assess", async (e) => {
                const $btn = $(e.currentTarget).prop("disabled", true);
                try {
                    await API.put(`/changes/notices/${$btn.data("id")}/assess`, { status: $btn.data("status") });
                    this.loadNotices();
                } catch (xhr) { $btn.prop("disabled", false); }
            })
            .on("click.reg", ".reg-change-btn", (e) => this.showChangeModal($(e.currentTarget).data("id")))
            .on("click.reg", ".reg-rule-decide", (e) => this.decideRuleChange($(e.currentTarget)))
            .on("click.reg", ".reg-map-decide", async (e) => {
                const $btn = $(e.currentTarget).prop("disabled", true);
                try {
                    await API.put(`/regulatory/mappings/${$btn.data("id")}/review`, { decision: $btn.data("decision") });
                    await this.loadTraceability();
                } catch (xhr) { $btn.prop("disabled", false); }
            })
            .on("change.reg", ".reg-map-select", async (e) => {
                const $select = $(e.currentTarget);
                if (!$select.val()) return;
                try {
                    await API.post('/regulatory/mappings', { obligation_id: $select.data("id"), control_code: $select.val() });
                    showToast('success', 'Control mapped.');
                    await this.loadTraceability();
                } catch (xhr) { $select.val(''); }
            })
            .on("click.reg", ".reg-extract-btn", (e) => this.extract($(e.currentTarget)))
            .on("click.reg", ".reg-review-btn", (e) => {
                const item = this.obligations.find(o => o.id === $(e.currentTarget).data("id"));
                if (item) this.showReviewModal(item);
            });
    },

    async loadSources() {
        try {
            this.sources = await API.get('/regulatory/sources');
            const counts = await Promise.all(this.sources.map(s =>
                API.get('/regulatory/sections', { source_id: s.id, page_size: 1 }).then(p => p.total).catch(() => null)));
            const reviewer = this.canReview('obligations.manage');
            $("#regSourcesBody").html(this.sources.map((s, i) => `
                <tr>
                    <td class="px-3 py-2"><strong>${escapeHtml(s.name)}</strong></td>
                    <td class="px-3 py-2 text-end">${counts[i] == null ? '—' : counts[i]}</td>
                    <td class="px-3 py-2 text-muted">${s.last_success_at ? escapeHtml(formatDateTime(s.last_success_at)) : 'Not loaded yet'}</td>
                    <td class="px-3 py-2 text-end">${reviewer && counts[i] ? `
                        <button type="button" class="btn btn-sm rc-actions__view reg-extract-btn" data-id="${escapeHtml(s.id)}">
                            <i class="fas fa-wand-magic-sparkles me-1"></i>Propose obligations
                        </button>` : ''}</td>
                </tr>`).join('') || '<tr><td colspan="4" class="rc-empty">No sources configured.</td></tr>');
        } catch (error) {
            $("#regSourcesBody").html('<tr><td colspan="4" class="rc-empty">Could not load sources.</td></tr>');
        }
    },

    async loadSummary() {
        try {
            const s = await API.get('/regulatory/obligations/summary');
            const n = (k) => s.by_status[k] || 0;
            $("#regSummary").html(`
                <div class="reg-summary">
                    <div class="fp-summary">
                        <div><span>Awaiting review</span><strong>${n('PROPOSED')}</strong></div>
                        <div><span>Confirmed</span><strong>${n('CONFIRMED')}</strong></div>
                        <div><span>Rejected</span><strong>${n('REJECTED')}</strong></div>
                        <div><span>Superseded by a rule change</span><strong>${n('SUPERSEDED')}</strong></div>
                        <div><span>Quote not found in source</span><strong>${s.unverified_quotes}</strong></div>
                    </div>
                </div>`);
        } catch (error) { $("#regSummary").empty(); }
    },

    async loadObligations() {
        const params = { page: this.page, page_size: this.pageSize };
        if (this.filters.status) params.status_filter = this.filters.status;
        if (this.filters.category) params.category = this.filters.category;
        if (this.filters.q) params.q = this.filters.q;
        try {
            const data = await API.get('/regulatory/obligations', params);
            this.obligations = data.items;
            this.total = data.total;
        } catch (error) {
            $("#regObligationsBody").html('<tr><td colspan="7" class="rc-empty">Could not load obligations.</td></tr>');
            return;
        }

        const reviewer = this.canReview('obligations.manage');
        const mock = this.obligations.some(o => o.extracted_by === 'mock');
        const rows = this.obligations.map(o => `
            <tr>
                <td class="px-3 py-2 text-nowrap"><strong>${escapeHtml(o.section_ref)}</strong><br><small class="text-muted">as amended ${escapeHtml(o.section_version)}</small></td>
                <td class="px-3 py-2 reg-cell">${escapeHtml(o.obligated_party)}</td>
                <td class="px-3 py-2 reg-cell reg-cell--wide">${escapeHtml(o.action)}${o.quote_verified ? '' : `
                    <br><span class="cd-chip cd-chip--high" title="The supporting sentence is not in the section text">Unverified quote</span>`}</td>
                <td class="px-3 py-2 reg-cell">${escapeHtml(o.deadline || '—')}</td>
                <td class="px-3 py-2 text-nowrap">${escapeHtml(this.human(o.category))}</td>
                <td class="px-3 py-2"><span class="cd-chip cd-chip--${this.STATUS_CHIP[o.status] || 'muted'}">${escapeHtml(this.human(o.status))}</span></td>
                <td class="px-3 py-2 text-end">
                    <button type="button" class="btn btn-sm rc-actions__view reg-review-btn" data-id="${escapeHtml(o.id)}">
                        ${reviewer && o.status !== 'SUPERSEDED' ? 'Review' : 'View'}
                    </button>
                </td>
            </tr>`).join('');

        $("#regObligationsBody").html((mock ? `
            <tr><td colspan="7" class="fp-empty">These proposals come from the built-in mock extractor (it picks out sentences with "shall" or "must"), not from an AI model. Expect rough wording; review before relying on them.</td></tr>` : '')
            + (rows || '<tr><td colspan="7" class="rc-empty">No obligations match these filters.</td></tr>'));

        const from = this.total ? (this.page - 1) * this.pageSize + 1 : 0;
        const to = Math.min(this.page * this.pageSize, this.total);
        $("#regCountLabel").text(`${this.total} obligation${this.total === 1 ? '' : 's'}`);
        $("#regPageInfo").text(this.total ? `${from}–${to} of ${this.total}` : '');
        $("#regPrev").prop("disabled", this.page <= 1);
        $("#regNext").prop("disabled", to >= this.total);
    },

    // ── Regulatory changes and rule changes (Phase 11.5) ─────────────────

    NUMERIC_SETTINGS: {
        AMOUNT_THRESHOLD: 'Amount threshold (R001)',
        VELOCITY_DAILY_LIMIT: 'Transactions per day (R002)',
        VELOCITY_HOURLY_LIMIT: 'Transactions per hour (R003)',
        RAPID_SUCCESSION_WINDOW_SECONDS: 'Rapid succession window, seconds (R010)',
        ALERT_THRESHOLD: 'Score that opens an alert',
        EDD_THRESHOLD: 'Score that recommends enhanced due diligence'
    },

    async loadNotices() {
        const status = $("#regNoticeStatus").val();
        let notices;
        try {
            notices = await API.get('/changes/notices', status ? { status_filter: status } : {});
        } catch (error) {
            $("#regNoticesBody").html('<tr><td colspan="6" class="rc-empty">Could not load notices.</td></tr>');
            return;
        }
        const reviewer = this.canReview('changes.assess');
        const today = new Date().toISOString().slice(0, 10);
        const statusChip = { ACTION_REQUIRED: ['high', 'Action required'], NO_ACTION: ['muted', 'No action needed'], CLOSED: ['low', 'Closed'] };
        $("#regNoticesBody").html(notices.map(n => {
            const dates = [
                n.effective_on ? `Effective ${formatDate(n.effective_on)}${n.effective_on > today ? ' (upcoming)' : ''}` : null,
                n.comments_close_on ? `Comments close ${formatDate(n.comments_close_on)}` : null
            ].filter(Boolean).join('<br>') || '—';
            const assessed = statusChip[n.status];
            return `
            <tr>
                <td class="px-3 py-2 text-nowrap">${escapeHtml(formatDate(n.publication_date))}</td>
                <td class="px-3 py-2 reg-cell reg-cell--wide">
                    <a href="${/^https:\/\//.test(n.url) ? escapeHtml(n.url) : '#'}" target="_blank" rel="noopener noreferrer"><strong>${escapeHtml(n.title)}</strong></a>
                    <br><small class="text-muted">${escapeHtml(n.action || '')} ${escapeHtml(n.agencies.slice(-1)[0] || '')}</small>
                </td>
                <td class="px-3 py-2"><span class="cd-chip cd-chip--${n.notice_type === 'Rule' ? 'high' : 'medium'}">${n.notice_type === 'Rule' ? 'Final rule' : escapeHtml(n.notice_type)}</span></td>
                <td class="px-3 py-2 text-nowrap">${dates}</td>
                <td class="px-3 py-2 text-nowrap">${escapeHtml(n.matched_parts.join(', '))}</td>
                <td class="px-3 py-2 text-end text-nowrap">${assessed ? `<span class="cd-chip cd-chip--${assessed[0]}">${assessed[1]}</span>` : (reviewer ? `
                    <button type="button" class="btn btn-sm rc-actions__view reg-notice-assess" data-id="${escapeHtml(n.id)}" data-status="ACTION_REQUIRED">Action required</button>
                    <button type="button" class="btn btn-sm rc-actions__icon reg-notice-assess" data-id="${escapeHtml(n.id)}" data-status="NO_ACTION" title="No action needed" aria-label="No action needed"><i class="fas fa-check"></i></button>` : '')}</td>
            </tr>`;
        }).join('') || `<tr><td colspan="6" class="rc-empty">${status === 'NEW' ? 'Nothing waiting to be assessed. Select "Check for updates" to fetch the latest notices.' : 'No notices with this status.'}</td></tr>`);
    },

    async loadChanges() {
        let changes;
        try {
            changes = await API.get('/changes/regulatory');
        } catch (error) {
            $("#regChangesBody").html('<tr><td colspan="6" class="rc-empty">Could not load regulatory changes.</td></tr>');
            return;
        }
        this.regulatoryChanges = changes;
        const typeChip = { ADDED: 'low', AMENDED: 'medium', REMOVED: 'high' };
        const statusChip = { OPEN: 'medium', ACTION_REQUIRED: 'high', NO_ACTION: 'muted', CLOSED: 'low' };
        $("#regChangesBody").html(changes.map(c => {
            const a = c.affected || {};
            const affects = [
                (a.obligations || []).length ? `${a.obligations.length} obligation${a.obligations.length === 1 ? '' : 's'}` : null,
                (a.controls || []).length ? `controls ${a.controls.map(x => x.code).join(', ')}` : null
            ].filter(Boolean).join('; ') || 'Nothing mapped yet';
            return `
            <tr>
                <td class="px-3 py-2 text-nowrap">${escapeHtml(formatDate(c.detected_at))}</td>
                <td class="px-3 py-2"><strong>${escapeHtml(c.section_ref)}</strong><br><small class="text-muted">${escapeHtml(c.heading || '')}</small></td>
                <td class="px-3 py-2"><span class="cd-chip cd-chip--${typeChip[c.change_type]}">${escapeHtml(this.human(c.change_type))}</span></td>
                <td class="px-3 py-2 reg-cell">${escapeHtml(affects)}</td>
                <td class="px-3 py-2"><span class="cd-chip cd-chip--${statusChip[c.status] || 'muted'}">${escapeHtml(this.human(c.status))}</span></td>
                <td class="px-3 py-2 text-end"><button type="button" class="btn btn-sm rc-actions__view reg-change-btn" data-id="${escapeHtml(c.id)}">Review</button></td>
            </tr>`;
        }).join('') || '<tr><td colspan="6" class="rc-empty">No changes detected. A change appears here when "Check for updates" finds different text for a loaded section.</td></tr>');
    },

    async showChangeModal(id) {
        let c;
        try {
            c = await API.get(`/changes/regulatory/${id}`);
        } catch (error) { return; }
        const a = c.affected || {};
        const reviewer = this.canReview('changes.assess');
        const keys = (a.config_keys || []).filter(k => this.NUMERIC_SETTINGS[k]);
        $("#regChangeModal").remove();
        $("body").append(`
            <div class="modal fade" id="regChangeModal" tabindex="-1" aria-labelledby="regChangeTitle" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered modal-lg modal-dialog-scrollable">
                    <div class="modal-content kx-modal">
                        <div class="modal-header">
                            <div>
                                <h5 class="modal-title" id="regChangeTitle">${escapeHtml(c.section_ref)} ${escapeHtml(this.human(c.change_type).toLowerCase())}</h5>
                                <small class="text-muted">${escapeHtml(c.heading || '')} &middot; ${c.old_version ? `version ${escapeHtml(c.old_version)}` : 'new'}${c.new_version ? ` &rarr; ${escapeHtml(c.new_version)}` : ''}</small>
                            </div>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <div class="kx-label">What changed in the text</div>
                            <div class="reg-diff">
                                ${c.diff.map(d => `<p class="reg-diff__${d.op}"><span>${d.op === 'added' ? 'Added' : 'Removed'}</span>${escapeHtml(d.text)}</p>`).join('') || '<p class="text-muted mb-0">No text differences.</p>'}
                            </div>

                            <div class="kx-label mt-3">What it affects</div>
                            ${(a.obligations || []).length ? `<ul class="reg-affects">${a.obligations.map(o => `<li><strong>${escapeHtml(o.obligated_party)}</strong> must ${escapeHtml(o.action)} <span class="text-muted">(${escapeHtml(this.human(o.status).toLowerCase())}; now superseded, needs re-extraction)</span></li>`).join('')}</ul>` : '<p class="kx-note mt-0">No obligations had been recorded for this section.</p>'}
                            ${(a.controls || []).length ? `<p class="mb-1">Controls: ${a.controls.map(x => `<strong>${escapeHtml(x.code)}</strong> ${escapeHtml(x.name)}`).join(', ')}</p>` : ''}
                            ${(a.config_keys || []).length ? `<p class="mb-0">Rule settings: ${escapeHtml(a.config_keys.join(', '))}</p>` : ''}

                            ${reviewer ? `
                            <label class="kx-label mt-3" for="regChangeNotes">Assessment notes</label>
                            <textarea class="form-control" id="regChangeNotes" rows="2">${escapeHtml(c.assessment_notes || '')}</textarea>` : (c.assessment_notes ? `<p class="mt-3 mb-0">${escapeHtml(c.assessment_notes)}</p>` : '')}
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-primary" data-bs-dismiss="modal">Close</button>
                            ${reviewer ? `
                            ${keys.length && this.canReview('rules.propose') ? `<button type="button" class="btn btn-outline-primary" id="regChangePropose">Propose rule change</button>` : ''}
                            <button type="button" class="btn btn-outline-primary reg-assess" data-status="NO_ACTION">No action needed</button>
                            <button type="button" class="btn btn-primary reg-assess" data-status="ACTION_REQUIRED">Action required</button>` : ''}
                        </div>
                    </div>
                </div>
            </div>`);
        const modalEl = document.getElementById('regChangeModal');
        new bootstrap.Modal(modalEl).show();

        $(".reg-assess").on("click", async (e) => {
            $(".reg-assess").prop("disabled", true);
            try {
                await API.put(`/changes/regulatory/${c.id}/assess`, { status: $(e.currentTarget).data("status"), notes: $("#regChangeNotes").val().trim() || null });
                closeModalSafely(modalEl);
                showToast('success', 'Assessment recorded.');
                this.loadChanges();
            } catch (xhr) { $(".reg-assess").prop("disabled", false); }
        });
        $("#regChangePropose").on("click", () => {
            $(modalEl).one("hidden.bs.modal", () => this.showProposeModal({ key: keys[0], changeId: c.id, sectionRef: c.section_ref }));
            closeModalSafely(modalEl);
        });
        $(modalEl).on("hidden.bs.modal", function() { setTimeout(() => $(this).remove(), 0); });
    },

    backtestText(b) {
        if (!b) return '—';
        if (!b.available) return 'Not backtested';
        const diff = b.difference;
        return `${b.transactions_flagged_now.toLocaleString()} → ${b.transactions_flagged_after.toLocaleString()} transactions flagged (${diff > 0 ? '+' : ''}${diff.toLocaleString()})`;
    },

    async loadRuleChanges() {
        let changes;
        try {
            changes = await API.get('/changes/rules');
        } catch (error) {
            $("#regRuleChangesBody").html('<tr><td colspan="7" class="rc-empty">Could not load rule changes.</td></tr>');
            return;
        }
        const me = (Auth.getUser() || {}).id;
        const reviewer = this.canReview('rules.approve');
        const chip = { PENDING_APPROVAL: 'medium', APPROVED: 'medium', ACTIVE: 'low', REJECTED: 'high', CANCELLED: 'muted' };
        const label = { PENDING_APPROVAL: 'Awaiting approval', APPROVED: 'Approved, scheduled', ACTIVE: 'In effect', REJECTED: 'Rejected', CANCELLED: 'Withdrawn' };
        $("#regRuleChangesBody").html(changes.map(c => {
            const b = c.backtest;
            const mine = c.proposed_by === me;
            let actions = '';
            if (c.status === 'PENDING_APPROVAL' && (mine ? this.canReview('rules.propose') : reviewer)) {
                actions = mine
                    ? `<button type="button" class="btn btn-sm rc-actions__view reg-rule-decide" data-id="${escapeHtml(c.id)}" data-decision="CANCELLED">Withdraw</button>`
                    : `<button type="button" class="btn btn-sm rc-actions__view reg-rule-decide" data-id="${escapeHtml(c.id)}" data-decision="APPROVED">Approve</button>
                       <button type="button" class="btn btn-sm rc-actions__icon reg-rule-decide" data-id="${escapeHtml(c.id)}" data-decision="REJECTED" title="Reject" aria-label="Reject change"><i class="fas fa-xmark"></i></button>`;
            }
            return `
            <tr>
                <td class="px-3 py-2"><strong>${escapeHtml(this.NUMERIC_SETTINGS[c.key] || c.key)}</strong><br><small class="text-muted">${escapeHtml(c.jurisdiction === 'GLOBAL' ? 'All jurisdictions' : c.jurisdiction)}</small></td>
                <td class="px-3 py-2 text-nowrap">${escapeHtml(String(c.previous_value.value))} &rarr; <strong>${escapeHtml(String(c.proposed_value.value))}</strong></td>
                <td class="px-3 py-2 text-nowrap">${escapeHtml(formatDate(c.effective_from))}</td>
                <td class="px-3 py-2 reg-cell">${escapeHtml(this.backtestText(b))}${b && b.available && !b.passes_recall_floor ? `
                    <br><span class="cd-chip cd-chip--high">Would miss ${b.confirmed_true_positive_customers_missed} confirmed true-positive customer${b.confirmed_true_positive_customers_missed === 1 ? '' : 's'}</span>` : ''}</td>
                <td class="px-3 py-2 reg-cell">${escapeHtml(c.proposed_by_name || '')}${mine ? ' (you)' : ''}<br><small class="text-muted" title="${escapeHtml(c.reason)}">${escapeHtml(c.reason.length > 60 ? c.reason.slice(0, 60) + '…' : c.reason)}</small></td>
                <td class="px-3 py-2"><span class="cd-chip cd-chip--${chip[c.status]}">${label[c.status]}</span>${c.reviewed_by_name ? `<br><small class="text-muted">by ${escapeHtml(c.reviewed_by_name)}</small>` : (c.status === 'PENDING_APPROVAL' && mine ? '<br><small class="text-muted">needs someone else</small>' : '')}</td>
                <td class="px-3 py-2 text-end text-nowrap">${actions}</td>
            </tr>`;
        }).join('') || '<tr><td colspan="7" class="rc-empty">No rule changes have been proposed.</td></tr>');
    },

    async decideRuleChange($btn) {
        const decision = $btn.data("decision");
        let notes = null;
        if (decision === 'REJECTED') {
            notes = window.prompt('Why is this change rejected? The reason is kept with the change.');
            if (!notes || !notes.trim()) return;
        }
        $btn.prop("disabled", true);
        try {
            await API.put(`/changes/rules/${$btn.data("id")}/review`, { decision, notes });
            showToast('success', { APPROVED: 'Change approved.', REJECTED: 'Change rejected.', CANCELLED: 'Change withdrawn.' }[decision]);
            await Promise.all([this.loadRuleChanges(), this.loadTraceability()]);
        } catch (xhr) { $btn.prop("disabled", false); }
    },

    async showProposeModal(preset = {}) {
        let effective;
        try {
            effective = await API.get('/rule-configs/effective');
        } catch (error) { return; }
        const today = new Date().toISOString().slice(0, 10);
        $("#regProposeModal").remove();
        $("body").append(`
            <div class="modal fade" id="regProposeModal" tabindex="-1" aria-labelledby="regProposeTitle" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content kx-modal">
                        <div class="modal-header">
                            <div>
                                <h5 class="modal-title" id="regProposeTitle">Propose a rule change</h5>
                                <small class="text-muted">${preset.sectionRef ? `For the change to ${escapeHtml(preset.sectionRef)}. ` : ''}Someone else must approve it before it takes effect.</small>
                            </div>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <label class="kx-label" for="rcKey">Setting</label>
                            <select class="form-select mb-1" id="rcKey">
                                ${Object.entries(this.NUMERIC_SETTINGS).map(([k, l]) => `<option value="${k}" ${k === preset.key ? 'selected' : ''}>${escapeHtml(l)}</option>`).join('')}
                            </select>
                            <p class="kx-note mt-0 mb-3" id="rcCurrent"></p>
                            <div class="row g-3 mb-3">
                                <div class="col-6">
                                    <label class="kx-label" for="rcValue">New value</label>
                                    <input type="number" class="form-control" id="rcValue" min="0" step="any">
                                </div>
                                <div class="col-6">
                                    <label class="kx-label" for="rcEffective">Effective from</label>
                                    <input type="date" class="form-control" id="rcEffective" min="${today}" value="${today}">
                                </div>
                            </div>
                            <label class="kx-label" for="rcReason">Reason</label>
                            <textarea class="form-control" id="rcReason" rows="3" placeholder="Why the change is needed and what it is based on"></textarea>
                            <div class="reg-backtest d-none" id="rcBacktest"></div>
                            <div class="text-danger small mt-2 d-none" id="rcError" role="alert"></div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-primary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-outline-primary" id="rcPreview">Preview impact</button>
                            <button type="button" class="btn btn-primary" id="rcSubmit">Send for approval</button>
                        </div>
                    </div>
                </div>
            </div>`);
        const modalEl = document.getElementById('regProposeModal');
        new bootstrap.Modal(modalEl).show();

        const showCurrent = () => $("#rcCurrent").text(`Current value: ${effective[$("#rcKey").val()]}`);
        showCurrent();
        $("#rcKey").on("change", () => { showCurrent(); $("#rcBacktest").addClass("d-none"); });
        const fail = (message) => $("#rcError").text(message).removeClass("d-none");
        const value = () => { const v = parseFloat($("#rcValue").val()); return isFinite(v) ? v : null; };
        const detail = (xhr, fallback) => { const d = xhr && xhr.responseJSON && xhr.responseJSON.detail; return typeof d === 'string' ? d : fallback; };

        $("#rcPreview").on("click", async () => {
            if (value() == null) return fail('Enter the new value first.');
            $("#rcError").addClass("d-none");
            try {
                const r = await API.post('/changes/rules/backtest', { key: $("#rcKey").val(), value: value() });
                const b = r.backtest;
                $("#rcBacktest").removeClass("d-none").html(b.available ? `
                    <strong>Over the last ${b.window_days} days</strong>
                    <p>${escapeHtml(this.backtestText(b))}, across ${b.customers_affected.toLocaleString()} customers.</p>
                    <p class="${b.passes_recall_floor ? '' : 'text-danger'}">${b.passes_recall_floor
                        ? 'No customer with a confirmed true positive on this rule would stop being flagged.'
                        : `${b.confirmed_true_positive_customers_missed} customer(s) with a confirmed true positive would stop being flagged.`}</p>`
                    : `<p class="mb-0">${escapeHtml(b.reason)}</p>`);
            } catch (xhr) { fail(detail(xhr, 'Could not run the backtest.')); }
        });

        $("#rcSubmit").on("click", async () => {
            const reason = $("#rcReason").val().trim();
            if (value() == null) return fail('Enter the new value.');
            if (reason.length < 10) return fail('Give a reason of at least a sentence.');
            const $btn = $("#rcSubmit").prop("disabled", true);
            try {
                await API.post('/changes/rules', {
                    key: $("#rcKey").val(), value: value(), reason, effective_from: $("#rcEffective").val() || today,
                    regulatory_change_id: preset.changeId || null
                });
                closeModalSafely(modalEl);
                showToast('success', 'Change sent for approval.');
                this.loadRuleChanges();
            } catch (xhr) {
                fail(detail(xhr, 'Could not propose the change.'));
                $btn.prop("disabled", false);
            }
        });
        $(modalEl).on("hidden.bs.modal", function() { setTimeout(() => $(this).remove(), 0); });
    },

    async loadTraceability() {
        let data;
        try {
            [data, this.controls] = await Promise.all([
                API.get('/regulatory/traceability'),
                this.controls ? Promise.resolve(this.controls) : API.get('/regulatory/controls')
            ]);
        } catch (error) {
            $("#regTraceBody").html('<tr><td colspan="7" class="rc-empty">Could not load the traceability matrix.</td></tr>');
            return;
        }
        const s = data.summary;
        const reviewer = this.canReview('mappings.manage');
        const chip = { CONFIRMED: 'low', PROPOSED: 'medium', GAP: 'high' };
        const label = { CONFIRMED: 'Covered', PROPOSED: 'Proposed', GAP: 'Gap' };

        $("#regTraceSummary").html(`
            <div class="reg-summary">
                <div class="fp-summary">
                    <div><span>Confirmed obligations</span><strong>${s.confirmed_obligations}</strong></div>
                    <div><span>Covered by a control</span><strong>${s.covered}</strong></div>
                    <div><span>Mapping awaiting review</span><strong>${s.awaiting_mapping_review}</strong></div>
                    <div><span>Gaps</span><strong>${s.gaps}</strong></div>
                    <div><span>Rules not tied to an obligation</span><strong>${s.rules_without_obligation.length}</strong></div>
                </div>
                ${s.rules_without_obligation.length ? `
                <p class="kx-note mb-0">Not yet tied to a confirmed obligation: ${escapeHtml(s.rules_without_obligation.join(', '))}. These are internal policy or still need an obligation.</p>` : ''}
            </div>`);

        const setting = (row) => {
            const entries = Object.entries(row.rule_config || {});
            return entries.length ? entries.map(([k, v]) => `${escapeHtml(k)} = ${escapeHtml(Array.isArray(v) ? `${v.length} values` : String(v))}`).join('<br>') : '—';
        };
        const actions = (row) => {
            if (!reviewer) return '';
            if (row.mapping_status === 'PROPOSED') return `
                <button type="button" class="btn btn-sm rc-actions__view reg-map-decide" data-id="${escapeHtml(row.mapping_id)}" data-decision="CONFIRMED">Confirm</button>
                <button type="button" class="btn btn-sm rc-actions__icon reg-map-decide" data-id="${escapeHtml(row.mapping_id)}" data-decision="REJECTED" title="Reject mapping" aria-label="Reject mapping"><i class="fas fa-xmark"></i></button>`;
            if (row.mapping_status === 'GAP') return `
                <select class="form-select form-select-sm reg-map-select" data-id="${escapeHtml(row.obligation_id)}" aria-label="Map a control">
                    <option value="">Map a control...</option>
                    ${this.controls.map(c => `<option value="${escapeHtml(c.code)}">${escapeHtml(c.code)} — ${escapeHtml(c.name)}</option>`).join('')}
                </select>`;
            return '';
        };

        $("#regTraceBody").html(data.rows.map(row => `
            <tr>
                <td class="px-3 py-2 text-nowrap"><strong>${escapeHtml(row.section_ref)}</strong><br><small class="text-muted">as amended ${escapeHtml(row.section_version)}</small></td>
                <td class="px-3 py-2 reg-cell reg-cell--wide"><strong>${escapeHtml(row.obligated_party)}</strong> must ${escapeHtml(row.action)}</td>
                <td class="px-3 py-2 reg-cell">${row.control_code ? `<strong>${escapeHtml(row.control_code)}</strong> ${escapeHtml(row.control_name)}` : '<span class="text-muted">No control mapped</span>'}</td>
                <td class="px-3 py-2 reg-cell">${setting(row)}</td>
                <td class="px-3 py-2 text-end">${row.alerts == null ? '—' : row.alerts}</td>
                <td class="px-3 py-2"><span class="cd-chip cd-chip--${chip[row.mapping_status]}">${label[row.mapping_status]}</span></td>
                <td class="px-3 py-2 text-end text-nowrap">${actions(row)}</td>
            </tr>`).join('') || '<tr><td colspan="7" class="rc-empty">Confirm obligations in the register above, then propose mappings to see coverage here.</td></tr>');
    },

    async extract($btn) {
        const original = $btn.html();
        $btn.prop("disabled", true).text('Working...');
        try {
            const r = await API.post(`/regulatory/obligations/extract?source_id=${encodeURIComponent($btn.data("id"))}`);
            showToast('success', r.sections_processed
                ? `${r.obligations_proposed} obligation(s) proposed from ${r.sections_processed} section(s).`
                : 'Every section of this source already has obligations.');
            await Promise.all([this.loadSummary(), this.loadObligations()]);
        } catch (xhr) { /* API layer already reported it (e.g. AI features are disabled) */ }
        $btn.prop("disabled", false).html(original);
    },

    showReviewModal(o) {
        const editable = this.canReview('obligations.manage') && o.status !== 'SUPERSEDED';
        const dis = editable ? '' : 'disabled';
        const html = `
            <div class="modal fade" id="regReviewModal" tabindex="-1" aria-labelledby="regReviewTitle" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered modal-lg">
                    <div class="modal-content kx-modal">
                        <div class="modal-header">
                            <div>
                                <h5 class="modal-title" id="regReviewTitle">${escapeHtml(o.section_ref)}</h5>
                                <small class="text-muted">As amended ${escapeHtml(o.section_version)} &middot; ${escapeHtml(this.human(o.status))} &middot; proposed by ${escapeHtml(o.extracted_by === 'mock' ? 'the mock extractor' : 'AI')}</small>
                            </div>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <div class="kx-label">Source text</div>
                            <blockquote class="reg-quote ${o.quote_verified ? '' : 'reg-quote--unverified'}">
                                ${escapeHtml(o.source_quote || 'No supporting sentence was given.')}
                                ${o.quote_verified ? '' : '<footer>This sentence was not found in the section text. Check the section before confirming.</footer>'}
                            </blockquote>

                            <div class="row g-3">
                                <div class="col-md-6">
                                    <label class="kx-label" for="regParty">Who</label>
                                    <input type="text" class="form-control" id="regParty" maxlength="255" value="${escapeHtml(o.obligated_party)}" ${dis}>
                                </div>
                                <div class="col-md-6">
                                    <label class="kx-label" for="regCategoryEdit">Category</label>
                                    <select class="form-select" id="regCategoryEdit" ${dis}>
                                        ${this.CATEGORIES.map(c => `<option value="${c}" ${c === o.category ? 'selected' : ''}>${escapeHtml(this.human(c))}</option>`).join('')}
                                    </select>
                                </div>
                                <div class="col-12">
                                    <label class="kx-label" for="regAction">Must</label>
                                    <textarea class="form-control" id="regAction" rows="3" ${dis}>${escapeHtml(o.action)}</textarea>
                                </div>
                                <div class="col-md-6">
                                    <label class="kx-label" for="regDeadline">By when</label>
                                    <input type="text" class="form-control" id="regDeadline" maxlength="255" value="${escapeHtml(o.deadline || '')}" ${dis}>
                                </div>
                                <div class="col-md-6">
                                    <label class="kx-label" for="regNotes">Review notes</label>
                                    <input type="text" class="form-control" id="regNotes" maxlength="2000" value="${escapeHtml(o.review_notes || '')}" ${dis}>
                                </div>
                            </div>
                            <div class="text-danger small mt-2 d-none" id="regReviewError" role="alert"></div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-primary" data-bs-dismiss="modal">Close</button>
                            ${editable ? `
                            <button type="button" class="btn btn-outline-primary reg-decide" data-decision="REJECTED">Reject</button>
                            <button type="button" class="btn btn-primary reg-decide" data-decision="CONFIRMED">Confirm obligation</button>` : ''}
                        </div>
                    </div>
                </div>
            </div>`;

        $("#regReviewModal").remove();
        $("body").append(html);
        const modalEl = document.getElementById('regReviewModal');
        const modal = new bootstrap.Modal(modalEl);
        modal.show();

        $(".reg-decide").on("click", async (e) => {
            const party = $("#regParty").val().trim();
            const action = $("#regAction").val().trim();
            if (!party || !action) {
                $("#regReviewError").text('"Who" and "Must" cannot be empty.').removeClass("d-none");
                return;
            }
            const payload = { decision: $(e.currentTarget).data("decision"), notes: $("#regNotes").val().trim() || null };
            // Send only what the reviewer changed, so the audit trail shows real edits
            if (party !== o.obligated_party) payload.obligated_party = party;
            if (action !== o.action) payload.action = action;
            if ($("#regCategoryEdit").val() !== o.category) payload.category = $("#regCategoryEdit").val();
            const deadline = $("#regDeadline").val().trim();
            if (deadline && deadline !== (o.deadline || '')) payload.deadline = deadline;

            $(".reg-decide").prop("disabled", true);
            try {
                await API.put(`/regulatory/obligations/${o.id}/review`, payload);
                closeModalSafely(modalEl);
                showToast('success', payload.decision === 'CONFIRMED' ? 'Obligation confirmed.' : 'Obligation rejected.');
                await Promise.all([this.loadSummary(), this.loadObligations(), this.loadTraceability()]);
            } catch (xhr) {
                const detail = xhr && xhr.responseJSON && xhr.responseJSON.detail;
                $("#regReviewError").text(typeof detail === 'string' ? detail : 'Could not save the review.').removeClass("d-none");
                $(".reg-decide").prop("disabled", false);
            }
        });

        $(modalEl).on("hidden.bs.modal", function() { setTimeout(() => $(this).remove(), 0); });
    }
};
