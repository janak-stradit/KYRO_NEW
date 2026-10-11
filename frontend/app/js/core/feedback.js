/**
 * core/feedback.js — Toasts and dialogs.
 */
import { html, raw } from './dom.js';

function region() {
    let el = document.getElementById('toasts');
    if (!el) {
        el = document.createElement('div');
        el.id = 'toasts';
        el.className = 'toasts';
        el.setAttribute('aria-live', 'polite');
        document.body.appendChild(el);
    }
    return el;
}

/** toast('success' | 'error' | 'info', message) */
export function toast(kind, message, duration = 4500) {
    const el = $(String(html`<div class="toast-item toast-item--${kind}" role="${kind === 'error' ? 'alert' : 'status'}">
        <span>${message}</span><button type="button" class="toast-item__close" aria-label="Dismiss">×</button></div>`));
    $(region()).append(el);
    const close = () => el.addClass('is-leaving').delay(200).queue(() => el.remove());
    el.find('.toast-item__close').on('click', close);
    setTimeout(close, duration);
}

/**
 * Open a Bootstrap dialog. `body` is markup from html``; `onSubmit(form, close)` runs on the primary button.
 * Resolves when the dialog is closed.
 */
export function dialog({ title, body, submitLabel = 'Save', cancelLabel = 'Cancel', onSubmit, size = '' }) {
    const id = `dlg-${Date.now()}`;
    const $el = $(String(html`
        <div class="modal fade" id="${id}" tabindex="-1" aria-labelledby="${id}-title" aria-hidden="true">
            <div class="modal-dialog modal-dialog-centered ${size}">
                <form class="modal-content" novalidate>
                    <div class="modal-header"><h2 class="modal-title" id="${id}-title">${title}</h2>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
                    <div class="modal-body">${raw(String(body))}<p class="form-error" role="alert" hidden></p></div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-quiet" data-bs-dismiss="modal">${cancelLabel}</button>
                        ${onSubmit ? html`<button type="submit" class="btn btn-primary">${submitLabel}</button>` : ''}
                    </div>
                </form>
            </div>
        </div>`));
    $('body').append($el);
    const modal = new bootstrap.Modal($el[0]);
    return new Promise((resolve) => {
        const close = (result) => { modal.hide(); resolve(result); };
        $el.find('form').on('submit', async (event) => {
            event.preventDefault();
            const $button = $el.find('button[type=submit]').prop('disabled', true);
            try {
                await onSubmit($el.find('form')[0], close);
            } catch (error) {
                $el.find('.form-error').text(error.message || 'Could not save.').prop('hidden', false);
            }
            $button.prop('disabled', false);
        });
        $el.on('hidden.bs.modal', () => { $el.remove(); resolve(undefined); });
        modal.show();
    });
}
