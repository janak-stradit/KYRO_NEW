/**
 * pages/placeholder — Shown for pages not rebuilt yet in the new frontend.
 */
import { html, render } from '../../core/dom.js';

export function forLegacy(legacyPath) {
    return {
        mount(root, { params }) {
            const target = params.id ? `${legacyPath}?id=${encodeURIComponent(params.id)}` : legacyPath;
            render(root, html`
                <div class="page-message">
                    <h1>Not rebuilt yet</h1>
                    <p>This page is still being moved to the new frontend. Open it in the current app in the meantime.</p>
                    <a class="btn btn-primary" href="${target}">Open in the current app</a>
                </div>`);
        },
        unmount() {},
    };
}
