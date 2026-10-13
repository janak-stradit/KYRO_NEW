/**
 * components/assign-form.js — The body of the "Assign" dialog: who the case goes to.
 */
import { html, list } from '../core/dom.js';
import { human } from '../core/format.js';

export function assignForm(people, subject, meId, currentId = null) {
    return html`
        <p class="muted">${subject}</p>
        <label class="field-label" for="assignee">Assign to</label>
        <select class="form-select" id="assignee" name="assignee" required>
            <option value="">Choose a person…</option>
            ${list(people, (p) => html`<option value="${p.id}" ${p.id === currentId ? 'selected' : ''}>${p.name}${p.id === meId ? ' (you)' : ''} · ${human(p.role)}</option>`)}
        </select>`;
}
