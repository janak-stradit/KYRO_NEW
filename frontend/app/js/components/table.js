/**
 * components/table.js — Table head, loading and empty rows, and the pagination footer.
 */
import { html, list } from '../core/dom.js';
import { number } from '../core/format.js';

/** columns: [{ label, className, title }] */
export const head = (columns) => html`<tr>${list(columns, (c) => html`<th class="${c.className || ''}" title="${c.title || ''}">${c.label || ''}${c.hidden ? html`<span class="visually-hidden">${c.hidden}</span>` : ''}</th>`)}</tr>`;

export function loadingRows(columns, rows = 8) {
    return list(Array.from({ length: rows }), () => html`<tr>${list(columns, () => html`<td><span class="skeleton"></span></td>`)}</tr>`);
}

export const emptyRow = (span, title, text, icon = 'fa-folder-open') =>
    html`<tr><td colspan="${span}"><div class="empty"><i class="fas ${icon}" aria-hidden="true"></i><strong>${title}</strong>${text}</div></td></tr>`;

/** Footer: rows per page, position, previous/next. Buttons carry data-page / data-size for the page to handle. */
export function pager({ page, size, total, sizes = [25, 50, 100] }) {
    const pages = Math.max(1, Math.ceil(total / size));
    const from = total ? (page - 1) * size + 1 : 0;
    const to = Math.min(page * size, total);
    return html`
        <div class="dt-foot">
            <label>Rows per page
                <select class="form-select form-select-sm" data-size aria-label="Rows per page">
                    ${list(sizes, (n) => html`<option value="${n}" ${n === size ? 'selected' : ''}>${n}</option>`)}
                </select></label>
            <span>${number(from)}–${number(to)} of ${number(total)}</span>
            <span>
                <button type="button" class="btn btn-quiet btn-sm" data-page="${page - 1}" ${page <= 1 ? 'disabled' : ''}>Previous</button>
                <button type="button" class="btn btn-quiet btn-sm" data-page="${page + 1}" ${page >= pages ? 'disabled' : ''}>Next</button>
            </span>
        </div>`;
}
