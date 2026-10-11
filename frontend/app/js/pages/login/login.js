/**
 * pages/login — Sign in, then return to the page that asked for it.
 */
import { session } from '../../core/auth.js';

const BASE = window.APP_BASE || '';

function safeNext() {
    const next = new URLSearchParams(window.location.search).get('next') || '';
    // Only paths inside this app; never another site
    return next.startsWith(`${BASE}/`) && !next.startsWith('//') ? next : `${BASE}/cases`;
}

$('#login-form').on('submit', async (event) => {
    event.preventDefault();
    const $error = $('#login-error').prop('hidden', true);
    const $button = $('#login-form button[type=submit]').prop('disabled', true).text('Signing in…');
    try {
        const response = await fetch('/api/v1/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ username: $('#username').val().trim(), password: $('#password').val() }),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Sign-in failed.');
        session.store(body);
        const me = await fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${body.access_token}` } });
        session.setUser(await me.json());
        window.location.href = safeNext();
    } catch (error) {
        $error.text(error.message === 'Incorrect username or password' ? 'The username or password is not right.' : error.message).prop('hidden', false);
        $button.prop('disabled', false).text('Sign in');
    }
});
