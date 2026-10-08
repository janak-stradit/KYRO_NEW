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
                        ${open ? `
                        <button type="button" class="btn btn-outline-primary" id="cpAssign"><i class="fas fa-user-plus me-2"></i>Assign</button>
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
