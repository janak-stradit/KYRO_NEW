/**
 * core/dom.js — Markup that is escaped by default.
 *
 *   html`<td>${customer.name}</td>`   → the name is escaped
 *   html`<td>${raw(trustedMarkup)}</td>` → inserted as is (only for markup built with html``)
 *
 * html`` returns a SafeHtml; nesting html`` inside html`` keeps it unescaped, and arrays are joined.
 */

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export class SafeHtml {
    constructor(value) { this.value = value; }
    toString() { return this.value; }
}

export const raw = (markup) => new SafeHtml(String(markup ?? ''));

export function escape(value) {
    if (value === null || value === undefined || value === false) return '';
    if (value instanceof SafeHtml) return value.value;
    if (Array.isArray(value)) return value.map(escape).join('');
    return String(value).replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

export function html(strings, ...values) {
    let out = strings[0];
    values.forEach((value, i) => { out += escape(value) + strings[i + 1]; });
    return new SafeHtml(out);
}

/** Replace an element's content with markup built by html``. */
export function render(target, markup) {
    $(target).html(String(markup));
}

/** Join items rendered by fn, or show `empty` when there are none. */
export function list(items, fn, empty = '') {
    return items && items.length ? raw(items.map((item, i) => String(fn(item, i))).join('')) : (empty instanceof SafeHtml ? empty : html`${empty}`);
}

/** Delegated events bound under a namespace, so a page can remove all of its handlers at once. */
export function on(root, namespace, events) {
    const $root = $(root);
    Object.entries(events).forEach(([key, handler]) => {
        const [type, ...selector] = key.split(' ');
        $root.on(`${type}.${namespace}`, selector.join(' ') || null, handler);
    });
    return () => $root.off(`.${namespace}`);
}
