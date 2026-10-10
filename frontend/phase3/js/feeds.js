/**
 * KYRO Data Feeds - bring in a client's CSV file without code changes:
 * choose what the file contains, confirm which column is which field,
 * check every row, then load it. Loaded rows go through the same screening,
 * rules and audit as records created in the app.
 *
 * The page also starts and stops the live synthetic feed: made-up
 * transactions for existing accounts, sent through the rules engine and
 * the AI anomaly models.
 */

const Feeds = {
    TARGETS: { CUSTOMERS: 'Customers', ACCOUNTS: 'Accounts', TRANSACTIONS: 'Transactions' },
    file: null,
    preview: null,
    lastCheck: null,
    saved: [],
    RATES: { 6: 'One every 10 seconds', 12: 'One every 5 seconds', 30: 'One every 2 seconds', 60: 'One every second' },
    live: null,
    liveTimer: null,

    canUse() {
        return Auth.can('feeds.load');
    },

    async init() {
        this.file = null;
        this.preview = null;
        this.lastCheck = null;
        $("#mainContent").html(`
            <div class="kyro-page">
                <div class="kyro-page-head">
                    <div>
                        <span class="kyro-kicker">Data Onboarding</span>
                        <h1 class="kyro-page-title">Data Feeds</h1>
                        <p class="kyro-page-sub">Load a client's customers, accounts or transactions from a CSV file. Loaded records are screened, run through the rules and audited like any other.</p>
                    </div>
                </div>
                ${this.canUse() ? `
                <section class="card kd-panel mb-4" id="liveFeed"></section>
                <section class="card kd-panel mb-4">
                    <header class="kd-panel__head"><div><h2>1. Choose a file</h2><p class="aml-subtitle">CSV with a header row, up to 5 MB. Load customers first, then accounts, then transactions.</p></div></header>
                    <form class="feed-pick" id="feedPickForm">
                        <select class="form-select" id="feedTarget" aria-label="What the file contains">
                            ${Object.entries(this.TARGETS).map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}
                        </select>
                        <input type="file" class="form-control" id="feedFile" accept=".csv,text/csv" aria-label="CSV file">
                        <select class="form-select" id="feedSaved" aria-label="Saved mapping"><option value="">No saved mapping</option></select>
                        <button type="submit" class="btn btn-primary">Read file</button>
                    </form>
                </section>
                <div id="feedMapping"></div>
                <div id="feedResult"></div>` : `
                <section class="card kd-panel mb-4"><p class="cp-empty mb-0">Your role cannot load data feeds. Past runs are listed below.</p></section>`}
                <div class="card border-0 rc-table-card">
                    <div class="rc-toolbar"><div class="rc-toolbar__title"><h2>Recent checks and loads</h2><small class="text-muted">Every run is kept with its file name and result</small></div></div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0 fp-table">
                            <thead><tr>
                                <th class="px-3 py-2">When</th><th class="px-3 py-2">File</th><th class="px-3 py-2">Contains</th><th class="px-3 py-2">Run</th>
                                <th class="px-3 py-2 text-end">Rows</th><th class="px-3 py-2 text-end">Loaded</th><th class="px-3 py-2 text-end">Already there</th><th class="px-3 py-2 text-end">Invalid</th>
                            </tr></thead>
                            <tbody id="feedRunsBody">${Skeleton.rows(8)}</tbody>
                        </table>
                    </div>
                </div>
            </div>
        `);
        $("#feedPickForm").on("submit", (e) => { e.preventDefault(); this.readFile(); });
        $("#feedTarget").on("change", () => this.renderSavedOptions());
        await Promise.all([this.loadSaved(), this.loadRuns(), this.canUse() ? this.loadLive() : null]);
    },

    // ── Live synthetic feed ──────────────────────────────────────────────

    /** JSON call that bypasses the shared API helper, which caches GETs. */
    async liveCall(path = '', body = null) {
        const response = await fetch(`${API.baseUrl}/feeds/live${path}`, {
            method: body ? 'POST' : 'GET', cache: 'no-store',
            headers: { Authorization: API.getHeaders().Authorization, 'Content-Type': 'application/json' },
            body: body ? JSON.stringify(body) : undefined
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'The request failed.');
        return data;
    },

    async loadLive() {
        clearTimeout(this.liveTimer);
        if (!document.getElementById('liveFeed')) return;  // the user has left the page
        try {
            this.live = await this.liveCall();
        } catch (error) {
            if (!this.live) $("#liveFeed").html('<p class="cp-empty mb-0">Could not load the live feed status.</p>');
        }
        if (!this.live) return;
        this.renderLive();
        if (this.live.running) this.liveTimer = setTimeout(() => this.loadLive(), 3000);
    },

    async toggleLive(start) {
        $("#liveStart, #liveStop").prop("disabled", true);
        try {
            this.live = await this.liveCall(start ? '/start' : '/stop', start ? { per_minute: Number($("#liveRate").val()) } : {});
            showToast('success', start ? 'The synthetic feed is running.' : 'The synthetic feed has stopped.');
            if (!start) API.clearCache();  // other pages should show the new transactions and alerts
        } catch (error) {
            showToast('error', error.message);
        }
        await this.loadLive();
    },

    renderLive() {
        const f = this.live;
        if (!f.enabled) {
            $("#liveFeed").html(`
                <header class="kd-panel__head"><div><h2>Live synthetic feed <span class="cd-chip cd-chip--muted">Turned off</span></h2>
                    <p class="aml-subtitle mb-0">Sends made-up transactions through the rules engine for demonstrations and testing. It is turned off on this system; an administrator can set SYNTHETIC_FEED_ENABLED=true where no real customer data is held.</p></div></header>`);
            return;
        }
        const rate = $("#liveRate").val() || f.per_minute;
        const tile = (label, value, cls = '') => `<div class="rq-tile rq-tile--static ${cls}"><span class="rq-tile__label">${label}</span><strong class="rq-tile__value">${value}</strong></div>`;
        const since = f.running ? `Started ${escapeHtml(formatDateTime(f.started_at))}${f.started_by ? ` by ${escapeHtml(f.started_by)}` : ''}.`
            : f.stopped_at ? `Stopped ${escapeHtml(formatDateTime(f.stopped_at))}.` : 'Not started yet.';
        $("#liveFeed").html(`
            <header class="kd-panel__head">
                <div><h2>Live synthetic feed <span class="cd-chip cd-chip--${f.running ? 'low' : 'muted'}">${f.running ? '<span class="feed-live__dot"></span>Running' : 'Stopped'}</span></h2>
                    <p class="aml-subtitle">Sends made-up transactions for existing accounts through the rules engine and the AI anomaly models, as a client feed would. They are marked "synthetic_feed" as their source. ${since}</p></div>
                <div class="feed-live__controls">
                    <select class="form-select" id="liveRate" aria-label="How often a transaction is sent" ${f.running ? 'disabled' : ''}>
                        ${Object.entries(this.RATES).map(([k, l]) => `<option value="${k}" ${Number(k) === Number(rate) ? 'selected' : ''}>${l}</option>`).join('')}
                    </select>
                    ${f.running ? '<button type="button" class="btn btn-danger" id="liveStop"><i class="fas fa-stop me-2"></i>Stop feed</button>'
                                : '<button type="button" class="btn btn-primary" id="liveStart"><i class="fas fa-play me-2"></i>Start feed</button>'}
                </div>
            </header>
            ${f.last_error ? `<div class="alert alert-warning py-2 px-3 mb-3">${escapeHtml(f.last_error)}</div>` : ''}
            ${f.ai_unavailable ? `<div class="alert alert-warning py-2 px-3 mb-3">AI anomaly scoring is not running: ${escapeHtml(f.ai_unavailable)}. Transactions are scored by the rules engine only.</div>` : ''}
            ${f.started_at ? `
            <div class="rq-tiles rq-tiles--four">
                ${tile('Transactions sent', f.transactions.toLocaleString())}
                ${tile('Flagged by a rule', f.flagged.toLocaleString())}
                ${tile('Alerts opened', f.alerts.toLocaleString(), f.alerts ? 'rq-tile--alert' : '')}
                ${tile('Flagged by AI', f.ai_unavailable ? '—' : f.anomalies.toLocaleString())}
            </div>
            <div class="table-responsive feed-live__recent">
                <table class="table mb-0 fp-table">
                    <thead><tr><th class="px-3 py-2">Time</th><th class="px-3 py-2">Customer</th><th class="px-3 py-2">Type</th><th class="px-3 py-2 text-end">Amount</th><th class="px-3 py-2">Country</th><th class="px-3 py-2 text-end">Rules score</th><th class="px-3 py-2 text-end">AI score</th><th class="px-3 py-2">Rules</th></tr></thead>
                    <tbody>
                        ${f.recent.map(t => `
                        <tr>
                            <td class="px-3 py-2 text-nowrap">${escapeHtml(new Date(t.at).toLocaleTimeString())}</td>
                            <td class="px-3 py-2">${escapeHtml(t.customer)}</td>
                            <td class="px-3 py-2">${escapeHtml(t.transaction_type)}</td>
                            <td class="px-3 py-2 text-end text-nowrap">${escapeHtml(formatCurrency(t.amount, t.currency))}</td>
                            <td class="px-3 py-2">${escapeHtml(t.country || '')}</td>
                            <td class="px-3 py-2 text-end">${t.risk_score}</td>
                            <td class="px-3 py-2 text-end">${t.ai_score === null ? '<span class="text-muted">—</span>' : `${t.anomaly ? `<span class="cd-chip cd-chip--high">${t.ai_score} · anomaly</span>` : t.ai_score}`}</td>
                            <td class="px-3 py-2">${t.triggered_rules.length ? `<span class="cd-chip cd-chip--${t.alert_opened ? 'high' : 'medium'}">${escapeHtml(t.triggered_rules.join(', '))}${t.alert_opened ? ' · alert' : ''}</span>` : '<span class="text-muted">—</span>'}</td>
                        </tr>`).join('') || '<tr><td colspan="8" class="rc-empty">Waiting for the first transaction...</td></tr>'}
                    </tbody>
                </table>
            </div>` : ''}`);
        $("#liveStart").on("click", () => this.toggleLive(true));
        $("#liveStop").on("click", () => this.toggleLive(false));
    },

    async loadSaved() {
        try { this.saved = await API.get('/feeds/mappings'); } catch (error) { this.saved = []; }
        this.renderSavedOptions();
    },

    renderSavedOptions() {
        const target = $("#feedTarget").val();
        $("#feedSaved").html('<option value="">No saved mapping</option>'
            + this.saved.filter(m => m.target === target).map(m => `<option value="${escapeHtml(m.id)}">${escapeHtml(m.name)}</option>`).join(''));
    },

    async loadRuns() {
        let runs;
        try { runs = await API.get('/feeds/runs'); } catch (error) { runs = null; }
        $("#feedRunsBody").html(runs ? (runs.map(r => `
            <tr>
                <td class="px-3 py-2 text-nowrap">${escapeHtml(formatDateTime(r.run_at))}</td>
                <td class="px-3 py-2">${escapeHtml(r.filename)}</td>
                <td class="px-3 py-2">${escapeHtml(this.TARGETS[r.target] || r.target)}</td>
                <td class="px-3 py-2"><span class="cd-chip cd-chip--${r.dry_run ? 'muted' : 'low'}">${r.dry_run ? 'Check only' : 'Load'}</span></td>
                <td class="px-3 py-2 text-end">${r.rows_total.toLocaleString()}</td>
                <td class="px-3 py-2 text-end">${r.rows_loaded.toLocaleString()}</td>
                <td class="px-3 py-2 text-end">${r.rows_skipped_existing.toLocaleString()}</td>
                <td class="px-3 py-2 text-end">${r.rows_invalid ? `<strong class="text-danger">${r.rows_invalid.toLocaleString()}</strong>` : '0'}</td>
            </tr>`).join('') || '<tr><td colspan="8" class="rc-empty">No files have been checked or loaded yet.</td></tr>')
            : '<tr><td colspan="8" class="rc-empty">Could not load the run history.</td></tr>');
    },

    /** Multipart POST; the shared API helper only sends JSON. */
    async send(path, fields) {
        const form = new FormData();
        Object.entries(fields).forEach(([k, v]) => { if (v !== null && v !== undefined) form.append(k, v); });
        const response = await fetch(`${API.baseUrl}/feeds/${path}`, { method: 'POST', headers: { Authorization: API.getHeaders().Authorization }, body: form });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'The request failed.');
        API.clearCache();
        return body;
    },

    async readFile() {
        const file = document.getElementById('feedFile').files[0];
        if (!file) { showToast('warning', 'Choose a CSV file first.'); return; }
        this.file = file;
        this.lastCheck = null;
        $("#feedResult").empty();
        try {
            this.preview = await this.send('preview', { target: $("#feedTarget").val(), file });
        } catch (error) {
            $("#feedMapping").empty();
            showToast('error', error.message);
            return;
        }
        this.renderMapping();
    },

    renderMapping() {
        const p = this.preview;
        const preset = this.saved.find(m => m.id === $("#feedSaved").val());
        const chosen = (field) => (preset ? preset.mapping[field.name] : (p.suggested[field.name] || {}).column) || '';
        const sample = (column) => p.sample_rows.map(r => r[column]).filter(Boolean).slice(0, 3).join(' · ');

        $("#feedMapping").html(`
            <section class="card border-0 rc-table-card mb-4">
                <div class="rc-toolbar">
                    <div class="rc-toolbar__title"><h2>2. Confirm the columns</h2>
                        <small class="text-muted">${p.row_count.toLocaleString()} rows and ${p.columns.length} columns in ${escapeHtml(this.file.name)}. ${preset ? `Using the saved mapping "${escapeHtml(preset.name)}".` : 'Suggestions come from the column names and sample values; change any that are wrong.'}</small></div>
                </div>
                <div class="table-responsive">
                    <table class="table mb-0 fp-table">
                        <thead><tr><th class="px-3 py-2">KYRO field</th><th class="px-3 py-2">Column in the file</th><th class="px-3 py-2">Sample values</th><th class="px-3 py-2">Suggestion</th></tr></thead>
                        <tbody>
                            ${p.fields.map(f => {
                                const s = p.suggested[f.name];
                                const column = chosen(f);
                                return `
                                <tr data-field="${escapeHtml(f.name)}">
                                    <td class="px-3 py-2"><strong>${escapeHtml(f.label)}</strong>${f.required ? ' <span class="text-danger" title="Required">*</span>' : ''}
                                        ${f.choices.length ? `<br><small class="text-muted">one of ${escapeHtml(f.choices.join(', ').toLowerCase())}</small>` : ''}</td>
                                    <td class="px-3 py-2">
                                        <select class="form-select form-select-sm feed-column" aria-label="Column for ${escapeHtml(f.label)}">
                                            <option value="">${f.required ? 'Choose a column...' : 'Not in this file'}</option>
                                            ${p.columns.map(c => `<option value="${escapeHtml(c)}" ${c === column ? 'selected' : ''}>${escapeHtml(c)}</option>`).join('')}
                                        </select>
                                    </td>
                                    <td class="px-3 py-2 text-muted feed-sample">${escapeHtml(column ? sample(column) : '')}</td>
                                    <td class="px-3 py-2">${!preset && s ? `<span class="cd-chip cd-chip--${s.confidence >= 0.85 ? 'low' : 'medium'}" title="${escapeHtml(s.reason)}">${Math.round(s.confidence * 100)}% ${escapeHtml(s.reason)}</span>` : '<span class="text-muted">—</span>'}</td>
                                </tr>`;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
                <div class="feed-actions">
                    <label class="feed-check"><input type="checkbox" class="form-check-input" id="feedDayFirst" ${!preset || preset.date_day_first ? 'checked' : ''}> Dates are written day first (31/12/2026)</label>
                    <input type="text" class="form-control form-control-sm" id="feedName" maxlength="150" placeholder="Name to save this mapping under (optional)" value="${escapeHtml(preset ? preset.name : '')}">
                    <button type="button" class="btn btn-outline-primary" id="feedSave">Save mapping</button>
                    <button type="button" class="btn btn-primary" id="feedCheck">Check file</button>
                </div>
            </section>`);

        $(".feed-column").on("change", (e) => {
            $(e.currentTarget).closest("tr").find(".feed-sample").text(sample($(e.currentTarget).val()));
            this.lastCheck = null;
            $("#feedResult").empty();
        });
        $("#feedCheck").on("click", () => this.run(true));
        $("#feedSave").on("click", () => this.saveMapping());
    },

    mapping() {
        const mapping = {};
        $("#feedMapping tr[data-field]").each((_, tr) => {
            const column = $(tr).find(".feed-column").val();
            if (column) mapping[$(tr).data("field")] = column;
        });
        return mapping;
    },

    async saveMapping() {
        const name = $("#feedName").val().trim();
        if (name.length < 3) { showToast('warning', 'Give the mapping a name of at least three characters.'); return; }
        try {
            await API.post('/feeds/mappings', { name, target: this.preview.target, mapping: this.mapping(), date_day_first: $("#feedDayFirst").is(":checked") });
            showToast('success', 'Mapping saved.');
            await this.loadSaved();
        } catch (xhr) { /* reported by the API helper */ }
    },

    async run(dryRun, skipInvalid = false) {
        const $buttons = $("#feedCheck, #feedLoad, #feedLoadValid").prop("disabled", true);
        let result;
        try {
            result = await this.send('run', {
                target: this.preview.target, mapping: JSON.stringify(this.mapping()), dry_run: dryRun, skip_invalid: skipInvalid,
                date_day_first: $("#feedDayFirst").is(":checked"), mapping_id: $("#feedSaved").val() || null, file: this.file
            });
        } catch (error) {
            showToast('error', error.message);
            $buttons.prop("disabled", false);
            return;
        }
        $buttons.prop("disabled", false);
        if (dryRun) this.lastCheck = result;
        this.renderResult(result);
        this.loadRuns();
    },

    renderResult(r) {
        const loaded = !r.dry_run && r.rows_loaded > 0;
        const refused = !r.dry_run && r.rows_loaded === 0 && r.rows_valid > 0;
        const tile = (label, value, cls = '') => `<div class="rq-tile rq-tile--static ${cls}"><span class="rq-tile__label">${label}</span><strong class="rq-tile__value">${value.toLocaleString()}</strong></div>`;
        $("#feedResult").html(`
            <section class="card kd-panel mb-4">
                <header class="kd-panel__head"><div><h2>3. ${r.dry_run ? 'Check result' : 'Load result'}</h2>
                    <p class="aml-subtitle">${loaded ? `${r.rows_loaded.toLocaleString()} rows were loaded.` : refused ? 'Nothing was loaded because some rows are invalid.' : r.dry_run ? 'Nothing has been loaded yet.' : 'Nothing needed loading.'}</p></div></header>
                <div class="rq-tiles rq-tiles--four">
                    ${tile('Rows in the file', r.rows_total)}
                    ${tile(r.dry_run ? 'Ready to load' : 'Loaded', r.dry_run ? r.rows_valid : r.rows_loaded)}
                    ${tile('Already in KYRO', r.rows_skipped_existing)}
                    ${tile('Invalid', r.rows_invalid, r.rows_invalid ? 'rq-tile--alert' : '')}
                </div>
                ${r.errors && r.errors.length ? `
                <div class="kx-label">Rows that cannot be loaded${r.rows_invalid > r.errors.length ? ` (first ${r.errors.length} of ${r.rows_invalid.toLocaleString()})` : ''}</div>
                <ul class="feed-errors">${r.errors.map(e => `<li><strong>Row ${e.row}</strong> ${escapeHtml(e.message)}</li>`).join('')}</ul>` : ''}
                ${r.dry_run && r.rows_valid ? `
                <div class="feed-actions feed-actions--end">
                    ${r.rows_invalid ? `<button type="button" class="btn btn-outline-primary" id="feedLoadValid">Load the ${r.rows_valid.toLocaleString()} valid rows and leave the rest</button>`
                                     : `<button type="button" class="btn btn-primary" id="feedLoad">Load ${r.rows_valid.toLocaleString()} rows</button>`}
                </div>` : ''}
            </section>`);
        $("#feedLoad").on("click", () => this.run(false));
        $("#feedLoadValid").on("click", () => this.run(false, true));
    }
};

window.Feeds = Feeds;
