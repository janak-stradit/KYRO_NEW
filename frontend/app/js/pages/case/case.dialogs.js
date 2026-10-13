/**
 * pages/case/case.dialogs.js — Assign the case, and record a decision on it.
 */
import { can, session } from '../../core/auth.js';
import { html, list } from '../../core/dom.js';
import { human } from '../../core/format.js';
import { dialog, toast } from '../../core/feedback.js';
import { assignForm } from '../../components/assign-form.js';
import * as API from './case.api.js';
import { OUTCOME_PERMISSION } from './case.views.js';

export async function assign({ alert, customer }, done) {
    let people;
    try { people = await API.assignees(); } catch (error) { toast('error', error.message); return; }
    await dialog({
        title: 'Assign', submitLabel: 'Assign',
        body: assignForm(people, `The case for ${customer.full_name || 'this customer'}.`, (session.user() || {}).id, alert.assigned_to),
        onSubmit: async (form, close) => {
            if (!form.assignee.value) throw new Error('Choose a person.');
            await API.assign(alert.id, form.assignee.value);
            close(true);
            toast('success', 'Case assigned.');
            done();
        },
    });
}

/** What happens next, in plain words, for each outcome. */
const CONSEQUENCE = {
    FALSE_POSITIVE: 'The case closes. It goes to the quality-check sample, and the outcome trains the risk model.',
    TRUE_POSITIVE_NO_SAR: 'The case closes as suspicious activity that does not need a report. The customer may be re-rated.',
    SAR_FILED: 'The case closes with the filing reference. The customer is re-rated and the case is restricted to people who see SAR work.',
    ESCALATED: 'The case goes to the MLRO, who takes the decision. You can mark it as a potential SAR to start the decision clock.',
};

export async function decide({ alert, customer }, done) {
    let options;
    try { options = await API.resolutionOptions(); } catch (error) { toast('error', error.message); return; }
    const outcomes = options.outcomes.filter((o) => can(OUTCOME_PERMISSION[o.code]));
    if (!outcomes.length) { toast('error', 'Your role cannot record an outcome on this case.'); return; }
    const reasonLabel = Object.fromEntries(options.reasons.map((r) => [r.code, r.label]));

    const shown = dialog({
        title: 'Record decision', submitLabel: 'Save decision', size: 'modal-lg',
        body: html`
            <p class="muted">${customer.full_name || 'Customer'} · Case ${String(alert.id).slice(0, 8)}</p>
            <fieldset><legend class="field-label">Outcome</legend>
                <div class="decide-outcomes">${list(outcomes, (o) => html`<label class="decide-outcome">
                    <input type="radio" name="outcome" value="${o.code}" class="form-check-input">
                    <span><strong>${human(o.code)}</strong><small>${o.label}</small></span></label>`)}</div>
            </fieldset>
            <p class="decide-next" data-next hidden></p>
            <fieldset><legend class="field-label">Reasons</legend><div class="decide-reasons" data-reasons><p class="muted">Choose an outcome to see its reasons.</p></div></fieldset>
            <label class="form-check" data-show="ESCALATED" hidden><input class="form-check-input" type="checkbox" name="potential_sar">
                <span class="form-check-label">Potential SAR: starts the MLRO decision clock and the filing deadline, and restricts the case notes to the people who decide on SARs</span></label>
            <div data-show="SAR_FILED" hidden><label class="field-label" for="decide-ref">SAR/STR filing reference</label>
                <input type="text" class="form-control" id="decide-ref" name="sar_reference" maxlength="100"></div>
            <label class="field-label" for="decide-notes">Notes</label>
            <textarea class="form-control" id="decide-notes" name="notes" rows="4" maxlength="4000" placeholder="What was checked and why this outcome was chosen"></textarea>`,
        onSubmit: async (form, close) => {
            const outcome = form.outcome.value;
            const reasons = [...form.querySelectorAll('[name=reason]:checked')].map((el) => el.value);
            const notes = form.notes.value.trim();
            if (!outcome) throw new Error('Choose an outcome.');
            if (!reasons.length) throw new Error('Choose at least one reason.');
            if (!notes) throw new Error('Say what was checked and why.');
            if (outcome === 'ESCALATED') {
                await API.escalate(alert.id, { resolution_notes: notes, reasons, potential_sar: form.potential_sar.checked });
            } else {
                await API.resolve(alert.id, { outcome, reasons, resolution_notes: notes, sar_reference: form.sar_reference.value.trim() || null });
            }
            close(true);
            toast('success', outcome === 'ESCALATED' ? 'Case sent to the MLRO.' : 'Decision recorded. The case is closed.');
            done();
        },
    });

    // The dialog is in the document now: show the reasons and fields for the chosen outcome
    const $form = $('.modal:last form');
    $form.on('change', '[name=outcome]', function () {
        const outcome = outcomes.find((o) => o.code === this.value);
        $form.find('[data-next]').prop('hidden', false).text(CONSEQUENCE[outcome.code] || '');
        $form.find('[data-show]').each((_, el) => { el.hidden = el.dataset.show !== outcome.code; });
        $form.find('[data-reasons]').html(String(list(outcome.reasons, (code) => html`<label class="form-check">
            <input class="form-check-input" type="checkbox" name="reason" value="${code}"><span class="form-check-label">${reasonLabel[code] || human(code)}</span></label>`)));
    });
    await shown;
}
