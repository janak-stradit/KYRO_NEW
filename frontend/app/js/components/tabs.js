/**
 * components/tabs.js — View tabs with counts. Each tab carries data-tab for the page to handle.
 */
import { html, list } from '../core/dom.js';
import { number } from '../core/format.js';

/** items: [{ key, label, count, alert, title }] */
export function tabs(items, active, label = 'Views') {
    return html`<div class="tabs" role="tablist" aria-label="${label}">
        ${list(items, (t) => html`<button type="button" class="tab ${t.key === active ? 'is-active' : ''}" role="tab"
            aria-selected="${t.key === active}" data-tab="${t.key}" title="${t.title || ''}">
            ${t.label}${t.count === undefined ? '' : html`<span class="tab__count ${t.alert && t.count ? 'tab__count--alert' : ''}">${number(t.count)}</span>`}
        </button>`)}
    </div>`;
}
