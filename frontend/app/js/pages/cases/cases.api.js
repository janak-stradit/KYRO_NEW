/**
 * pages/cases/cases.api.js — What the work queue reads and changes.
 */
import { api } from '../../core/api.js';

export const summary = () => api.get('/alerts/queue/summary');

/** One row per customer (unresolved alerts only). */
export const byCustomer = (filters, page, size) => api.get('/alerts/queue/customers', {
    page, page_size: size, sort: filters.sort, q: filters.q, risk: filters.risk, rule: filters.rule,
    assignment: filters.assignment, attention: filters.attention,
});

/** One row per alert. */
export const byAlert = (filters, page, size) => api.get('/alerts/queue', {
    page, page_size: size, sort: filters.sort, status_filter: filters.status, q: filters.q, risk: filters.risk, rule: filters.rule,
    assignment: filters.assignment, attention: filters.attention, customer_id: filters.customerId,
});

export const assignees = () => api.get('/alerts/assignees');

export const assign = (alertId, userId) => api.put(`/alerts/${alertId}/assign`, { assigned_to: userId });

/** Several alerts, or every unresolved alert of one customer. */
export const bulkAssign = ({ alertIds, customerId }, userId) =>
    api.put('/alerts/bulk-assign', { assigned_to: userId, alert_ids: alertIds || [], customer_id: customerId || null });
