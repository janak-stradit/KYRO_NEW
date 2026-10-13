/**
 * Activity: the last 30 days against the customer's own baseline, who and where they deal with,
 * and their transactions (flagged first), filterable and exportable.
 */
import { html, list, render } from '../../../core/dom.js';
import { date, dateTime, human, number } from '../../../core/format.js';
import { ruleName } from '../../../config/rules.js';
import * as API from '../case.api.js';
import { chip, empty, failed, lines, money, names, panel, plural } from '../case.ui.js';

const PAGE = 25;
let ctx;
let tx = [];
let filters;

function view() {
    return html`
        ${panel({ id: 'case-baseline', title: "Activity against the customer's own baseline", sub: 'The last 30 days beside the 90 days before', body: lines(5) })}
        ${panel({ id: 'case-parties', title: 'Counterparties and countries', sub: 'Who and where this customer deals with', body: lines(4) })}
        <section class="card-x case-panel" id="case-tx">
            <header class="card-x__head">
                <div><h2 class="card-x__title">Transactions</h2><p class="card-x__sub" id="case-tx-count">&nbsp;</p></div>
                <div class="case-tx-controls">
                    <div class="segmented" role="group" aria-label="Which transactions">
                        <button type="button" class="is-active" data-scope="flagged" aria-pressed="true">Flagged</button>
                        <button type="button" data-scope="evidence" aria-pressed="false" title="The transactions this alert was raised on">This alert</button>
                        <button type="button" data-scope="all" aria-pressed="false">All</button>
                    </div>
                    <select class="form-select form-select-sm" data-tx="type" aria-label="Transaction type"><option value="">All types</option></select>
                    <input type="date" class="form-control form-control-sm" data-tx="from" aria-label="From date" title="From date">
                    <input type="date" class="form-control form-control-sm" data-tx="to" aria-label="To date" title="To date">
                    <input type="number" class="form-control form-control-sm" data-tx="min" min="0" step="any" placeholder="Min amount" aria-label="Minimum amount">
                    <button type="button" class="btn btn-quiet btn-sm" data-action="tx-export"><i class="fas fa-file-csv me-1" aria-hidden="true"></i>Export CSV</button>
                </div>
            </header>
            <div class="dt-wrap"><table class="dt">
                <thead><tr><th>Date</th><th>Type</th><th class="right">Amount</th><th>Counterparty</th><th>Rules fired</th><th class="right">Score</th></tr></thead>
                <tbody id="case-tx-body"><tr><td colspan="6">${lines(4)}</td></tr></tbody>
            </table></div>
            <div class="dt-foot" id="case-tx-foot" hidden><span></span><button type="button" class="btn btn-quiet btn-sm" data-action="tx-more">Show more</button></div>
        </section>`;
}

// ── Baseline ─────────────────────────────────────────────────────────────

function baseline(a) {
    const c = a.comparison;
    const total = a.buckets.reduce((sum, b) => sum + b.transactions, 0);
    const peak = Math.max(1, ...a.buckets.map((b) => b.transactions));
    const chart = total ? html`
        <div class="case-bars" role="img" aria-label="Transactions in each 10-day period: the previous ${a.baseline_days} days and the last ${a.window_days} days">
            ${list(a.buckets, (b) => html`<div class="case-bars__col" title="${date(b.start)} to ${date(b.end)}: ${plural(b.transactions, 'transaction')}">
                <span class="case-bars__n">${b.transactions || ''}</span>
                <span class="case-bars__bar ${b.current ? 'is-current' : ''}" data-h="${Math.round((b.transactions / peak) * 20)}"></span>
                <span class="case-bars__x">${new Date(`${b.start}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}</span></div>`)}
        </div>
        <p class="case-legend"><span><i class="is-base"></i>Previous ${a.baseline_days} days</span><span><i class="is-current"></i>Last ${a.window_days} days</span> · transactions in each 10-day period</p>`
        : empty(`No transactions in the last ${a.baseline_days + a.window_days} days.`);
    return html`
        <div class="case-split">
            <div>${chart}</div>
            <div>
                <h3 class="case-label case-label--first">Last ${a.window_days} days against the customer's usual</h3>
                <ul class="case-weights">
                    <li><span>Transactions</span><span><strong>${c.transactions.current}</strong> <small class="muted">usually ${c.transactions.usual}</small></span></li>
                    ${list(c.largest_amount.slice(0, 2), (l) => html`<li><span>Largest amount</span><span><strong>${money(l.current, l.currency)}</strong>
                        <small class="muted">${l.previous == null ? 'none before in this currency' : `before: ${money(l.previous, l.currency)}`}</small></span></li>`)}
                    <li><span>New counterparties</span><span>${c.new_counterparties.length ? html`<strong>${c.new_counterparties.length}</strong> of ${c.counterparties} <small class="muted">${names(c.new_counterparties)}</small>` : 'None'}</span></li>
                    <li><span>New countries</span><span>${c.new_countries.length ? html`<strong>${c.new_countries.length}</strong> <small class="muted">${names(c.new_countries)}</small>` : 'None'}</span></li>
                    ${c.high_risk_countries.length ? html`<li><span>High-risk jurisdictions</span><span>${chip('high', names(c.high_risk_countries))}</span></li>` : ''}
                </ul>
                <h3 class="case-label">Behaviour changes</h3>
                ${a.findings.length ? html`<ul class="case-findings">${list(a.findings, (f) => html`<li>${chip('medium', f.label)}<span>${f.evidence}</span></li>`)}</ul>`
                    : empty(a.enough_history ? "Nothing in the last 30 days departs from this customer's own history."
                        : `Fewer than ${a.min_baseline} transactions in the previous ${a.baseline_days} days, so there is no baseline to judge against.`)}
            </div>
        </div>`;
}

function parties(d) {
    if (!d.transactions) return empty(`No transactions in the last ${d.days} days.`);
    const totals = (g) => g.totals.slice(0, 2).map((t) => money(t.amount, t.currency, 0)).join(', ');
    const rows = (items, sub) => html`<ul class="case-parties">${list(items, (g) => html`
        <li><span class="case-parties__name"><strong>${g.name}</strong>${sub(g)} ${g.new ? chip('medium', 'New') : ''}${g.high_risk ? chip('high', 'High-risk') : ''}</span>
            <span class="muted">${plural(g.transactions, 'txn')}</span><span class="case-parties__amt">${totals(g)}</span></li>`)}</ul>`;
    return html`
        <div class="case-split">
            <div><h3 class="case-label case-label--first">Counterparties${d.counterparty_count > d.counterparties.length ? ` (top ${d.counterparties.length} of ${d.counterparty_count})` : ''}</h3>
                ${d.counterparties.length ? rows(d.counterparties, (g) => (g.countries.length ? html` <small class="muted">${g.countries.join(', ')}</small>` : '')) : empty('No counterparty is recorded on these transactions.')}</div>
            <div><h3 class="case-label case-label--first">Countries${d.country_count > d.countries.length ? ` (top ${d.countries.length} of ${d.country_count})` : ''}</h3>
                ${d.countries.length ? rows(d.countries, () => '') : empty('No country is recorded on these transactions.')}</div>
        </div>
        <p class="case-note">Last ${d.days} days. "New" means first seen in the last ${d.new_since_days} days.</p>`;
}

// ── Transactions ─────────────────────────────────────────────────────────

const rulesOf = (t) => (t.risk_flags && t.risk_flags.triggered_rules) || [];
const flagged = (t) => rulesOf(t).length > 0;

function filtered() {
    const f = filters;
    const evidence = new Set((ctx.alert.evidence_transaction_ids || []).map(String));
    const from = f.from ? new Date(`${f.from}T00:00:00`) : null;
    const to = f.to ? new Date(`${f.to}T23:59:59`) : null;
    const min = f.min === '' ? null : Number(f.min);
    return tx.filter((t) => (f.scope === 'all' || (f.scope === 'flagged' ? flagged(t) : evidence.has(String(t.id))))
        && (!f.type || t.transaction_type === f.type)
        && (!from || new Date(t.transaction_date) >= from) && (!to || new Date(t.transaction_date) <= to)
        && (min === null || Number.isNaN(min) || Number(t.amount) >= min))
        .sort((a, b) => new Date(b.transaction_date) - new Date(a.transaction_date));
}

function showTransactions() {
    const rows = filtered();
    const evidence = new Set((ctx.alert.evidence_transaction_ids || []).map(String));
    $('#case-tx-count').text(`${number(Math.min(filters.shown, rows.length))} of ${number(rows.length)} shown · ${number(tx.filter(flagged).length)} flagged of ${number(tx.length)} loaded${tx.length >= 500 ? ' (the most recent 500)' : ''}`);
    render('#case-tx-body', rows.length ? list(rows.slice(0, filters.shown), (t) => html`
        <tr class="${evidence.has(String(t.id)) ? 'is-evidence' : ''}">
            <td class="nowrap">${dateTime(t.transaction_date)}${evidence.has(String(t.id)) ? html` ${chip('info', 'This alert')}` : ''}</td>
            <td>${human(t.transaction_type)}${t.direction ? html`<span class="cell-sub">${human(t.direction)}${t.channel ? ` · ${human(t.channel)}` : ''}</span>` : ''}</td>
            <td class="right nowrap"><strong>${money(t.amount, t.currency)}</strong></td>
            <td>${t.meta_counterparty || '—'}${t.meta_country ? html` <small class="muted">${t.meta_country}</small>` : ''}</td>
            <td>${rulesOf(t).length ? html`<div class="tags">${list(rulesOf(t), (code) => html`<span class="tag" title="${code}">${ruleName(code)}</span>`)}</div>` : html`<span class="muted">None</span>`}</td>
            <td class="right">${t.risk_score ?? '—'}</td>
        </tr>`) : html`<tr><td colspan="6">${empty(tx.length ? 'No transactions match these filters.' : 'No transactions on record for this customer.')}</td></tr>`);
    $('#case-tx-foot').prop('hidden', rows.length <= filters.shown).find('button').text(`Show ${Math.min(PAGE, rows.length - filters.shown)} more`);
    $('[data-action=tx-export]').prop('disabled', !rows.length);
}

function exportCsv() {
    // A leading =, +, - or @ would be run as a formula by a spreadsheet
    const cell = (value) => {
        let text = value === null || value === undefined ? '' : String(value);
        if (/^[=+\-@]/.test(text) && Number.isNaN(Number(text))) text = `'${text}`;
        return `"${text.replace(/"/g, '""')}"`;
    };
    const out = [['Date', 'Type', 'Amount', 'Currency', 'Counterparty', 'Country', 'Rules fired', 'Risk score']];
    filtered().forEach((t) => out.push([new Date(t.transaction_date).toISOString(), t.transaction_type, Number(t.amount).toFixed(2), t.currency,
        t.meta_counterparty, t.meta_country, rulesOf(t).join(' '), t.risk_score]));
    const name = (ctx.customer.full_name || 'customer').replace(/[^A-Za-z0-9]+/g, '-');
    API.saveBlob(new Blob([`﻿${out.map((r) => r.map(cell).join(',')).join('\r\n')}`], { type: 'text/csv;charset=utf-8' }),
        `transactions-${name}-${new Date().toISOString().slice(0, 10)}.csv`);
}

const change = (key, value) => { filters[key] = value; filters.shown = PAGE; showTransactions(); };

// ── Loading ──────────────────────────────────────────────────────────────

async function section(target, load, show, what) {
    const mine = ctx;
    try {
        const data = await load();
        if (mine.current()) render(`${target} .case-panel__body`, show(data));
    } catch (error) {
        if (mine.current()) render(`${target} .case-panel__body`, failed(what));
    }
    $(`${target} .case-bars__bar`).each((_, el) => { el.style.setProperty('--h', el.dataset.h); });
}

async function loadTransactions() {
    const mine = ctx;
    let data;
    try {
        data = await API.transactions(mine.alert.customer_id);
    } catch (error) {
        if (mine.current()) render('#case-tx-body', html`<tr><td colspan="6">${failed('Transactions')}</td></tr>`);
        return;
    }
    if (!mine.current()) return;
    tx = data.items || [];
    const types = [...new Set(tx.map((t) => t.transaction_type).filter(Boolean))].sort();
    $('[data-tx=type]').append(String(list(types, (t) => html`<option value="${t}">${human(t)}</option>`)));
    const count = tx.filter(flagged).length;
    // Open on the transactions the alert was raised on, when the engine recorded them
    if ((mine.alert.evidence_transaction_ids || []).length) {
        filters.scope = 'evidence';
        $('[data-scope]').each((_, el) => { el.classList.toggle('is-active', el.dataset.scope === 'evidence'); el.setAttribute('aria-pressed', el.dataset.scope === 'evidence'); });
    }
    mine.glance('flagged', number(count), `of ${number(tx.length)} loaded`);
    mine.count('activity', count);
    showTransactions();
}

export default {
    render: view,
    load(c) {
        ctx = c;
        tx = [];
        filters = { scope: 'flagged', type: '', from: '', to: '', min: '', shown: PAGE };
        section('#case-baseline', () => API.activity(c.alert.customer_id), baseline, 'Activity');
        section('#case-parties', () => API.counterparties(c.alert.customer_id), parties, 'Counterparties');
        loadTransactions();
    },
    handlers: {
        'click [data-scope]': function () {
            $('[data-scope]').removeClass('is-active').attr('aria-pressed', 'false');
            $(this).addClass('is-active').attr('aria-pressed', 'true');
            change('scope', this.dataset.scope);
        },
        'change [data-tx]': function () { change(this.dataset.tx, this.value); },
        'input [data-tx=min]': function () { change('min', this.value); },
        'click [data-action=tx-more]': () => { filters.shown += PAGE; showTransactions(); },
        'click [data-action=tx-export]': () => exportCsv(),
    },
};
