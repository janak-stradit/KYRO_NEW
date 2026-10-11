/**
 * core/router.js — Client-side routing with a page lifecycle.
 *
 * Routes (config/routes.js) map a path such as /cases/:id to a page module loaded on
 * first use. Before showing a page the router unmounts the current one, so its
 * timers and handlers go with it. Internal links are plain <a href="/cases"> elements.
 */
import { can } from './auth.js';
import { html, render } from './dom.js';

const BASE = window.APP_BASE || '';
let routes = [];
let current = null;  // { route, page }
let onChange = () => {};

function compile(path) {
    const keys = [];
    const pattern = path.replace(/:([a-zA-Z]+)/g, (_, key) => { keys.push(key); return '([^/]+)'; });
    return { regex: new RegExp(`^${pattern}/?$`), keys };
}

function match(pathname) {
    const path = pathname.startsWith(BASE) ? pathname.slice(BASE.length) || '/' : pathname;
    for (const route of routes) {
        const m = route.compiled.regex.exec(path);
        if (m) return { route, params: Object.fromEntries(route.compiled.keys.map((k, i) => [k, decodeURIComponent(m[i + 1])])) };
    }
    return null;
}

export const href = (path) => `${BASE}${path}`;

export function navigate(path, { replace = false } = {}) {
    const url = href(path);
    if (replace) window.history.replaceState({}, '', url); else window.history.pushState({}, '', url);
    return show();
}

function message(title, text) {
    return html`<div class="page-message"><h1>${title}</h1><p>${text}</p><a class="btn btn-primary" href="${href('/cases')}">Go to Review Cases</a></div>`;
}

async function show() {
    const view = document.getElementById('view');
    const found = match(window.location.pathname);
    if (current && current.page.unmount) current.page.unmount();
    current = null;
    window.scrollTo(0, 0);

    if (!found) {
        render(view, message('Page not found', 'The address does not match any page in KYRO.'));
        return onChange(null);
    }
    const { route, params } = found;
    if (!can(...(route.permission || []))) {
        render(view, message('Not available to your role', 'Ask an administrator if you need access to this page.'));
        return onChange(route);
    }
    document.title = `${route.title} · KYRO AML`;
    onChange(route);
    try {
        const page = (await route.load()).default;
        current = { route, page };
        view.className = `view page-${route.name}`;
        await page.mount(view, { params, query: Object.fromEntries(new URLSearchParams(window.location.search)), navigate });
    } catch (error) {
        console.error(error);
        render(view, message('This page could not load', error.message || 'Try again in a moment.'));
    }
}

export function start(routeTable, { onRouteChange } = {}) {
    routes = routeTable.map((r) => ({ ...r, compiled: compile(r.path) }));
    if (onRouteChange) onChange = onRouteChange;
    window.addEventListener('popstate', show);
    // Internal links navigate without reloading the page
    document.addEventListener('click', (event) => {
        const link = event.target.closest('a[href]');
        if (!link || link.target || link.hasAttribute('download') || event.metaKey || event.ctrlKey || event.shiftKey) return;
        const url = new URL(link.href, window.location.origin);
        if (url.origin !== window.location.origin || !url.pathname.startsWith(BASE || '/') || url.pathname.endsWith('.html')) return;
        if (!match(url.pathname)) return;
        event.preventDefault();
        navigate(url.pathname.slice(BASE.length) + url.search);
    });
    return show();
}

export const reload = () => show();
