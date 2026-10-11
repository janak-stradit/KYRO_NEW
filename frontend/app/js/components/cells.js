/**
 * components/cells.js — The small pieces tables are made of: score, status, stage, person, tags.
 */
import { html, list } from '../core/dom.js';
import { human, initials } from '../core/format.js';

export const band = (score) => (score >= 80 ? 'high' : score >= 60 ? 'medium' : 'low');

export const score = (value, title = '') => html`<span class="score score--${band(value)}" title="${title}">${value ?? '—'}</span>`;

const STATUS = { OPEN: ['open', 'Open'], ASSIGNED: ['assigned', 'Assigned'], IN_REVIEW: ['review', 'In review'],
    ESCALATED: ['mlro', 'With the MLRO'], RESOLVED: ['closed', 'Closed'] };

export function status(code, label) {
    const [tone, text] = STATUS[code] || ['open', human(code)];
    return html`<span class="status status--${tone}">${label || text}</span>`;
}

const STATE_WORDS = { done: 'done', current: 'now', skipped: 'skipped', todo: 'to come' };

/** Five short segments for the case's stages, and where it is now. */
export function stage(stages, label) {
    if (!stages || !stages.length) return html`<span class="muted">—</span>`;
    const title = stages.map((s) => `${s.label}: ${STATE_WORDS[s.state]}`).join(' · ');
    return html`<div class="stage" title="${title}">
        <div class="stage__bar" aria-hidden="true">${list(stages, (s) => html`<i class="stage__seg stage__seg--${s.state}"></i>`)}</div>
        <span class="stage__label">${label || 'Complete'}</span><span class="visually-hidden">${title}</span></div>`;
}

export function person(name, meta = '', { small = false } = {}) {
    return html`<div class="person"><span class="avatar ${small ? 'avatar--sm' : ''}" aria-hidden="true">${initials(name)}</span>
        <span><span class="person__name">${name}</span>${meta ? html`<span class="person__meta">${meta}</span>` : ''}</span></div>`;
}

export function owner(names) {
    if (!names || !names.length) return html`<span class="muted">Unassigned</span>`;
    return names.length === 1 ? person(names[0], '', { small: true }) : html`<span class="muted">${names.length} people</span>`;
}

/** Up to `max` tags; marked ones get a small red dot; the rest are summarised as "+N". */
export function tags(items, { max = 2, marked = () => false, title = '' } = {}) {
    if (!items.length) return html`<span class="muted">None recorded</span>`;
    const shown = items.slice(0, max);
    return html`<div class="tags" title="${title}">
        ${list(shown, (t) => html`<span class="tag">${marked(t) ? html`<i class="tag__dot" aria-hidden="true"></i>` : ''}${t.label}${t.count ? html`<b>${t.count}</b>` : ''}</span>`)}
        ${items.length > max ? html`<span class="tag">+${items.length - max}</span>` : ''}</div>`;
}
