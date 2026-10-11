/**
 * My profile - who you are signed in as, what your role is responsible for,
 * and changing your own password.
 */

const Profile = {
    async init() {
        showLoading("#mainContent", "Loading your profile...");
        let user, roles;
        try {
            [user, roles] = await Promise.all([API.get("/auth/me"), API.get("/roles")]);
        } catch (error) {
            $("#mainContent").html('<div class="kyro-page"><section class="card kd-panel"><p class="cp-empty mb-0">Could not load your profile.</p></section></div>');
            return;
        }
        const role = roles.roles.find(r => r.code === user.role) || { label: user.role, purpose: '', responsibilities: [], limits: [] };
        const name = user.full_name || user.username;
        const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '?';
        const list = (items, cls = '') => `<ul class="adm-list ${cls}">${items.map(x => `<li>${escapeHtml(x)}</li>`).join('')}</ul>`;
        const row = (label, value) => `<div class="pf-row"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`;

        $("#mainContent").html(`
            <div class="kyro-page">
                <div class="kyro-page-head">
                    <div>
                        <span class="kyro-kicker">Account</span>
                        <h1 class="kyro-page-title">My Profile</h1>
                        <p class="kyro-page-sub">Your account, what your role is responsible for, and your password.</p>
                    </div>
                </div>
                <div class="pf-grid">
                    <section class="card kd-panel">
                        <div class="rc-customer mb-3">
                            <span class="rc-customer__avatar cp-head__avatar" aria-hidden="true">${escapeHtml(initials)}</span>
                            <div>
                                <h2 class="pf-name">${escapeHtml(name)}</h2>
                                <p class="aml-subtitle mb-0">${escapeHtml(role.label)}${role.read_only ? ' &middot; read-only' : ''}</p>
                            </div>
                        </div>
                        ${row('Username', user.username)}
                        ${row('Email', user.email)}
                        ${row('Last sign-in', user.last_login ? formatDateTime(user.last_login) : 'Never')}
                        ${row('Account created', user.created_at ? formatDate(user.created_at) : '—')}
                        <p class="kx-note mt-3 mb-0">Your name, email and role are managed by an administrator.</p>
                    </section>

                    <section class="card kd-panel">
                        <header class="kd-panel__head"><div><h2>Your role</h2><p class="aml-subtitle">${escapeHtml(role.purpose)}</p></div></header>
                        <div class="kx-label">Responsible for</div>
                        ${list(role.responsibilities)}
                        <div class="kx-label">Limits</div>
                        ${list(role.limits, 'adm-list--limits')}
                    </section>

                    <section class="card kd-panel">
                        <header class="kd-panel__head"><div><h2>Change password</h2><p class="aml-subtitle">Use at least 10 characters. Change a temporary password as soon as you receive it.</p></div></header>
                        <form id="pfPasswordForm" novalidate>
                            <input type="text" class="visually-hidden" autocomplete="username" value="${escapeHtml(user.username)}" tabindex="-1" aria-hidden="true" readonly>
                            <label class="kx-label" for="pfCurrent">Current password</label>
                            <input type="password" class="form-control mb-3" id="pfCurrent" autocomplete="current-password" required>
                            <label class="kx-label" for="pfNew">New password</label>
                            <input type="password" class="form-control mb-3" id="pfNew" minlength="10" autocomplete="new-password" required>
                            <label class="kx-label" for="pfConfirm">Confirm new password</label>
                            <input type="password" class="form-control" id="pfConfirm" minlength="10" autocomplete="new-password" required>
                            <p class="adm-error d-none" id="pfError" role="alert"></p>
                            <button type="submit" class="btn btn-primary mt-3">Change password</button>
                        </form>
                    </section>
                </div>
            </div>
        `);
        $("#pfPasswordForm").on("submit", (e) => { e.preventDefault(); this.changePassword(); });
    },

    async changePassword() {
        const current = $("#pfCurrent").val();
        const next = $("#pfNew").val();
        const fail = (message, focus) => { $("#pfError").text(message).removeClass("d-none"); if (focus) $(focus).trigger("focus"); };
        if (!current) return fail('Enter your current password.', '#pfCurrent');
        if (next.length < 10) return fail('The new password needs at least 10 characters.', '#pfNew');
        if (next !== $("#pfConfirm").val()) return fail('The new password and its confirmation do not match.', '#pfConfirm');
        if (next === current) return fail('Choose a password different from the current one.', '#pfNew');

        const $submit = $("#pfPasswordForm button[type=submit]").prop("disabled", true);
        try {
            await API.post('/auth/change-password', { current_password: current, new_password: next });
        } catch (xhr) {
            const detail = xhr && xhr.responseJSON && xhr.responseJSON.detail;
            fail(typeof detail === 'string' ? detail : 'Could not change the password. Try again.');
            $submit.prop("disabled", false);
            return;
        }
        $("#pfPasswordForm")[0].reset();
        $("#pfError").addClass("d-none");
        $submit.prop("disabled", false);
        showToast("success", "Password changed.");
    }
};

window.Profile = Profile;
