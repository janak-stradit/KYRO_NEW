/**
 * Overview: the case at a glance, why the alert fired, the AI summary, who the customer is,
 * how the case was decided, and the customer's other cases.
 */
import { can, session } from '../../../core/auth.js';
import { html, list, render } from '../../../core/dom.js';
import { date, dateTime, human, number } from '../../../core/format.js';
import { dialog, toast } from '../../../core/feedback.js';
import { href } from '../../../core/router.js';
import { score } from '../../../components/cells.js';
import { ruleName } from '../../../config/rules.js';
import * as API from '../case.api.js';
import { chip, empty, facts, failed, lines, money, panel, plural, RISK_TONE } from '../case.ui.js';

let ctx;

const GLANCE = [
    ['flagged', 'fa-flag', 'Flagged transactions', 'activity'],
    ['others', 'fa-bell', 'Other open alerts', 'overview'],
    ['notes', 'fa-pen', 'Notes', 'investigation'],
    ['requests', 'fa-envelope', 'Open requests', 'investigation'],
    ['matches', 'fa-user-shield', 'Screening matches', 'file'],
];

const SEVERITY = { CRITICAL: 'high', HIGH: 'high', MEDIUM: 'medium', LOW: 'low' };
const OUTCOME_TONE = { FALSE_POSITIVE: 'muted', TRUE_POSITIVE_NO_SAR: 'medium', SAR_FILED: 'high' };

export const ruleCodes = (alert) => {
    const r = alert.triggered_rules && (alert.triggered_rules.rules || alert.triggered_rules);
    return Array.isArray(r) ? r : [];
};

function view(c) {
    const { alert } = c;
    return html`
        <div class="case-glance">${list(GLANCE, ([key, icon, label, tab]) => html`
            <button type="button" class="case-glance__tile" data-tab="${tab}" id="glance-${key}">
                <i class="fas ${icon}" aria-hidden="true"></i><span>${label}</span><strong>—</strong><small>&nbsp;</small></button>`)}
        </div>
        <div class="case-grid case-grid--wide">
            <div class="case-col">
                ${why(alert)}
                ${panel({ id: 'case-summary', title: html`<i class="fas fa-wand-magic-sparkles case-ai" aria-hidden="true"></i> Case summary`,
                    sub: 'Written from the facts on this case', body: lines(4),
                    actions: can('alerts.escalate') && !alert.restricted ? html`<button type="button" class="btn btn-quiet btn-sm" data-action="summary-write">Write again</button>` : '' })}
                ${decision(alert)}
            </div>
            <div class="case-col">
                ${customerPanel(c)}
                ${panel({ title: 'Other cases for this customer', sub: 'What else is open, and how earlier alerts ended',
                    body: html`${othersOpen(c)}<div id="case-history">${lines(3)}</div>` })}
            </div>
        </div>`;
}

/** Why this alert: the rules that fired, with the values and thresholds the engine used. */
function why(alert) {
    const p = alert.parameters || {};
    const described = Object.fromEntries((p.rules || []).map((r) => [r.rule, r]));
    const codes = ruleCodes(alert);
    const t = p.thresholds || {};
    const fx = p.fx_missing ? chip('medium', 'No exchange rate: compared in the original currency')
        : p.fx_stale ? chip('medium', 'Exchange rate more than 5 days old') : '';
    const merged = (p.consolidated || []).length;
    const body = html`
        ${codes.length ? html`<ul class="case-rules">${list(codes, (code) => {
            const r = described[code] || {};
            return html`<li><span class="case-rules__code">${code}</span>
                <span class="case-rules__text"><strong>${ruleName(code)}</strong>${r.description ? html`<small>${r.description}</small>` : ''}</span>
                ${r.severity ? chip(SEVERITY[r.severity] || 'muted', human(r.severity)) : ''}</li>`;
        })}</ul>` : empty('No rule triggers were recorded for this alert.')}
        ${p.amount !== undefined ? facts([
            ['Amount', html`${money(p.amount, p.currency)}${p.amount_base != null && p.base_currency !== p.currency ? html` <small class="muted">${money(p.amount_base, p.base_currency)} in the base currency</small>` : ''} ${fx}`],
            ['Amount threshold', t.AMOUNT_THRESHOLD != null ? money(t.AMOUNT_THRESHOLD, p.base_currency, 0) : ''],
            ['Alert raised at', t.ALERT_THRESHOLD != null ? `score ${t.ALERT_THRESHOLD}` : ''],
            ['Enhanced due diligence at', t.EDD_THRESHOLD != null ? `score ${t.EDD_THRESHOLD}` : ''],
            ['Merged today', merged ? `${merged + 1} transactions in this one alert` : ''],
        ]) : ''}
        ${p.options && p.options.noise_reduction ? html`<p class="case-note">Weak indicators count only alongside a substantive rule.</p>` : ''}
        <div id="case-basis"></div>`;
    return panel({ title: 'Why this alert', body,
        sub: html`Rule version <code>${alert.rule_version || '—'}</code>${(alert.evidence_transaction_ids || []).length ? html` · ${plural(alert.evidence_transaction_ids.length, 'evidence transaction')}` : ''}` });
}

function decision(alert) {
    if (alert.status !== 'RESOLVED' && !alert.resolution_outcome) return '';
    const me = (session.user() || {}).id;
    let form = '';
    if (alert.status === 'RESOLVED' && can('alerts.qa')) {
        form = alert.resolved_by === me
            ? html`<p class="case-note">You resolved this case, so someone else must quality-check it.</p>`
            : html`<form class="case-qa" data-form="qa">
                <label class="field-label" for="case-qa-notes">${alert.qa_result ? 'Record a new check' : 'Did this case follow policy?'}</label>
                <textarea class="form-control" id="case-qa-notes" name="notes" rows="2" maxlength="2000" placeholder="Notes (required when the case fails)"></textarea>
                <div class="case-actions"><button type="submit" class="btn btn-quiet btn-sm" value="FAIL">Fail</button>
                    <button type="submit" class="btn btn-primary btn-sm" value="PASS">Pass</button></div></form>`;
    }
    const body = html`
        ${alert.resolution_outcome ? html`
            <p class="case-outcome">${chip(OUTCOME_TONE[alert.resolution_outcome] || 'info', human(alert.resolution_outcome))}
                ${(alert.resolution_reasons || []).map(human).join(', ')}${alert.sar_reference ? html` · Ref <strong>${alert.sar_reference}</strong>` : ''}</p>
            ${alert.resolution_notes ? html`<p class="case-quote">${alert.resolution_notes}</p>` : ''}
            ${alert.resolved_at ? html`<p class="case-note">Resolved ${dateTime(alert.resolved_at)}</p>` : ''}` : ''}
        ${alert.status === 'RESOLVED' ? html`
            <h3 class="case-label">Quality check</h3>
            ${alert.qa_result ? html`<p>${chip(alert.qa_result === 'PASS' ? 'low' : 'high', alert.qa_result === 'PASS' ? 'Passed' : 'Failed')}
                <small class="muted">${dateTime(alert.qa_at)}</small></p>${alert.qa_notes ? html`<p class="case-quote">${alert.qa_notes}</p>` : ''}`
            : html`<p class="case-note">Not checked yet.</p>`}
            ${form}` : ''}`;
    return panel({ title: 'Decision', sub: alert.status === 'RESOLVED' ? 'How the case was closed' : 'Recorded so far', body });
}

function customerPanel({ customer, profile }) {
    const m = customer.customer_metadata || {};
    const body = html`
        ${facts([
            ['Risk rating', html`${chip(RISK_TONE[customer.risk_level] || 'muted', human(customer.risk_level) || '—')}${customer.risk_score != null ? html` <small class="muted">score ${customer.risk_score}</small>` : ''}`],
            ['Type', human(customer.customer_type)],
            ['Country', [customer.country, customer.residency_country && customer.residency_country !== customer.country ? `lives in ${customer.residency_country}` : ''].filter(Boolean).join(' · ')],
            ['KYC status', human(customer.kyc_status)],
            ['Last KYC review', customer.kyc_last_review ? date(customer.kyc_last_review) : ''],
            ['Last screened', customer.last_screened_at ? date(customer.last_screened_at) : ''],
            [customer.customer_type === 'INDIVIDUAL' ? 'Occupation' : 'Business', m.occupation || m.industry],
            ['Source of funds', m.source_of_funds],
            ['Expected monthly turnover', m.expected_monthly_turnover ? money(m.expected_monthly_turnover.amount, m.expected_monthly_turnover.currency, 0) : ''],
            ['Customer since', m.onboarded_on ? date(m.onboarded_on) : ''],
        ])}
        <h3 class="case-label">Why this rating</h3>
        ${profile === null ? failed('The rating factors') : profile.length ? html`<ul class="case-weights">${list(profile, (f) => html`
            <li><span>${f.risk_factor}</span><strong>+${number(f.risk_weight)}</strong></li>`)}</ul>` : empty('No risk factors apply to this customer.')}`;
    return panel({ title: 'Customer', sub: 'Who they are and why they have their rating', body,
        actions: html`<button type="button" class="link-btn" data-tab="file">Customer file <i class="fas fa-arrow-right" aria-hidden="true"></i></button>` });
}

function othersOpen({ alert, others, customer }) {
    if (!others) return html`<h3 class="case-label">Open now</h3>${failed('Other open alerts')}`;
    const items = others.items.filter((a) => a.id !== alert.id);
    const total = Math.max(0, others.total - (alert.status !== 'RESOLVED' ? 1 : 0));
    return html`
        <h3 class="case-label">Open now</h3>
        ${items.length ? html`<ul class="case-links">${list(items.slice(0, 5), (a) => html`
            <li><a href="${href(`/cases/${a.id}`)}">${score(a.risk_score)}
                <span class="case-links__text">${ruleCodes(a).map(ruleName).join(', ') || 'No rule recorded'}<small>${a.status_label || human(a.status)} · opened ${date(a.created_at)}</small></span>
                <i class="fas fa-chevron-right" aria-hidden="true"></i></a></li>`)}</ul>
            ${total > 5 ? html`<a class="link-btn" href="${href(`/cases?q=${encodeURIComponent(customer.full_name || '')}`)}">See all ${number(total)} in the work queue</a>` : ''}`
        : empty('No other open alerts on this customer.')}`;
}

function history(h) {
    if (!h.total) return empty('This is the first alert on this customer.');
    const sameRule = (r) => {
        if (!r.resolved) return 'none resolved yet';
        const other = r.resolved - r.false_positive - r.sar_filed;
        return [`${r.resolved} resolved`, r.false_positive ? `${r.false_positive} false positive` : '', r.sar_filed ? `${r.sar_filed} SAR filed` : '',
            other ? `${other} no suspicion` : ''].filter(Boolean).join(' · ');
    };
    return html`
        <div class="case-stats">
            <div><span>Other alerts</span><strong>${number(h.total)}</strong></div>
            <div><span>Still open</span><strong>${number(h.open)}</strong></div>
            <div><span>False positive</span><strong>${number(h.outcomes.FALSE_POSITIVE || 0)}</strong></div>
            <div><span>SAR filed</span><strong>${number(h.outcomes.SAR_FILED || 0)}</strong></div>
        </div>
        ${h.same_rules.length ? html`<h3 class="case-label">The rules on this case, earlier</h3>
            <ul class="case-weights">${list(h.same_rules, (r) => html`<li><span><strong>${r.rule}</strong> ${ruleName(r.rule)}</span><span class="muted">${sameRule(r)}</span></li>`)}</ul>` : ''}
        <h3 class="case-label">Most recently resolved</h3>
        ${h.recent.length ? html`<ul class="case-links">${list(h.recent, (a) => html`
            <li><a href="${href(`/cases/${a.id}`)}">${score(a.risk_score)}
                <span class="case-links__text">${a.rules.map(ruleName).join(', ') || 'No rule recorded'}<small>Resolved ${date(a.resolved_at || a.created_at)}${a.sar_reference ? ` · Ref ${a.sar_reference}` : ''}</small></span>
                ${chip(OUTCOME_TONE[a.outcome] || 'muted', a.outcome ? human(a.outcome) : 'No outcome')}</a></li>`)}</ul>`
        : empty('None of the earlier alerts has been resolved yet.')}`;
}

// ── AI summary ───────────────────────────────────────────────────────────

function summary(alert) {
    const mayReview = can('alerts.escalate') && !alert.restricted;
    const checked = Boolean(alert.summary_attested_at);
    const source = alert.summary_provider === 'mock'
        ? 'Arranged from the facts on file by the built-in template; no AI model is connected'
        : 'Written by the AI model from the facts on file; names, IDs and account numbers were masked before sending';
    return html`
        <p class="case-summary">${alert.summary}</p>
        <p class="case-note">${source} · ${dateTime(alert.summary_at)}</p>
        <p class="case-check">${checked ? html`${chip('low', 'Checked')} against the records on ${dateTime(alert.summary_attested_at)}`
            : html`${chip('medium', 'Not checked')} Compare it with the transactions, screening and documents before relying on it.`}</p>
        ${mayReview && !checked ? html`
            <div class="case-confirm">
                <label class="form-check"><input class="form-check-input" type="checkbox" data-confirm="summary">
                    <span class="form-check-label">I have checked this summary against the source records</span></label>
                <div class="case-actions">
                    <button type="button" class="btn btn-quiet btn-sm" data-action="summary-review" data-decision="REJECTED">Reject</button>
                    <button type="button" class="btn btn-quiet btn-sm" data-action="summary-correct">Correct</button>
                    <button type="button" class="btn btn-primary btn-sm" data-action="summary-review" data-decision="ACCEPTED">Keep as written</button>
                </div>
            </div>` : ''}`;
}

function showSummary() {
    const { alert } = ctx;
    const target = '#case-summary .case-panel__body';
    if (alert.summary) return render(target, summary(alert));
    if (alert.restricted) return render(target, empty('This case is with the MLRO. Any summary written since is restricted.'));
    if (can('alerts.escalate')) return writeSummary();  // first visit: write it once and keep it
    return render(target, empty('No summary has been written for this case yet.'));
}

async function writeSummary() {
    const mine = ctx;
    const target = '#case-summary .case-panel__body';
    $('[data-action=summary-write]').prop('disabled', true);
    render(target, html`${lines(4)}<p class="case-note">Writing the summary from the facts on this case. This can take up to a minute.</p>`);
    try {
        const result = await API.writeSummary(mine.alert.id);
        if (!mine.current()) return;
        Object.assign(mine.alert, result);
        showSummary();
    } catch (error) {
        if (mine.current()) render(target, empty(error.status === 409 ? 'AI features are switched off, so no summary can be written.' : `The summary could not be written: ${error.message}`));
    }
    $('[data-action=summary-write]').prop('disabled', false);
}

async function reviewSummary(decision, text) {
    if (decision !== 'REJECTED' && !$('[data-confirm=summary]').is(':checked')) {
        toast('error', 'Tick the box to confirm you checked the summary against the records.');
        return;
    }
    try {
        const result = await API.reviewSummary(ctx.alert.id, decision, text);
        toast('success', decision === 'REJECTED' ? 'Summary removed from the case.' : 'Summary recorded as checked.');
        if (decision === 'REJECTED') {
            ctx.alert.summary = null;
            render('#case-summary .case-panel__body', empty('The summary was rejected and removed. Select "Write again" for a new one.'));
        } else {
            Object.assign(ctx.alert, result);
            showSummary();
        }
        ctx.refreshTimeline();
    } catch (error) {
        toast('error', error.message);
    }
}

// ── Loading ──────────────────────────────────────────────────────────────

async function loadHistory() {
    const mine = ctx;
    try {
        const h = await API.caseHistory(mine.alert.customer_id, mine.alert.id);
        if (mine.current()) render('#case-history', history(h));
    } catch (error) {
        if (mine.current()) render('#case-history', failed('Earlier cases'));
    }
}

async function loadBasis() {
    const mine = ctx;
    const codes = ruleCodes(mine.alert);
    if (!codes.length) return;
    let basis;
    try { basis = await API.basis(codes); } catch (error) { return; }
    if (!mine.current()) return;
    const mapped = codes.filter((code) => (basis[code] || []).length);
    render('#case-basis', html`
        <h3 class="case-label">Regulatory basis</h3>
        ${mapped.length ? html`<ul class="case-basis">${list(mapped, (code) => html`<li><span class="case-rules__code">${code}</span><span>
            ${list(basis[code].slice(0, 3), (b) => html`<span class="case-basis__line"><strong>${b.citation}</strong> ${b.who} must ${b.action}${b.deadline ? ` (${b.deadline})` : ''}</span>`)}
            ${basis[code].length > 3 ? html`<small class="muted">and ${basis[code].length - 3} more</small>` : ''}</span></li>`)}</ul>` : ''}
        ${mapped.length < codes.length ? html`<p class="case-note">${mapped.length ? 'The other rules have' : 'These rules have'} no confirmed obligation mapped to them yet. Mappings are confirmed on the Regulations page.</p>` : ''}`);
}

export default {
    render: view,
    load(c) {
        ctx = c;
        const others = c.others ? Math.max(0, c.others.total - (c.alert.status !== 'RESOLVED' ? 1 : 0)) : null;
        c.glance('others', others === null ? '—' : number(others), 'on this customer');
        showSummary();
        loadHistory();
        loadBasis();
    },
    handlers: {
        'click [data-action=summary-write]': () => writeSummary(),
        'click [data-action=summary-review]': function () { reviewSummary(this.dataset.decision); },
        'click [data-action=summary-correct]': () => {
            if (!$('[data-confirm=summary]').is(':checked')) {
                toast('error', 'Tick the box to confirm you checked the summary against the records.');
                return;
            }
            dialog({
                title: 'Correct the summary', submitLabel: 'Save corrected summary', size: 'modal-lg',
                body: html`<label class="field-label" for="case-summary-text">Summary</label>
                    <textarea class="form-control" id="case-summary-text" name="text" rows="10" maxlength="8000">${ctx.alert.summary}</textarea>`,
                onSubmit: async (form, close) => {
                    const text = form.text.value.trim();
                    if (!text) throw new Error('The summary cannot be empty.');
                    close(true);
                    await reviewSummary('EDITED', text);
                },
            });
        },
        'submit [data-form=qa]': async function (event) {
            event.preventDefault();
            const result = event.originalEvent && event.originalEvent.submitter ? event.originalEvent.submitter.value : 'PASS';
            const notes = this.notes.value.trim();
            if (result === 'FAIL' && !notes) { toast('error', 'Say what was wrong when a case fails the quality check.'); this.notes.focus(); return; }
            $(this).find('button').prop('disabled', true);
            try {
                await API.recordQa(ctx.alert.id, result, notes);
                toast('success', 'Quality check recorded.');
                ctx.reload();
            } catch (error) {
                toast('error', error.message);
                $(this).find('button').prop('disabled', false);
            }
        },
    },
};
