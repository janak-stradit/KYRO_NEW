/**
 * core/api.js — The one way to call the KYRO API.
 *
 * Adds the bearer token, refreshes it once on a 401, parses JSON and turns failures
 * into an ApiError with the server's message. Callers decide what to tell the user.
 */
import { session } from './auth.js';

const BASE = '/api/v1';

export class ApiError extends Error {
    constructor(status, message, detail) {
        super(message);
        this.status = status;
        this.detail = detail;
    }
}

function messageOf(status, body) {
    const detail = body && body.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((d) => String(d.msg || '').replace(/^Value error, /, '')).join(' ');
    if (status === 0) return 'Cannot reach the server. Check your connection.';
    if (status === 403) return 'Your role cannot do this.';
    if (status === 404) return 'Not found.';
    if (status >= 500) return 'The server had a problem. Try again in a moment.';
    return 'The request failed.';
}

async function send(method, path, { body, query, timeout = 30000, retry = true } = {}) {
    const url = new URL(BASE + path, window.location.origin);
    Object.entries(query || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v); });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    let response;
    try {
        response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json', ...(session.token() ? { Authorization: `Bearer ${session.token()}` } : {}) },
            body: body === undefined ? undefined : JSON.stringify(body),
            signal: controller.signal,
        });
    } catch (error) {
        throw new ApiError(0, error.name === 'AbortError' ? 'The server took too long to answer.' : messageOf(0));
    } finally {
        clearTimeout(timer);
    }
    if (response.status === 401 && retry && path !== '/auth/refresh' && (await session.refresh())) {
        return send(method, path, { body, query, timeout, retry: false });
    }
    if (response.status === 401) {
        session.expire();
        throw new ApiError(401, 'Your session has ended. Sign in again.');
    }
    const text = await response.text();
    const data = text ? JSON.parse(text) : null;
    if (!response.ok) throw new ApiError(response.status, messageOf(response.status, data), data && data.detail);
    return data;
}

export const api = {
    get: (path, query, options) => send('GET', path, { ...options, query }),
    post: (path, body, options) => send('POST', path, { ...options, body }),
    put: (path, body, options) => send('PUT', path, { ...options, body }),
    delete: (path, options) => send('DELETE', path, options),
    /** For calls that wait on the AI model or long replays. */
    slow: (method, path, body) => send(method, path, { body, timeout: 180000 }),
};
