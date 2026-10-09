/**
 * KYRO Case page - everything about one alert on a single page: why it
 * fired, who the customer is and why they have their rating, the flagged
 * transactions, screening results, documents, reviews and the customer's
 * other open alerts. Assign, resolve and export from the header.
 */

const CaseDetail = {
    id: null,
    caseData: null,

    async init(params = {}) {
        this.id = params.id || null;
        // Keep the Review Cases tab highlighted: a case belongs to the queue
        $('.nav-link[data-page]').removeClass('active');
        $('.nav-link[data-page="cases"]').addClass('active');
        document.title = 'KYRO - Case';
        // Assign / Resolve dialogs are shared with the queue; refresh this page after they save
        Cases.afterChange = () => this.load();
        await this.load();
    },

    human(v) {
        return v ? String(v).replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase()).replace(/\b(Pep|Kyc|Sar|Fx)\b/g, m => m.toUpperCase()) : '—';
    },

    empty(message) {
        return `<p class="cp-empty">${escapeHtml(message)}</p>`;
    },

    async load() {
        if (!this.id) { this.renderMissing('No case was selected.'); return; }
        $("#mainContent").html('<div class="kyro-page"><div class="cp-loading"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div></div></div>');

        let alert;
        try {
            alert = await API.get(`/alerts/${this.id}`);
        } catch (xhr) {
            this.renderMissing(xhr && xhr.status === 404 ? 'This case does not exist.' : 'The case could not be loaded.');
            return;
        }
        const customerId = alert.customer_id;
        const settle = (p) => p.catch(() => null);
        const [customer, profile, transactions, screening, reviews, others, assignees] = await Promise.all([
            settle(API.get(`/customers/${customerId}`)),
            settle(API.get(`/customers/${customerId}/risk-profile`)),
            settle(API.get('/transactions', { customer_id: customerId, page_size: 500 })),
            settle(API.get(`/customers/${customerId}/screening`)),
            settle(API.get(`/customers/${customerId}/kyc-reviews`)),
            settle(API.get('/alerts/queue', { customer_id: customerId, page_size: 6 })),
            settle(API.get('/alerts/assignees')),
            settle(Cases.loadCustomerCodes())
        ]);

        const score = Number(alert.risk_score);
        const riskLevel = score >= 80 ? 'HIGH' : score >= 60 ? 'MEDIUM' : 'LOW';
        const owner = (assignees || []).find(u => u.id === alert.assigned_to);
        this.caseData = {
            caseId: alert.id,
            customerId: Cases.customerCodes[customerId] || '—',
            customerName: (customer && customer.full_name) || '',
            rawCustomerId: customerId,
            triggerType: 'RULE BASED',
            priority: riskLevel === 'HIGH' ? 'URGENT' : riskLevel === 'MEDIUM' ? 'HIGH' : 'LOW',
            riskLevel,
            status: alert.status || 'OPEN',
            createdAt: new Date(alert.created_at).toLocaleDateString(),
            assignedTo: owner ? owner.name : (alert.assigned_to ? 'Assigned' : 'Unassigned'),
            fullData: alert
        };
        Cases.casesData = [this.caseData];  // the shared export dialog looks the case up here

        this.render({ alert, customer, profile: profile || [], transactions: (transactions && transactions.items) || [],
                      screening: screening || [], reviews: reviews || [], others: others || { items: [], total: 0 } });
    },

    renderMissing(message) {
        $("#mainContent").html(`
            <div class="kyro-page">
                <button type="button" class="cp-back" id="cpBack"><i class="fas fa-arrow-left"></i> Work queue</button>
                <div class="card kd-panel"><p class="cp-empty mb-0">${escapeHtml(message)}</p></div>
            </div>`);
        $("#cpBack").on("click", () => App.navigateTo('cases'));
    },

    // ── Case file: notes and timeline, earlier cases, activity, owners ─────
    // Each panel loads on its own, so a slow or failed one does not hold up the page.
    loadCaseFile(alert, customer) {
        this.loadTimeline(alert.id);
        this.loadHistory(alert);
        this.loadActivity(alert.customer_id);
        if (customer.customer_type && customer.customer_type !== 'INDIVIDUAL') this.loadOwners(alert.customer_id);
    },

    TIMELINE_ICONS: {
        created: 'fa-bell', note: 'fa-pen', assigned: 'fa-user-plus', escalated: 'fa-arrow-up', resolved: 'fa-check-double',
        qa: 'fa-clipboard-check', document: 'fa-file-lines', updated: 'fa-rotate'
    },

    async loadTimeline(alertId) {
        let data;
        try {
            data = await API.get(`/alerts/${alertId}/timeline`);
        } catch (error) {
            $("#cpTimeline").html(this.empty('The timeline could not be loaded.'));
            return;
        }
        if (this.id !== alertId) return;  // the user has moved to another case
        $("#cpTimelineCount").text(`${data.note_count} note${data.note_count === 1 ? '' : 's'}, ${data.events.length - data.note_count} event${data.events.length - data.note_count === 1 ? '' : 's'}`);
        $("#cpTimeline").html(`<ol class="cp-tl">${data.events.map(e => `
            <li class="cp-tl__item cp-tl__item--${escapeHtml(e.kind)}">
                <span class="cp-tl__icon" aria-hidden="true"><i class="fas ${this.TIMELINE_ICONS[e.kind] || 'fa-circle'}"></i></span>
                <div class="cp-tl__body">
                    <p class="cp-tl__title">${escapeHtml(e.title)}</p>
                    ${e.detail ? `<p class="cp-tl__detail">${escapeHtml(e.detail)}</p>` : ''}
                    <p class="cp-tl__meta">${escapeHtml(e.by)} &middot; ${escapeHtml(formatDateTime(e.at))}</p>
                </div>
            </li>`).join('')}</ol>`);
    },

    async addNote(alertId) {
        const $input = $("#cpNoteBody");
        const body = ($input.val() || '').trim();
        if (!body) { $input.trigger("focus"); return; }
        const $button = $("#cpNoteAdd").prop("disabled", true);
        try {
            await API.post(`/alerts/${alertId}/notes`, { body });
            $input.val('');
            await this.loadTimeline(alertId);
        } catch (xhr) { /* the API layer has already reported it; the text stays in the box */ }
        $button.prop("disabled", false);
    },

    async loadHistory(alert) {
        let h;
        try {
            h = await API.get(`/customers/${alert.customer_id}/case-history`, { alert_id: alert.id });
        } catch (error) {
            $("#cpHistory").html(this.empty('Earlier cases could not be loaded.'));
            return;
        }
        if (this.id !== alert.id) return;
        if (!h.total) {
            $("#cpHistory").html(this.empty('This is the first alert on this customer.'));
            return;
        }
        const tile = (label, value) => `<div class="cp-stat"><span>${label}</span><strong>${Number(value).toLocaleString()}</strong></div>`;
        const outcomeChip = { FALSE_POSITIVE: 'muted', TRUE_POSITIVE_NO_SAR: 'medium', SAR_FILED: 'high' };
        const ruleName = (code) => (Cases.RULES[code] || [code])[0];
        const sameRule = (r) => {
            if (!r.resolved) return 'no earlier alert on this rule has been resolved';
            const parts = [];
            if (r.false_positive) parts.push(`${r.false_positive} false positive`);
            if (r.sar_filed) parts.push(`${r.sar_filed} SAR filed`);
            const other = r.resolved - r.false_positive - r.sar_filed;
            if (other) parts.push(`${other} reviewed, no suspicion`);
            return `${r.resolved} resolved earlier: ${parts.join(', ')}`;
        };
        $("#cpHistory").html(`
            <div class="cp-stats">
                ${tile('Other alerts', h.total)}
                ${tile('Still open', h.open)}
                ${tile('False positive', h.outcomes.FALSE_POSITIVE || 0)}
                ${tile('SAR filed', h.outcomes.SAR_FILED || 0)}
            </div>
            ${h.same_rules.length ? `
            <div class="kx-label mt-3">The rules on this case, earlier</div>
            <ul class="cp-factors">${h.same_rules.map(r => `<li><span><strong>${escapeHtml(r.rule)}</strong> ${escapeHtml(ruleName(r.rule))}</span><span class="text-end">${escapeHtml(sameRule(r))}</span></li>`).join('')}</ul>` : ''}
            <div class="kx-label mt-3">Most recently resolved</div>
            ${h.recent.length ? `
            <ul class="cp-others">${h.recent.map(a => `
                <li><button type="button" class="cp-other cp-history-open" data-id="${escapeHtml(a.id)}">
                    <span class="rq-score rq-score--${a.risk_score >= 80 ? 'high' : a.risk_score >= 60 ? 'medium' : 'low'}">${a.risk_score}</span>
                    <span class="cp-other__text">${escapeHtml(a.rules.map(ruleName).join(', ') || 'No rule recorded')}<br><small class="text-muted">Resolved ${escapeHtml(formatDate(a.resolved_at || a.created_at))}${a.sar_reference ? ` &middot; Ref ${escapeHtml(a.sar_reference)}` : ''}</small></span>
                    <span class="cd-chip cd-chip--${outcomeChip[a.outcome] || 'muted'}">${escapeHtml(a.outcome ? this.human(a.outcome) : 'No outcome recorded')}</span>
                </button></li>`).join('')}</ul>` : this.empty('None of the earlier alerts has been resolved yet.')}
        `);
        $(".cp-history-open").on("click", (e) => this.open($(e.currentTarget).data("id")));
    },

    async loadActivity(customerId) {
        let a;
        try {
            a = await API.get(`/customers/${customerId}/activity`);
        } catch (error) {
            $("#cpActivity").html(this.empty('Activity could not be loaded.'));
            return;
        }
        if (!this.caseData || this.caseData.rawCustomerId !== customerId) return;
        const c = a.comparison;
        const money = (amount, currency) => `${Number(amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency || ''}`.trim();
        const names = (list, limit = 4) => list.slice(0, limit).join(', ') + (list.length > limit ? ` and ${list.length - limit} more` : '');
        const row = (label, value) => `<li><span>${label}</span><span class="text-end">${value}</span></li>`;
        const total = a.buckets.reduce((sum, b) => sum + b.transactions, 0);

        $("#cpActivity").html(`
            <div class="cp-act">
                <div>
                    ${total ? `
                    <div class="cp-act__legend" aria-hidden="true">
                        <span><i style="background:#98A2B3"></i>Previous ${a.baseline_days} days</span>
                        <span><i style="background:#F97316"></i>Last ${a.window_days} days</span>
                    </div>
                    <div class="cp-act__chart"><canvas id="cpActivityChart" role="img" aria-label="Transactions in each 10-day period: the previous ${a.baseline_days} days and the last ${a.window_days} days"></canvas></div>
                    <p class="kx-note mb-0">Transactions in each 10-day period.</p>` : this.empty(`No transactions in the last ${a.baseline_days + a.window_days} days.`)}
                </div>
                <div>
                    <div class="kx-label">Last ${a.window_days} days against the customer's usual</div>
                    <ul class="cp-factors">
                        ${row('Transactions', `<strong>${c.transactions.current}</strong> &middot; usually ${c.transactions.usual} in ${a.window_days} days`)}
                        ${c.largest_amount.slice(0, 2).map(l => row('Largest amount', `<strong>${escapeHtml(money(l.current, l.currency))}</strong> &middot; ${l.previous == null ? 'no earlier transaction in this currency' : `previous largest ${escapeHtml(money(l.previous, l.currency))}`}`)).join('')}
                        ${row('New counterparties', c.new_counterparties.length ? `<strong>${c.new_counterparties.length}</strong> of ${c.counterparties}: ${escapeHtml(names(c.new_counterparties))}` : 'None')}
                        ${row('New countries', c.new_countries.length ? `<strong>${c.new_countries.length}</strong>: ${escapeHtml(names(c.new_countries))}` : 'None')}
                        ${c.high_risk_countries.length ? row('High-risk jurisdictions', `<span class="cd-chip cd-chip--high">${escapeHtml(names(c.high_risk_countries))}</span>`) : ''}
                    </ul>
                    <div class="kx-label mt-3">Behaviour changes</div>
                    ${a.findings.length ? `
                    <ul class="cp-findings">${a.findings.map(f => `<li><span class="cd-chip cd-chip--medium">${escapeHtml(f.label)}</span><span>${escapeHtml(f.evidence)}</span></li>`).join('')}</ul>`
                    : this.empty(a.enough_history
                        ? "Nothing in the last 30 days departs from this customer's own history."
                        : `Fewer than ${a.min_baseline} transactions in the previous ${a.baseline_days} days, so there is no baseline to judge against.`)}
                </div>
            </div>
        `);

        const canvas = document.getElementById("cpActivityChart");
        if (!canvas || !window.Chart) return;
        if (this.activityChart) this.activityChart.destroy();
        const day = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        this.activityChart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: a.buckets.map(b => day(b.start)),
                datasets: [{
                    label: 'Transactions',
                    data: a.buckets.map(b => b.transactions),
                    backgroundColor: a.buckets.map(b => (b.current ? '#F97316' : '#98A2B3')),
                    borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: false, maxBarThickness: 28
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#ffffff', borderColor: '#e5e7eb', borderWidth: 1, titleColor: '#1c2430', bodyColor: '#4b5563',
                        padding: 10, cornerRadius: 8, displayColors: false,
                        callbacks: {
                            title: (items) => { const b = a.buckets[items[0].dataIndex]; return `${day(b.start)} to ${day(b.end)}`; },
                            label: (ctx) => `${ctx.parsed.y} transaction${ctx.parsed.y === 1 ? '' : 's'}`,
                            afterLabel: (ctx) => (a.buckets[ctx.dataIndex].current ? `Last ${a.window_days} days` : `Previous ${a.baseline_days} days`)
                        }
                    }
                },
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#667085', font: { size: 11 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 6 } },
                    y: { beginAtZero: true, ticks: { precision: 0, color: '#667085', font: { size: 11 } }, grid: { color: '#ECEFF3' }, border: { display: false } }
                }
            }
        });
    },

    async loadOwners(customerId) {
        let owners, summary;
        try {
            [owners, summary] = await Promise.all([
                API.get(`/customers/${customerId}/beneficial-owners`),
                API.get(`/customers/${customerId}/beneficial-owners/summary`)
            ]);
        } catch (error) {
            $("#cpOwnersBody").html('<tr><td colspan="6" class="rc-empty">Beneficial owners could not be loaded.</td></tr>');
            return;
        }
        if (!this.caseData || this.caseData.rawCustomerId !== customerId) return;
        const verification = { VERIFIED: 'low', PENDING: 'medium', REJECTED: 'high' };
        $("#cpOwnersSummary").text(owners.length
            ? `${summary.owner_count} on record, ${Number(summary.total_ownership_percentage).toLocaleString()}% of ownership identified, ${summary.verified_count} verified`
            : 'Who ultimately owns or controls this customer');
        $("#cpOwnersBody").html(owners.map(o => `
            <tr>
                <td class="px-3 py-2"><strong>${escapeHtml(o.full_name)}</strong><br><small class="text-muted">${escapeHtml(this.human(o.owner_type))}${o.effective_to ? ` &middot; ended ${escapeHtml(formatDate(o.effective_to))}` : ''}</small></td>
                <td class="px-3 py-2 text-end">${o.ownership_percentage == null ? '—' : `${Number(o.ownership_percentage).toLocaleString()}%`}</td>
                <td class="px-3 py-2">${escapeHtml(this.human(o.control_type))}</td>
                <td class="px-3 py-2">${escapeHtml(o.nationality || '—')}${o.country_of_residence && o.country_of_residence !== o.nationality ? ` <small class="text-muted">lives in ${escapeHtml(o.country_of_residence)}</small>` : ''}</td>
                <td class="px-3 py-2">${o.sanctions_flag ? '<span class="cd-chip cd-chip--high">Sanctions</span> ' : ''}${o.is_pep ? '<span class="cd-chip cd-chip--medium">PEP</span>' : ''}${!o.sanctions_flag && !o.is_pep ? '<span class="text-muted">None</span>' : ''}</td>
                <td class="px-3 py-2"><span class="cd-chip cd-chip--${verification[o.verification_status] || 'muted'}">${escapeHtml(this.human(o.verification_status))}</span></td>
            </tr>`).join('') || '<tr><td colspan="6" class="rc-empty">No beneficial owners are recorded for this customer.</td></tr>');
        if (owners.length && !summary.is_cdd_complete) {
            $("#cpOwnersNote").removeClass("d-none");
        }
    },

    /** Quality check on a resolved case: the recorded result, and the form for those who may check it. */
    qaBlock(alert) {
        if (alert.status !== 'RESOLVED') return '';
        const me = (Auth.getUser() || {}).id;
        const recorded = alert.qa_result ? `
            <p><span class="cd-chip cd-chip--${alert.qa_result === 'PASS' ? 'low' : 'high'}">${alert.qa_result === 'PASS' ? 'Passed' : 'Failed'}</span>
               <span class="kx-note">Checked ${escapeHtml(formatDateTime(alert.qa_at))}</span></p>
            ${alert.qa_notes ? `<p class="mb-0">${escapeHtml(alert.qa_notes)}</p>` : ''}` : '';
        let form = '';
        if (Auth.can('alerts.qa')) {
            form = alert.resolved_by === me
                ? '<p class="kx-note mb-0">You resolved this case, so someone else must quality-check it.</p>'
                : `
            <label class="kx-label mt-2" for="cpQaNotes">${alert.qa_result ? 'Record a new check' : 'Did this case follow policy?'}</label>
            <textarea class="form-control mb-2" id="cpQaNotes" rows="2" maxlength="2000" placeholder="Notes (required when the case fails)"></textarea>
            <button type="button" class="btn btn-sm btn-outline-primary cp-qa-btn" data-result="PASS">Pass</button>
            <button type="button" class="btn btn-sm btn-outline-primary cp-qa-btn" data-result="FAIL">Fail</button>`;
        }
        if (!recorded && !form) return '';
        return `<div class="cp-disposition"><div class="kx-label">Quality check</div>${recorded || '<p class="kx-note">Not checked yet.</p>'}${form}</div>`;
    },

    async recordQA(alertId, result) {
        const notes = ($("#cpQaNotes").val() || '').trim();
        if (result === 'FAIL' && !notes) {
            showToast('error', 'Say what was wrong when a case fails the quality check.');
            $("#cpQaNotes").trigger("focus");
            return;
        }
        $(".cp-qa-btn").prop("disabled", true);
        try {
            await API.put(`/alerts/${alertId}/qa`, { result, notes: notes || null });
            showToast('success', 'Quality check recorded.');
            await this.load();
        } catch (xhr) {
            $(".cp-qa-btn").prop("disabled", false);
        }
    },

    render(d) {
        const c = this.caseData;
        const alert = d.alert;
        const customer = d.customer || {};
        const score = Number(alert.risk_score);
        const band = c.riskLevel.toLowerCase();
        const open = c.status !== 'RESOLVED';
        const statusColors = {
            OPEN: ['#e0f2fe', '#0369a1'], ASSIGNED: ['#ede9fe', '#6d28d9'], IN_REVIEW: ['#fef3c7', '#b45309'],
            ESCALATED: ['#fee2e2', '#b91c1c'], RESOLVED: ['#dcfce7', '#15803d']
        };
        const [statusBg, statusFg] = statusColors[c.status] || statusColors.OPEN;
        const codes = (alert.triggered_rules && (alert.triggered_rules.rules || alert.triggered_rules)) || [];
        const rules = (Array.isArray(codes) ? codes : []).map(code => {
            const r = Cases.RULES[code] || [code, 'Rule triggered', '—'];
            return { code, name: r[0], detail: r[1], severity: r[2] };
        });
        const sev = (s) => (s === 'CRITICAL' || s === 'HIGH' ? 'high' : s === 'MEDIUM' ? 'medium' : 'low');
        const displayName = c.customerName || c.customerId;
        const kv = (label, value) => `<div><label>${label}</label><strong>${value}</strong></div>`;

        // Flagged transactions first, newest first
        const flagged = d.transactions
            .filter(t => ((t.risk_flags && t.risk_flags.triggered_rules) || []).length)
            .sort((a, b) => new Date(b.transaction_date) - new Date(a.transaction_date));
        const txRows = flagged.slice(0, 10).map(t => `
            <tr>
                <td class="px-3 py-2 text-nowrap">${escapeHtml(formatDateTime(t.transaction_date))}</td>
                <td class="px-3 py-2">${escapeHtml(this.human(t.transaction_type))}</td>
                <td class="px-3 py-2 text-end text-nowrap">${Number(t.amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${escapeHtml(t.currency || '')}</td>
                <td class="px-3 py-2">${escapeHtml(t.meta_counterparty || '—')}${t.meta_country ? ` <small class="text-muted">${escapeHtml(t.meta_country)}</small>` : ''}</td>
                <td class="px-3 py-2"><div class="rq-rules">${t.risk_flags.triggered_rules.map(code => `<span class="rq-rule" title="${escapeHtml(code)}">${escapeHtml((Cases.RULES[code] || [code])[0])}</span>`).join('')}</div></td>
                <td class="px-3 py-2 text-end">${t.risk_score}</td>
            </tr>`).join('');

        const hits = d.screening.filter(s => s.match_status && s.match_status !== 'NO_MATCH');
        const otherAlerts = d.others.items.filter(a => a.id !== alert.id);
        const otherCount = Math.max(0, d.others.total - (open ? 1 : 0));

        $("#mainContent").html(`
            <div class="kyro-page cp">
                <button type="button" class="cp-back" id="cpBack"><i class="fas fa-arrow-left"></i> Work queue</button>

                <header class="cp-head">
                    <div class="rc-customer">
                        <span class="rc-customer__avatar cp-head__avatar" aria-hidden="true">${escapeHtml(displayName.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '?')}</span>
                        <div>
                            <h1 class="cp-head__title">${escapeHtml(displayName)}</h1>
                            <p class="cp-head__meta">
                                ${escapeHtml(c.customerId)} &middot; Case ${escapeHtml(String(alert.id).slice(0, 8))}
                                <span class="badge" style="background:${statusBg};color:${statusFg};">${escapeHtml(this.human(c.status))}</span>
                                ${customer.sanctions_flag ? '<span class="cd-chip cd-chip--high">Sanctions</span>' : ''}
                                ${customer.pep_flag ? '<span class="cd-chip cd-chip--medium">PEP</span>' : ''}
                            </p>
                        </div>
                    </div>
                    <div class="cp-head__actions">
                        ${open && Auth.can('alerts.assign') ? `
                        <button type="button" class="btn btn-outline-primary" id="cpAssign"><i class="fas fa-user-plus me-2"></i>Assign</button>` : ''}
                        ${open && Cases.canDecide() ? `
                        <button type="button" class="btn btn-primary" id="cpResolve"><i class="fas fa-check-double me-2"></i>Resolve</button>` : ''}
                        <button type="button" class="btn btn-outline-primary" id="cpExport"><i class="fas fa-file-arrow-down me-2"></i>Export report</button>
                    </div>
                </header>

                <div class="cp-grid">
                    <section class="card kd-panel">
                        <header class="kd-panel__head"><div><h2>Why this case was flagged</h2><p class="aml-subtitle">Opened ${escapeHtml(formatDateTime(alert.created_at))}${open ? `, waiting ${escapeHtml(Cases.age(alert.created_at))}` : ''}</p></div></header>
                        <div class="cd-score cd-score--${band}">
                            <div class="cd-score__value"><span>Risk score</span><strong>${isFinite(score) ? score : '—'}<small>/100</small></strong></div>
                            <div class="cd-score__meter" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${isFinite(score) ? score : 0}" aria-label="Risk score"><span style="width: ${isFinite(score) ? Math.max(0, Math.min(100, score)) : 0}%"></span></div>
                            <div class="cd-score__meta"><span class="cd-chip cd-chip--${band}">${escapeHtml(c.riskLevel)} risk</span></div>
                        </div>
                        <div class="cd-grid">
                            ${kv('Alert type', escapeHtml(this.human(alert.alert_type)))}
                            ${kv('Recommended action', escapeHtml(this.human(alert.recommended_action)))}
                            ${kv('Owner', escapeHtml(c.assignedTo))}
                        </div>
                        ${rules.length ? `
                        <ul class="cd-rules">
                            ${rules.map(r => `
                                <li>
                                    <span class="cd-rules__code">${escapeHtml(r.code)}</span>
                                    <span class="cd-rules__text"><strong>${escapeHtml(r.name)}</strong>${escapeHtml(r.detail)}</span>
                                    <span class="cd-chip cd-chip--${sev(r.severity)}">${escapeHtml(r.severity)}</span>
                                </li>`).join('')}
                        </ul>` : this.empty('No rule triggers were recorded for this alert.')}
                        ${alert.resolution_outcome ? `
                        <div class="cp-disposition">
                            <div class="kx-label">Disposition</div>
                            <p><strong>${escapeHtml(this.human(alert.resolution_outcome))}</strong>${(alert.resolution_reasons || []).length ? ` &middot; ${escapeHtml(alert.resolution_reasons.map(r => this.human(r)).join(', '))}` : ''}${alert.sar_reference ? ` &middot; Ref ${escapeHtml(alert.sar_reference)}` : ''}</p>
                            ${alert.resolution_notes ? `<p class="mb-0">${escapeHtml(alert.resolution_notes)}</p>` : ''}
                            ${alert.resolved_at ? `<p class="kx-note mb-0">Resolved ${escapeHtml(formatDateTime(alert.resolved_at))}</p>` : ''}
                        </div>` : ''}
                        ${this.qaBlock(alert)}
                    </section>

                    <section class="card kd-panel">
                        <header class="kd-panel__head"><div><h2>Customer</h2><p class="aml-subtitle">${escapeHtml(this.human(customer.customer_type))}${customer.country ? ` &middot; ${escapeHtml(customer.country)}` : ''}</p></div></header>
                        <div class="cd-grid cp-kv">
                            ${kv('Risk rating', `<span class="cd-chip cd-chip--${String(customer.risk_level || 'low').toLowerCase()}">${escapeHtml(this.human(customer.risk_level))}</span> ${customer.risk_score != null ? `<small class="text-muted">score ${customer.risk_score}</small>` : ''}`)}
                            ${kv('KYC status', escapeHtml(this.human(customer.kyc_status)))}
                            ${kv('Date of birth', customer.date_of_birth ? escapeHtml(formatDate(customer.date_of_birth)) : '—')}
                            ${kv('Residency', escapeHtml(customer.residency_country || '—'))}
                            ${kv('Last KYC review', customer.kyc_last_review ? escapeHtml(formatDate(customer.kyc_last_review)) : '—')}
                            ${kv('Last screened', customer.last_screened_at ? escapeHtml(formatDate(customer.last_screened_at)) : '—')}
                        </div>
                        <div class="kx-label">Why this rating</div>
                        ${d.profile.length ? `<ul class="cp-factors">${d.profile.map(f => `<li><span>${escapeHtml(f.risk_factor)}</span><strong>+${Number(f.risk_weight)}</strong></li>`).join('')}</ul>`
                            : this.empty('No risk factors apply to this customer.')}
                        <div class="kx-label mt-3">Other open alerts for this customer</div>
                        ${otherAlerts.length ? `
                        <ul class="cp-others">
                            ${otherAlerts.slice(0, 5).map(a => `
                                <li><button type="button" class="cp-other" data-id="${escapeHtml(a.id)}">
                                    <span class="rq-score rq-score--${a.risk_score >= 80 ? 'high' : a.risk_score >= 60 ? 'medium' : 'low'}">${a.risk_score}</span>
                                    <span class="cp-other__text">${escapeHtml(((a.triggered_rules && a.triggered_rules.rules) || []).map(code => (Cases.RULES[code] || [code])[0]).join(', ') || 'No rule recorded')}</span>
                                    <small class="text-muted">${escapeHtml(this.human(a.status))}</small>
                                </button></li>`).join('')}
                        </ul>
                        ${otherCount > otherAlerts.slice(0, 5).length ? `<button type="button" class="rq-more" id="cpAllAlerts">See all ${otherCount.toLocaleString()} in the work queue</button>` : ''}`
                        : this.empty('None.')}
                    </section>
                </div>

                <div class="cp-grid">
                    <section class="card kd-panel">
                        <header class="kd-panel__head"><div><h2>Notes and timeline</h2><p class="aml-subtitle" id="cpTimelineCount">What has been done on this case</p></div></header>
                        ${Auth.can('cases.view') && !(Auth.getUser() || {}).read_only ? `
                        <form class="cp-note" id="cpNoteForm">
                            <label class="visually-hidden" for="cpNoteBody">Add a note</label>
                            <textarea class="form-control" id="cpNoteBody" rows="2" maxlength="4000" placeholder="Add a note: what you checked, who you spoke to, what you found"></textarea>
                            <div class="cp-note__foot">
                                <span class="kx-note">Notes cannot be edited or removed once saved.</span>
                                <button type="submit" class="btn btn-sm btn-primary" id="cpNoteAdd">Add note</button>
                            </div>
                        </form>` : ''}
                        <div id="cpTimeline"><div class="kd-skeleton"></div></div>
                    </section>

                    <section class="card kd-panel">
                        <header class="kd-panel__head"><div><h2>Other cases for this customer</h2><p class="aml-subtitle">How this customer's other alerts ended</p></div></header>
                        <div id="cpHistory"><div class="kd-skeleton"></div></div>
                    </section>
                </div>

                <section class="card kd-panel mb-4">
                    <header class="kd-panel__head"><div><h2>Activity against the customer's own baseline</h2><p class="aml-subtitle">The last 30 days beside the 90 days before</p></div></header>
                    <div id="cpActivity"><div class="kd-skeleton"></div></div>
                </section>

                <section class="card border-0 rc-table-card mb-4">
                    <div class="rc-toolbar"><div class="rc-toolbar__title"><h2>Flagged transactions</h2>
                        <small class="text-muted">${flagged.length ? `${Math.min(10, flagged.length)} most recent of ${flagged.length} flagged, out of ${d.transactions.length} loaded` : `${d.transactions.length} transactions loaded, none flagged`}</small></div></div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0 fp-table">
                            <thead><tr>
                                <th class="px-3 py-2">Date</th><th class="px-3 py-2">Type</th><th class="px-3 py-2 text-end">Amount</th>
                                <th class="px-3 py-2">Counterparty</th><th class="px-3 py-2">Rules fired</th><th class="px-3 py-2 text-end">Score</th>
                            </tr></thead>
                            <tbody>${txRows || '<tr><td colspan="6" class="rc-empty">No flagged transactions for this customer.</td></tr>'}</tbody>
                        </table>
                    </div>
                </section>

                ${customer.customer_type && customer.customer_type !== 'INDIVIDUAL' ? `
                <section class="card border-0 rc-table-card mb-4">
                    <div class="rc-toolbar"><div class="rc-toolbar__title"><h2>Beneficial owners</h2>
                        <small class="text-muted" id="cpOwnersSummary">Who ultimately owns or controls this customer</small></div></div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0 fp-table">
                            <thead><tr>
                                <th class="px-3 py-2">Owner</th><th class="px-3 py-2 text-end">Ownership</th><th class="px-3 py-2">Control</th>
                                <th class="px-3 py-2">Nationality</th><th class="px-3 py-2">Flags</th><th class="px-3 py-2 text-start">Verification</th>
                            </tr></thead>
                            <tbody id="cpOwnersBody"><tr><td colspan="6" class="rc-empty">Loading...</td></tr></tbody>
                        </table>
                    </div>
                    <p class="cp-owners-note d-none" id="cpOwnersNote"><i class="fas fa-triangle-exclamation me-1" aria-hidden="true"></i>Ownership checks are not complete for this customer: an owner is still awaiting verification or is flagged for sanctions.</p>
                </section>` : ''}

                <div class="cp-grid">
                    <section class="card kd-panel">
                        <header class="kd-panel__head"><div><h2>Documents</h2><p class="aml-subtitle">Upload KYC documents and check what they say against the record</p></div></header>
                        <div id="caseDocuments"></div>
                    </section>

                    <div class="cp-stack">
                        <section class="card kd-panel">
                            <header class="kd-panel__head"><div><h2>Screening</h2><p class="aml-subtitle">Sanctions and PEP watchlist results</p></div></header>
                            ${hits.length ? `<ul class="kd-list">${hits.slice(0, 6).map(s => `
                                <li><span>${escapeHtml(this.human(s.screening_type))} &middot; ${escapeHtml((s.match_details && (s.match_details.matched_name || s.match_details.primary_name)) || 'match')}</span>
                                    <strong>${escapeHtml(this.human(s.match_status))}${s.match_score != null ? ` (${Number(s.match_score).toFixed(0)})` : ''}</strong></li>`).join('')}</ul>`
                                : this.empty(d.screening.length ? 'Screened, no matches.' : 'No screening results recorded.')}
                        </section>
                        <section class="card kd-panel">
                            <header class="kd-panel__head"><div><h2>KYC reviews</h2><p class="aml-subtitle">Scheduled and completed reviews</p></div></header>
                            ${d.reviews.length ? `<ul class="kd-list">${d.reviews.slice(0, 5).map(r => `
                                <li><span>${escapeHtml(this.human(r.review_type))} &middot; ${r.completed_date ? `completed ${escapeHtml(formatDate(r.completed_date))}` : (r.scheduled_date ? `due ${escapeHtml(formatDate(r.scheduled_date))}` : 'not scheduled')}</span>
                                    <strong>${escapeHtml(this.human(r.review_status))}</strong></li>`).join('')}</ul>`
                                : this.empty('No reviews on record.')}
                        </section>
                    </div>
                </div>
            </div>
        `);

        $("#cpBack").on("click", () => App.navigateTo('cases'));
        $("#cpAssign").on("click", () => Cases.showAssignModal(c));
        $("#cpNoteForm").on("submit", (e) => { e.preventDefault(); this.addNote(alert.id); });
        this.loadCaseFile(alert, customer);
        $(".cp-qa-btn").on("click", (e) => this.recordQA(alert.id, $(e.currentTarget).data("result")));
        $("#cpResolve").on("click", () => Cases.showResolveModal(c));
        $("#cpExport").on("click", () => Cases.showExportModal(c.caseId, c.customerId));
        $("#cpAllAlerts").on("click", () => App.navigateTo('cases', { customer: c.customerId }));
        $(".cp-other").on("click", (e) => this.open($(e.currentTarget).data("id")));
        Documents.renderSection('#caseDocuments', { customerId: c.rawCustomerId, alertId: alert.id, customerName: displayName });
    },

    /** Move to another case without leaving the page. */
    open(id) {
        this.id = id;
        window.history.pushState({ page: 'case', params: { id } }, "", `/case?id=${encodeURIComponent(id)}`);
        window.scrollTo(0, 0);
        this.load();
    }
};

window.CaseDetail = CaseDetail;
