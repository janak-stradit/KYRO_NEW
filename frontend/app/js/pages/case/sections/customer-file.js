/**
 * Customer file: what was recorded at onboarding, accounts, beneficial owners, watchlist matches
 * (decided here) and KYC reviews.
 */
import { can } from '../../../core/auth.js';
import { html, list, render } from '../../../core/dom.js';
import { date, dateTime, human, number } from '../../../core/format.js';
import { toast } from '../../../core/feedback.js';
import * as API from '../case.api.js';
import { chip, empty, facts, failed, lines, money, panel, plural } from '../case.ui.js';

const SHOWN_MATCHES = 3;
let ctx;
let matches = [];
let showAll = false;

function view({ customer, reviews }) {
    const company = customer.customer_type && customer.customer_type !== 'INDIVIDUAL';
    const m = customer.customer_metadata || {};
    return html`
        ${panel({ title: 'Customer profile', sub: `What was recorded when the customer was taken on${m.sample_data ? ' (sample data)' : ''}`, body: profile(customer) })}
        <section class="card-x case-panel" id="case-accounts">
            <header class="card-x__head"><div><h2 class="card-x__title">Accounts</h2><p class="card-x__sub" data-sub>Accounts held by this customer</p></div></header>
            <div class="dt-wrap"><table class="dt">
                <thead><tr><th>Account</th><th>Purpose</th><th>Opened</th><th>Status</th><th class="right">Balance</th><th class="right">Last 30 days</th><th>Last activity</th></tr></thead>
                <tbody><tr><td colspan="7">${lines(3)}</td></tr></tbody></table></div>
            <p class="case-warning" data-turnover hidden></p>
        </section>
        ${company ? html`<section class="card-x case-panel" id="case-owners">
            <header class="card-x__head"><div><h2 class="card-x__title">Beneficial owners</h2><p class="card-x__sub" data-sub>Who ultimately owns or controls this customer</p></div></header>
            <div class="dt-wrap"><table class="dt">
                <thead><tr><th>Owner</th><th class="right">Ownership</th><th>Control</th><th>Nationality</th><th>Flags</th><th>Verification</th></tr></thead>
                <tbody><tr><td colspan="6">${lines(2)}</td></tr></tbody></table></div>
            <p class="case-warning" data-cdd hidden><i class="fas fa-triangle-exclamation me-1" aria-hidden="true"></i>Ownership checks are not complete: an owner is still awaiting verification or is flagged for sanctions.</p>
        </section>` : ''}
        <div class="case-grid case-grid--wide">
            ${panel({ id: 'case-screening', title: 'Screening matches', body: lines(4),
                sub: `The watchlist entry beside the customer${customer.last_screened_at ? `; last screened ${date(customer.last_screened_at)}` : ''}` })}
            ${panel({ title: 'KYC reviews', sub: 'Scheduled and completed reviews', body: reviews === null ? failed('KYC reviews')
                : reviews.length ? html`<ul class="case-weights">${list(reviews.slice(0, 6), (r) => html`
                    <li><span>${human(r.review_type)} <small class="muted">${r.completed_date ? `completed ${date(r.completed_date)}` : r.scheduled_date ? `due ${date(r.scheduled_date)}` : 'not scheduled'}</small></span>
                        <strong>${human(r.review_status)}</strong></li>`)}</ul>` : empty('No reviews on record.') })}
        </div>`;
}

function profile(customer) {
    const m = customer.customer_metadata || {};
    const individual = customer.customer_type === 'INDIVIDUAL';
    const address = m.address ? [m.address.line1, m.address.city, m.address.postal_code, m.address.country].filter(Boolean).join(', ') : '';
    const id = m.id_document;
    const expired = id && id.expires_on && new Date(id.expires_on) < new Date();
    return facts([
        ['Legal name', customer.full_name],
        ['Type', human(customer.customer_type)],
        [individual ? 'Date of birth' : 'Incorporated', individual ? (customer.date_of_birth && date(customer.date_of_birth)) : (m.incorporated_on && date(m.incorporated_on))],
        [individual ? 'Occupation' : 'Business', m.occupation || m.industry],
        [individual ? 'Employer' : 'Registration number', individual ? m.employer : m.registration_number],
        ['Country', customer.country],
        ['Residency', customer.residency_country],
        ['Tax residency', m.tax_residency],
        ['Address', address],
        ['Email', customer.email],
        ['Phone', customer.phone],
        ['Identity document', id ? html`${id.type} ending ${id.number_ending}${id.expires_on ? html` ${chip(expired ? 'high' : 'muted', `${expired ? 'Expired' : 'Expires'} ${date(id.expires_on)}`)}` : ''}` : ''],
        ['Source of funds', m.source_of_funds],
        ['Source of wealth', m.source_of_wealth],
        ['Purpose of relationship', m.purpose_of_relationship],
        ['Expected monthly turnover', m.expected_monthly_turnover ? money(m.expected_monthly_turnover.amount, m.expected_monthly_turnover.currency, 0) : ''],
        ['Customer since', m.onboarded_on && date(m.onboarded_on)],
        ['Onboarded through', m.onboarding_channel],
        ['Relationship manager', m.relationship_manager],
        ['Employees', m.employees],
    ]);
}

// ── Accounts and owners ──────────────────────────────────────────────────

const ACCOUNT_TONE = { ACTIVE: 'low', FROZEN: 'high', CLOSED: 'muted', SUSPENDED: 'medium' };

async function loadAccounts() {
    const mine = ctx;
    let d;
    try { d = await API.accounts(mine.alert.customer_id); } catch (error) {
        if (mine.current()) render('#case-accounts tbody', html`<tr><td colspan="7">${failed('Accounts')}</td></tr>`);
        return;
    }
    if (!mine.current()) return;
    $('#case-accounts [data-sub]').text(`${plural(d.accounts.length, 'account')}${d.accounts.some((a) => a.sample_data) ? ' · account details are sample data' : ''}`);
    render('#case-accounts tbody', d.accounts.length ? list(d.accounts, (a) => html`
        <tr><td><span class="cell-strong">${a.product || human(a.account_type)}</span>
                <span class="cell-sub">${a.account_number ? `No. ${a.account_number} · ` : ''}${human(a.account_type)} · ${a.currency}${a.branch ? ` · ${a.branch}` : ''}</span></td>
            <td>${a.purpose || '—'}</td>
            <td class="nowrap">${a.opened_date ? date(a.opened_date) : '—'}${a.opened_channel ? html`<span class="cell-sub">${a.opened_channel}</span>` : ''}</td>
            <td>${chip(ACCOUNT_TONE[a.account_status] || 'muted', human(a.account_status))}</td>
            <td class="right nowrap"><strong>${money(a.balance, a.currency)}</strong></td>
            <td class="right nowrap">${a.last_30_days.transactions ? html`${money(a.last_30_days.amount, a.currency)}<span class="cell-sub">${plural(a.last_30_days.transactions, 'transaction')}</span>` : html`<span class="muted">No activity</span>`}</td>
            <td class="nowrap">${a.last_transaction_at ? date(a.last_transaction_at) : '—'}<span class="cell-sub">${number(a.transactions)} in all${a.flagged_transactions ? `, ${a.flagged_transactions} flagged` : ''}</span></td>
        </tr>`) : html`<tr><td colspan="7">${empty('No accounts on record.')}</td></tr>`);
    // Actual turnover beside what the customer said to expect, when both are in the same currency
    const expected = d.expected_monthly_turnover;
    const actual = expected && d.turnover_last_30_days.find((t) => t.currency === expected.currency);
    if (actual && actual.amount > expected.amount * 1.5) {
        $('#case-accounts [data-turnover]').prop('hidden', false).text(`Turnover in the last 30 days was ${money(actual.amount, actual.currency, 0)}, against ${money(expected.amount, expected.currency, 0)} a month expected at onboarding.`);
    }
}

const VERIFY_TONE = { VERIFIED: 'low', PENDING: 'medium', REJECTED: 'high' };

async function loadOwners() {
    const mine = ctx;
    let owners, summary;
    try { [owners, summary] = await API.owners(mine.alert.customer_id); } catch (error) {
        if (mine.current()) render('#case-owners tbody', html`<tr><td colspan="6">${failed('Beneficial owners')}</td></tr>`);
        return;
    }
    if (!mine.current()) return;
    if (owners.length) {
        $('#case-owners [data-sub]').text(`${summary.owner_count} on record, ${number(summary.total_ownership_percentage)}% of ownership identified, ${summary.verified_count} verified`);
        $('#case-owners [data-cdd]').prop('hidden', summary.is_cdd_complete);
    }
    render('#case-owners tbody', owners.length ? list(owners, (o) => html`
        <tr><td><span class="cell-strong">${o.full_name}</span><span class="cell-sub">${human(o.owner_type)}${o.effective_to ? ` · ended ${date(o.effective_to)}` : ''}</span></td>
            <td class="right">${o.ownership_percentage == null ? '—' : `${number(o.ownership_percentage)}%`}</td>
            <td>${human(o.control_type)}</td>
            <td>${o.nationality || '—'}${o.country_of_residence && o.country_of_residence !== o.nationality ? html` <small class="muted">lives in ${o.country_of_residence}</small>` : ''}</td>
            <td>${o.sanctions_flag ? chip('high', 'Sanctions') : ''} ${o.is_pep ? chip('medium', 'PEP') : ''}${!o.sanctions_flag && !o.is_pep ? html`<span class="muted">None</span>` : ''}</td>
            <td>${chip(VERIFY_TONE[o.verification_status] || 'muted', human(o.verification_status))}</td></tr>`)
        : html`<tr><td colspan="6">${empty('No beneficial owners are recorded for this customer.')}</td></tr>`);
}

// ── Screening ────────────────────────────────────────────────────────────

const RESOLUTION = { CLEARED: ['low', 'Not the same person'], CONFIRMED: ['high', 'Confirmed match'], ESCALATED: ['medium', 'Escalated'] };
const cell = (v) => (v === null || v === undefined || v === '' ? html`<span class="muted">—</span>` : v);

function match(m) {
    const done = RESOLUTION[m.resolution];
    const remarks = m.listed.remarks && m.listed.remarks.length > 220 ? `${m.listed.remarks.slice(0, 217)}…` : m.listed.remarks;
    return html`<article class="case-match" data-match="${m.id}">
        <header class="case-match__head"><span><strong>${human(m.screening_type)}</strong>${m.match_score != null ? ` · match score ${Number(m.match_score).toFixed(0)}` : ''}${m.listed.still_listed === false ? html` · <span class="muted">no longer listed</span>` : ''}</span>
            ${done ? chip(done[0], done[1]) : chip(m.match_status === 'CONFIRMED_MATCH' ? 'high' : 'medium', human(m.match_status))}</header>
        <table class="case-match__table">
            <thead><tr><th></th><th>${m.subject.kind}</th><th>List entry</th></tr></thead>
            <tbody>
                <tr><th>Name</th><td>${cell(m.subject.name)}</td><td>${cell(m.listed.name)}${m.listed.aka_names.length ? html`<small class="muted">also ${m.listed.aka_names.join('; ')}</small>` : ''}</td></tr>
                <tr><th>Date of birth</th><td>${cell(m.subject.date_of_birth && date(m.subject.date_of_birth))}</td><td>${cell(m.listed.date_of_birth && date(m.listed.date_of_birth))} ${m.dob_match === true ? chip('high', 'Same') : ''}</td></tr>
                <tr><th>Country</th><td>${cell(m.subject.country)}</td><td>${cell(m.listed.nationalities.join(', '))}</td></tr>
                <tr><th>List</th><td></td><td>${cell(m.listed.list)}${m.listed.programs.length ? html`<small class="muted">${m.listed.programs.join(', ')}</small>` : ''}</td></tr>
            </tbody>
        </table>
        ${remarks ? html`<p class="case-note">${remarks}</p>` : ''}
        ${m.resolution ? html`<p class="case-quote">${m.resolution_notes || ''}<small class="muted"> ${m.resolved_by_name || 'Unknown user'} · ${dateTime(m.resolved_at)}</small></p>`
            : can('screening.run') ? html`
            <label class="visually-hidden" for="case-match-${m.id}">Reason for the decision</label>
            <textarea class="form-control" id="case-match-${m.id}" rows="2" maxlength="2000" placeholder="Reason for the decision (required)"></textarea>
            <div class="case-actions">
                <button type="button" class="btn btn-quiet btn-sm" data-action="match-decide" data-decision="CLEARED">Not the same person</button>
                <button type="button" class="btn btn-quiet btn-sm" data-action="match-decide" data-decision="ESCALATED">Escalate</button>
                <button type="button" class="btn btn-quiet btn-sm case-danger" data-action="match-decide" data-decision="CONFIRMED">Confirmed match</button>
            </div>` : html`<p class="case-note">Awaiting a decision.</p>`}
    </article>`;
}

function showMatches() {
    const body = '#case-screening .case-panel__body';
    if (!matches.length) return render(body, empty('No possible or confirmed watchlist matches on record.'));
    const visible = showAll ? matches : matches.slice(0, SHOWN_MATCHES);
    return render(body, html`${list(visible, match)}
        ${matches.length > SHOWN_MATCHES ? html`<button type="button" class="link-btn" data-action="matches-toggle">${showAll ? `Show the first ${SHOWN_MATCHES} only` : `Show all ${matches.length} matches`}</button>` : ''}`);
}

async function loadScreening() {
    const mine = ctx;
    try { matches = await API.screeningMatches(mine.alert.customer_id); } catch (error) {
        if (mine.current()) render('#case-screening .case-panel__body', failed('Screening results'));
        return;
    }
    if (!mine.current()) return;
    const undecided = matches.filter((m) => !m.resolution).length;
    mine.glance('matches', matches.length, matches.length ? (undecided ? `${undecided} awaiting a decision` : 'all decided') : 'none on record', undecided > 0);
    mine.count('file', undecided);
    showMatches();
}

export default {
    render: view,
    load(c) {
        ctx = c;
        showAll = false;
        loadAccounts();
        if (c.customer.customer_type && c.customer.customer_type !== 'INDIVIDUAL') loadOwners();
        loadScreening();
    },
    handlers: {
        'click [data-action=matches-toggle]': () => { showAll = !showAll; showMatches(); },
        'click [data-action=match-decide]': async function () {
            const $match = $(this).closest('[data-match]');
            const notes = $match.find('textarea').val().trim();
            if (!notes) { toast('error', 'Give the reason for the decision.'); $match.find('textarea').trigger('focus'); return; }
            $match.find('button').prop('disabled', true);
            try {
                await API.decideMatch($match.data('match'), this.dataset.decision, notes);
                toast('success', 'Screening decision recorded.');
                ctx.reload();  // a confirmed match changes the customer's flags and rating
            } catch (error) {
                toast('error', error.message);
                $match.find('button').prop('disabled', false);
            }
        },
    },
};
