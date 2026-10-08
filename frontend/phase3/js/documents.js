/**
 * KYRO Documents - upload KYC documents for a customer and review what the
 * AI read from them. Each value shows the page it came from and how it
 * compares with KYRO's records; the analyst accepts, corrects or rejects it.
 */

const Documents = {
    TYPES: {
        ID_DOCUMENT: 'Identity document',
        PROOF_OF_ADDRESS: 'Proof of address',
        COMPANY_REGISTRY: 'Company registry extract',
        FINANCIAL_STATEMENT: 'Financial statement',
        SOURCE_OF_FUNDS: 'Source of funds letter',
        OTHER: 'Other'
    },
    CHECK: {
        MATCH: ['low', 'Matches record'],
        MISMATCH: ['high', 'Differs from record'],
        NOT_ON_RECORD: ['medium', 'Not on record'],
        EXPIRED: ['high', 'Expired'],
        NOT_CHECKED: ['muted', 'Not checked']
    },

    human(value) {
        return String(value || '').replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase());
    },

    /** List and upload control for one customer, inside `selector`. */
    async renderSection(selector, context) {
        this.context = context;
        this.selector = selector;
        $(selector).html(`
            <ul class="doc-list" id="docList"><li class="kd-skeleton"></li></ul>
            <form class="doc-upload" id="docUploadForm">
                <select class="form-select form-select-sm" id="docType" aria-label="Document type">
                    ${Object.entries(this.TYPES).map(([k, l]) => `<option value="${k}">${escapeHtml(l)}</option>`).join('')}
                </select>
                <input type="file" class="form-control form-control-sm" id="docFile" accept=".pdf,.docx,.txt" aria-label="Document file">
                <button type="submit" class="btn btn-sm rc-actions__view"><i class="fas fa-upload me-1"></i>Upload</button>
            </form>
            <p class="kx-note mt-2 mb-0">PDF, Word or text, up to 10 MB. Scanned images cannot be read yet.</p>
        `);
        $("#docUploadForm").on("submit", (e) => { e.preventDefault(); this.upload(); });
        $(selector).off("click.docs").on("click.docs", ".doc-open", (e) => {
            this.showReview($(e.currentTarget).data("id"));
        });
        await this.loadList();
    },

    async loadList() {
        let docs;
        try {
            docs = await API.get('/documents', { customer_id: this.context.customerId });
        } catch (error) {
            $("#docList").html('<li class="text-muted">Could not load documents.</li>');
            return;
        }
        $("#docList").html(docs.map(d => {
            const s = d.summary || {};
            let state;
            if (d.text_status !== 'EXTRACTED') state = `<span class="cd-chip cd-chip--medium">${d.text_status === 'NEEDS_OCR' ? 'Scanned, cannot be read yet' : 'Text could not be read'}</span>`;
            else if (!d.extracted_at) state = '<span class="cd-chip cd-chip--muted">Fields not read yet</span>';
            else if (s.issues) state = `<span class="cd-chip cd-chip--high">${s.issues} issue${s.issues === 1 ? '' : 's'}</span>`;
            else if (s.awaiting_review) state = `<span class="cd-chip cd-chip--medium">${s.awaiting_review} to review</span>`;
            else state = '<span class="cd-chip cd-chip--low">Reviewed</span>';
            return `
                <li>
                    <button type="button" class="doc-open" data-id="${escapeHtml(d.id)}">
                        <i class="far fa-file-lines" aria-hidden="true"></i>
                        <span class="doc-open__text">
                            <strong>${escapeHtml(d.filename)}</strong>
                            <small>${escapeHtml(this.TYPES[d.doc_type] || d.doc_type)} &middot; ${d.page_count} page${d.page_count === 1 ? '' : 's'} &middot; uploaded ${escapeHtml(formatDate(d.uploaded_at))}${this.context.alertId && d.alert_id === this.context.alertId ? ' &middot; for this case' : ''}</small>
                        </span>
                        ${state}
                    </button>
                </li>`;
        }).join('') || '<li class="text-muted" style="font-size: 13.5px;">No documents uploaded for this customer.</li>');
    },

    async upload() {
        const file = document.getElementById('docFile').files[0];
        if (!file) { showToast('warning', 'Choose a file to upload.'); return; }
        const form = new FormData();
        form.append('customer_id', this.context.customerId);
        form.append('doc_type', $("#docType").val());
        if (this.context.alertId) form.append('alert_id', this.context.alertId);
        form.append('file', file);

        const $btn = $("#docUploadForm button").prop("disabled", true);
        try {
            const response = await fetch(`${API.baseUrl}/documents`, {
                method: 'POST', headers: { Authorization: API.getHeaders().Authorization }, body: form
            });
            const body = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'The upload failed.');
            API.clearCache();  // the upload bypassed the API helper, which caches GET responses
            showToast('success', 'Document uploaded.');
            $("#docFile").val('');
            await this.loadList();
        } catch (error) {
            showToast('error', error.message);
        }
        $btn.prop("disabled", false);
    },

    // ── Review dialog ────────────────────────────────────────────────────

    async showReview(id) {
        let doc;
        try {
            doc = await API.get(`/documents/${id}`);
        } catch (error) { return; }
        this.doc = doc;

        $("#docReviewModal").remove();
        $("body").append(`
            <div class="modal fade" id="docReviewModal" tabindex="-1" aria-labelledby="docReviewTitle" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered modal-xl modal-dialog-scrollable">
                    <div class="modal-content kx-modal">
                        <div class="modal-header">
                            <div>
                                <h5 class="modal-title" id="docReviewTitle">${escapeHtml(doc.filename)}</h5>
                                <small class="text-muted">${escapeHtml(this.TYPES[doc.doc_type] || doc.doc_type)}${this.context && this.context.customerName ? ` &middot; ${escapeHtml(this.context.customerName)}` : ''}</small>
                            </div>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <div class="doc-review">
                                <section class="doc-review__text" aria-label="Document text">
                                    <div class="kx-label">Document text</div>
                                    <div id="docPages"></div>
                                </section>
                                <section class="doc-review__fields" aria-label="Extracted fields">
                                    <div class="kx-label">What was read from it</div>
                                    <div id="docFields"></div>
                                </section>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-primary" data-bs-dismiss="modal">Close</button>
                            <button type="button" class="btn btn-outline-primary" id="docDownload"><i class="fas fa-file-arrow-down me-2"></i>Download original</button>
                            ${doc.text_status === 'EXTRACTED' ? `<button type="button" class="btn btn-primary" id="docExtract">${doc.extracted_at ? 'Read fields again' : 'Read fields'}</button>` : ''}
                        </div>
                    </div>
                </div>
            </div>`);
        const modalEl = document.getElementById('docReviewModal');
        new bootstrap.Modal(modalEl).show();
        this.renderReview();

        $("#docExtract").on("click", async () => {
            const $btn = $("#docExtract").prop("disabled", true).text('Reading...');
            try {
                this.doc = await API.post(`/documents/${doc.id}/extract`);
                this.renderReview();
                showToast('success', `${this.doc.extractions.length} field${this.doc.extractions.length === 1 ? '' : 's'} read from the document.`);
            } catch (xhr) { /* API layer reports the reason (e.g. AI features are disabled) */ }
            $btn.prop("disabled", false).text('Read fields again');
        });
        $("#docDownload").on("click", async () => {
            try {
                const response = await fetch(`${API.baseUrl}/documents/${doc.id}/file`, { headers: { Authorization: API.getHeaders().Authorization } });
                if (!response.ok) throw new Error();
                downloadBlob(await response.blob(), doc.filename);
            } catch (error) { showToast('error', 'Could not download the file.'); }
        });
        $(modalEl).off("click.docs")
            .on("click.docs", ".doc-field__page", (e) => this.highlight($(e.currentTarget).data("id")))
            .on("click.docs", ".doc-decide", (e) => this.decide($(e.currentTarget)));
        $(modalEl).on("hidden.bs.modal", function() { setTimeout(() => $(this).remove(), 0); });
    },

    renderReview() {
        const doc = this.doc;
        $("#docPages").html(doc.pages.length ? doc.pages.map(p => `
            <div class="doc-page" id="docPage${p.page_number}">
                <span class="doc-page__no">Page ${p.page_number}</span>
                <pre>${escapeHtml(p.text) || '<em>No text on this page</em>'}</pre>
            </div>`).join('') : `<p class="text-muted">${doc.text_status === 'NEEDS_OCR'
                ? 'This looks like a scanned document. Reading scanned images (OCR) is not set up yet, so its fields have to be checked by hand from the original.'
                : 'The text of this document could not be read.'}</p>`);

        if (!doc.extractions.length) {
            $("#docFields").html(`<p class="text-muted">${doc.text_status !== 'EXTRACTED' ? 'Nothing can be read from this document automatically.'
                : doc.extracted_at ? 'None of the expected fields were found in this document.' : 'Select "Read fields" to have the fields for this document type read and checked against the customer record.'}</p>`);
            return;
        }
        const mock = doc.extractions.some(e => e.extracted_by === 'mock');
        $("#docFields").html((mock ? '<p class="fp-empty doc-mock">Read by the built-in mock reader, which only finds lines written as "Label: value". It is not an AI model.</p>' : '')
            + doc.extractions.map(e => {
                const [chip, label] = this.CHECK[e.check_status] || this.CHECK.NOT_CHECKED;
                const done = e.status !== 'PROPOSED';
                return `
                <div class="doc-field ${e.status === 'REJECTED' ? 'is-rejected' : ''}" data-id="${escapeHtml(e.id)}">
                    <div class="doc-field__head">
                        <span class="doc-field__name">${escapeHtml(this.human(e.field))}</span>
                        <span class="cd-chip cd-chip--${chip}">${label}</span>
                        ${e.quote_verified ? '' : '<span class="cd-chip cd-chip--high" title="This value is not in the document text">Not found in document</span>'}
                        ${e.page_number ? `<button type="button" class="doc-field__page" data-id="${escapeHtml(e.id)}">Page ${e.page_number}</button>` : ''}
                    </div>
                    <input type="text" class="form-control form-control-sm doc-field__value" value="${escapeHtml(e.value)}" ${done ? 'disabled' : ''} aria-label="${escapeHtml(this.human(e.field))}">
                    ${e.record_value || e.check_detail ? `<p class="doc-field__detail">${e.record_value ? `On record: <strong>${escapeHtml(e.record_value)}</strong>. ` : ''}${escapeHtml(e.check_detail || '')}</p>` : ''}
                    <div class="doc-field__actions">
                        ${done ? `<span class="text-muted">${escapeHtml(this.human(e.status))}${e.applied_to_record ? ', customer record updated' : ''}</span>` : `
                        ${e.can_apply && e.check_status !== 'MATCH' ? `<label class="doc-field__apply"><input type="checkbox" class="form-check-input doc-apply"> Update the customer record</label>` : ''}
                        <button type="button" class="btn btn-sm rc-actions__icon doc-decide" data-decision="REJECTED" title="Reject" aria-label="Reject ${escapeHtml(this.human(e.field))}"><i class="fas fa-xmark"></i></button>
                        <button type="button" class="btn btn-sm rc-actions__view doc-decide" data-decision="ACCEPTED">Accept</button>`}
                    </div>
                </div>`;
            }).join(''));
    },

    /** Scroll to the page a value came from and mark the line it was read from. */
    highlight(extractionId) {
        const e = this.doc.extractions.find(x => x.id === extractionId);
        const page = e && document.getElementById(`docPage${e.page_number}`);
        if (!page) return;
        const text = this.doc.pages.find(p => p.page_number === e.page_number).text;
        const needle = e.source_quote && text.includes(e.source_quote) ? e.source_quote : e.value;
        const at = text.indexOf(needle);
        $(".doc-page pre mark").each((_, m) => $(m).replaceWith(document.createTextNode(m.textContent)));
        if (at >= 0) {
            $(page).find("pre").html(`${escapeHtml(text.slice(0, at))}<mark>${escapeHtml(needle)}</mark>${escapeHtml(text.slice(at + needle.length))}`);
        }
        page.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    },

    async decide($btn) {
        const $field = $btn.closest(".doc-field");
        const extraction = this.doc.extractions.find(x => x.id === $field.data("id"));
        const decision = $btn.data("decision");
        const value = $field.find(".doc-field__value").val().trim();
        if (decision === 'ACCEPTED' && !value) { showToast('warning', 'The value cannot be empty.'); return; }
        const payload = { decision, apply_to_record: decision === 'ACCEPTED' && $field.find(".doc-apply").is(":checked") };
        if (decision === 'ACCEPTED' && value !== extraction.value) payload.value = value;

        $field.find("button").prop("disabled", true);
        try {
            const updated = await API.put(`/documents/extractions/${extraction.id}/review`, payload);
            Object.assign(extraction, updated);
            this.renderReview();
            if (updated.applied_to_record) showToast('success', 'Customer record updated.');
        } catch (xhr) {
            $field.find("button").prop("disabled", false);
        }
    }
};

window.Documents = Documents;
