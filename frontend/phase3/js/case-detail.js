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

        this.transactions = (transactions && transactions.items) || [];
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
        this.loadCounterparties(alert.customer_id);
        this.loadAccounts(alert.customer_id);
        this.loadScreening(alert.customer_id);
        this.loadRequests(alert.id);
        if (customer.customer_type && customer.customer_type !== 'INDIVIDUAL') this.loadOwners(alert.customer_id);
    },

    TIMELINE_ICONS: {
        created: 'fa-bell', note: 'fa-pen', assigned: 'fa-user-plus', escalated: 'fa-arrow-up', resolved: 'fa-check-double',
        qa: 'fa-clipboard-check', document: 'fa-file-lines', request: 'fa-envelope', updated: 'fa-rotate'
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
        if (data.clock) this.renderClock(data.clock);
        if (data.stages) this.renderStages(data.stages);
        $("#cpGlanceNotes").text(data.note_count);
        $("#cpGlanceNotesNote").text(`${data.events.length - data.note_count} other event${data.events.length - data.note_count === 1 ? '' : 's'} on the timeline`);
        this.setInvestigationCount('notes', data.note_count);
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

    // ── Tabs ───────────────────────────────────────────────────────────────
    TABS: ['overview', 'activity', 'investigation', 'file'],
    tab: 'overview',
    counts: {},

    showTab(name, scroll = true) {
        if (!this.TABS.includes(name)) name = 'overview';
        this.tab = name;
        this.TABS.forEach(t => {
            $(`#cpTab-${t}`).toggleClass("is-active", t === name).attr({ "aria-selected": String(t === name), tabindex: t === name ? 0 : -1 });
            $(`#cpPane-${t}`).prop("hidden", t !== name);
        });
        if (name === 'activity' && this.activityChart) this.activityChart.resize();
        if (scroll) window.scrollTo({ top: 0 });
    },

    /** The small number on a tab: things waiting in that section. */
    setCount(tab, n) {
        $(`#cpCount-${tab}`).text(n ? Number(n).toLocaleString() : '').toggleClass("d-none", !n);
    },

    setInvestigationCount(part, n) {
        this.counts[part] = n;
        this.setCount('investigation', (this.counts.notes || 0) + (this.counts.requests || 0));
    },

    // ── Stage tracker: where the case stands ───────────────────────────────
    renderStages(stages) {
        $("#cpStages").html(stages.map((st, i) => {
            const state = st.done ? 'done' : st.current ? 'current' : st.skipped ? 'skipped' : 'todo';
            const note = st.done ? [st.detail, st.at ? formatDate(st.at) : ''].filter(Boolean).join(' · ') : st.current ? 'Current stage' : st.skipped ? 'Skipped' : '';
            return `
            <li class="cp-stage cp-stage--${state}" ${st.current ? 'aria-current="step"' : ''}>
                <span class="cp-stage__dot" aria-hidden="true">${st.done ? '<i class="fas fa-check"></i>' : i + 1}</span>
                <span class="cp-stage__text"><strong>${escapeHtml(st.label)}</strong><small>${escapeHtml(note)}<span class="visually-hidden">${st.done ? ' (done)' : st.current ? '' : ' (not reached)'}</span></small></span>
            </li>`;
        }).join(''));
    },

    // ── Case clock (filled from the timeline response) ─────────────────────
    renderClock(clock) {
        const days = (n) => `${n} day${n === 1 ? '' : 's'}`;
        const sinceDays = (iso) => Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86400000));
        const chips = [];
        if (clock.closed_at) {
            chips.push(`<span class="cd-chip cd-chip--muted" title="Target for ${clock.risk_band}-risk cases: ${days(clock.target_days)}">Closed after ${days(clock.age_days)}</span>`);
        } else {
            chips.push(`<span class="cd-chip cd-chip--${clock.overdue ? 'high' : 'muted'}" title="Target for ${clock.risk_band}-risk cases: ${days(clock.target_days)}">${clock.overdue ? 'Overdue: open' : 'Open'} ${days(clock.age_days)} &middot; target ${clock.target_days}</span>`);
            if (clock.assigned_at) {
                const n = sinceDays(clock.assigned_at);
                chips.push(`<span class="cd-chip cd-chip--muted">Assigned ${n ? `${days(n)} ago` : 'today'}</span>`);
            }
        }
        $("#cpClock").html(chips.join(' '));
    },

    // ── Why each rule exists ───────────────────────────────────────────────
    async loadBasis(alertId, codes) {
        if (!codes.length) return;
        let basis;
        try {
            basis = await API.get('/controls/basis', { codes: codes.join(',') });
        } catch (error) { return; }
        if (this.id !== alertId) return;
        const withBasis = codes.filter(code => (basis[code] || []).length);
        const body = withBasis.length ? withBasis.map(code => `
            <li>
                <span class="cd-rules__code">${escapeHtml(code)}</span>
                <span class="cp-basis__text">${basis[code].slice(0, 3).map(b => `<span><strong>${escapeHtml(b.citation)}</strong> ${escapeHtml(b.who)} must ${escapeHtml(b.action)}${b.deadline ? ` (${escapeHtml(b.deadline)})` : ''}</span>`).join('')}${basis[code].length > 3 ? `<span class="kx-note">and ${basis[code].length - 3} more</span>` : ''}</span>
            </li>`).join('')
            : '';
        $("#cpBasis").html(`
            <div class="kx-label mt-3">Regulatory basis</div>
            ${body ? `<ul class="cp-basis">${body}</ul>` : ''}
            ${withBasis.length < codes.length ? `<p class="kx-note mb-0">${withBasis.length ? 'The other rules have' : 'These rules have'} no confirmed obligation mapped to them yet. Mappings are confirmed on the Regulations page.</p>` : ''}
        `);
    },

    // ── Customer profile ───────────────────────────────────────────────────
    money(amount, currency) {
        return `${Number(amount).toLocaleString(undefined, { maximumFractionDigits: 0 })} ${currency || ''}`.trim();
    },

    /** A few lines on who the customer is, for the Overview. */
    profileSummary(customer) {
        const m = customer.customer_metadata || {};
        const rows = [
            [customer.customer_type === 'INDIVIDUAL' ? 'Occupation' : 'Business', m.occupation || m.industry],
            ['Source of funds', m.source_of_funds],
            ['Expected monthly turnover', m.expected_monthly_turnover && this.money(m.expected_monthly_turnover.amount, m.expected_monthly_turnover.currency)],
            ['Customer since', m.onboarded_on && formatDate(m.onboarded_on)]
        ].filter(r => r[1]);
        if (!rows.length) return '';
        return `<div class="kx-label mt-3">Profile</div>
            <ul class="cp-factors">${rows.map(([label, value]) => `<li><span>${label}</span><span class="text-end">${escapeHtml(String(value))}</span></li>`).join('')}</ul>`;
    },

    /** Everything recorded at onboarding, for the Customer file tab. */
    profilePanel(customer) {
        const m = customer.customer_metadata || {};
        const individual = customer.customer_type === 'INDIVIDUAL';
        const address = m.address ? [m.address.line1, m.address.city, m.address.postal_code, m.address.country].filter(Boolean).join(', ') : null;
        const id = m.id_document;
        const expired = id && id.expires_on && new Date(id.expires_on) < new Date();
        const fields = [
            ['Legal name', customer.full_name],
            ['Type', this.human(customer.customer_type)],
            [individual ? 'Date of birth' : 'Incorporated', individual ? (customer.date_of_birth && formatDate(customer.date_of_birth)) : (m.incorporated_on && formatDate(m.incorporated_on))],
            [individual ? 'Occupation' : 'Business', m.occupation || m.industry],
            [individual ? 'Employer' : 'Registration number', individual ? m.employer : m.registration_number],
            ['Country', customer.country],
            ['Residency', customer.residency_country],
            ['Tax residency', m.tax_residency],
            ['Address', address],
            ['Email', customer.email],
            ['Phone', customer.phone],
            ['Source of funds', m.source_of_funds],
            ['Source of wealth', m.source_of_wealth],
            ['Purpose of relationship', m.purpose_of_relationship],
            ['Expected monthly turnover', m.expected_monthly_turnover && this.money(m.expected_monthly_turnover.amount, m.expected_monthly_turnover.currency)],
            ['Customer since', m.onboarded_on && formatDate(m.onboarded_on)],
            ['Onboarded through', m.onboarding_channel],
            ['Relationship manager', m.relationship_manager],
            ['Employees', m.employees]
        ].filter(f => f[1] !== undefined && f[1] !== null && f[1] !== '');
        const cell = ([label, value]) => `<div><label>${label}</label><strong>${escapeHtml(String(value))}</strong></div>`;
        return `<div class="cd-grid cp-profile">${fields.map(cell).join('')}
            ${id ? `<div><label>Identity document</label><strong>${escapeHtml(id.type)} ending ${escapeHtml(id.number_ending)}${id.expires_on ? ` <span class="cd-chip cd-chip--${expired ? 'high' : 'muted'}">${expired ? 'Expired' : 'Expires'} ${escapeHtml(formatDate(id.expires_on))}</span>` : ''}</strong></div>` : ''}
        </div>`;
    },

    // ── Accounts ───────────────────────────────────────────────────────────
    async loadAccounts(customerId) {
        let d;
        try {
            d = await API.get(`/customers/${customerId}/accounts-overview`);
        } catch (error) {
            $("#cpAccountsBody").html('<tr><td colspan="7" class="rc-empty">Accounts could not be loaded.</td></tr>');
            return;
        }
        if (!this.caseData || this.caseData.rawCustomerId !== customerId) return;
        const statusChip = { ACTIVE: 'low', FROZEN: 'high', CLOSED: 'muted', SUSPENDED: 'medium' };
        const amount = (v, c) => `${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${escapeHtml(c || '')}`;
        $("#cpAccountsSub").text(`${d.accounts.length} account${d.accounts.length === 1 ? '' : 's'}${d.accounts.some(a => a.sample_data) ? ' · account details are sample data' : ''}`);
        $("#cpAccountsBody").html(d.accounts.map(a => `
            <tr>
                <td class="px-3 py-2"><strong>${escapeHtml(a.product || this.human(a.account_type))}</strong><br><small class="text-muted">${a.account_number ? `No. ${escapeHtml(a.account_number)} &middot; ` : ''}${escapeHtml(this.human(a.account_type))} &middot; ${escapeHtml(a.currency)}${a.branch ? ` &middot; ${escapeHtml(a.branch)}` : ''}</small></td>
                <td class="px-3 py-2">${escapeHtml(a.purpose || '—')}</td>
                <td class="px-3 py-2 text-nowrap">${a.opened_date ? escapeHtml(formatDate(a.opened_date)) : '—'}${a.opened_channel ? `<br><small class="text-muted">${escapeHtml(a.opened_channel)}</small>` : ''}</td>
                <td class="px-3 py-2"><span class="cd-chip cd-chip--${statusChip[a.account_status] || 'muted'}">${escapeHtml(this.human(a.account_status))}</span></td>
                <td class="px-3 py-2 text-end text-nowrap"><strong>${amount(a.balance, a.currency)}</strong></td>
                <td class="px-3 py-2 text-end text-nowrap">${a.last_30_days.transactions ? `${amount(a.last_30_days.amount, a.currency)}<br><small class="text-muted">${a.last_30_days.transactions} transaction${a.last_30_days.transactions === 1 ? '' : 's'}</small>` : '<span class="text-muted">No activity</span>'}</td>
                <td class="px-3 py-2 text-nowrap">${a.last_transaction_at ? escapeHtml(formatDate(a.last_transaction_at)) : '—'}<br><small class="text-muted">${a.transactions} in all${a.flagged_transactions ? `, ${a.flagged_transactions} flagged` : ''}</small></td>
            </tr>`).join('') || '<tr><td colspan="7" class="rc-empty">No accounts on record.</td></tr>');

        // Actual turnover beside what the customer said to expect, when both are in the same currency
        const expected = d.expected_monthly_turnover;
        const actual = expected && d.turnover_last_30_days.find(t => t.currency === expected.currency);
        if (expected && actual && actual.amount > expected.amount * 1.5) {
            $("#cpTurnoverNote").removeClass("d-none").html(`<i class="fas fa-triangle-exclamation me-1" aria-hidden="true"></i>Turnover in the last 30 days was ${escapeHtml(this.money(actual.amount, actual.currency))}, against ${escapeHtml(this.money(expected.amount, expected.currency))} a month expected at onboarding.`);
        }
    },

    // ── Counterparties and countries ───────────────────────────────────────
    async loadCounterparties(customerId) {
        let d;
        try {
            d = await API.get(`/customers/${customerId}/counterparties`);
        } catch (error) {
            $("#cpCounterparties").html(this.empty('Counterparties could not be loaded.'));
            return;
        }
        if (!this.caseData || this.caseData.rawCustomerId !== customerId) return;
        if (!d.transactions) {
            $("#cpCounterparties").html(this.empty(`No transactions in the last ${d.days} days.`));
            return;
        }
        const totals = (g) => g.totals.slice(0, 2).map(t => `${Number(t.amount).toLocaleString(undefined, { maximumFractionDigits: 0 })} ${escapeHtml(t.currency)}`).join(', ');
        const chips = (g) => `${g.new ? '<span class="cd-chip cd-chip--medium">New</span>' : ''}${g.high_risk ? '<span class="cd-chip cd-chip--high">High-risk</span>' : ''}`;
        const list = (items, sub) => `<ul class="cp-parties">${items.map(g => `
            <li>
                <span class="cp-parties__name"><strong>${escapeHtml(g.name)}</strong>${sub(g)} ${chips(g)}</span>
                <span class="cp-parties__n">${g.transactions} txn${g.transactions === 1 ? '' : 's'}</span>
                <span class="cp-parties__amt">${totals(g)}</span>
            </li>`).join('')}</ul>`;
        $("#cpCounterpartiesSub").text(`Last ${d.days} days. "New" means first seen in the last ${d.new_since_days} days.`);
        $("#cpCounterparties").html(`
            <div class="cp-act">
                <div>
                    <div class="kx-label">Counterparties${d.counterparty_count > d.counterparties.length ? ` (top ${d.counterparties.length} of ${d.counterparty_count})` : ''}</div>
                    ${d.counterparties.length ? list(d.counterparties, g => (g.countries.length ? ` <small class="text-muted">${escapeHtml(g.countries.join(', '))}</small>` : '')) : this.empty('No counterparty is recorded on these transactions.')}
                </div>
                <div>
                    <div class="kx-label">Countries${d.country_count > d.countries.length ? ` (top ${d.countries.length} of ${d.country_count})` : ''}</div>
                    ${d.countries.length ? list(d.countries, () => '') : this.empty('No country is recorded on these transactions.')}
                </div>
            </div>
        `);
    },

    // ── Screening matches ──────────────────────────────────────────────────
    async loadScreening(customerId) {
        let matches;
        try {
            matches = await API.get(`/customers/${customerId}/screening-matches`);
        } catch (error) {
            $("#cpScreening").html(this.empty('Screening results could not be loaded.'));
            return;
        }
        if (!this.caseData || this.caseData.rawCustomerId !== customerId) return;
        const undecided = matches.filter(m => !m.resolution).length;
        $("#cpGlanceMatches").text(matches.length).toggleClass("cp-glance__value--high", undecided > 0);
        $("#cpGlanceMatchesNote").text(matches.length ? (undecided ? `${undecided} awaiting a decision` : 'all decided') : 'none on record');
        this.setCount('file', undecided);
        if (!matches.length) {
            $("#cpScreening").html(this.empty('No possible or confirmed watchlist matches on record.'));
            return;
        }
        const mayDecide = Auth.can('screening.run');
        const resolution = { CLEARED: ['low', 'Not the same person'], CONFIRMED: ['high', 'Confirmed match'], ESCALATED: ['medium', 'Escalated'] };
        const cell = (v) => (v == null || v === '' ? '<span class="text-muted">—</span>' : escapeHtml(String(v)));
        const SHOWN = 3;
        const showAll = this.showAllMatches === customerId;
        const visible = showAll ? matches : matches.slice(0, SHOWN);
        $("#cpScreening").html(visible.map(m => {
            const done = resolution[m.resolution];
            return `
            <article class="cp-match" data-id="${escapeHtml(m.id)}">
                <header class="cp-match__head">
                    <span><strong>${escapeHtml(this.human(m.screening_type))}</strong>${m.match_score != null ? ` &middot; match score ${Number(m.match_score).toFixed(0)}` : ''}${m.listed.still_listed === false ? ' &middot; <span class="text-muted">no longer listed</span>' : ''}</span>
                    <span class="cd-chip cd-chip--${done ? done[0] : (m.match_status === 'CONFIRMED_MATCH' ? 'high' : 'medium')}">${done ? done[1] : escapeHtml(this.human(m.match_status))}</span>
                </header>
                <table class="cp-match__table">
                    <thead><tr><th></th><th>${escapeHtml(m.subject.kind)}</th><th>List entry</th></tr></thead>
                    <tbody>
                        <tr><th>Name</th><td>${cell(m.subject.name)}</td><td>${cell(m.listed.name)}${m.listed.aka_names.length ? `<br><small class="text-muted">also ${escapeHtml(m.listed.aka_names.join('; '))}</small>` : ''}</td></tr>
                        <tr><th>Date of birth</th><td>${cell(m.subject.date_of_birth && formatDate(m.subject.date_of_birth))}</td><td>${cell(m.listed.date_of_birth && formatDate(m.listed.date_of_birth))}${m.dob_match === true ? ' <span class="cd-chip cd-chip--high">Same</span>' : ''}</td></tr>
                        <tr><th>Country</th><td>${cell(m.subject.country)}</td><td>${cell(m.listed.nationalities.join(', '))}</td></tr>
                        <tr><th>List</th><td></td><td>${cell(m.listed.list)}${m.listed.programs.length ? `<br><small class="text-muted">${escapeHtml(m.listed.programs.join(', '))}</small>` : ''}</td></tr>
                    </tbody>
                </table>
                ${m.listed.remarks ? `<p class="kx-note mb-2">${escapeHtml(m.listed.remarks.length > 220 ? m.listed.remarks.slice(0, 217) + '...' : m.listed.remarks)}</p>` : ''}
                ${m.resolution ? `
                <p class="cp-match__decision">${escapeHtml(m.resolution_notes || '')}<br><small class="text-muted">${escapeHtml(m.resolved_by_name || 'Unknown user')} &middot; ${escapeHtml(formatDateTime(m.resolved_at))}</small></p>`
                : mayDecide ? `
                <label class="visually-hidden" for="cpMatchNotes-${escapeHtml(m.id)}">Reason for the decision</label>
                <textarea class="form-control mb-2 cp-match__notes" id="cpMatchNotes-${escapeHtml(m.id)}" rows="2" maxlength="2000" placeholder="Reason for the decision (required)"></textarea>
                <div class="cp-match__actions">
                    <button type="button" class="btn btn-sm btn-outline-primary cp-match-decide" data-decision="CLEARED">Not the same person</button>
                    <button type="button" class="btn btn-sm btn-outline-primary cp-match-decide" data-decision="ESCALATED">Escalate</button>
                    <button type="button" class="btn btn-sm btn-outline-primary cp-match-decide" data-decision="CONFIRMED">Confirmed match</button>
                </div>` : '<p class="kx-note mb-0">Awaiting a decision.</p>'}
            </article>`;
        }).join('') + (matches.length > SHOWN ? `<button type="button" class="rq-more mt-2" id="cpMatchesToggle">${showAll ? `Show the first ${SHOWN} only` : `Show all ${matches.length} matches`}</button>` : ''));
        $("#cpMatchesToggle").on("click", () => { this.showAllMatches = showAll ? null : customerId; this.loadScreening(customerId); });
        $("#cpScreening").off("click.match").on("click.match", ".cp-match-decide", (e) => this.decideMatch($(e.currentTarget)));
    },

    async decideMatch($button) {
        const $match = $button.closest(".cp-match");
        const $notes = $match.find(".cp-match__notes");
        const notes = ($notes.val() || '').trim();
        if (!notes) {
            showToast('error', 'Give the reason for the decision.');
            $notes.trigger("focus");
            return;
        }
        $match.find(".cp-match-decide").prop("disabled", true);
        try {
            await API.put(`/screening/${$match.data("id")}/decision`, { decision: $button.data("decision"), notes });
            showToast('success', 'Screening decision recorded.');
            await this.load();  // a confirmed match changes the customer's flags and rating
        } catch (xhr) {
            $match.find(".cp-match-decide").prop("disabled", false);
        }
    },

    // ── Transactions: flagged or all, filtered, exportable ─────────────────
    txFilters: { scope: 'flagged', type: '', from: '', to: '', min: '', shown: 25 },

    isFlagged(t) {
        return ((t.risk_flags && t.risk_flags.triggered_rules) || []).length > 0;
    },

    filteredTransactions() {
        const f = this.txFilters;
        const from = f.from ? new Date(`${f.from}T00:00:00`) : null;
        const to = f.to ? new Date(`${f.to}T23:59:59`) : null;
        const min = f.min === '' ? null : Number(f.min);
        return (this.transactions || [])
            .filter(t => (f.scope === 'all' || this.isFlagged(t))
                && (!f.type || t.transaction_type === f.type)
                && (!from || new Date(t.transaction_date) >= from)
                && (!to || new Date(t.transaction_date) <= to)
                && (min == null || isNaN(min) || Number(t.amount) >= min))
            .sort((a, b) => new Date(b.transaction_date) - new Date(a.transaction_date));
    },

    renderTransactions() {
        const rows = this.filteredTransactions();
        const f = this.txFilters;
        const total = (this.transactions || []).length;
        const flaggedCount = (this.transactions || []).filter(t => this.isFlagged(t)).length;
        $("#cpTxCount").text(`${Math.min(f.shown, rows.length)} of ${rows.length.toLocaleString()} shown · ${flaggedCount} flagged of ${total} loaded${total >= 500 ? ' (the most recent 500)' : ''}`);
        $("#cpTxBody").html(rows.slice(0, f.shown).map(t => {
            const codes = (t.risk_flags && t.risk_flags.triggered_rules) || [];
            return `
            <tr>
                <td class="px-3 py-2 text-nowrap">${escapeHtml(formatDateTime(t.transaction_date))}</td>
                <td class="px-3 py-2">${escapeHtml(this.human(t.transaction_type))}</td>
                <td class="px-3 py-2 text-end text-nowrap">${Number(t.amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${escapeHtml(t.currency || '')}</td>
                <td class="px-3 py-2">${escapeHtml(t.meta_counterparty || '—')}${t.meta_country ? ` <small class="text-muted">${escapeHtml(t.meta_country)}</small>` : ''}</td>
                <td class="px-3 py-2">${codes.length ? `<div class="rq-rules">${codes.map(code => `<span class="rq-rule" title="${escapeHtml(code)}">${escapeHtml((Cases.RULES[code] || [code])[0])}</span>`).join('')}</div>` : '<span class="text-muted">None</span>'}</td>
                <td class="px-3 py-2 text-end">${t.risk_score == null ? '—' : t.risk_score}</td>
            </tr>`;
        }).join('') || `<tr><td colspan="6" class="rc-empty">${total ? 'No transactions match these filters.' : 'No transactions on record for this customer.'}</td></tr>`);
        $("#cpTxMore").toggleClass("d-none", rows.length <= f.shown).text(`Show ${Math.min(25, rows.length - f.shown)} more`);
        $("#cpTxExport").prop("disabled", !rows.length);
    },

    setupTransactions() {
        this.txFilters = { scope: 'flagged', type: '', from: '', to: '', min: '', shown: 25 };
        const types = [...new Set((this.transactions || []).map(t => t.transaction_type).filter(Boolean))].sort();
        $("#cpTxType").append(types.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(this.human(t))}</option>`).join(''));
        const change = (key, value) => { this.txFilters[key] = value; this.txFilters.shown = 25; this.renderTransactions(); };
        $(".cp-tx-scope").on("click", (e) => {
            $(".cp-tx-scope").removeClass("is-active").attr("aria-pressed", "false");
            $(e.currentTarget).addClass("is-active").attr("aria-pressed", "true");
            change('scope', $(e.currentTarget).data("scope"));
        });
        $("#cpTxType").on("change", (e) => change('type', $(e.currentTarget).val()));
        $("#cpTxFrom").on("change", (e) => change('from', $(e.currentTarget).val()));
        $("#cpTxTo").on("change", (e) => change('to', $(e.currentTarget).val()));
        $("#cpTxMin").on("input", (e) => change('min', $(e.currentTarget).val()));
        $("#cpTxMore").on("click", () => { this.txFilters.shown += 25; this.renderTransactions(); });
        $("#cpTxExport").on("click", () => this.exportTransactions());
        this.renderTransactions();
    },

    exportTransactions() {
        // A leading =, +, - or @ would be run as a formula by a spreadsheet
        const cell = (value) => {
            let text = value == null ? '' : String(value);
            if (/^[=+\-@]/.test(text) && isNaN(Number(text))) text = `'${text}`;
            return `"${text.replace(/"/g, '""')}"`;
        };
        const lines = [['Date', 'Type', 'Amount', 'Currency', 'Counterparty', 'Country', 'Rules fired', 'Risk score'].map(cell).join(',')];
        this.filteredTransactions().forEach(t => lines.push([
            new Date(t.transaction_date).toISOString(), t.transaction_type, Number(t.amount).toFixed(2), t.currency, t.meta_counterparty, t.meta_country,
            ((t.risk_flags && t.risk_flags.triggered_rules) || []).join(' '), t.risk_score
        ].map(cell).join(',')));
        const url = URL.createObjectURL(new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }));
        const link = document.createElement('a');
        link.href = url;
        link.download = `transactions-${(this.caseData.customerId || 'customer').replace(/[^A-Za-z0-9-]/g, '')}-${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    },

    // ── Requests for information ───────────────────────────────────────────
    async loadRequests(alertId) {
        let requests;
        try {
            requests = await API.get(`/alerts/${alertId}/requests`);
        } catch (error) {
            $("#cpRequests").html(this.empty('Requests could not be loaded.'));
            return;
        }
        if (this.id !== alertId) return;
        const openRequests = requests.filter(r => r.status === 'OPEN');
        const lateRequests = openRequests.filter(r => r.overdue).length;
        $("#cpGlanceRequests").text(openRequests.length).toggleClass("cp-glance__value--high", lateRequests > 0);
        $("#cpGlanceRequestsNote").text(lateRequests ? `${lateRequests} past the due date` : requests.length ? `${requests.length} recorded in all` : 'nothing asked for yet');
        this.setInvestigationCount('requests', openRequests.length);
        const mayEdit = Auth.can('alerts.escalate');
        const chip = (r) => (r.status === 'RECEIVED' ? ['low', 'Received'] : r.status === 'CANCELLED' ? ['muted', 'Withdrawn'] : r.overdue ? ['high', 'Overdue'] : ['medium', 'Waiting']);
        $("#cpRequests").html(requests.length ? `<ul class="cp-requests">${requests.map(r => `
            <li class="cp-request" data-id="${escapeHtml(r.id)}">
                <div class="cp-request__head">
                    <strong>${escapeHtml(r.requested_from)}</strong>
                    <span class="cd-chip cd-chip--${chip(r)[0]}">${chip(r)[1]}</span>
                </div>
                <p class="cp-request__subject">${escapeHtml(r.subject)}</p>
                <p class="cp-tl__meta">Asked by ${escapeHtml(r.requested_by_name)} on ${escapeHtml(formatDate(r.created_at))} &middot; due ${escapeHtml(formatDate(r.due_date))}</p>
                ${r.response_note ? `<p class="cp-request__answer">${escapeHtml(r.response_note)}<br><small class="text-muted">${escapeHtml(r.closed_by_name || '')} &middot; ${escapeHtml(formatDate(r.closed_at))}</small></p>` : ''}
                ${r.status === 'OPEN' && mayEdit ? `
                <div class="cp-request__close">
                    <label class="visually-hidden" for="cpReqNote-${escapeHtml(r.id)}">What was received</label>
                    <input type="text" class="form-control form-control-sm cp-request__note" id="cpReqNote-${escapeHtml(r.id)}" maxlength="2000" placeholder="What was received">
                    <button type="button" class="btn btn-sm btn-outline-primary cp-request-close" data-status="RECEIVED">Mark received</button>
                    <button type="button" class="btn btn-sm rc-actions__icon cp-request-close" data-status="CANCELLED" title="Withdraw this request" aria-label="Withdraw this request"><i class="fas fa-xmark"></i></button>
                </div>` : ''}
            </li>`).join('')}</ul>` : this.empty('Nothing has been requested on this case.'));
        $("#cpRequests").off("click.req").on("click.req", ".cp-request-close", (e) => this.closeRequest($(e.currentTarget)));
    },

    async addRequest(alertId) {
        const body = { requested_from: $("#cpReqFrom").val().trim(), subject: $("#cpReqSubject").val().trim(), due_date: $("#cpReqDue").val() };
        if (!body.requested_from || !body.subject || !body.due_date) {
            showToast('error', 'Say who was asked, what for, and by when.');
            return;
        }
        const $button = $("#cpReqAdd").prop("disabled", true);
        try {
            await API.post(`/alerts/${alertId}/requests`, body);
            $("#cpReqSubject").val('');
            await Promise.all([this.loadRequests(alertId), this.loadTimeline(alertId)]);
        } catch (xhr) { /* reported by the API layer */ }
        $button.prop("disabled", false);
    },

    async closeRequest($button) {
        const $request = $button.closest(".cp-request");
        const status = $button.data("status");
        const note = ($request.find(".cp-request__note").val() || '').trim();
        if (status === 'RECEIVED' && !note) {
            showToast('error', 'Say what was received.');
            $request.find(".cp-request__note").trigger("focus");
            return;
        }
        $request.find("button").prop("disabled", true);
        try {
            await API.put(`/alerts/requests/${$request.data("id")}`, { status, response_note: note || null });
            await Promise.all([this.loadRequests(this.id), this.loadTimeline(this.id)]);
        } catch (xhr) {
            $request.find("button").prop("disabled", false);
        }
    },

    // ── Case summary ───────────────────────────────────────────────────────
    renderSummary(alert) {
        if (alert.summary) {
            const mock = alert.summary_provider === 'mock';
            $("#cpSummary").html(`<p class="cp-summary__text">${escapeHtml(alert.summary)}</p>`);
            $("#cpSummaryMeta").text(`${mock ? 'Built by the template from the facts on file; an AI model is not connected' : 'Written by the AI model from the facts on file, names removed before sending'} · ${formatDateTime(alert.summary_at)}`);
            return;
        }
        if (Auth.can('alerts.escalate')) {
            this.generateSummary(alert.id);  // first visit to this case: write it once and keep it
        } else {
            $("#cpSummary").html(this.empty('No summary has been written for this case yet.'));
        }
    },

    async generateSummary(alertId) {
        const $button = $("#cpSummaryRefresh").prop("disabled", true);
        $("#cpSummary").html('<p class="cp-summary__wait"><span class="spinner-border spinner-border-sm" aria-hidden="true"></span>Writing the summary from the facts on this case. This can take up to a minute.</p>');
        let result;
        try {
            result = await API.postSlow(`/alerts/${alertId}/summary`, {});
        } catch (xhr) {
            const off = xhr && xhr.status === 409;
            if (this.id === alertId) {
                $("#cpSummary").html(this.empty(off ? 'AI features are switched off, so no summary can be written.' : 'The summary could not be written. Select "Regenerate" to try again.'));
            }
            $button.prop("disabled", false);
            return;
        }
        $button.prop("disabled", false);
        if (this.id !== alertId) return;
        this.renderSummary(result);
    },

    // ── Draft narrative ────────────────────────────────────────────────────
    async draftNarrative(alertId) {
        const $button = $("#cpNarrativeDraft").prop("disabled", true).text('Drafting...');
        let result;
        try {
            result = await API.postSlow(`/alerts/${alertId}/draft-narrative`, {});
        } catch (xhr) {
            $button.prop("disabled", false).text('Draft narrative');
            return;
        }
        if (this.id !== alertId) return;
        $button.prop("disabled", false).text('Draft again');
        $("#cpNarrative").html(`
            <p class="cp-narrative__source">${result.mock
                ? 'Arranged from the facts on file by the built-in template. It is not written by an AI model and adds nothing to the facts.'
                : 'Drafted by the AI model from the facts on file, with names removed before sending. Check every statement before using it.'}</p>
            <label class="visually-hidden" for="cpNarrativeText">Draft narrative</label>
            <textarea class="form-control cp-narrative__text" id="cpNarrativeText" rows="14">${escapeHtml(result.narrative)}</textarea>
            <div class="cp-note__foot">
                <span class="kx-note">Edit the draft, then copy it or keep it on the case as a note.</span>
                <span>
                    <button type="button" class="btn btn-sm btn-outline-primary" id="cpNarrativeCopy">Copy</button>
                    <button type="button" class="btn btn-sm btn-primary" id="cpNarrativeSave">Save as note</button>
                </span>
            </div>
        `);
        $("#cpNarrativeCopy").on("click", async () => {
            try {
                await navigator.clipboard.writeText($("#cpNarrativeText").val());
                showToast('success', 'Draft copied.');
            } catch (error) {
                $("#cpNarrativeText").trigger("select");
                showToast('error', 'Copying is blocked by the browser. The text is selected: press Ctrl+C.');
            }
        });
        $("#cpNarrativeSave").on("click", async () => {
            const text = ($("#cpNarrativeText").val() || '').trim();
            if (!text) return;
            if (text.length > 4000) { showToast('error', 'A note can hold 4,000 characters. Shorten the draft first.'); return; }
            $("#cpNarrativeSave").prop("disabled", true);
            try {
                await API.post(`/alerts/${alertId}/notes`, { body: text });
                showToast('success', 'Draft saved as a note.');
                await this.loadTimeline(alertId);
            } catch (xhr) { /* reported by the API layer */ }
            $("#cpNarrativeSave").prop("disabled", false);
        });
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

        const otherAlerts = d.others.items.filter(a => a.id !== alert.id);
        const otherCount = Math.max(0, d.others.total - (open ? 1 : 0));

        $("#mainContent").html(`
            <div class="kyro-page cp">
                <div class="cp-sticky">
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
                                <span id="cpClock"></span>
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
                    <ol class="cp-stages" id="cpStages" aria-label="Case stage"></ol>
                    <div class="cp-tabs" role="tablist" aria-label="Case sections">
                        <button type="button" class="cp-tab" role="tab" id="cpTab-overview" data-tab="overview" aria-controls="cpPane-overview">Overview</button>
                        <button type="button" class="cp-tab" role="tab" id="cpTab-activity" data-tab="activity" aria-controls="cpPane-activity">Activity <span class="cp-tab__count" id="cpCount-activity"></span></button>
                        <button type="button" class="cp-tab" role="tab" id="cpTab-investigation" data-tab="investigation" aria-controls="cpPane-investigation">Investigation <span class="cp-tab__count" id="cpCount-investigation"></span></button>
                        <button type="button" class="cp-tab" role="tab" id="cpTab-file" data-tab="file" aria-controls="cpPane-file">Customer file <span class="cp-tab__count" id="cpCount-file"></span></button>
                    </div>
                </div>

                <div class="cp-pane" id="cpPane-overview" role="tabpanel" aria-labelledby="cpTab-overview" data-pane="overview">
                    <div class="cp-glance">
                        <button type="button" class="cp-glance__tile" data-tab="overview"><i class="fas fa-gauge-high" aria-hidden="true"></i><span>Risk score</span><strong class="cp-glance__value--${band}">${isFinite(score) ? score : '—'}</strong><small>${escapeHtml(c.riskLevel.toLowerCase())} risk</small></button>
                        <button type="button" class="cp-glance__tile" data-tab="activity"><i class="fas fa-flag" aria-hidden="true"></i><span>Flagged transactions</span><strong id="cpGlanceFlagged">—</strong><small id="cpGlanceFlaggedNote">&nbsp;</small></button>
                        <button type="button" class="cp-glance__tile" data-tab="overview"><i class="fas fa-bell" aria-hidden="true"></i><span>Other open alerts</span><strong>${otherCount.toLocaleString()}</strong><small>on this customer</small></button>
                        <button type="button" class="cp-glance__tile" data-tab="investigation"><i class="fas fa-pen" aria-hidden="true"></i><span>Notes</span><strong id="cpGlanceNotes">—</strong><small id="cpGlanceNotesNote">&nbsp;</small></button>
                        <button type="button" class="cp-glance__tile" data-tab="investigation"><i class="fas fa-envelope" aria-hidden="true"></i><span>Open requests</span><strong id="cpGlanceRequests">—</strong><small id="cpGlanceRequestsNote">&nbsp;</small></button>
                        <button type="button" class="cp-glance__tile" data-tab="file"><i class="fas fa-user-shield" aria-hidden="true"></i><span>Screening matches</span><strong id="cpGlanceMatches">—</strong><small id="cpGlanceMatchesNote">&nbsp;</small></button>
                    </div>
                    <section class="card kd-panel cp-summary mb-4" aria-live="polite">
                        <header class="kd-panel__head">
                            <div><h2><i class="fas fa-wand-magic-sparkles cp-summary__icon" aria-hidden="true"></i>Case summary</h2><p class="aml-subtitle" id="cpSummaryMeta">Written from the facts on this case</p></div>
                            ${Auth.can('alerts.escalate') ? '<button type="button" class="btn btn-sm rc-actions__view" id="cpSummaryRefresh">Regenerate</button>' : ''}
                        </header>
                        <div id="cpSummary"><div class="kd-skeleton"></div></div>
                    </section>
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
                        <div id="cpBasis"></div>
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
                        ${this.profileSummary(customer)}
                        <div class="kx-label mt-3">Why this rating</div>
                        ${d.profile.length ? `<ul class="cp-factors">${d.profile.map(f => `<li><span>${escapeHtml(f.risk_factor)}</span><strong>+${Number(f.risk_weight)}</strong></li>`).join('')}</ul>`
                            : this.empty('No risk factors apply to this customer.')}
                    </section>
                    </div>
                    <section class="card kd-panel mb-4">
                        <header class="kd-panel__head"><div><h2>Other cases for this customer</h2><p class="aml-subtitle">What else is open, and how earlier alerts ended</p></div></header>
                        <div class="cp-act">
                            <div>
                        <div class="kx-label">Open now</div>
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
                            </div>
                            <div id="cpHistory"><div class="kd-skeleton"></div></div>
                        </div>
                    </section>
                </div>

                <div class="cp-pane" id="cpPane-activity" role="tabpanel" aria-labelledby="cpTab-activity" data-pane="activity" hidden>
                <section class="card kd-panel mb-4">
                    <header class="kd-panel__head"><div><h2>Activity against the customer's own baseline</h2><p class="aml-subtitle">The last 30 days beside the 90 days before</p></div></header>
                    <div id="cpActivity"><div class="kd-skeleton"></div></div>
                </section>
                <section class="card kd-panel mb-4">
                    <header class="kd-panel__head"><div><h2>Counterparties and countries</h2><p class="aml-subtitle" id="cpCounterpartiesSub">Who and where this customer deals with</p></div></header>
                    <div id="cpCounterparties"><div class="kd-skeleton"></div></div>
                </section>
                <section class="card border-0 rc-table-card mb-4">
                    <div class="rc-toolbar">
                        <div class="rc-toolbar__title"><h2>Transactions</h2><small class="text-muted" id="cpTxCount"></small></div>
                        <div class="rc-toolbar__controls cp-tx-controls">
                            <div class="cp-seg" role="group" aria-label="Which transactions to show">
                                <button type="button" class="cp-tx-scope is-active" data-scope="flagged" aria-pressed="true">Flagged</button>
                                <button type="button" class="cp-tx-scope" data-scope="all" aria-pressed="false">All</button>
                            </div>
                            <select class="form-select form-select-sm" id="cpTxType" aria-label="Transaction type"><option value="">All types</option></select>
                            <input type="date" class="form-control form-control-sm" id="cpTxFrom" aria-label="From date" title="From date">
                            <input type="date" class="form-control form-control-sm" id="cpTxTo" aria-label="To date" title="To date">
                            <input type="number" class="form-control form-control-sm" id="cpTxMin" min="0" step="any" placeholder="Min amount" aria-label="Minimum amount">
                            <button type="button" class="btn btn-sm rc-actions__view" id="cpTxExport"><i class="fas fa-file-csv me-1"></i>Export CSV</button>
                        </div>
                    </div>
                    <div class="table-responsive">
                        <table class="table table-hover mb-0 fp-table">
                            <thead><tr>
                                <th class="px-3 py-2">Date</th><th class="px-3 py-2">Type</th><th class="px-3 py-2 text-end">Amount</th>
                                <th class="px-3 py-2">Counterparty</th><th class="px-3 py-2">Rules fired</th><th class="px-3 py-2 text-end">Score</th>
                            </tr></thead>
                            <tbody id="cpTxBody"></tbody>
                        </table>
                    </div>
                    <div class="cp-tx-more"><button type="button" class="btn btn-sm rc-actions__view d-none" id="cpTxMore">Show more</button></div>
                </section>
                </div>

                <div class="cp-pane" id="cpPane-investigation" role="tabpanel" aria-labelledby="cpTab-investigation" data-pane="investigation" hidden>
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
                        <header class="kd-panel__head"><div><h2>Requests for information</h2><p class="aml-subtitle">What has been asked for, from whom, and whether it arrived</p></div></header>
                        <div id="cpRequests"><div class="kd-skeleton"></div></div>
                        ${open && Auth.can('alerts.escalate') ? `
                        <form class="cp-request-form" id="cpReqForm">
                            <div class="kx-label mt-3">Record a new request</div>
                            <div class="cp-request-form__row">
                                <label class="visually-hidden" for="cpReqFrom">Asked from</label>
                                <input type="text" class="form-control form-control-sm" id="cpReqFrom" list="cpReqFromList" maxlength="150" placeholder="Asked from">
                                <datalist id="cpReqFromList"><option value="Customer"><option value="Relationship manager"><option value="Counterparty bank"><option value="Internal team"></datalist>
                                <label class="visually-hidden" for="cpReqDue">Due date</label>
                                <input type="date" class="form-control form-control-sm" id="cpReqDue" title="Due date" min="${new Date().toISOString().slice(0, 10)}" value="${new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10)}">
                            </div>
                            <label class="visually-hidden" for="cpReqSubject">What was asked for</label>
                            <input type="text" class="form-control form-control-sm mt-2" id="cpReqSubject" maxlength="2000" placeholder="What was asked for, e.g. source of funds for the 12 Sep transfer">
                            <div class="cp-note__foot">
                                <span class="kx-note">KYRO records the request; it does not send it.</span>
                                <button type="submit" class="btn btn-sm btn-primary" id="cpReqAdd">Record request</button>
                            </div>
                        </form>` : ''}
                    </section>
                    </div>
                    <div class="cp-grid">
                    <section class="card kd-panel">
                        <header class="kd-panel__head"><div><h2>Draft narrative</h2><p class="aml-subtitle">Who, what, when, where and why, from the facts on this case</p></div>
                            ${Auth.can('alerts.escalate') ? '<button type="button" class="btn btn-sm rc-actions__view" id="cpNarrativeDraft">Draft narrative</button>' : ''}</header>
                        <div id="cpNarrative">${this.empty(Auth.can('alerts.escalate')
                            ? 'Select "Draft narrative" to assemble a first draft from the customer, the alert, the flagged transactions, your notes and requests.'
                            : 'Your role cannot draft a narrative.')}</div>
                    </section>
                    <section class="card kd-panel">
                        <header class="kd-panel__head"><div><h2>Documents</h2><p class="aml-subtitle">Upload KYC documents and check what they say against the record</p></div></header>
                        <div id="caseDocuments"></div>
                    </section>
                    </div>
                </div>

                <div class="cp-pane" id="cpPane-file" role="tabpanel" aria-labelledby="cpTab-file" data-pane="file" hidden>
                    <section class="card kd-panel mb-4">
                        <header class="kd-panel__head"><div><h2>Customer profile</h2><p class="aml-subtitle">What was recorded when the customer was taken on${(customer.customer_metadata || {}).sample_data ? ' (sample data)' : ''}</p></div></header>
                        ${this.profilePanel(customer)}
                    </section>
                    <section class="card border-0 rc-table-card mb-4">
                        <div class="rc-toolbar"><div class="rc-toolbar__title"><h2>Accounts</h2><small class="text-muted" id="cpAccountsSub">Accounts held by this customer</small></div></div>
                        <div class="table-responsive">
                            <table class="table table-hover mb-0 fp-table">
                                <thead><tr>
                                    <th class="px-3 py-2">Account</th><th class="px-3 py-2">Purpose</th><th class="px-3 py-2">Opened</th><th class="px-3 py-2">Status</th>
                                    <th class="px-3 py-2 text-end">Balance</th><th class="px-3 py-2 text-end">Last 30 days</th><th class="px-3 py-2">Last activity</th>
                                </tr></thead>
                                <tbody id="cpAccountsBody"><tr><td colspan="7" class="rc-empty">Loading...</td></tr></tbody>
                            </table>
                        </div>
                        <p class="cp-owners-note d-none" id="cpTurnoverNote"></p>
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
                            <header class="kd-panel__head"><div><h2>Screening matches</h2><p class="aml-subtitle">The watchlist entry beside the customer${customer.last_screened_at ? `; last screened ${escapeHtml(formatDate(customer.last_screened_at))}` : ''}</p></div></header>
                            <div id="cpScreening"><div class="kd-skeleton"></div></div>
                        </section>
                        <div class="cp-stack">
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
            </div>
        `);

        $("#cpBack").on("click", () => App.navigateTo('cases'));
        $("#cpAssign").on("click", () => Cases.showAssignModal(c));
        $(".cp-tab, .cp-glance__tile").on("click", (e) => this.showTab($(e.currentTarget).data("tab")));
        $(".cp-tabs").on("keydown", (e) => {
            if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
            const order = this.TABS;
            const next = order[(order.indexOf(this.tab) + (e.key === 'ArrowRight' ? 1 : order.length - 1)) % order.length];
            this.showTab(next);
            $(`#cpTab-${next}`).trigger("focus");
        });
        if (this.tabFor !== alert.id) { this.tab = 'overview'; this.tabFor = alert.id; }
        this.showTab(this.tab, false);
        const flaggedCount = this.transactions.filter(t => this.isFlagged(t)).length;
        $("#cpGlanceFlagged").text(flaggedCount.toLocaleString());
        $("#cpGlanceFlaggedNote").text(`of ${this.transactions.length.toLocaleString()} loaded`);
        this.setCount('activity', flaggedCount);
        $("#cpNoteForm").on("submit", (e) => { e.preventDefault(); this.addNote(alert.id); });
        $("#cpReqForm").on("submit", (e) => { e.preventDefault(); this.addRequest(alert.id); });
        $("#cpNarrativeDraft").on("click", () => this.draftNarrative(alert.id));
        this.setupTransactions();
        $("#cpSummaryRefresh").on("click", () => this.generateSummary(alert.id));
        this.renderSummary(alert);
        this.loadCaseFile(alert, customer);
        this.loadBasis(alert.id, rules.map(r => r.code));
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
