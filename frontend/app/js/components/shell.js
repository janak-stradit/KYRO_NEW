/**
 * components/shell.js — Top bar: logo, navigation filtered by permission, user menu.
 */
import { can, session } from '../core/auth.js';
import { html, list, render } from '../core/dom.js';
import { human, initials } from '../core/format.js';
import { href, navigate } from '../core/router.js';

export function renderShell(routes) {
    const user = session.user() || {};
    const items = routes.filter((r) => r.nav && can(...(r.permission || [])));
    render('#shell', html`
        <header class="topbar">
            <a class="topbar__brand" href="${href('/cases')}" aria-label="KYRO AML home">
                <img src="${href('/assets/logo.svg')}" alt="" width="28" height="28"><span>KYRO</span><b>AML</b>
            </a>
            <nav class="topbar__nav" aria-label="Main">
                ${list(items, (r) => html`<a class="topbar__link" data-route="${r.name}" href="${href(r.path)}">${r.nav}</a>`)}
            </nav>
            <div class="topbar__user dropdown">
                <button type="button" class="topbar__avatar" data-bs-toggle="dropdown" aria-expanded="false" aria-label="Account menu">
                    ${initials(user.full_name || user.username)}
                </button>
                <div class="dropdown-menu dropdown-menu-end">
                    <div class="dropdown-header"><strong>${user.full_name || user.username || ''}</strong><br>${human(user.role)}</div>
                    <a class="dropdown-item" href="${href('/profile')}">My profile</a>
                    <a class="dropdown-item" href="/">Open the current app</a>
                    <button type="button" class="dropdown-item" data-action="sign-out">Sign out</button>
                </div>
            </div>
        </header>`);
    $('#shell').off('.shell').on('click.shell', '[data-action=sign-out]', () => {
        session.clear();
        window.location.href = href('/login.html');
    });
}

/** Mark the navigation item for the current route (a child route marks its parent). */
export function markActive(route) {
    const active = route ? (route.navParent || route.name) : null;
    $('.topbar__link').each((_, el) => {
        const on = el.dataset.route === active;
        el.classList.toggle('is-active', on);
        if (on) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
    });
}

export { navigate };
