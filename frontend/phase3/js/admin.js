/**
 * Administration - users, role definitions and the audit log.
 * Users need the "users.manage" permission, the audit log "audit.read";
 * the role definitions are visible to anyone who can open the page.
 */

const Admin = {
    tab: 'users',
    users: [],
    roles: [],
    permissions: [],
    audit: { page: 1, pageSize: 25, entityType: '' },

    ENTITY_TYPES: ['ALERT', 'CUSTOMER', 'ACCOUNT', 'TRANSACTION', 'DOCUMENT', 'RULE_CONFIG', 'RULE_CONFIG_CHANGE',
        'OBLIGATION', 'OBLIGATION_MAPPING', 'REGULATORY_CHANGE', 'USER'],

    human(value) {
        return value ? String(value).replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase()) : '—';
    },

    roleLabel(code) {
        const role = this.roles.find(r => r.code === code);
        return role ? role.label : this.human(code);
    },

    async init() {
        const tabs = [];
        if (Auth.can('users.manage')) tabs.push(['users', 'Users']);
        tabs.push(['roles', 'Roles and permissions']);
        if (Auth.can('audit.read')) tabs.push(['audit', 'Audit log']);
        if (!tabs.some(([key]) => key === this.tab)) this.tab = tabs[0][0];

        $("#mainContent").html(`
            <div class="kyro-page">
                <div class="kyro-page-head">
                    <div>
                        <span class="kyro-kicker">Administration</span>
                        <h1 class="kyro-page-title">Users and Access</h1>
                        <p class="kyro-page-sub">Who can sign in, what each role is responsible for, and a record of every change made in KYRO.</p>
                    </div>
                </div>
                <div class="adm-tabs" role="tablist">
                    ${tabs.map(([key, label]) => `<button type="button" class="adm-tab ${key === this.tab ? 'is-active' : ''}" role="tab" aria-selected="${key === this.tab}" data-tab="${key}">${label}</button>`).join('')}
                </div>
                <div id="admBody"></div>
            </div>
        `);
        $(".adm-tab").on("click", (e) => {
            this.tab = $(e.currentTarget).data("tab");
            $(".adm-tab").removeClass("is-active").attr("aria-selected", "false");
            $(e.currentTarget).addClass("is-active").attr("aria-selected", "true");
            this.renderTab();
        });

        try {
            const data = await API.get('/roles');
            this.roles = data.roles;
            this.permissions = data.permissions;
        } catch (error) {
            $("#admBody").html('<section class="card kd-panel"><p class="cp-empty mb-0">Could not load the role definitions.</p></section>');
            return;
        }
        this.renderTab();
    },

    renderTab() {
        if (this.tab === 'users') return this.renderUsers();
        if (this.tab === 'audit') return this.renderAudit();
        return this.renderRoles();
    },

    // ── Users ────────────────────────────────────────────────────────────
    async renderUsers() {
        $("#admBody").html(`
            <div class="card border-0 rc-table-card">
                <div class="rc-toolbar">
                    <div class="rc-toolbar__title"><h2>Users</h2><small class="text-muted">Every change to a user is recorded in the audit log</small></div>
                    <div class="rc-toolbar__controls">
                        <button type="button" class="btn btn-sm btn-primary" id="admAddUser"><i class="fas fa-plus me-1"></i>Add user</button>
                    </div>
                </div>
                <div class="table-responsive">
                    <table class="table table-hover mb-0 fp-table">
                        <thead><tr>
                            <th class="px-3 py-2">Name</th><th class="px-3 py-2">Username</th><th class="px-3 py-2">Email</th>
                            <th class="px-3 py-2">Role</th><th class="px-3 py-2">Status</th><th class="px-3 py-2">Last sign-in</th><th class="px-3 py-2"></th>
                        </tr></thead>
                        <tbody id="admUsersBody"><tr><td colspan="7" class="rc-empty">Loading...</td></tr></tbody>
                    </table>
                </div>
            </div>
        `);
        $("#admAddUser").on("click", () => this.showUserModal(null));
        $("#admUsersBody")
            .on("click", ".adm-edit", (e) => this.showUserModal(this.users.find(u => u.id === $(e.currentTarget).data("id"))))
            .on("click", ".adm-reset", (e) => this.showPasswordModal(this.users.find(u => u.id === $(e.currentTarget).data("id"))));
        await this.loadUsers();
    },

    async loadUsers() {
        try {
            API.clearCache();
            this.users = await API.get('/users');
        } catch (error) {
            $("#admUsersBody").html('<tr><td colspan="7" class="rc-empty">Could not load users.</td></tr>');
            return;
        }
        const me = (Auth.getUser() || {}).id;
        $("#admUsersBody").html(this.users.map(u => `
            <tr>
                <td class="px-3 py-2"><strong>${escapeHtml(u.full_name || u.username)}</strong>${u.id === me ? ' <small class="text-muted">(you)</small>' : ''}</td>
                <td class="px-3 py-2">${escapeHtml(u.username)}</td>
                <td class="px-3 py-2">${escapeHtml(u.email)}</td>
                <td class="px-3 py-2">${escapeHtml(this.roleLabel(u.role))}</td>
                <td class="px-3 py-2"><span class="cd-chip cd-chip--${u.is_active ? 'low' : 'muted'}">${u.is_active ? 'Active' : 'Deactivated'}</span></td>
                <td class="px-3 py-2 text-muted text-nowrap">${u.last_login ? escapeHtml(formatDateTime(u.last_login)) : 'Never'}</td>
                <td class="px-3 py-2 text-end text-nowrap">
                    <button type="button" class="btn btn-sm rc-actions__view adm-edit" data-id="${escapeHtml(u.id)}">Edit</button>
                    <button type="button" class="btn btn-sm rc-actions__icon adm-reset" data-id="${escapeHtml(u.id)}" title="Reset password" aria-label="Reset password for ${escapeHtml(u.username)}"><i class="fas fa-key"></i></button>
                </td>
            </tr>`).join('') || '<tr><td colspan="7" class="rc-empty">No users.</td></tr>');
    },

    roleOptions(selected) {
        const option = r => `<option value="${escapeHtml(r.code)}" ${r.code === selected ? 'selected' : ''}>${escapeHtml(r.label)}</option>`;
        return this.roles.filter(r => !r.legacy || r.code === selected).map(option).join('');
    },

    roleSummary(code) {
        const r = this.roles.find(x => x.code === code);
        if (!r) return '';
        return `<p class="mb-1"><strong>${escapeHtml(r.purpose)}</strong></p>
            <ul class="adm-list">${r.responsibilities.map(x => `<li>${escapeHtml(x)}</li>`).join('')}</ul>
            <ul class="adm-list adm-list--limits">${r.limits.map(x => `<li>${escapeHtml(x)}</li>`).join('')}</ul>`;
    },

    showUserModal(user) {
        const isNew = !user;
        const role = isNew ? 'L1_ANALYST' : user.role;
        $("#admUserModal").remove();
        $("body").append(`
            <div class="modal fade" id="admUserModal" tabindex="-1" aria-labelledby="admUserTitle" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered">
                    <form class="modal-content" id="admUserForm" novalidate>
                        <div class="modal-header">
                            <h5 class="modal-title" id="admUserTitle">${isNew ? 'Add user' : `Edit ${escapeHtml(user.username)}`}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <label class="kx-label" for="admFullName">Full name</label>
                            <input type="text" class="form-control mb-3" id="admFullName" maxlength="255" required value="${escapeHtml(isNew ? '' : (user.full_name || ''))}">
                            ${isNew ? `
                            <label class="kx-label" for="admUsername">Username</label>
                            <input type="text" class="form-control mb-3" id="admUsername" maxlength="100" required autocomplete="off">
                            <label class="kx-label" for="admEmail">Email</label>
                            <input type="email" class="form-control mb-3" id="admEmail" required autocomplete="off">
                            <label class="kx-label" for="admPassword">Temporary password</label>
                            <input type="password" class="form-control mb-1" id="admPassword" minlength="10" required autocomplete="new-password">
                            <p class="kx-note mb-3">At least 10 characters. Give it to the user directly.</p>` : ''}
                            <label class="kx-label" for="admRole">Role</label>
                            <select class="form-select mb-2" id="admRole">${this.roleOptions(role)}</select>
                            <div class="adm-role-summary" id="admRoleSummary">${this.roleSummary(role)}</div>
                            ${isNew ? '' : `
                            <label class="adm-check mt-3"><input type="checkbox" class="form-check-input" id="admActive" ${user.is_active ? 'checked' : ''}> Can sign in</label>`}
                            <p class="adm-error d-none" id="admUserError" role="alert"></p>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-primary" data-bs-dismiss="modal">Cancel</button>
                            <button type="submit" class="btn btn-primary">${isNew ? 'Create user' : 'Save changes'}</button>
                        </div>
                    </form>
                </div>
            </div>
        `);
        $("#admRole").on("change", (e) => $("#admRoleSummary").html(this.roleSummary($(e.currentTarget).val())));
        $("#admUserForm").on("submit", async (e) => {
            e.preventDefault();
            const body = { full_name: $("#admFullName").val().trim(), role: $("#admRole").val() };
            if (isNew) {
                body.username = $("#admUsername").val().trim();
                body.email = $("#admEmail").val().trim();
                body.password = $("#admPassword").val();
            } else {
                body.is_active = $("#admActive").is(":checked");
            }
            const missing = !body.full_name || (isNew && (!body.username || !body.email || body.password.length < 10));
            if (missing) return this.showError("#admUserError", isNew ? 'Fill in every field; the password needs at least 10 characters.' : 'Enter the full name.');
            await this.save("#admUserModal", "#admUserError",
                () => (isNew ? API.post('/users', body) : API.put(`/users/${user.id}`, body)),
                isNew ? 'User created.' : 'User updated.');
        });
        new bootstrap.Modal(document.getElementById("admUserModal")).show();
    },

    showPasswordModal(user) {
        if (!user) return;
        $("#admPasswordModal").remove();
        $("body").append(`
            <div class="modal fade" id="admPasswordModal" tabindex="-1" aria-labelledby="admPasswordTitle" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered">
                    <form class="modal-content" id="admPasswordForm" novalidate>
                        <div class="modal-header">
                            <h5 class="modal-title" id="admPasswordTitle">Reset password for ${escapeHtml(user.username)}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <label class="kx-label" for="admNewPassword">New password</label>
                            <input type="password" class="form-control mb-1" id="admNewPassword" minlength="10" required autocomplete="new-password">
                            <p class="kx-note mb-0">At least 10 characters. The old password stops working immediately.</p>
                            <p class="adm-error d-none" id="admPasswordError" role="alert"></p>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-outline-primary" data-bs-dismiss="modal">Cancel</button>
                            <button type="submit" class="btn btn-primary">Reset password</button>
                        </div>
                    </form>
                </div>
            </div>
        `);
        $("#admPasswordForm").on("submit", async (e) => {
            e.preventDefault();
            const password = $("#admNewPassword").val();
            if (password.length < 10) return this.showError("#admPasswordError", 'The password needs at least 10 characters.');
            await this.save("#admPasswordModal", "#admPasswordError",
                () => API.post(`/users/${user.id}/reset-password`, { password }), 'Password reset.');
        });
        new bootstrap.Modal(document.getElementById("admPasswordModal")).show();
    },

    showError(selector, message) {
        $(selector).text(message).removeClass("d-none");
    },

    async save(modalSelector, errorSelector, request, successMessage) {
        const $submit = $(`${modalSelector} button[type=submit]`).prop("disabled", true);
        try {
            await request();
        } catch (xhr) {
            const detail = xhr && xhr.responseJSON && xhr.responseJSON.detail;
            const message = Array.isArray(detail) ? detail.map(d => String(d.msg || '').replace(/^Value error, /, '')).join(' ') : detail;
            this.showError(errorSelector, message || 'Could not save. Try again.');
            $submit.prop("disabled", false);
            return;
        }
        closeModalSafely(modalSelector.slice(1));
        showToast("success", successMessage);
        await this.loadUsers();
    },

    // ── Roles ────────────────────────────────────────────────────────────
    renderRoles() {
        const current = this.roles.filter(r => !r.legacy);
        const legacy = this.roles.filter(r => r.legacy);
        const card = r => `
            <article class="card kd-panel adm-role">
                <header class="adm-role__head">
                    <h3>${escapeHtml(r.label)}</h3>
                    ${r.read_only ? '<span class="cd-chip cd-chip--muted">Read-only</span>' : ''}
                </header>
                <p class="adm-role__purpose">${escapeHtml(r.purpose)}</p>
                <div class="kx-label">Responsible for</div>
                <ul class="adm-list">${r.responsibilities.map(x => `<li>${escapeHtml(x)}</li>`).join('')}</ul>
                <div class="kx-label">Limits</div>
                <ul class="adm-list adm-list--limits">${r.limits.map(x => `<li>${escapeHtml(x)}</li>`).join('')}</ul>
            </article>`;
        const short = label => label.replace(' (legacy)', '').replace('Level 1 ', 'L1 ').replace('Level 2 ', 'L2 ').replace(' / AML Officer', '');
        $("#admBody").html(`
            <div class="adm-roles">${current.map(card).join('')}</div>
            <div class="card border-0 rc-table-card mt-4">
                <div class="rc-toolbar"><div class="rc-toolbar__title"><h2>Who can do what</h2><small class="text-muted">Nobody approves a rule change, or quality-checks a case, that they prepared themselves</small></div></div>
                <div class="table-responsive">
                    <table class="table mb-0 fp-table adm-matrix">
                        <thead><tr><th class="px-3 py-2">Action</th>${current.map(r => `<th class="py-2 text-center" title="${escapeHtml(r.label)}">${escapeHtml(short(r.label))}</th>`).join('')}</tr></thead>
                        <tbody>${this.permissions.map(p => `
                            <tr><td class="px-3 py-2">${escapeHtml(p.label)}</td>${current.map(r => r.permissions.includes(p.code)
                                ? `<td class="text-center"><i class="fas fa-check adm-yes" aria-hidden="true"></i><span class="visually-hidden">Yes</span></td>`
                                : `<td class="text-center adm-no"><span aria-hidden="true">–</span><span class="visually-hidden">No</span></td>`).join('')}</tr>`).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
            ${legacy.length ? `
            <section class="card kd-panel mt-4">
                <header class="kd-panel__head"><div><h2>Earlier roles</h2><p class="aml-subtitle">Existing users keep these until an administrator moves them to one of the roles above</p></div></header>
                <ul class="adm-list mb-0">${legacy.map(r => `<li><strong>${escapeHtml(r.label)}</strong>: ${escapeHtml(r.responsibilities.join('; '))}</li>`).join('')}</ul>
            </section>` : ''}
        `);
    },

    // ── Audit log ────────────────────────────────────────────────────────
    renderAudit() {
        $("#admBody").html(`
            <div class="card border-0 rc-table-card">
                <div class="rc-toolbar">
                    <div class="rc-toolbar__title"><h2>Audit log</h2><small class="text-muted" id="admAuditCount">Newest first</small></div>
                    <div class="rc-toolbar__controls">
                        <select class="form-select form-select-sm" id="admAuditType" aria-label="Record type">
                            <option value="">All record types</option>
                            ${this.ENTITY_TYPES.map(t => `<option value="${t}" ${t === this.audit.entityType ? 'selected' : ''}>${escapeHtml(this.human(t))}</option>`).join('')}
                        </select>
                    </div>
                </div>
                <div class="table-responsive">
                    <table class="table table-hover mb-0 fp-table">
                        <thead><tr><th class="px-3 py-2">When</th><th class="px-3 py-2">Who</th><th class="px-3 py-2">Action</th><th class="px-3 py-2">Record</th><th class="px-3 py-2">What changed</th></tr></thead>
                        <tbody id="admAuditBody"><tr><td colspan="5" class="rc-empty">Loading...</td></tr></tbody>
                    </table>
                </div>
                <div class="d-flex justify-content-between align-items-center">
                    <button type="button" class="btn btn-sm rc-actions__view" id="admAuditPrev">Newer</button>
                    <small class="text-muted" id="admAuditPage"></small>
                    <button type="button" class="btn btn-sm rc-actions__view" id="admAuditNext">Older</button>
                </div>
            </div>
        `);
        $("#admAuditType").on("change", (e) => { this.audit.entityType = $(e.currentTarget).val(); this.audit.page = 1; this.loadAudit(); });
        $("#admAuditPrev").on("click", () => { this.audit.page -= 1; this.loadAudit(); });
        $("#admAuditNext").on("click", () => { this.audit.page += 1; this.loadAudit(); });
        this.loadAudit();
    },

    describeChange(row) {
        const values = row.new_values || {};
        const parts = Object.entries(values).slice(0, 4).map(([key, value]) => {
            const text = value !== null && typeof value === 'object' ? JSON.stringify(value) : String(value);
            return `${this.human(key)}: ${text.length > 60 ? text.slice(0, 57) + '...' : text}`;
        });
        const more = Object.keys(values).length - parts.length;
        return parts.join('; ') + (more > 0 ? ` (+${more} more)` : '');
    },

    async loadAudit() {
        const a = this.audit;
        const params = { page: a.page, page_size: a.pageSize };
        if (a.entityType) params.entity_type = a.entityType;
        let data;
        try {
            data = await API.get('/audit-logs', params);
        } catch (error) {
            $("#admAuditBody").html('<tr><td colspan="5" class="rc-empty">Could not load the audit log.</td></tr>');
            return;
        }
        const pages = Math.max(1, Math.ceil(data.total / a.pageSize));
        $("#admAuditCount").text(`${data.total.toLocaleString()} entr${data.total === 1 ? 'y' : 'ies'}, newest first`);
        $("#admAuditPage").text(`Page ${a.page} of ${pages.toLocaleString()}`);
        $("#admAuditPrev").prop("disabled", a.page <= 1);
        $("#admAuditNext").prop("disabled", a.page >= pages);
        $("#admAuditBody").html(data.items.map(r => `
            <tr>
                <td class="px-3 py-2 text-nowrap">${escapeHtml(formatDateTime(r.performed_at))}</td>
                <td class="px-3 py-2">${escapeHtml(r.performed_by_name)}</td>
                <td class="px-3 py-2">${escapeHtml(this.human(r.action))}</td>
                <td class="px-3 py-2 text-nowrap">${escapeHtml(this.human(r.entity_type))} <small class="text-muted">${escapeHtml(r.entity_id.slice(0, 8))}</small></td>
                <td class="px-3 py-2 reg-cell">${escapeHtml(this.describeChange(r)) || '<span class="text-muted">—</span>'}</td>
            </tr>`).join('') || '<tr><td colspan="5" class="rc-empty">Nothing recorded yet.</td></tr>');
    }
};

window.Admin = Admin;
