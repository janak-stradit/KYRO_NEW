/**
 * Documents: the customer's KYC documents, upload, and the review of what was read from each.
 * Every value read shows the page it came from and how it compares with the record; a person
 * accepts, corrects or rejects it.
 */
import { can } from '../../../core/auth.js';
import { html, list, raw, render } from '../../../core/dom.js';
import { date } from '../../../core/format.js';
import { toast } from '../../../core/feedback.js';
import * as API from '../case.api.js';
import { chip, empty, failed, lines, panel, plural } from '../case.ui.js';

const TYPES = {
    ID_DOCUMENT: 'Identity document', PROOF_OF_ADDRESS: 'Proof of address', COMPANY_REGISTRY: 'Company registry extract',
    FINANCIAL_STATEMENT: 'Financial statement', SOURCE_OF_FUNDS: 'Source of funds letter', OTHER: 'Other',
};
const CHECK = { MATCH: ['low', 'Matches record'], MISMATCH: ['high', 'Differs from record'], NOT_ON_RECORD: ['medium', 'Not on record'],
    EXPIRED: ['high', 'Expired'], NOT_CHECKED: ['muted', 'Not checked'] };
const label = (field) => String(field || '').replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

let ctx;
let doc = null;    // the document open in the review dialog
let modal = null;

function view() {
    return panel({ id: 'case-docs', title: 'Documents', sub: 'KYC documents for this customer, and what was read from them', body: html`
        <ul class="case-docs" id="case-doc-list">${lines(2)}</ul>
        ${can('documents.manage') ? html`<form class="case-form case-docs__upload" data-form="upload">
            <select class="form-select form-select-sm" name="type" aria-label="Document type">${list(Object.entries(TYPES), ([k, v]) => html`<option value="${k}">${v}</option>`)}</select>
            <input type="file" class="form-control form-control-sm" name="file" accept=".pdf,.docx,.txt" aria-label="Document file">
            <button type="submit" class="btn btn-quiet btn-sm"><i class="fas fa-upload me-1" aria-hidden="true"></i>Upload</button>
        </form><p class="case-note">PDF, Word or text, up to 10 MB. Scanned images cannot be read yet.</p>` : ''}` });
}

function state(d) {
    const s = d.summary || {};
    if (d.text_status !== 'EXTRACTED') return chip('medium', d.text_status === 'NEEDS_OCR' ? 'Scanned, cannot be read yet' : 'Text could not be read');
    if (!d.extracted_at) return chip('muted', 'Fields not read yet');
    if (s.issues) return chip('high', plural(s.issues, 'issue'));
    if (s.awaiting_review) return chip('medium', `${s.awaiting_review} to review`);
    return chip('low', 'Reviewed');
}

async function loadList() {
    const mine = ctx;
    let docs;
    try {
        docs = await API.documents(mine.alert.customer_id);
    } catch (error) {
        if (mine.current()) render('#case-doc-list', html`<li>${failed('Documents')}</li>`);
        return;
    }
    if (!mine.current()) return;
    render('#case-doc-list', docs.length ? list(docs, (d) => html`
        <li><button type="button" class="case-docs__item" data-doc="${d.id}">
            <i class="far fa-file-lines" aria-hidden="true"></i>
            <span class="case-docs__text"><strong>${d.filename}</strong><small>${TYPES[d.doc_type] || d.doc_type} · ${plural(d.page_count, 'page')} · uploaded ${date(d.uploaded_at)}${d.alert_id === mine.alert.id ? ' · for this case' : ''}</small></span>
            ${state(d)}</button></li>`) : html`<li>${empty('No documents uploaded for this customer.')}</li>`);
}

// ── Review dialog ────────────────────────────────────────────────────────

function pages() {
    if (!doc.pages.length) {
        return html`<p class="muted">${doc.text_status === 'NEEDS_OCR'
            ? 'This looks like a scanned document. Reading scanned images is not set up yet, so check its fields by hand from the original.'
            : 'The text of this document could not be read.'}</p>`;
    }
    return list(doc.pages, (p) => html`<div class="doc-page" id="doc-page-${p.page_number}"><span class="doc-page__no">Page ${p.page_number}</span>
        <pre>${p.text || raw('<em>No text on this page</em>')}</pre></div>`);
}

function fields() {
    if (!doc.extractions.length) {
        return html`<p class="muted">${doc.text_status !== 'EXTRACTED' ? 'Nothing can be read from this document automatically.'
            : doc.extracted_at ? 'None of the expected fields were found in this document.'
                : 'Select "Read fields" to read the fields for this document type and check them against the customer record.'}</p>`;
    }
    const mayReview = can('documents.manage');
    return html`
        ${doc.extractions.some((e) => e.extracted_by === 'mock') ? html`<p class="case-note">Read by the built-in reader, which only finds lines written as "Label: value". It is not an AI model.</p>` : ''}
        ${list(doc.extractions, (e) => {
            const [tone, text] = CHECK[e.check_status] || CHECK.NOT_CHECKED;
            const done = e.status !== 'PROPOSED';
            return html`<div class="doc-field ${e.status === 'REJECTED' ? 'is-rejected' : ''}" data-field="${e.id}">
                <div class="doc-field__head"><strong>${label(e.field)}</strong>${chip(tone, text)}
                    ${e.quote_verified ? '' : chip('high', 'Not found in document', 'This value is not in the document text')}
                    ${e.page_number ? html`<button type="button" class="link-btn" data-action="doc-cite" data-field="${e.id}">Page ${e.page_number}</button>` : ''}</div>
                <input type="text" class="form-control form-control-sm" value="${e.value}" ${done || !mayReview ? 'disabled' : ''} aria-label="${label(e.field)}">
                ${e.record_value || e.check_detail ? html`<p class="doc-field__detail">${e.record_value ? html`On record: <strong>${e.record_value}</strong>. ` : ''}${e.check_detail || ''}</p>` : ''}
                <div class="doc-field__actions">${done ? html`<small class="muted">${label(e.status)}${e.applied_to_record ? ', customer record updated' : ''}</small>`
                    : !mayReview ? html`<small class="muted">Awaiting review</small>` : html`
                    ${e.can_apply && e.check_status !== 'MATCH' ? html`<label class="form-check"><input type="checkbox" class="form-check-input" data-apply> <span class="form-check-label">Update the customer record</span></label>` : ''}
                    <button type="button" class="btn btn-quiet btn-sm" data-action="doc-decide" data-decision="REJECTED">Reject</button>
                    <button type="button" class="btn btn-primary btn-sm" data-action="doc-decide" data-decision="ACCEPTED">Accept</button>`}</div>
            </div>`;
        })}`;
}

function showReview() {
    $('#doc-review [data-pages]').html(String(pages()));
    $('#doc-review [data-fields]').html(String(fields()));
}

async function openReview(id) {
    try { doc = await API.document(id); } catch (error) { toast('error', error.message); return; }
    $('#doc-review').remove();
    const $el = $(String(html`
        <div class="modal fade" id="doc-review" tabindex="-1" aria-labelledby="doc-review-title" aria-hidden="true">
            <div class="modal-dialog modal-dialog-centered modal-xl modal-dialog-scrollable"><div class="modal-content">
                <div class="modal-header"><div><h2 class="modal-title" id="doc-review-title">${doc.filename}</h2>
                    <small class="muted">${TYPES[doc.doc_type] || doc.doc_type} · ${ctx.customer.full_name || ''}</small></div>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
                <div class="modal-body"><div class="doc-review">
                    <section aria-label="Document text"><h3 class="doc-review__title">Document text</h3><div data-pages></div></section>
                    <section aria-label="What was read"><h3 class="doc-review__title">What was read from it</h3><div data-fields></div></section>
                </div></div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-quiet" data-bs-dismiss="modal">Close</button>
                    <button type="button" class="btn btn-quiet" data-action="doc-download"><i class="fas fa-file-arrow-down me-2" aria-hidden="true"></i>Download original</button>
                    ${doc.text_status === 'EXTRACTED' && can('documents.manage') ? html`<button type="button" class="btn btn-primary" data-action="doc-extract">${doc.extracted_at ? 'Read fields again' : 'Read fields'}</button>` : ''}
                </div></div></div></div>`));
    $('body').append($el);
    // The dialog lives outside the page root, so it carries its own handlers
    $el.on('click', '[data-action=doc-cite]', function () { cite(this.dataset.field); })
        .on('click', '[data-action=doc-decide]', function () { decide($(this)); })
        .on('click', '[data-action=doc-extract]', function () { extract($(this)); })
        .on('click', '[data-action=doc-download]', () => API.downloadOriginal(doc).catch((error) => toast('error', error.message)))
        .on('hidden.bs.modal', () => { $el.remove(); modal = null; loadList(); });
    showReview();
    modal = new bootstrap.Modal($el[0]);
    modal.show();
}

/** Scroll to the page a value came from and mark the text it was read from. */
function cite(id) {
    const e = doc.extractions.find((x) => x.id === id);
    const page = e && window.document.getElementById(`doc-page-${e.page_number}`);
    if (!page) return;
    const text = doc.pages.find((p) => p.page_number === e.page_number).text || '';
    const needle = e.source_quote && text.includes(e.source_quote) ? e.source_quote : e.value;
    const at = text.indexOf(needle);
    showReview();
    if (at >= 0) {
        $(`#doc-page-${e.page_number} pre`).html(String(html`${text.slice(0, at)}<mark>${needle}</mark>${text.slice(at + needle.length)}`));
    }
    window.document.getElementById(`doc-page-${e.page_number}`).scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function extract($button) {
    $button.prop('disabled', true).text('Reading…');
    try {
        doc = await API.extract(doc.id);
        showReview();
        toast('success', `${plural(doc.extractions.length, 'field')} read from the document.`);
    } catch (error) { toast('error', error.message); }
    $button.prop('disabled', false).text('Read fields again');
}

async function decide($button) {
    const $field = $button.closest('[data-field]');
    const e = doc.extractions.find((x) => x.id === $field.data('field'));
    const decision = $button.data('decision');
    const value = $field.find('input[type=text]').val().trim();
    if (decision === 'ACCEPTED' && !value) { toast('error', 'The value cannot be empty.'); return; }
    const payload = { decision, apply_to_record: decision === 'ACCEPTED' && $field.find('[data-apply]').is(':checked') };
    if (decision === 'ACCEPTED' && value !== e.value) payload.value = value;
    $field.find('button').prop('disabled', true);
    try {
        Object.assign(e, await API.reviewExtraction(e.id, payload));
        showReview();
        if (e.applied_to_record) toast('success', 'Customer record updated.');
    } catch (error) {
        toast('error', error.message);
        $field.find('button').prop('disabled', false);
    }
}

export default {
    render: view,
    load(c) { ctx = c; loadList(); },
    unload() { if (modal) modal.hide(); },
    handlers: {
        'click [data-doc]': function () { openReview(this.dataset.doc); },
        'submit [data-form=upload]': async function (event) {
            event.preventDefault();
            const file = this.file.files[0];
            if (!file) { toast('error', 'Choose a file to upload.'); return; }
            const form = new FormData();
            form.append('customer_id', ctx.alert.customer_id);
            form.append('doc_type', this.type.value);
            form.append('alert_id', ctx.alert.id);
            form.append('file', file);
            const $button = $(this).find('button').prop('disabled', true);
            try {
                await API.upload(form);
                toast('success', 'Document uploaded.');
                this.file.value = '';
                loadList();
                ctx.refreshTimeline();
            } catch (error) { toast('error', error.message); }
            $button.prop('disabled', false);
        },
    },
};
