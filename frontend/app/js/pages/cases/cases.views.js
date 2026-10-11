/**
 * pages/cases/cases.views.js — The work queue's markup. No data fetching, no event handling.
 */
import { can } from '../../core/auth.js';
import { html, list } from '../../core/dom.js';
import { age, dateTime, human, number } from '../../core/format.js';
import { href } from '../../core/router.js';
import { owner, score, stage, status, tags } from '../../components/cells.js';
import { head } from '../../components/table.js';
import { tabs } from '../../components/tabs.js';
import { MARKED_RULES, RULES, ruleName } from '../../config/rules.js';

export const VIEWS = [
    { key: 'all', label: 'All unresolved', count: (s) => s.unresolved, filters: {} },
    { key: 'high', label: 'High risk', count: (s) => s.high_risk, alert: true, filters: { risk: 'high' }, title: 'Risk score 80 or more' },
    { key: 'unassigned', label: 'Unassigned', count: (s) => s.unassigned, filters: { assignment: 'unassigned' } },
    { key: 'mine', label: 'Mine', count: (s) => s.assigned_to_me, filters: { assignment: 'mine' } },
    { key: 'mlro', label: 'With the MLRO', count: (s) => s.escalated, filters: { status: 'ESCALATED' }, title: 'Escalated, awaiting a senior decision' },
    { key: 'overdue', label: 'Overdue', count: (s) => s.overdue, alert: true, filters: { attention: 'overdue', sort: 'oldest' } },
    { key: 'waiting', label: 'Waiting on info', count: (s) => s.awaiting_information, filters: { attention: 'awaiting_information' } },
];

const select = (name, label, options, value) => html`
    <select class="form-select" data-filter="${name}" aria-label="${label}">
        ${list(options, ([v, text]) => html`<option value="${v}" ${v === value ? 'selected' : ''}>${text}</option>`)}
    </select>`;

export function page(state) {
    return html`
        <div class="page-head">
            <div>
                <span class="page-head__kicker">Case management</span>
                <h1 class="page-head__title">Review Cases</h1>
                <p class="page-head__sub">The highest-risk, longest-waiting work comes first.</p>
            </div>
            <div class="page-head__actions">
                <button type="button" class="btn btn-quiet" data-action="refresh"><i class="fas fa-rotate-right me-2" aria-hidden="true"></i>Refresh</button>
            </div>
        </div>
        <div class="cases-views" id="cases-views">${tabs(VIEWS.map((v) => ({ ...v, count: undefined })), state.view)}</div>
        <section class="card-x">
            <div class="card-x__head">
                <div>
                    <h2 class="card-x__title">Work queue</h2>
                    <p class="card-x__sub" id="cases-count">&nbsp;</p>
                </div>
                <div class="segmented" role="group" aria-label="List by">
                    <button type="button" data-group="customer" class="${state.group === 'customer' ? 'is-active' : ''}" aria-pressed="${state.group === 'customer'}">By customer</button>
                    <button type="button" data-group="alert" class="${state.group === 'alert' ? 'is-active' : ''}" aria-pressed="${state.group === 'alert'}">By alert</button>
                </div>
            </div>
            ${filters(state)}
            <div id="cases-bulk"></div>
            <div class="dt-wrap"><table class="dt"><thead id="cases-head"></thead><tbody id="cases-body"></tbody></table></div>
            <div id="cases-pager"></div>
        </section>`;
}

export function filters(state) {
    const f = state.filters;
    return html`
        <div class="cases-filters">
            <div class="search"><i class="fas fa-magnifying-glass" aria-hidden="true"></i>
                <input type="search" class="form-control" data-filter="q" value="${f.q}" placeholder="Search customer name" aria-label="Search customer name"></div>
            ${state.group === 'alert' ? select('status', 'Status', [['UNRESOLVED', 'Unresolved'], ['OPEN', 'Open'], ['ASSIGNED', 'Assigned'],
                ['IN_REVIEW', 'In review'], ['ESCALATED', 'With the MLRO'], ['RESOLVED', 'Closed'],
                ...(can('alerts.qa') ? [['AWAITING_QA', 'Awaiting quality check'], ['QA_FAILED', 'Failed quality check']] : []), ['ALL', 'All statuses']], f.status) : ''}
            ${select('risk', 'Risk', [['', 'All risk levels'], ['high', 'High (80+)'], ['medium', 'Medium (60–79)'], ['low', 'Low (under 60)']], f.risk)}
            ${select('rule', 'Rule', [['', 'All rules'], ...Object.entries(RULES).filter(([c]) => c.startsWith('R')).map(([c, n]) => [c, `${c} ${n}`])], f.rule)}
            ${select('assignment', 'Owner', [['', 'Any owner'], ['unassigned', 'Unassigned'], ['mine', 'Mine']], f.assignment)}
            ${select('attention', 'Needs attention', [['', 'Any age'], ['overdue', 'Overdue'], ['awaiting_information', 'Waiting on information']], f.attention)}
            ${select('sort', 'Sort', [['priority', 'Highest risk first'], ['oldest', 'Oldest first'], ['newest', 'Newest first']], f.sort)}
            ${f.customerId ? html`<button type="button" class="tag tag--filter" data-action="clear-customer">${f.customerName || 'One customer'} <i class="fas fa-xmark" aria-hidden="true"></i></button>` : ''}
        </div>`;
}

export const viewTabs = (s, active) => tabs(VIEWS.map((v) => ({ key: v.key, label: v.label, alert: v.alert, title: v.title, count: v.count(s) })), active);

// ── By customer ──────────────────────────────────────────────────────────

export const CUSTOMER_COLUMNS = [
    { label: 'Customer' }, { label: 'Risk', title: 'Highest score among open alerts' }, { label: 'Alerts', className: 'right' },
    { label: 'Why it was flagged' }, { label: 'Stage', title: 'Where the highest-risk case stands' },
    { label: 'Waiting', className: 'right' }, { label: 'Owner' }, { hidden: 'Actions' },
];

export const customerHead = () => head(CUSTOMER_COLUMNS);

export function customerRow(g) {
    const flags = html`
        ${g.customer_sanctions ? html`<span class="flag flag--danger">Sanctions</span>` : ''}
        ${g.customer_pep ? html`<span class="flag">PEP</span>` : ''}
        ${String(g.customer_risk_level || '').toUpperCase() === 'HIGH' ? html`<span class="flag flag--quiet" title="Customer risk rating">High-risk customer</span>` : ''}`;
    const reasons = g.rules.map((r) => ({ code: r.rule, label: ruleName(r.rule), count: r.alerts }));
    return html`
        <tr class="is-link" data-open="${g.top_alert_id}" tabindex="0" aria-label="${g.customer_name}: ${g.open_alerts} open alerts. Press Enter to review.">
            <td>${personCell(g.customer_name, flags)}</td>
            <td>${score(g.max_risk_score, 'Highest score among open alerts')}</td>
            <td class="right"><span class="cell-strong">${number(g.open_alerts)}</span><span class="cell-sub">${g.high_risk_alerts ? `${number(g.high_risk_alerts)} high` : 'none high'}</span></td>
            <td>${tags(reasons, { marked: (t) => MARKED_RULES.has(t.code), title: reasons.map((r) => `${r.label} (${r.count})`).join(', ') })}</td>
            <td>${stage(g.top_stages, g.top_stage)}</td>
            <td class="right" title="Oldest unresolved alert created ${dateTime(g.oldest_created_at)}">
                <span class="cell-strong">${age(g.oldest_created_at)}</span>
                <span class="cell-sub ${g.overdue_alerts ? 'cell-sub--alert' : ''}">${g.overdue_alerts ? `${g.overdue_alerts} overdue` : 'on time'}</span></td>
            <td>${owner(g.owners)}</td>
            <td class="right nowrap">
                <button type="button" class="link-btn" data-action="customer-alerts" data-customer="${g.customer_id}" data-name="${g.customer_name}">All ${number(g.open_alerts)}</button>
                ${can('alerts.assign') ? html`<button type="button" class="icon-btn" data-action="assign-customer" data-customer="${g.customer_id}" data-name="${g.customer_name}" data-count="${g.open_alerts}" title="Assign all ${g.open_alerts} open alerts" aria-label="Assign all open alerts for ${g.customer_name}"><i class="fas fa-user-plus"></i></button>` : ''}
                <a class="icon-btn" href="${href(`/cases/${g.top_alert_id}`)}" aria-label="Review ${g.customer_name}"><i class="fas fa-chevron-right"></i></a>
            </td>
        </tr>`;
}

const personCell = (name, meta) => html`<div class="person"><span class="avatar" aria-hidden="true">${String(name).split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase()}</span>
    <span><span class="person__name">${name}</span><span class="person__meta">${meta}</span></span></div>`;

// ── By alert ─────────────────────────────────────────────────────────────

export const alertColumns = () => [
    ...(can('alerts.assign') ? [{ label: html`<input type="checkbox" class="form-check-input" data-action="select-all" aria-label="Select every alert on this page">` }] : []),
    { label: 'Customer' }, { label: 'Risk' }, { label: 'Why it was flagged' }, { label: 'Status' }, { label: 'Stage' },
    { label: 'Waiting', className: 'right' }, { label: 'Owner' }, { hidden: 'Actions' },
];

export function alertRow(a, selected) {
    const open = a.status !== 'RESOLVED';
    const rules = ((a.triggered_rules && (a.triggered_rules.rules || a.triggered_rules)) || []);
    const reasons = (Array.isArray(rules) ? rules : []).map((code) => ({ code, label: ruleName(code) }));
    const others = (a.customer_open_alerts || 0) - (open ? 1 : 0);
    const meta = html`
        ${a.customer_sanctions ? html`<span class="flag flag--danger">Sanctions</span>` : ''}${a.customer_pep ? html`<span class="flag">PEP</span>` : ''}
        ${others > 0 ? html`<span>+${number(others)} other open</span>` : ''}`;
    return html`
        <tr class="is-link" data-open="${a.id}" tabindex="0">
            ${can('alerts.assign') ? html`<td>${open ? html`<input type="checkbox" class="form-check-input" data-select="${a.id}" ${selected ? 'checked' : ''} aria-label="Select the alert for ${a.customer_name}">` : ''}</td>` : ''}
            <td>${personCell(a.customer_name, meta)}</td>
            <td>${score(a.risk_score)}</td>
            <td>${tags(reasons, { marked: (t) => MARKED_RULES.has(t.code), title: reasons.map((r) => r.label).join(', ') })}</td>
            <td>${status(a.status, a.status_label)}</td>
            <td>${stage(a.stages, a.stage)}</td>
            <td class="right" title="Created ${dateTime(a.created_at)}">
                <span class="cell-strong">${open ? age(a.created_at) : '—'}</span>
                <span class="cell-sub ${a.overdue ? 'cell-sub--alert' : ''}">${a.overdue ? 'overdue' : a.open_requests ? 'waiting on info' : open ? 'on time' : ''}</span></td>
            <td>${owner(a.assigned_to_name ? [a.assigned_to_name] : [])}</td>
            <td class="right nowrap">
                ${open && can('alerts.assign') ? html`<button type="button" class="icon-btn" data-action="assign-one" data-alert="${a.id}" data-name="${a.customer_name}" title="Assign" aria-label="Assign the alert for ${a.customer_name}"><i class="fas fa-user-plus"></i></button>` : ''}
                <a class="icon-btn" href="${href(`/cases/${a.id}`)}" aria-label="Open the case for ${a.customer_name}"><i class="fas fa-chevron-right"></i></a>
            </td>
        </tr>`;
}

export const bulkBar = (count) => (count ? html`
    <div class="bulkbar" role="status"><strong>${number(count)}</strong> selected
        <button type="button" class="btn btn-primary" data-action="assign-selected"><i class="fas fa-user-plus me-1" aria-hidden="true"></i>Assign</button>
        <button type="button" class="btn btn-quiet" data-action="clear-selection">Clear</button></div>` : '');

export function assignForm(people, subject, meId) {
    const me = people.find((p) => p.id === meId);
    return html`
        <p class="muted">${subject}</p>
        <label class="field-label" for="assignee">Assign to</label>
        <select class="form-select" id="assignee" name="assignee" required>
            <option value="">Choose a person…</option>
            ${list(people, (p) => html`<option value="${p.id}">${p.name}${p === me ? ' (you)' : ''} · ${human(p.role)}</option>`)}
        </select>`;
}
