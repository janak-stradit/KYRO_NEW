/**
 * pages/case/case.ui.js — Small pieces of markup shared by the case page's sections.
 */
import { html, list } from '../../core/dom.js';

/** A coloured label: tone is high, medium, low, info or muted. */
export const chip = (tone, text, title = '') => html`<span class="chip chip--${tone}" title="${title}">${text}</span>`;

export const empty = (text) => html`<p class="case-empty">${text}</p>`;

export const failed = (what) => html`<p class="case-empty case-empty--error"><i class="fas fa-triangle-exclamation" aria-hidden="true"></i> ${what} could not be loaded.</p>`;

export const lines = (n = 3) => html`<div class="case-loading" role="status" aria-label="Loading">${list(Array.from({ length: n }), () => html`<span class="skeleton"></span>`)}</div>`;

/** A card with a heading, an optional line under it and optional actions on the right. */
export const panel = ({ id = '', title, sub = '', actions = '', body = '', className = '' }) => html`
    <section class="card-x case-panel ${className}" ${id ? html`id="${id}"` : ''}>
        <header class="card-x__head"><div><h2 class="card-x__title">${title}</h2>${sub ? html`<p class="card-x__sub" data-sub>${sub}</p>` : ''}</div>
            ${actions ? html`<div class="case-panel__actions">${actions}</div>` : ''}</header>
        <div class="case-panel__body">${body}</div>
    </section>`;

/** label → value rows; rows whose value is empty are left out. */
export const facts = (rows) => html`<dl class="case-facts">${list(rows.filter((r) => r[1] !== undefined && r[1] !== null && r[1] !== ''),
    ([label, value]) => html`<div><dt>${label}</dt><dd>${value}</dd></div>`)}</dl>`;

export function money(amount, currency, digits = 2) {
    if (amount === null || amount === undefined) return '—';
    return `${Number(amount).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })} ${currency || ''}`.trim();
}

export const plural = (n, word, many = `${word}s`) => `${Number(n).toLocaleString()} ${n === 1 ? word : many}`;

/** "A, B, C and 3 more" */
export const names = (items, limit = 4) => items.slice(0, limit).join(', ') + (items.length > limit ? ` and ${items.length - limit} more` : '');

export const RISK_TONE = { HIGH: 'high', MEDIUM: 'medium', LOW: 'low' };
