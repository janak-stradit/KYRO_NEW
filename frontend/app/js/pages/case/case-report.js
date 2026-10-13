/**
 * pages/case/case-report — A case report to print or save as PDF (the browser's print dialog),
 * or to download as JSON. Built from live data when it is opened; each section that cannot be
 * loaded says so instead of being left out silently.
 */
import { session } from '../../core/auth.js';
import { html, list, on, render } from '../../core/dom.js';
import { date, dateTime, human, number } from '../../core/format.js';
import { href } from '../../core/router.js';
import { ruleName } from '../../config/rules.js';
import * as API from './case.api.js';
import { money } from './case.ui.js';
import { ruleCodes } from './sections/overview.js';
import { shortId } from './case.views.js';

let off = () => {};
let token = 0;

const settle = (promise) => promise.catch(() => null);
const section = (title, body) => html`<section class="report__section"><h2>${title}</h2>${body}</section>`;
const unavailable = html`<p class="report__muted">Could not be loaded when this report was produced.</p>`;
const rows = (items) => html`<table class="report__kv"><tbody>${list(items.filter((r) => r[1] !== undefined && r[1] !== null && r[1] !== ''),
    ([k, v]) => html`<tr><th>${k}</th><td>${v}</td></tr>`)}</tbody></table>`;

function report(d) {
    const { alert, customer } = d;
    const c = customer || {};
    const p = alert.parameters || {};
    const evidence = new Set((alert.evidence_transaction_ids || []).map(String));
    const tx = d.transactions ? d.transactions.items.filter((t) => evidence.has(String(t.id)) || ((t.risk_flags || {}).triggered_rules || []).length) : null;
    const user = session.user() || {};
    return html`
        <div class="report__bar no-print">
            <a class="btn btn-quiet" href="${href(`/cases/${alert.id}`)}"><i class="fas fa-arrow-left me-2" aria-hidden="true"></i>Back to the case</a>
            <span class="report__bar-gap"></span>
            <button type="button" class="btn btn-quiet" data-action="json"><i class="fas fa-file-code me-2" aria-hidden="true"></i>Download JSON</button>
            <button type="button" class="btn btn-primary" data-action="print"><i class="fas fa-print me-2" aria-hidden="true"></i>Print or save as PDF</button>
        </div>
        <article class="report">
            <header class="report__head">
                <div><span class="report__kicker">KYRO AML · Case report · Confidential</span>
                    <h1>${c.full_name || 'Unknown customer'}</h1>
                    <p class="report__muted">Case ${alert.id}</p></div>
                <dl class="report__meta"><div><dt>Produced</dt><dd>${dateTime(new Date().toISOString())}</dd></div><div><dt>By</dt><dd>${user.full_name || user.email || '—'}</dd></div></dl>
            </header>

            ${section('Case', rows([
                ['Status', alert.status_label || human(alert.status)],
                ['Risk score', alert.risk_score],
                ['Alert type', human(alert.alert_type)],
                ['Opened', dateTime(alert.created_at)],
                ['Owner', d.ownerName || 'Unassigned'],
                ['Potential SAR', alert.potential_sar ? 'Yes' : ''],
                ['Rule version', alert.rule_version],
                ['Amount', p.amount !== undefined ? money(p.amount, p.currency) : ''],
            ]))}

            ${section('Why this alert', ruleCodes(alert).length ? html`<ul class="report__list">${list(ruleCodes(alert), (code) => {
                const r = (p.rules || []).find((x) => x.rule === code) || {};
                return html`<li><strong>${code} ${ruleName(code)}</strong>${r.description ? ` — ${r.description}` : ''}</li>`;
            })}</ul>` : html`<p class="report__muted">No rule triggers were recorded.</p>`)}

            ${section('Customer', customer ? html`${rows([
                ['Type', human(c.customer_type)],
                ['Country', c.country],
                ['Date of birth', c.date_of_birth ? date(c.date_of_birth) : ''],
                ['Risk rating', `${human(c.risk_level)}${c.risk_score != null ? ` (score ${c.risk_score})` : ''}`],
                ['KYC status', human(c.kyc_status)],
                ['Flags', [c.sanctions_flag && 'Sanctions', c.pep_flag && 'PEP', c.adverse_media_flag && 'Adverse media'].filter(Boolean).join(', ') || 'None'],
            ])}
            ${d.profile && d.profile.length ? html`<h3>Why this rating</h3><ul class="report__list">${list(d.profile, (f) => html`<li>${f.risk_factor} (+${number(f.risk_weight)})</li>`)}</ul>` : ''}` : unavailable)}

            ${section('Transactions on this alert and flagged', tx === null ? unavailable : tx.length ? html`
                <table class="report__table"><thead><tr><th>Date</th><th>Type</th><th class="right">Amount</th><th>Counterparty</th><th>Rules</th></tr></thead>
                <tbody>${list(tx.slice(0, 50), (t) => html`<tr><td>${dateTime(t.transaction_date)}</td><td>${human(t.transaction_type)}</td>
                    <td class="right">${money(t.amount, t.currency)}</td><td>${t.meta_counterparty || '—'}${t.meta_country ? ` (${t.meta_country})` : ''}</td>
                    <td>${((t.risk_flags || {}).triggered_rules || []).join(', ')}${evidence.has(String(t.id)) ? ' · this alert' : ''}</td></tr>`)}</tbody></table>
                ${tx.length > 50 ? html`<p class="report__muted">The first 50 of ${tx.length} are shown.</p>` : ''}` : html`<p class="report__muted">None.</p>`)}

            ${section('Screening matches', d.matches === null ? unavailable : d.matches.length ? html`<ul class="report__list">${list(d.matches, (m) => html`
                <li><strong>${human(m.screening_type)}</strong>: ${m.listed.name || '—'} on ${m.listed.list || '—'}${m.match_score != null ? `, score ${Number(m.match_score).toFixed(0)}` : ''}
                    — ${m.resolution ? `${human(m.resolution)}: ${m.resolution_notes || ''}` : 'awaiting a decision'}</li>`)}</ul>` : html`<p class="report__muted">None on record.</p>`)}

            ${section('Requests for information', d.requests === null ? unavailable : d.requests.length ? html`<ul class="report__list">${list(d.requests, (r) => html`
                <li><strong>${r.requested_from}</strong>: ${r.subject} — ${human(r.status)}${r.response_note ? `: ${r.response_note}` : ''} <span class="report__muted">(due ${date(r.due_date)})</span></li>`)}</ul>`
                : html`<p class="report__muted">None.</p>`)}

            ${section('Documents', d.documents === null ? unavailable : d.documents.length ? html`<ul class="report__list">${list(d.documents, (doc) => html`
                <li>${doc.filename} <span class="report__muted">(${human(doc.doc_type)}, uploaded ${date(doc.uploaded_at)})</span></li>`)}</ul>` : html`<p class="report__muted">None.</p>`)}

            ${alert.summary ? section('Case summary', html`<p>${alert.summary}</p>
                <p class="report__muted">${alert.summary_attested_at ? `Checked against the records on ${dateTime(alert.summary_attested_at)}.` : 'Not checked against the records.'}</p>`) : ''}

            ${d.narrative ? section('Narrative', html`<p class="report__pre">${d.narrative.text}</p><p class="report__muted">Version ${d.narrative.version}, ${dateTime(d.narrative.at)}</p>`) : ''}

            ${section('Decision', alert.resolution_outcome ? rows([
                ['Outcome', human(alert.resolution_outcome)],
                ['Reasons', (alert.resolution_reasons || []).map(human).join(', ')],
                ['Notes', alert.resolution_notes],
                ['SAR reference', alert.sar_reference],
                ['Resolved', alert.resolved_at ? dateTime(alert.resolved_at) : ''],
                ['Quality check', alert.qa_result ? `${alert.qa_result === 'PASS' ? 'Passed' : 'Failed'} ${dateTime(alert.qa_at)}${alert.qa_notes ? ` — ${alert.qa_notes}` : ''}` : ''],
            ]) : html`<p class="report__muted">No decision recorded yet.</p>`)}

            ${section('Timeline', d.timeline === null ? unavailable : html`<table class="report__table"><thead><tr><th>When</th><th>Who</th><th>What</th></tr></thead>
                <tbody>${list(d.timeline.events, (e) => html`<tr><td class="nowrap">${dateTime(e.at)}</td><td>${e.by}</td><td><strong>${e.title}</strong>${e.detail ? html`<br>${e.detail}` : ''}</td></tr>`)}</tbody></table>`)}

            <footer class="report__foot">Produced by KYRO from live records on ${dateTime(new Date().toISOString())}. Case ${shortId(alert.id)}. Confidential: do not disclose to the customer.</footer>
        </article>`;
}

export default {
    async mount(root, { params }) {
        token += 1;
        const mine = token;
        render(root, html`<div class="report"><span class="skeleton"></span><span class="skeleton"></span><span class="skeleton"></span></div>`);
        let alert;
        try { alert = await API.alert(params.id); } catch (error) {
            render(root, html`<div class="page-message"><h1>The case could not be loaded</h1><p>${error.message}</p></div>`);
            return;
        }
        const id = alert.customer_id;
        const [customer, profile, transactions, matches, requests, documents, timeline, narratives, people] = await Promise.all([
            settle(API.customer(id)), settle(API.riskProfile(id)), settle(API.transactions(id)), settle(API.screeningMatches(id)),
            settle(API.requests(alert.id)), settle(API.documents(id)), settle(API.timeline(alert.id)),
            alert.restricted ? null : settle(API.narratives(alert.id)), settle(API.assignees()),
        ]);
        if (mine !== token) return;
        const owner = (people || []).find((p) => p.id === alert.assigned_to);
        const data = { alert, customer, profile, transactions, matches, requests, documents, timeline,
            narrative: narratives && !narratives.restricted ? narratives.versions[0] : null, ownerName: alert.assigned_to_name || (owner && owner.name) };
        document.title = `Case report · ${(customer || {}).full_name || shortId(alert.id)} · KYRO AML`;
        render(root, report(data));
        off = on(root, 'report', {
            'click [data-action=print]': () => window.print(),
            'click [data-action=json]': () => API.saveBlob(new Blob([JSON.stringify({ produced_at: new Date().toISOString(), ...data }, null, 2)], { type: 'application/json' }),
                `case-${shortId(alert.id)}-${new Date().toISOString().slice(0, 10)}.json`),
        });
    },
    unmount() {
        token += 1;
        off();
        off = () => {};
    },
};
