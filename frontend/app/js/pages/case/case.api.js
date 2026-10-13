/**
 * pages/case/case.api.js — What the case page reads and changes.
 */
import { api } from '../../core/api.js';
import { session } from '../../core/auth.js';

// ── The case ─────────────────────────────────────────────────────────────
export const alert = (id) => api.get(`/alerts/${id}`);
export const timeline = (id) => api.get(`/alerts/${id}/timeline`);
export const deadlines = (id) => api.get(`/alerts/${id}/deadlines`);
export const basis = (codes) => api.get('/controls/basis', { codes: codes.join(',') });
export const assignees = () => api.get('/alerts/assignees');
export const assign = (id, userId) => api.put(`/alerts/${id}/assign`, { assigned_to: userId });
export const resolutionOptions = () => api.get('/alerts/resolution-options');
export const resolve = (id, body) => api.put(`/alerts/${id}/resolve`, body);
export const escalate = (id, body) => api.put(`/alerts/${id}/escalate`, body);
export const recordQa = (id, result, notes) => api.put(`/alerts/${id}/qa`, { result, notes: notes || null });

// ── Investigation ────────────────────────────────────────────────────────
export const addNote = (id, body) => api.post(`/alerts/${id}/notes`, { body });
export const requests = (id) => api.get(`/alerts/${id}/requests`);
export const addRequest = (id, body) => api.post(`/alerts/${id}/requests`, body);
export const closeRequest = (requestId, status, note) => api.put(`/alerts/requests/${requestId}`, { status, response_note: note || null });
export const writeSummary = (id) => api.slow('POST', `/alerts/${id}/summary`, {});
export const reviewSummary = (id, decision, text) => api.put(`/alerts/${id}/summary/review`, { decision, text, confirmed: decision !== 'REJECTED' });
export const narratives = (id) => api.get(`/alerts/${id}/narratives`);
export const draftNarrative = (id) => api.slow('POST', `/alerts/${id}/draft-narrative`, {});
export const saveNarrative = (id, text) => api.post(`/alerts/${id}/narratives`, { text, confirmed: true });

// ── The customer ─────────────────────────────────────────────────────────
export const customer = (id) => api.get(`/customers/${id}`);
export const riskProfile = (id) => api.get(`/customers/${id}/risk-profile`);
export const kycReviews = (id) => api.get(`/customers/${id}/kyc-reviews`);
export const caseHistory = (customerId, alertId) => api.get(`/customers/${customerId}/case-history`, { alert_id: alertId });
export const openAlerts = (customerId) => api.get('/alerts/queue', { customer_id: customerId, page_size: 6 });
export const activity = (id) => api.get(`/customers/${id}/activity`);
export const counterparties = (id) => api.get(`/customers/${id}/counterparties`);
export const transactions = (customerId) => api.get('/transactions', { customer_id: customerId, page_size: 500 });
export const accounts = (id) => api.get(`/customers/${id}/accounts-overview`);
export const owners = (id) => Promise.all([api.get(`/customers/${id}/beneficial-owners`), api.get(`/customers/${id}/beneficial-owners/summary`)]);
export const screeningMatches = (id) => api.get(`/customers/${id}/screening-matches`);
export const decideMatch = (matchId, decision, notes) => api.put(`/screening/${matchId}/decision`, { decision, notes });

// ── Documents ────────────────────────────────────────────────────────────
export const documents = (customerId) => api.get('/documents', { customer_id: customerId });
export const document = (id) => api.get(`/documents/${id}`);
export const extract = (id) => api.slow('POST', `/documents/${id}/extract`);
export const reviewExtraction = (id, payload) => api.put(`/documents/extractions/${id}/review`, payload);

/** Multipart upload: the JSON helper cannot send a file. */
export async function upload(form) {
    const response = await fetch('/api/v1/documents', { method: 'POST', headers: { Authorization: `Bearer ${session.token()}` }, body: form });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'The upload failed.');
    return body;
}

export async function downloadOriginal(doc) {
    const response = await fetch(`/api/v1/documents/${doc.id}/file`, { headers: { Authorization: `Bearer ${session.token()}` } });
    if (!response.ok) throw new Error('Could not download the file.');
    saveBlob(await response.blob(), doc.filename);
}

export function saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = Object.assign(window.document.createElement('a'), { href: url, download: filename });
    window.document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}
