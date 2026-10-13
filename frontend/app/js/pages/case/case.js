/**
 * pages/case — One case: why it fired, the customer, their activity, the investigation, the decision.
 *
 * The page loads the alert and the customer, draws the frame (header, key facts, stages, tabs)
 * and hands each tab to its sections (sections/*.js). A section renders its markup, loads its own
 * data, and declares its handlers; the page binds them all under one namespace and removes them
 * on unmount. A slow or failing section never holds up the others.
 */
import { on, render } from '../../core/dom.js';
import { reload as reloadPage } from '../../core/router.js';
import * as API from './case.api.js';
import * as Dialogs from './case.dialogs.js';
import * as V from './case.views.js';
import activity from './sections/activity.js';
import customerFile from './sections/customer-file.js';
import documents from './sections/documents.js';
import investigation, { loadTimeline } from './sections/investigation.js';
import overview from './sections/overview.js';

/** Which sections fill which tab, in order. */
const SECTIONS = [
    ['overview', overview],
    ['activity', activity],
    ['investigation', investigation],
    ['investigation', documents],
    ['file', customerFile],
];

let token = 0;
let off = () => {};
let tab = 'overview';

const settle = (promise) => promise.catch(() => null);

function showTab(name, { focus = false } = {}) {
    tab = V.TABS.some((t) => t.key === name) ? name : 'overview';
    V.TABS.forEach(({ key }) => {
        $(`#case-tab-${key}`).toggleClass('is-active', key === tab).attr({ 'aria-selected': key === tab, tabindex: key === tab ? 0 : -1 });
        $(`#case-pane-${key}`).prop('hidden', key !== tab);
    });
    if (focus) $(`#case-tab-${tab}`).trigger('focus');
    const url = new URL(window.location.href);
    if (tab === 'overview') url.searchParams.delete('tab'); else url.searchParams.set('tab', tab);
    window.history.replaceState(window.history.state, '', url);
    $('#case-top').removeClass('is-condensed');
    window.scrollTo({ top: 0 });
}

/** The context every section gets: the case, and ways to report back to the frame. */
function context(data) {
    const mine = token;
    const ctx = {
        ...data,
        current: () => mine === token,
        /** A tile on the Overview: value, the line under it, and whether it needs attention. */
        glance(key, value, note = '', alert = false) {
            if (!ctx.current()) return;
            const $tile = $(`#glance-${key}`).toggleClass('is-alert', Boolean(alert));
            $tile.find('strong').text(value);
            $tile.find('small').text(note || ' ');
        },
        /** The small number on a tab: things waiting there. */
        count(key, n) {
            if (ctx.current()) $(`#case-count-${key}`).text(n ? Number(n).toLocaleString() : '').prop('hidden', !n);
        },
        async refreshTimeline() {
            const data2 = await loadTimeline();
            if (!data2 || !ctx.current()) return;
            if (data2.stages) render('#case-stages', V.stages(data2.stages));
            if (data2.clock) render('#case-clock', V.clock(data2.clock));
        },
        reload: () => reloadPage(),
    };
    return ctx;
}

async function loadDeadlines(ctx) {
    let d;
    try { d = await API.deadlines(ctx.alert.id); } catch (error) { return; }
    if (ctx.current() && d.sar && d.sar.potential_sar) render('#case-sar', V.sarDeadlines(d.sar));
}

const pageHandlers = (ctx) => ({
    'click [data-tab]': function () { showTab(this.dataset.tab); },
    'keydown [role=tab]': function (event) {
        if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
        const keys = V.TABS.map((t) => t.key);
        const step = event.key === 'ArrowRight' ? 1 : keys.length - 1;
        showTab(keys[(keys.indexOf(tab) + step) % keys.length], { focus: true });
    },
    'click [data-action=assign]': () => Dialogs.assign(ctx, () => reloadPage()),
    'click [data-action=decide]': () => Dialogs.decide(ctx, () => reloadPage()),
});

/** Scrolled into the page, the header keeps the name, actions and tabs. Two thresholds, because condensing changes the height. */
function onScroll() {
    const y = window.scrollY;
    if (y > 220) $('#case-top').addClass('is-condensed');
    else if (y < 40) $('#case-top').removeClass('is-condensed');
}

export default {
    async mount(root, { params, query }) {
        token += 1;
        const mine = token;
        tab = query.tab || 'overview';
        render(root, V.loading());

        let alert;
        try {
            alert = await API.alert(params.id);
        } catch (error) {
            if (mine === token) render(root, V.missing(error.status === 404 ? 'This case does not exist' : 'The case could not be loaded'));
            return;
        }
        const [customer, profile, reviews, others, people] = await Promise.all([
            settle(API.customer(alert.customer_id)),
            settle(API.riskProfile(alert.customer_id)),
            settle(API.kycReviews(alert.customer_id)),
            settle(API.openAlerts(alert.customer_id)),
            settle(API.assignees()),
        ]);
        if (mine !== token) return;  // the user has moved on

        const owner = (people || []).find((p) => p.id === alert.assigned_to);
        const ctx = context({ alert, customer: customer || {}, profile, reviews, others,
            ownerName: alert.assigned_to_name || (owner ? owner.name : alert.assigned_to ? 'Assigned' : '') });
        document.title = `${ctx.customer.full_name || 'Case'} · Case ${V.shortId(alert.id)} · KYRO AML`;

        render(root, V.frame(ctx, V.TABS.some((t) => t.key === tab) ? tab : 'overview'));
        SECTIONS.forEach(([pane, section]) => $(`#case-pane-${pane}`).append(String(section.render(ctx))));
        const handlers = Object.assign({}, pageHandlers(ctx), ...SECTIONS.map(([, s]) => s.handlers || {}));
        off = on(root, 'case', handlers);
        $(window).on('scroll.case', onScroll);

        SECTIONS.forEach(([, section]) => section.load(ctx));
        ctx.refreshTimeline();
        if (alert.potential_sar) loadDeadlines(ctx);
        if (tab !== 'overview') showTab(tab);
    },
    unmount() {
        token += 1;  // answers to this page's requests are ignored from now on
        off();
        off = () => {};
        $(window).off('scroll.case');
        SECTIONS.forEach(([, section]) => section.unload && section.unload());
    },
};
