/**
 * core/format.js — How numbers, dates and codes are shown everywhere.
 */
export const number = (n) => (n === null || n === undefined || Number.isNaN(Number(n)) ? '—' : Number(n).toLocaleString());

export const percent = (fraction) => (fraction === null || fraction === undefined ? '—' : `${Math.round(fraction * 100)}%`);

export const date = (value) => (value ? new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—');

export const dateTime = (value) => (value
    ? new Date(value).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '—');

/** "3 h", "4 d": how long ago, short. */
export function age(value) {
    if (!value) return '—';
    const hours = (Date.now() - new Date(value).getTime()) / 3600000;
    if (hours < 1) return '< 1 h';
    return hours < 48 ? `${Math.floor(hours)} h` : `${Math.floor(hours / 24)} d`;
}

/** "TRUE_POSITIVE_NO_SAR" → "True positive no SAR" */
export function human(code) {
    if (!code) return '';
    const text = String(code).replace(/_/g, ' ').toLowerCase();
    return (text.charAt(0).toUpperCase() + text.slice(1)).replace(/\b(sar|pep|kyc|mlro|aml|id|edd|qa)\b/gi, (w) => w.toUpperCase());
}

export function initials(name) {
    return String(name || '').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?';
}
