/**
 * pages/case/case.views.js — The frame of the case page: header, key facts, stage tracker, tabs.
 * The sections fill their own panes (sections/*.js).
 */
import { can } from '../../core/auth.js';
import { html, list } from '../../core/dom.js';
import { date, human, initials } from '../../core/format.js';
import { href } from '../../core/router.js';
import { band, status } from '../../components/cells.js';
import { chip, RISK_TONE } from './case.ui.js';

export const TABS = [
    { key: 'overview', label: 'Overview' },
    { key: 'activity', label: 'Activity', title: 'Flagged transactions' },
    { key: 'investigation', label: 'Investigation', title: 'Notes and open requests' },
    { key: 'file', label: 'Customer file', title: 'Screening matches awaiting a decision' },
];

/** Who may record each outcome; the decision button shows when the role holds any of them. */
export const OUTCOME_PERMISSION = {
    FALSE_POSITIVE: 'alerts.close_false_positive',
    TRUE_POSITIVE_NO_SAR: 'alerts.close',
    SAR_FILED: 'sar.approve',
    ESCALATED: 'alerts.escalate',
};
export const canDecide = () => can(...Object.values(OUTCOME_PERMISSION));

export const shortId = (id) => String(id).slice(0, 8);

export function frame({ alert, customer, ownerName }, tab) {
    const name = customer.full_name || 'Unknown customer';
    const open = alert.status !== 'RESOLVED';
    return html`
        <div class="case-top" id="case-top">
            <nav class="case-crumbs" aria-label="Breadcrumb">
                <a href="${href('/cases')}">Review Cases</a><i class="fas fa-chevron-right" aria-hidden="true"></i>
                <a href="${href(`/cases?q=${encodeURIComponent(name)}`)}">${name}</a><i class="fas fa-chevron-right" aria-hidden="true"></i>
                <span aria-current="page">Case ${shortId(alert.id)}</span>
            </nav>
            <header class="case-head">
                <div class="case-head__who">
                    <span class="avatar avatar--lg" aria-hidden="true">${initials(name)}</span>
                    <div>
                        <h1 class="case-head__name">${name}</h1>
                        <div class="case-head__chips">
                            ${status(alert.status)}
                            ${alert.potential_sar ? chip('high', 'Potential SAR') : ''}
                            ${alert.restricted ? chip('muted', 'With the MLRO · details restricted', 'Notes and decisions recorded since the escalation are restricted to the people who decide on SARs') : ''}
                            ${customer.sanctions_flag ? chip('high', 'Sanctions') : ''}
                            ${customer.pep_flag ? chip('medium', 'PEP') : ''}
                            ${customer.adverse_media_flag ? chip('medium', 'Adverse media') : ''}
                        </div>
                    </div>
                </div>
                <div class="case-head__actions">
                    ${open && can('alerts.assign') ? html`<button type="button" class="btn btn-quiet" data-action="assign"><i class="fas fa-user-plus me-2" aria-hidden="true"></i>Assign</button>` : ''}
                    <a class="btn btn-quiet" href="${href(`/cases/${alert.id}/report`)}"><i class="fas fa-file-lines me-2" aria-hidden="true"></i>Report</a>
                    ${open && canDecide() ? html`<button type="button" class="btn btn-primary" data-action="decide"><i class="fas fa-gavel me-2" aria-hidden="true"></i>Record decision</button>` : ''}
                </div>
            </header>
            <dl class="case-strip">
                <div><dt>Risk score</dt><dd><span class="case-score case-score--${band(alert.risk_score)}">${alert.risk_score}</span></dd></div>
                <div><dt>Owner</dt><dd>${ownerName || html`<span class="muted">Unassigned</span>`}</dd></div>
                <div><dt>Case age</dt><dd id="case-clock">—</dd></div>
                ${alert.potential_sar ? html`<div><dt>SAR deadlines</dt><dd id="case-sar">…</dd></div>` : ''}
                <div><dt>Alert type</dt><dd>${human(alert.alert_type) || '—'}</dd></div>
                <div><dt>Recommended action</dt><dd>${human(alert.recommended_action) || '—'}</dd></div>
                <div><dt>Customer rating</dt><dd>${customer.risk_level ? chip(RISK_TONE[customer.risk_level] || 'muted', human(customer.risk_level)) : '—'}</dd></div>
                <div><dt>Opened</dt><dd>${date(alert.created_at)}</dd></div>
            </dl>
            <ol class="case-stages" id="case-stages" aria-label="Case stage"></ol>
            <div class="tabs case-tabs" role="tablist" aria-label="Case sections">
                ${list(TABS, (t) => html`<button type="button" class="tab ${t.key === tab ? 'is-active' : ''}" role="tab" id="case-tab-${t.key}"
                    data-tab="${t.key}" aria-controls="case-pane-${t.key}" aria-selected="${t.key === tab}" tabindex="${t.key === tab ? 0 : -1}" title="${t.title || ''}">
                    ${t.label}<span class="tab__count" id="case-count-${t.key}" hidden></span></button>`)}
            </div>
        </div>
        ${list(TABS, (t) => html`<div class="case-pane" id="case-pane-${t.key}" role="tabpanel" aria-labelledby="case-tab-${t.key}" ${t.key === tab ? '' : 'hidden'}></div>`)}`;
}

const STAGE_STATE = (s) => (s.done ? 'done' : s.current ? 'current' : s.skipped ? 'skipped' : 'todo');

export function stages(items) {
    return list(items, (s, i) => {
        const state = STAGE_STATE(s);
        const note = s.done ? [s.detail, s.at ? date(s.at) : ''].filter(Boolean).join(' · ') : s.current ? 'Now' : s.skipped ? 'Skipped' : '';
        return html`<li class="case-stage case-stage--${state}" ${s.current ? html`aria-current="step"` : ''}>
            <span class="case-stage__dot" aria-hidden="true">${s.done ? html`<i class="fas fa-check"></i>` : i + 1}</span>
            <span class="case-stage__text"><strong>${s.label}</strong><small>${note}</small></span>
            <span class="visually-hidden">${{ done: '(done)', current: '(current stage)', skipped: '(skipped)', todo: '(not reached)' }[state]}</span></li>`;
    });
}

export function clock(c) {
    const days = (n) => `${n} day${n === 1 ? '' : 's'}`;
    if (c.closed_at) return html`Closed after ${days(c.age_days)} <small class="muted">target ${days(c.target_days)}</small>`;
    return html`${c.overdue ? chip('high', 'Overdue') : ''} ${days(c.age_days)} <small class="muted">of ${days(c.target_days)}</small>`;
}

const DEADLINE = { ON_TRACK: ['low', 'On track'], DUE_SOON: ['medium', 'Due soon'], OVERDUE: ['high', 'Overdue'], MET: ['low', 'Met'],
    MISSED: ['high', 'Missed'], OPEN: ['muted', 'Open'], FILED: ['low', 'Filed'], FILED_LATE: ['high', 'Filed late'], NO_FIXED_DEADLINE: ['muted', 'No fixed deadline'] };

export function sarDeadlines({ decision, filing }) {
    const one = (label, d) => {
        const [tone, text] = DEADLINE[d.status] || ['muted', human(d.status)];
        return html`<span class="case-deadline">${label} ${chip(tone, text)}${d.due_at ? html` <small class="muted">by ${date(d.due_at)}</small>` : ''}</span>`;
    };
    return html`${decision ? one('Decision', decision) : ''}${filing ? one('Filing', filing) : ''}`;
}

export const missing = (text) => html`
    <div class="page-message"><h1>${text}</h1><p>It may have been closed, or it is not visible to your role.</p>
        <a class="btn btn-primary" href="${href('/cases')}">Back to Review Cases</a></div>`;

export const loading = () => html`
    <div class="case-top"><span class="skeleton case-skel-crumb"></span><span class="skeleton case-skel-title"></span><span class="skeleton case-skel-strip"></span></div>
    <div class="case-grid"><span class="skeleton case-skel-card"></span><span class="skeleton case-skel-card"></span></div>`;
