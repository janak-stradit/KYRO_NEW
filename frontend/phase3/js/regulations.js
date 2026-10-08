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

    canReview() {
        return ['ADMIN', 'COMPLIANCE_OFFICER'].includes(String(Auth.getUserRole() || '').toUpperCase());
    },

    async init() {
        this.page = 1;
        this.filters = { status: 'PROPOSED', category: '', q: '' };
        this.renderLayout();
        this.setupListeners();
        await Promise.all([this.loadSources(), this.loadSummary(), this.loadObligations()]);
    },

    renderLayout() {
        const reviewer = this.canReview();
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
                const runs = await API.post('/regulatory/ingest');
                const changed = runs.reduce((n, r) => n + r.sections_added + r.sections_changed + r.sections_removed, 0);
                const failed = runs.filter(r => r.status === 'FAILED').length;
                showToast(failed ? 'warning' : 'success', failed
                    ? `${failed} source(s) could not be reached; existing text was kept.`
                    : changed ? `${changed} section(s) added or changed.` : 'All sources are up to date.');
                await Promise.all([this.loadSources(), this.loadSummary(), this.loadObligations()]);
            } catch (xhr) { /* API layer already reported it */ }
            $btn.prop("disabled", false);
        });

        $("#mainContent").off("click.reg")
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
            const reviewer = this.canReview();
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

        const reviewer = this.canReview();
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
        const editable = this.canReview() && o.status !== 'SUPERSEDED';
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
                modal.hide();
                showToast('success', payload.decision === 'CONFIRMED' ? 'Obligation confirmed.' : 'Obligation rejected.');
                await Promise.all([this.loadSummary(), this.loadObligations()]);
            } catch (xhr) {
                const detail = xhr && xhr.responseJSON && xhr.responseJSON.detail;
                $("#regReviewError").text(typeof detail === 'string' ? detail : 'Could not save the review.').removeClass("d-none");
                $(".reg-decide").prop("disabled", false);
            }
        });

        $(modalEl).on("hidden.bs.modal", function() { setTimeout(() => $(this).remove(), 0); });
    }
};
