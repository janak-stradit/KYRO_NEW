# KYRO Frontend — Architecture and Rewrite Plan

**Decision:** keep HTML, jQuery and Bootstrap (no framework, no build step), but replace the single-page
script pile in `frontend/phase3/` with a modular application in `frontend/app/`. Full rewrite; switch over when
every page is done.

## 1. Why

`frontend/phase3/index.html` loads 36 `<script>` tags of global objects (`Cases`, `CaseDetail`, `Auth`, …),
~23,600 lines of JS and CSS. Pages build HTML from template strings and call `escapeHtml` by hand; every
release bumps `?v=` numbers by hand; state, timers and event handlers leak between pages; there is no shared
component layer, so the same table, badge and modal are written again on every page.

## 2. Principles

1. **Native ES modules.** `<script type="module">`, `import`/`export`. Every browser KYRO supports runs them; no
   bundler, no Node toolchain.
2. **Escaped by default.** All markup goes through the `html` tagged template (`core/dom.js`): values are escaped
   unless explicitly wrapped in `raw()`. No hand-written `escapeHtml` calls in pages.
3. **One page, one folder.** A page owns its logic, templates, API calls and CSS.
4. **Pages have a lifecycle.** `mount(root, ctx)` and `unmount()`; the router calls `unmount` before the next page,
   so timers and handlers never leak.
5. **Components are functions.** A component returns markup (`render(props)`) and, if it is interactive, binds its
   behaviour with `bind(root, handlers)`. No global component registry.
6. **Design tokens.** Colours, spacing, radii and type are CSS custom properties in `css/tokens.css`; components and
   pages use the tokens, never raw hex values.
7. **Permissions in one place.** Routes declare the permission they need; navigation and page guards read it.

## 3. Layout

```
frontend/app/
├── index.html                 shell only: header, nav, <main id="view">, vendor scripts, js/main.js
├── login.html                 sign-in page (module: js/pages/login/login.js)
├── css/
│   ├── tokens.css             design tokens (colour, space, radius, type, shadow)
│   ├── base.css               reset, typography, focus, utilities
│   ├── layout.css             app shell, top navigation, page header, grid
│   ├── components.css         button, tag, badge, tabs, card, table, form, modal, toast, skeleton, empty, stage
│   └── pages.css              page styles, each scoped under .page-<name>
├── js/
│   ├── main.js                boot: session check, shell, router start
│   ├── config/
│   │   └── routes.js          path → page module (lazy import), title, permission, nav label/group
│   ├── core/
│   │   ├── api.js             fetch wrapper: base URL, auth header, token refresh, JSON, errors
│   │   ├── auth.js            session, current user, can(...permissions)
│   │   ├── router.js          history routing, params, guards, page lifecycle
│   │   ├── dom.js             html`` (auto-escaping), raw(), mount(), delegated events with namespaces
│   │   ├── format.js          dates, numbers, age, human labels
│   │   └── feedback.js        toasts and dialogs (Bootstrap modal with submit handling)
│   ├── config/rules.js        detection rule names, the rules shown with a marker
│   ├── components/
│   │   ├── shell.js           top bar, navigation filtered by permission, user menu
│   │   ├── tabs.js            view tabs with counts
│   │   ├── table.js           head, loading rows, empty row, pagination footer
│   │   └── cells.js           score, status, stage, person, owner, tags
│   └── pages/
│       ├── cases/             cases.js (page and handlers), cases.views.js (markup), cases.api.js (calls)
│       ├── case/              case.js (frame and tabs), case.views.js, case.api.js, case.dialogs.js, case-report.js, sections/
│       ├── dashboard/  rules/  process/  admin/  regulations/  feeds/  patterns/  periodic-reviews/  profile/
│       └── login/
└── assets/                    logo, favicon
```

## 4. Contracts

**Route** (`config/routes.js`):
```js
{ path: '/cases', title: 'Review Cases', permission: ['cases.view'], nav: 'Review Cases',
  load: () => import('../pages/cases/cases.js') }
```

**Page module** (`pages/<name>/<name>.js`):
```js
export default {
  async mount(root, { params, query, navigate }) { /* render, bind, load data */ },
  unmount() { /* clear timers, remove namespaced handlers */ },
};
```

**Component**:
```js
export function render(props) { return html`...`; }
export function bind(root, handlers) { /* delegated events */ }
```

## 5. Conventions

- Files and CSS classes in kebab-case; page CSS is scoped under `.page-<name>`.
- No inline styles; no colours outside `tokens.css`.
- Event handlers are delegated from the page root with a namespace (`.page-cases`), removed in `unmount`.
- API calls live in `<page>.api.js` (or `core/api.js` for shared ones); templates in `<page>.views.js`.
- Accessibility: every control has a label; tabs, tables and dialogs use the right roles; focus is visible;
  `prefers-reduced-motion` is respected.

## 6. Serving

- During the rewrite the new app is served at **`/next/`** next to the current app (`FRONTEND_NEXT_PREVIEW=true`).
  It uses the same API and the same sign-in token, so both can be compared side by side.
- At switch-over `SERVE_FRONTEND_DIR` (and the nginx `root`) points to `frontend/app`, `/next/` is removed and
  `frontend/phase3` is deleted.

## 7. Order of work

| # | Scope | Notes |
|---|---|---|
| 1 | Core, tokens, components, shell, login, routing | the foundation every page uses |
| 2 | Review Cases | reference page: views, filters, table, stage, bulk assign |
| 3 | Case page | the largest page; split into sections (summary, timeline, investigation, customer file) |
| 4 | Dashboard, Rules, How KYRO works | |
| 5 | Administration (users, roles, access requests, audit, teams and routing) | |
| 6 | Regulations, Data Feeds, Patterns, Periodic Reviews, Profile, Kyro Chat | |
| 7 | Switch-over | parity checklist per page, screenshots, remove phase3 |

## 8. Switch-over checklist (per page)

- Every action of the old page exists, with the same permission checks.
- Loading, empty and error states.
- Keyboard and screen-reader check; reduced motion.
- Screenshot compared at 1440 px and 1024 px.
- No console errors; no `escapeHtml` or global objects.

## 9. Progress

| Step | Status |
|---|---|
| 1. Core, tokens, components, shell, sign-in, routing | Done: `/next/` serves the new app; one sign-in works for both apps |
| 2. Review Cases | Done: views with counts, by customer / by alert, filters, search, pagination, stage, assign one / all for a customer / selected |
| | Not yet: resolve and export from the list (both move to the case page, where the decision is taken) |
| 3. Case page | Done: header with key facts, SAR deadlines and stage tracker (sticky, condensed on scroll); tabs Overview, Activity, Investigation, Customer file (`?tab=` in the address); assign; record decision (outcome, reasons, what happens next, potential SAR); AI summary check; QA; notes, requests, narrative versions; documents with page citations; screening decisions; printable report at `/cases/:id/report` (print or save as PDF, or JSON) replacing the jsPDF export |
| | Each tab is filled by sections (`pages/case/sections/*.js`): a section renders its markup, loads its own data and declares its handlers; the page binds them under one namespace |
| 4–7 | To do; pages not rebuilt yet show a placeholder linking to the current app |

Customer codes such as "CUST-152" are not shown: the previous frontend invented them by numbering up to 10,000
customers in load order, which was slow and not stable between days.
