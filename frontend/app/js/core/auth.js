/**
 * core/auth.js — The signed-in user and what they may do.
 *
 * Uses the same storage keys as the previous frontend, so a sign-in works for both
 * during the rewrite. can() is the only permission check pages and components use.
 */
const KEYS = { token: 'access_token', refresh: 'refresh_token', user: 'user_data' };

function read(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
}

function write(key, value) {
    try { value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch (e) { /* storage blocked */ }
}

let refreshing = null;

export const session = {
    token: () => read(KEYS.token),

    user() {
        try { return JSON.parse(read(KEYS.user) || 'null'); } catch (e) { return null; }
    },

    signedIn() { return Boolean(this.token() && this.user()); },

    store({ access_token, refresh_token }, user) {
        write(KEYS.token, access_token);
        if (refresh_token) write(KEYS.refresh, refresh_token);
        if (user) write(KEYS.user, JSON.stringify(user));
    },

    setUser(user) { write(KEYS.user, JSON.stringify(user)); },

    /** One refresh at a time; true when a new access token was obtained. */
    refresh() {
        const token = read(KEYS.refresh);
        if (!token) return Promise.resolve(false);
        refreshing = refreshing || fetch('/api/v1/auth/refresh', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: token }),
        }).then(async (r) => {
            if (!r.ok) return false;
            const body = await r.json();
            write(KEYS.token, body.access_token);
            if (body.refresh_token) write(KEYS.refresh, body.refresh_token);
            return true;
        }).catch(() => false).finally(() => { refreshing = null; });
        return refreshing;
    },

    clear() { Object.values(KEYS).forEach((k) => write(k, null)); },

    /** The session ended: back to sign-in, then return here. */
    expire() {
        this.clear();
        const back = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.href = `${window.APP_BASE || ''}/login.html?next=${back}`;
    },
};

/** True when the user's role holds any of the permissions. */
export function can(...permissions) {
    const held = (session.user() || {}).permissions || [];
    return permissions.length === 0 || permissions.some((p) => held.includes(p));
}

export const isReadOnly = () => Boolean((session.user() || {}).read_only);
