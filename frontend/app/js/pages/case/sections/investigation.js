/**
 * Investigation: notes and the timeline, requests for information, and the draft narrative.
 * Notes and narrative versions are never changed once saved; every action lands on the timeline.
 */
import { can, isReadOnly } from '../../../core/auth.js';
import { html, list, render } from '../../../core/dom.js';
import { date, dateTime } from '../../../core/format.js';
import { toast } from '../../../core/feedback.js';
import * as API from '../case.api.js';
import { chip, empty, failed, lines, panel, plural } from '../case.ui.js';

let ctx;
const counts = { notes: 0, requests: 0 };

const ICONS = { created: 'fa-bell', note: 'fa-pen', assigned: 'fa-user-plus', escalated: 'fa-arrow-up', resolved: 'fa-check-double',
    qa: 'fa-clipboard-check', document: 'fa-file-lines', request: 'fa-envelope', updated: 'fa-rotate' };

const isoDay = (days) => new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);

function view({ alert }) {
    const open = alert.status !== 'RESOLVED';
    const mayRequest = open && can('alerts.escalate');
    const mayNarrate = can('alerts.escalate') && !alert.restricted;
    return html`
        <div class="case-grid">
            ${panel({ id: 'case-notes', title: 'Notes and timeline', sub: 'What has been done on this case', body: html`
                ${isReadOnly() ? '' : html`<form class="case-form" data-form="note">
                    <label class="visually-hidden" for="case-note">Add a note</label>
                    <textarea class="form-control" id="case-note" name="body" rows="3" maxlength="4000" placeholder="What you checked, who you spoke to, what you found"></textarea>
                    <div class="case-form__foot"><small class="muted">Notes cannot be edited or removed once saved.</small>
                        <button type="submit" class="btn btn-primary btn-sm">Add note</button></div></form>`}
                <div id="case-timeline">${lines(5)}</div>` })}
            ${panel({ id: 'case-requests', title: 'Requests for information', sub: 'What was asked for, from whom, and whether it arrived', body: html`
                <div id="case-request-list">${lines(3)}</div>
                ${mayRequest ? html`<form class="case-form case-form--boxed" data-form="request">
                    <h3 class="case-label case-label--first">Record a new request</h3>
                    <div class="case-form__row">
                        <div><label class="field-label" for="case-req-from">Asked from</label>
                            <input type="text" class="form-control form-control-sm" id="case-req-from" name="from" list="case-req-from-list" maxlength="150" required>
                            <datalist id="case-req-from-list"><option value="Customer"><option value="Relationship manager"><option value="Counterparty bank"><option value="Internal team"></datalist></div>
                        <div><label class="field-label" for="case-req-due">Due</label>
                            <input type="date" class="form-control form-control-sm" id="case-req-due" name="due" min="${isoDay(0)}" value="${isoDay(7)}" required></div>
                    </div>
                    <label class="field-label" for="case-req-subject">What was asked for</label>
                    <input type="text" class="form-control form-control-sm" id="case-req-subject" name="subject" maxlength="2000" placeholder="e.g. source of funds for the 12 Sep transfer" required>
                    <div class="case-form__foot"><small class="muted">KYRO records the request; it does not send it.</small>
                        <button type="submit" class="btn btn-primary btn-sm">Record request</button></div></form>` : ''}` })}
        </div>
        ${panel({ id: 'case-narrative', title: 'Narrative', sub: 'Who, what, when, where and why, from the facts on this case',
            actions: mayNarrate ? html`<button type="button" class="btn btn-quiet btn-sm" data-action="narrative-draft">Draft narrative</button>` : '',
            body: alert.restricted ? empty('This case is with the MLRO. Its narrative is restricted to the people who decide on SARs.')
                : empty(mayNarrate ? 'Select "Draft narrative" for a first draft built from the customer, the alert, the flagged transactions, your notes and requests.'
                    : 'Your role cannot draft a narrative.') })}`;
}

// ── Timeline ─────────────────────────────────────────────────────────────

export async function loadTimeline() {
    const mine = ctx;
    let data;
    try {
        data = await API.timeline(mine.alert.id);
    } catch (error) {
        if (mine.current()) render('#case-timeline', failed('The timeline'));
        return null;
    }
    if (!mine.current()) return null;
    const others = data.events.length - data.note_count;
    counts.notes = data.note_count;
    mine.count('investigation', counts.notes + counts.requests);
    mine.glance('notes', data.note_count, plural(others, 'other event'));
    $('#case-notes [data-sub]').text(`${plural(data.note_count, 'note')}, ${plural(others, 'other event')}`);
    render('#case-timeline', data.events.length ? html`<ol class="case-tl">${list(data.events, (e) => html`
        <li class="case-tl__item case-tl__item--${e.kind}">
            <span class="case-tl__icon" aria-hidden="true"><i class="fas ${ICONS[e.kind] || 'fa-circle'}"></i></span>
            <div><p class="case-tl__title">${e.title}</p>${e.detail ? html`<p class="case-tl__detail">${e.detail}</p>` : ''}
                <p class="case-tl__meta">${e.by} · ${dateTime(e.at)}</p></div></li>`)}</ol>` : empty('Nothing recorded yet.'));
    return data;
}

// ── Requests ─────────────────────────────────────────────────────────────

const REQUEST_STATE = (r) => (r.status === 'RECEIVED' ? ['low', 'Received'] : r.status === 'CANCELLED' ? ['muted', 'Withdrawn'] : r.overdue ? ['high', 'Overdue'] : ['medium', 'Waiting']);

async function loadRequests() {
    const mine = ctx;
    let items;
    try {
        items = await API.requests(mine.alert.id);
    } catch (error) {
        if (mine.current()) render('#case-request-list', failed('Requests'));
        return;
    }
    if (!mine.current()) return;
    const open = items.filter((r) => r.status === 'OPEN');
    const late = open.filter((r) => r.overdue).length;
    counts.requests = open.length;
    mine.count('investigation', counts.notes + counts.requests);
    mine.glance('requests', open.length, late ? `${late} past the due date` : items.length ? `${items.length} recorded in all` : 'nothing asked for yet', late > 0);
    const mayClose = can('alerts.escalate');
    render('#case-request-list', items.length ? html`<ul class="case-requests">${list(items, (r) => {
        const [tone, label] = REQUEST_STATE(r);
        return html`<li class="case-request" data-request="${r.id}">
            <div class="case-request__head"><strong>${r.requested_from}</strong>${chip(tone, label)}</div>
            <p class="case-request__subject">${r.subject}</p>
            <p class="case-tl__meta">Asked by ${r.requested_by_name} on ${date(r.created_at)} · due ${date(r.due_date)}</p>
            ${r.response_note ? html`<p class="case-quote">${r.response_note}<small class="muted"> ${r.closed_by_name || ''} · ${date(r.closed_at)}</small></p>` : ''}
            ${r.status === 'OPEN' && mayClose ? html`<div class="case-request__close">
                <label class="visually-hidden" for="case-req-note-${r.id}">What was received</label>
                <input type="text" class="form-control form-control-sm" id="case-req-note-${r.id}" maxlength="2000" placeholder="What was received">
                <button type="button" class="btn btn-quiet btn-sm" data-action="request-close" data-status="RECEIVED">Mark received</button>
                <button type="button" class="icon-btn" data-action="request-close" data-status="CANCELLED" title="Withdraw this request" aria-label="Withdraw this request"><i class="fas fa-xmark"></i></button>
            </div>` : ''}</li>`;
    })}</ul>` : empty('Nothing has been requested on this case.'));
}

// ── Narrative ────────────────────────────────────────────────────────────

async function loadNarratives() {
    const mine = ctx;
    if (mine.alert.restricted) return;
    let data;
    try { data = await API.narratives(mine.alert.id); } catch (error) { return; }
    if (!mine.current()) return;
    if (data.restricted) {
        $('[data-action=narrative-draft]').remove();
        render('#case-narrative .case-panel__body', empty('This case is with the MLRO. Its narrative is restricted to the people who decide on SARs.'));
        return;
    }
    const latest = data.versions[0];
    if (!latest) return;
    $('[data-action=narrative-draft]').text('Draft again');
    const mayEdit = can('alerts.escalate');
    const source = latest.source === 'EDITED'
        ? `Version ${latest.version}, checked and saved by ${latest.by || 'an investigator'} on ${dateTime(latest.at)}`
        : `Version ${latest.version}, ${latest.provider === 'mock' ? 'arranged from the facts on file by the built-in template; it adds nothing to the facts'
            : 'drafted by the AI model from the facts on file, with names masked before sending; check every statement'} (${dateTime(latest.at)})`;
    render('#case-narrative .case-panel__body', html`
        <p class="case-note">${source}${data.versions.length > 1 ? ` · ${data.versions.length} versions kept` : ''}</p>
        <label class="visually-hidden" for="case-narrative-text">Narrative</label>
        <textarea class="form-control case-narrative" id="case-narrative-text" rows="14" ${mayEdit ? '' : 'readonly'}>${latest.text}</textarea>
        <div class="case-confirm">
            ${mayEdit ? html`<label class="form-check"><input class="form-check-input" type="checkbox" data-confirm="narrative">
                <span class="form-check-label">I have checked this against the source records</span></label>` : html`<small class="muted">Saving keeps a new version; earlier versions are not changed.</small>`}
            <div class="case-actions">
                <button type="button" class="btn btn-quiet btn-sm" data-action="narrative-copy">Copy</button>
                ${mayEdit ? html`<button type="button" class="btn btn-primary btn-sm" data-action="narrative-save">Save as new version</button>` : ''}
            </div>
        </div>`);
}

export default {
    render: view,
    load(c) {
        ctx = c;
        counts.notes = 0;
        counts.requests = 0;
        loadRequests();
        loadNarratives();
        // The timeline is loaded by the page: it also carries the stages and the case clock
    },
    handlers: {
        'submit [data-form=note]': async function (event) {
            event.preventDefault();
            const body = this.body.value.trim();
            if (!body) { this.body.focus(); return; }
            const $button = $(this).find('button').prop('disabled', true);
            try {
                await API.addNote(ctx.alert.id, body);
                this.reset();
                ctx.refreshTimeline();
            } catch (error) { toast('error', error.message); }
            $button.prop('disabled', false);
        },
        'submit [data-form=request]': async function (event) {
            event.preventDefault();
            const body = { requested_from: this.from.value.trim(), subject: this.subject.value.trim(), due_date: this.due.value };
            if (!body.requested_from || !body.subject || !body.due_date) { toast('error', 'Say who was asked, what for, and by when.'); return; }
            const $button = $(this).find('button').prop('disabled', true);
            try {
                await API.addRequest(ctx.alert.id, body);
                this.subject.value = '';
                loadRequests();
                ctx.refreshTimeline();
            } catch (error) { toast('error', error.message); }
            $button.prop('disabled', false);
        },
        'click [data-action=request-close]': async function () {
            const $request = $(this).closest('[data-request]');
            const note = $request.find('input').val().trim();
            if (this.dataset.status === 'RECEIVED' && !note) { toast('error', 'Say what was received.'); $request.find('input').trigger('focus'); return; }
            $request.find('button').prop('disabled', true);
            try {
                await API.closeRequest($request.data('request'), this.dataset.status, note);
                loadRequests();
                ctx.refreshTimeline();
            } catch (error) {
                toast('error', error.message);
                $request.find('button').prop('disabled', false);
            }
        },
        'click [data-action=narrative-draft]': async function () {
            const mine = ctx;
            const $button = $(this).prop('disabled', true).text('Drafting…');
            render('#case-narrative .case-panel__body', html`${lines(8)}<p class="case-note">Drafting the narrative. This can take up to a minute.</p>`);
            try {
                await API.draftNarrative(mine.alert.id);
                if (mine.current()) await loadNarratives();
            } catch (error) {
                toast('error', error.message);
                if (mine.current()) render('#case-narrative .case-panel__body', empty('The narrative could not be drafted. Try again.'));
            }
            $button.prop('disabled', false);
        },
        'click [data-action=narrative-copy]': async () => {
            try {
                await navigator.clipboard.writeText($('#case-narrative-text').val());
                toast('success', 'Narrative copied.');
            } catch (error) {
                $('#case-narrative-text').trigger('select');
                toast('error', 'The browser blocked copying. The text is selected: press Ctrl+C.');
            }
        },
        'click [data-action=narrative-save]': async function () {
            const text = $('#case-narrative-text').val().trim();
            if (!text) return;
            if (!$('[data-confirm=narrative]').is(':checked')) { toast('error', 'Tick the box to confirm you checked the narrative against the records.'); return; }
            $(this).prop('disabled', true);
            try {
                await API.saveNarrative(ctx.alert.id, text);
                toast('success', 'Narrative saved as a new version.');
                await loadNarratives();
                ctx.refreshTimeline();
            } catch (error) {
                toast('error', error.message);
                $(this).prop('disabled', false);
            }
        },
    },
};
