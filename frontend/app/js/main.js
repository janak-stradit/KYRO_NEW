/**
 * main.js — Start the app: check the session, draw the shell, start routing.
 */
import { ROUTES } from './config/routes.js';
import { renderShell, markActive } from './components/shell.js';
import { api } from './core/api.js';
import { session } from './core/auth.js';
import { start } from './core/router.js';

async function boot() {
    if (!session.signedIn()) return session.expire();
    try {
        session.setUser(await api.get('/auth/me'));  // fresh role and permissions
    } catch (error) {
        if (error.status === 401) return undefined;  // api.js has already sent the user to sign in
    }
    renderShell(ROUTES);
    await start(ROUTES, { onRouteChange: markActive });
}

boot();
