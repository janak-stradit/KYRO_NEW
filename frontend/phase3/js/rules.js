/**
 * KYRO Rules - the detection rules (R001-R010) in one place: what each rule
 * checks and with which threshold, how its alerts have ended, and the
 * regulation behind it; which rules engine switches are on; the exchange
 * rates amounts are converted with; and a replay that shows what a change
 * would do to past alerts before it goes live.
 *
 * Threshold changes are proposed and approved under Regulations > Changes.
 */

const Rules = {
    // Which setting each rule is tuned by (rules_engine.DEFAULTS)
    PARAMS: {
        R001: [['AMOUNT_THRESHOLD', 'Amount above', 'money']],
        R002: [['VELOCITY_DAILY_LIMIT', 'More than', 'perDay']],
        R003: [['VELOCITY_HOURLY_LIMIT', 'More than', 'perHour']],
        R004: [['HIGH_RISK_COUNTRIES', 'Countries listed', 'list']],
        R010: [['RAPID_SUCCESSION_WINDOW_SECONDS', 'Within', 'seconds']]
    },
    WEAK: ['R007', 'R008', 'R009'],

    async init() {
        $("#mainContent").html(`
            <div class="kyro-page">
                <div class="kyro-page-head">
                    <div>
                        <span class="kyro-kicker">Transaction Monitoring</span>
                        <h1 class="kyro-page-title">Rules</h1>
                        <p class="kyro-page-sub">What each detection rule checks, how its alerts have ended, and what a change would do before it goes live.</p>
                    </div>
                    <div class="kyro-page-actions">
                        ${Auth.can('rules.propose', 'rules.approve') ? '<a class="btn btn-outline-primary" href="/regulations" data-page-link="regulations"><i class="fas fa-code-pull-request me-2"></i>Propose or approve a change</a>' : ''}
                    </div>
                </div>
                <div class="ru-top">
                    <section class="card kd-panel" id="ruEngine">${Skeleton.lines(4)}</section>
                    <section class="card kd-panel" id="ruFx">${Skeleton.lines(4)}</section>
                </div>
                <section class="card border-0 rc-table-card mb-4">
                    <div class="rc-toolbar"><div class="rc-toolbar__title"><h2>Rule catalogue</h2>
                        <small class="text-muted" id="ruWindow">How alerts from each rule ended in the last 90 days</small></div></div>
                    <div class="table-responsive">
                        <table class="table mb-0 rq-table ru-table">
                            <thead><tr><th>Rule</th><th>What it checks</th><th>Setting</th><th>Severity</th><th>Alerts</th><th>False positives</th><th>SAR / escalated</th><th>Regulatory basis</th></tr></thead>
                            <tbody id="ruBody">${Skeleton.rows(6)}</tbody>
                        </table>
                    </div>
                    <p class="kx-note px-3 py-2 mb-0" id="ruScoring"></p>
                </section>
                ${Auth.can('rules.propose') ? `<section class="card kd-panel mb-4" id="ruReplay"></section>` : ''}
            </div>`);
        $("[data-page-link]").on("click", (e) => { e.preventDefault(); App.navigateTo($(e.currentTarget).data("page-link")); });
        this.renderReplayForm();
        await Promise.all([this.loadEngine(), this.loadFx(), this.loadCatalogue()]);
    },

    human(v) { return String(v || '').replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase()); },

    // ── Engine switches ─────────────────────────────────────────────────
    async loadEngine() {
        let o;
        try { o = await API.get('/rules/options'); } catch (e) { $("#ruEngine").html(this.fail('the engine settings')); return; }
        const row = (on, title, text) => `
            <li class="ru-switch"><span class="cd-chip cd-chip--${on ? 'low' : 'muted'}">${on ? 'On' : 'Off'}</span>
                <span><strong>${title}</strong><small>${text}</small></span></li>`;
        $("#ruEngine").html(`
            <h2 class="ru-title">Rules engine switches</h2>
            <ul class="ru-switches">
                ${row(o.base_currency, 'Compare in the base currency', 'R001 converts each amount with the day\'s exchange rate before comparing.')}
                ${row(o.noise_reduction, 'Noise reduction', 'No PEP/sanctions alert on every payment (one sanctions case instead); weekend, round amount and new counterparty count only with a stronger rule; R010 looks back only.')}
                ${row(o.consolidate_daily, 'One alert per customer per day', 'Further hits on the same day are added to the open alert.')}
            </ul>
            <p class="kx-note mb-0">Switches are set by the system administrator (RULES_* settings) after Compliance has reviewed a replay. Scoring version <code>${escapeHtml(o.signature)}</code>.</p>`);
    },

    // ── Exchange rates ──────────────────────────────────────────────────
    async loadFx() {
        let fx;
        try { fx = await API.get('/rules/fx'); } catch (e) { $("#ruFx").html(this.fail('the exchange rates')); return; }
        $("#ruFx").html(`
            <h2 class="ru-title">Exchange rates</h2>
            <div class="ru-stats">
                <div><span>Base currency</span><strong>${escapeHtml(fx.base_currency)}</strong></div>
                <div><span>Latest rates</span><strong>${fx.latest_rate_date ? escapeHtml(new Date(fx.latest_rate_date).toLocaleDateString()) : 'None loaded'}</strong>
                    ${fx.stale ? '<small class="text-danger">Out of date</small>' : `<small>${fx.currencies} currencies</small>`}</div>
                <div><span>Without a base amount</span><strong>${Number(fx.transactions_without_base_amount).toLocaleString()}</strong><small>transactions</small></div>
            </div>
            <p class="kx-note">European Central Bank reference rates, loaded every working day. Transactions are converted as rates arrive.</p>
            ${Auth.can('feeds.load') ? '<button type="button" class="btn btn-sm btn-outline-primary ru-inline-btn" id="ruFxRefresh"><i class="fas fa-rotate me-1"></i>Load today\'s rates</button>' : ''}`);
        $("#ruFxRefresh").on("click", async (e) => {
            const $b = $(e.currentTarget).prop("disabled", true).text('Loading…');
            try {
                const r = await API.post('/rules/fx/refresh', {});
                showToast('success', `Loaded ${r.stored} rates for ${r.rate_date}; ${r.backfilled.toLocaleString()} transactions converted.`);
            } catch (xhr) { /* reported by the API layer */ }
            this.loadFx();
        });
    },

    // ── Rule catalogue ──────────────────────────────────────────────────
    async loadCatalogue() {
        const codes = Object.keys(Cases.RULES);
        const [cfg, baseline, basis] = await Promise.all([
            API.get('/rule-configs/effective').catch(() => null),
            Auth.can('alerts.baseline') ? API.get('/alerts/disposition-baseline', { days: 90 }).catch(() => null) : null,
            API.get('/controls/basis', { codes: codes.join(',') }).catch(() => ({})),
        ]);
        const stats = Object.fromEntries(((baseline && baseline.by_rule) || []).map(r => [r.rule, r]));
        const pct = (v) => v == null ? '—' : `${Math.round(v * 100)}%`;
        const setting = (code) => (this.PARAMS[code] || []).map(([key, label, kind]) => {
            const v = cfg ? cfg[key] : null;
            if (v == null) return '';
            const shown = kind === 'money' ? Number(v).toLocaleString() : kind === 'list' ? `${v.length}`
                : kind === 'perDay' ? `${v} a day` : kind === 'perHour' ? `${v} an hour` : `${v} s`;
            return `<span class="ru-param" title="${escapeHtml(key)}">${label} <b>${escapeHtml(shown)}</b></span>`;
        }).join('') || '<span class="text-muted">Customer attribute</span>';
        $("#ruBody").html(codes.map(code => {
            const [name, text, severity] = Cases.RULES[code];
            const s = stats[code] || {};
            const fpRate = s.false_positive_rate;
            const refs = (basis[code] || []).slice(0, 2);
            return `
                <tr>
                    <td class="text-nowrap"><strong>${code}</strong><br><span class="text-muted">${escapeHtml(name)}</span>
                        ${this.WEAK.includes(code) ? '<br><span class="cd-chip cd-chip--muted" title="With noise reduction on, counts only alongside a stronger rule">Supporting</span>' : ''}</td>
                    <td class="ru-text">${escapeHtml(text)}</td>
                    <td>${setting(code)}</td>
                    <td><span class="cd-chip cd-chip--${{ CRITICAL: 'high', HIGH: 'high', MEDIUM: 'medium' }[severity] || 'low'}">${this.human(severity)}</span></td>
                    <td class="text-nowrap">${s.alerts != null ? Number(s.alerts).toLocaleString() : '—'}</td>
                    <td class="text-nowrap">${fpRate == null ? '<span class="text-muted">Not yet</span>'
                        : `<span class="ru-fp ${fpRate >= 0.9 ? 'ru-fp--bad' : fpRate >= 0.7 ? 'ru-fp--warn' : ''}">${pct(fpRate)}</span> <small class="text-muted">of ${s.resolved} closed</small>`}</td>
                    <td class="text-nowrap">${s.alerts != null ? `${s.sar_filed} / ${s.escalated}` : '—'}</td>
                    <td class="ru-basis">${refs.length ? refs.map(r => `<span title="${escapeHtml(r.action || '')}">${escapeHtml(r.citation || '')}</span>`).join('<br>')
                        : '<span class="text-muted">Not mapped yet</span>'}</td>
                </tr>`;
        }).join(''));
        $("#ruScoring").html(cfg ? `Each rule adds its severity weight to the transaction's score (${Object.entries(cfg.SEVERITY_WEIGHT).map(([k, v]) => `${this.human(k)} ${v}`).join(', ')}).
            An alert opens at score <b>${cfg.ALERT_THRESHOLD}</b>; enhanced due diligence is recommended at <b>${cfg.EDD_THRESHOLD}</b>; a critical rule always opens one.
            Values shown are the global settings; a jurisdiction can override them.` : '');
        if (baseline) $("#ruWindow").text(`How alerts from each rule ended in the last ${baseline.window_days} days. A high false-positive rate is a reason to review the rule's setting.`);
    },

    // ── Replay ──────────────────────────────────────────────────────────
    renderReplayForm() {
        if (!Auth.can('rules.propose')) return;
        const today = new Date().toISOString().slice(0, 10);
        const monthAgo = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);
        $("#ruReplay").html(`
            <h2 class="ru-title">Replay a change</h2>
            <p class="kx-note">Runs the rules again over past transactions with today's switches and with the ones you choose, and shows the difference. Nothing is changed.</p>
            <form class="row g-2 align-items-end" id="ruReplayForm">
                <div class="col-md-2"><label class="kx-label" for="ruFrom">From</label><input type="date" class="form-control" id="ruFrom" value="${monthAgo}" max="${today}"></div>
                <div class="col-md-2"><label class="kx-label" for="ruTo">To</label><input type="date" class="form-control" id="ruTo" value="${today}" max="${today}"></div>
                <div class="col-md-5 d-flex gap-3 pb-2">
                    <label class="form-check mb-0"><input class="form-check-input" type="checkbox" id="ruBase" checked> <span class="form-check-label">Base currency</span></label>
                    <label class="form-check mb-0"><input class="form-check-input" type="checkbox" id="ruNoise" checked> <span class="form-check-label">Noise reduction</span></label>
                </div>
                <div class="col-md-3 text-end"><button type="submit" class="btn btn-primary" id="ruRun"><i class="fas fa-play me-2"></i>Run replay</button></div>
            </form>
            <div id="ruResult" class="mt-3"></div>`);
        $("#ruReplayForm").on("submit", (e) => { e.preventDefault(); this.runReplay(); });
    },

    async runReplay() {
        const from = $("#ruFrom").val(), to = $("#ruTo").val();
        if (!from || !to || to < from) return showToast('error', 'Choose a period whose end is after its start.');
        const $b = $("#ruRun").prop("disabled", true);
        $("#ruResult").html(`<div role="status" aria-busy="true">${Skeleton.lines(4)}<p class="kx-note">Replaying… large periods can take a minute.</p></div>`);
        let r;
        try {
            r = await API.postSlow('/rules/replay', {
                start: `${from}T00:00:00Z`, end: new Date(new Date(`${to}T00:00:00Z`).getTime() + 86400000).toISOString(),
                base_currency: $("#ruBase").is(":checked"), noise_reduction: $("#ruNoise").is(":checked"),
            });
        } catch (xhr) {
            $("#ruResult").html(this.fail('the replay'));
            $b.prop("disabled", false);
            return;
        }
        $b.prop("disabled", false);
        const delta = (a, b) => { const d = b - a; return d === 0 ? '<span class="text-muted">no change</span>' : `<span class="${d < 0 ? 'ru-down' : 'ru-up'}">${d > 0 ? '+' : ''}${d.toLocaleString()}${a ? ` (${d > 0 ? '+' : ''}${Math.round(100 * d / a)}%)` : ''}</span>`; };
        const rules = [...new Set([...Object.keys(r.rule_hits.current), ...Object.keys(r.rule_hits.proposed)])].sort();
        const lost = r.possible_lost_true_positives;
        $("#ruResult").html(`
            <div class="ru-stats ru-stats--wide">
                <div><span>Transactions replayed</span><strong>${r.transactions_replayed.toLocaleString()}</strong>${r.truncated ? '<small class="text-danger">limit reached: shorten the period</small>' : ''}</div>
                <div><span>Would alert today</span><strong>${r.alerting_transactions.current.toLocaleString()}</strong><small>transactions</small></div>
                <div><span>Would alert with the change</span><strong>${r.alerting_transactions.proposed.toLocaleString()}</strong><small>${delta(r.alerting_transactions.current, r.alerting_transactions.proposed)}</small></div>
                <div><span>Customers alerting</span><strong>${r.customers_alerting.proposed.toLocaleString()}</strong><small>${delta(r.customers_alerting.current, r.customers_alerting.proposed)}</small></div>
            </div>
            <div class="ru-lost ${lost.length ? 'ru-lost--bad' : ''}">
                ${lost.length ? `<strong><i class="fas fa-triangle-exclamation me-1"></i>${lost.length} productive case${lost.length === 1 ? '' : 's'} would no longer alert.</strong> Review each before the change goes live:
                    <ul class="mb-0">${lost.map(l => `<li><a href="/case?id=${escapeHtml(l.alert_id)}" data-case="${escapeHtml(l.alert_id)}" class="ru-case">${escapeHtml(this.human(l.outcome))} case of ${escapeHtml(new Date(l.created_at).toLocaleDateString())}</a></li>`).join('')}</ul>`
                    : `<strong><i class="fas fa-circle-check me-1"></i>No escalated, SAR or true-positive case in the period would be lost.</strong> (${r.productive_cases_in_period} such cases checked.)`}
            </div>
            <table class="table table-sm mb-0 ru-hits">
                <thead><tr><th>Rule</th><th>Hits today</th><th>Hits with the change</th><th>Difference</th></tr></thead>
                <tbody>${rules.map(code => {
                    const a = r.rule_hits.current[code] || 0, b = r.rule_hits.proposed[code] || 0;
                    return `<tr><td>${escapeHtml(code)} <span class="text-muted">${escapeHtml((Cases.RULES[code] || [''])[0])}</span></td><td>${a.toLocaleString()}</td><td>${b.toLocaleString()}</td><td>${delta(a, b)}</td></tr>`;
                }).join('') || '<tr><td colspan="4" class="text-muted">No rule fired in this period.</td></tr>'}</tbody>
            </table>`);
        $(".ru-case").on("click", (e) => { e.preventDefault(); App.navigateTo('case', { id: $(e.currentTarget).data("case") }); });
    },

    fail(what) {
        return `<p class="cp-empty mb-0"><i class="fas fa-triangle-exclamation me-1"></i>Could not load ${what}. Try again.</p>`;
    }
};
