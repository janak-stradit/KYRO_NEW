/**
 * pages/cases — Review Cases: the work queue.
 *
 * State lives in one object; every change goes through load(), which fetches and redraws
 * the table. Views (tabs) are presets over the same filters. Handlers are delegated from
 * the page root under the "cases" namespace and removed on unmount.
 */
import { session } from '../../core/auth.js';
import { html, on, render } from '../../core/dom.js';
import { number } from '../../core/format.js';
import { dialog, toast } from '../../core/feedback.js';
import { navigate } from '../../core/router.js';
import { emptyRow, head, loadingRows, pager } from '../../components/table.js';
import * as API from './cases.api.js';
import * as V from './cases.views.js';

const DEFAULT_FILTERS = { q: '', status: 'UNRESOLVED', risk: '', rule: '', assignment: '', attention: '', sort: 'priority', customerId: '', customerName: '' };

let state;
let off = () => {};
let searchTimer = null;
let request = 0;

/** By customer only lists unresolved work; a status filter or a single customer means listing alerts. */
const grouped = () => state.group === 'customer' && !state.filters.customerId && state.filters.status === 'UNRESOLVED';

async function loadSummary() {
    try {
        render('#cases-views', V.viewTabs(await API.summary(), state.view));
    } catch (error) { /* the tabs keep their labels without counts */ }
}

async function load() {
    const mine = ++request;
    const customerView = grouped();
    const columns = customerView ? V.CUSTOMER_COLUMNS : V.alertColumns();
    render('#cases-head', head(columns));
    render('#cases-body', loadingRows(columns));
    render('#cases-bulk', V.bulkBar(state.selected.size));
    let data;
    try {
        data = customerView
            ? await API.byCustomer(state.filters, state.page, state.size)
            : await API.byAlert(state.filters, state.page, state.size);
    } catch (error) {
        if (mine !== request) return;
        render('#cases-body', emptyRow(columns.length, 'Could not load the queue', html` ${error.message}`, 'fa-triangle-exclamation'));
        render('#cases-pager', '');
        return;
    }
    if (mine !== request) return;  // a newer request has started
    const noun = customerView ? 'customers with unresolved alerts' : 'alerts';
    $('#cases-count').text(data.total ? `${number(data.total)} ${noun}` : `No ${noun} match these filters`);
    render('#cases-body', data.items.length
        ? html`${data.items.map((item) => (customerView ? V.customerRow(item) : V.alertRow(item, state.selected.has(item.id))))}`
        : emptyRow(columns.length, 'Nothing matches these filters', ' Try clearing the search or a filter.'));
    render('#cases-pager', pager({ page: state.page, size: state.size, total: data.total }));
}

function markTabs() {
    $('.tab').each((_, el) => { el.classList.toggle('is-active', el.dataset.tab === state.view); el.setAttribute('aria-selected', el.dataset.tab === state.view); });
    $('[data-group]').each((_, el) => { el.classList.toggle('is-active', el.dataset.group === state.group); el.setAttribute('aria-pressed', el.dataset.group === state.group); });
}

function setFilters(changes, { view } = {}) {
    state.filters = { ...state.filters, ...changes };
    if (view !== undefined) state.view = view;
    state.page = 1;
    state.selected.clear();
    $('.cases-filters').replaceWith(String(V.filters(state)));  // the status filter only exists when listing alerts
    markTabs();
    load();
}

async function chooseAssignee(subject, submit) {
    let people;
    try {
        people = await API.assignees();
    } catch (error) {
        return toast('error', error.message);
    }
    await dialog({
        title: 'Assign', submitLabel: 'Assign', body: V.assignForm(people, subject, (session.user() || {}).id),
        onSubmit: async (form, close) => {
            const userId = form.assignee.value;
            if (!userId) throw new Error('Choose a person.');
            const message = await submit(userId);
            close(true);
            toast('success', message);
            state.selected.clear();
            loadSummary();
            load();
        },
    });
}

const handlers = {
    'click [data-tab]': function () {
        const view = V.VIEWS.find((v) => v.key === this.dataset.tab);
        const group = view.filters.status && view.filters.status !== 'UNRESOLVED' ? 'alert' : state.group;
        state.group = group;
        setFilters({ ...DEFAULT_FILTERS, ...view.filters }, { view: view.key });
    },
    'click [data-group]': function () {
        state.group = this.dataset.group;
        setFilters({});
    },
    'change [data-filter]': function () {
        if (this.dataset.filter === 'q') return;
        setFilters({ [this.dataset.filter]: this.value }, { view: '' });
    },
    'input [data-filter=q]': function () {
        clearTimeout(searchTimer);
        const value = this.value;
        searchTimer = setTimeout(() => { state.filters.q = value; state.page = 1; load(); }, 300);
    },
    'click [data-action=refresh]': () => { loadSummary(); load(); },
    'click [data-action=clear-customer]': () => { state.group = 'customer'; setFilters({ customerId: '', customerName: '' }); },
    'click [data-action=customer-alerts]': function (event) {
        event.stopPropagation();
        state.group = 'alert';
        setFilters({ customerId: this.dataset.customer, customerName: this.dataset.name, status: 'UNRESOLVED' }, { view: '' });
    },
    'click [data-action=assign-customer]': function (event) {
        event.stopPropagation();
        const { customer, name, count } = this.dataset;
        chooseAssignee(`All ${count} open alerts for ${name}.`, async (userId) => {
            const r = await API.bulkAssign({ customerId: customer }, userId);
            return `${number(r.assigned ?? count)} alerts assigned.`;
        });
    },
    'click [data-action=assign-one]': function (event) {
        event.stopPropagation();
        const { alert, name } = this.dataset;
        chooseAssignee(`The alert for ${name}.`, async (userId) => { await API.assign(alert, userId); return 'Alert assigned.'; });
    },
    'click [data-action=assign-selected]': () => {
        const ids = [...state.selected];
        chooseAssignee(`${ids.length} selected alerts.`, async (userId) => {
            const r = await API.bulkAssign({ alertIds: ids }, userId);
            return `${number(r.assigned ?? ids.length)} alerts assigned.`;
        });
    },
    'click [data-action=clear-selection]': () => { state.selected.clear(); $('[data-select]').prop('checked', false); render('#cases-bulk', ''); },
    'change [data-select]': function () {
        if (this.checked) state.selected.add(this.dataset.select); else state.selected.delete(this.dataset.select);
        render('#cases-bulk', V.bulkBar(state.selected.size));
    },
    'change [data-action=select-all]': function () {
        $('[data-select]').each((_, el) => { el.checked = this.checked; if (this.checked) state.selected.add(el.dataset.select); else state.selected.delete(el.dataset.select); });
        render('#cases-bulk', V.bulkBar(state.selected.size));
    },
    'click [data-page]': function () { state.page = Number(this.dataset.page); load(); },
    'change [data-size]': function () { state.size = Number(this.value); state.page = 1; load(); },
    'click tr[data-open]': function (event) {
        if ($(event.target).closest('a, button, input, label, select').length) return;
        navigate(`/cases/${this.dataset.open}`);
    },
    'keydown tr[data-open]': function (event) {
        if (event.key === 'Enter' && event.target === this) navigate(`/cases/${this.dataset.open}`);
    },
};

export default {
    async mount(root, { query }) {
        state = {
            view: 'all', group: 'customer', page: 1, size: 25, selected: new Set(),
            filters: { ...DEFAULT_FILTERS, q: query.q || '' },
        };
        render(root, V.page(state));
        off = on(root, 'cases', handlers);
        loadSummary();
        await load();
    },
    unmount() {
        off();
        clearTimeout(searchTimer);
        request += 1;  // ignore answers to requests made by this page
    },
};
