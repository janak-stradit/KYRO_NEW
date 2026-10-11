/**
 * notifications.js — Header notification bell.
 *
 * Owns the badge (open-alert count) and the dropdown of newest alerts so both
 * stay consistent on every page. "Unread" means created after the user last
 * opened the dropdown, remembered per browser.
 */
const Notifications = {
    seenKey: "kyro_notifications_seen_at",
    maxItems: 8,
    refreshMs: 60000,
    items: [],
    count: 0,
    state: "loading", // loading | ready | error

    init() {
        if (!$("#notificationList").length || this.initialized) return;
        this.initialized = true;

        this.render();
        this.refresh();
        setInterval(() => this.refresh(), this.refreshMs);

        $("#notificationsDropdown").on("shown.bs.dropdown", () => {
            // Let the unread dots show for a moment before clearing them
            this.markSeenTimer = setTimeout(() => this.markSeen(), 4000);
        }).on("hidden.bs.dropdown", () => {
            clearTimeout(this.markSeenTimer);
        });

        $(document).on("click", "#notifMarkSeen", (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.markSeen();
        });

        $(document).on("click", "#notifRetry", (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.state = "loading";
            this.render();
            this.refresh();
        });

        $(document).on("click", "#notificationList a[data-page]", (e) => {
            e.preventDefault();
            const caseId = $(e.currentTarget).data("case");
            if (caseId && Auth.can('cases.view')) {
                // One route serves every case, so tell the case page directly when it is already open
                if (App.currentPage === 'case') CaseDetail.open(caseId);
                else App.navigateTo('case', { id: caseId });
                const menu = bootstrap.Dropdown.getInstance(document.getElementById('notificationsDropdown'));
                if (menu) menu.hide();
                return;
            }
            this.close();
            if (window.App && App.navigateTo) {
                App.navigateTo($(e.currentTarget).data("page"));
            }
        });
    },

    async refresh() {
        await Auth.ensureUser();  // what the bell may show depends on the role
        const [kpis, alerts] = await Promise.allSettled([
            API.get("/dashboard/kpis"),
            (Auth.can("cases.view") ? API.get("/dashboard/recent-alerts") : Promise.resolve([]))
        ]);

        if (kpis.status === "fulfilled" && kpis.value) {
            this.setCount(kpis.value.pending_alerts);
        }
        if (alerts.status === "fulfilled") {
            this.items = (alerts.value || []).slice(0, this.maxItems);
            this.state = "ready";
        } else if (!this.items.length) {
            this.state = "error";
        }
        this.render();
    },

    /** Called for alerts pushed over the live stream. */
    add(alert) {
        if (!alert) return;
        this.items = [alert, ...this.items.filter((a) => a.id !== alert.id)].slice(0, this.maxItems);
        this.state = "ready";
        this.setCount(this.count + 1);
        this.render();
    },

    setCount(value) {
        this.count = Math.max(0, Number(value) || 0);
        const label = this.count > 99 ? "99+" : String(this.count);
        $("#notificationBadge").text(label).toggleClass("d-none", this.count === 0);
        $("#sidebarAlertCount").text(this.count);
        $("#notificationsDropdown").attr("aria-label", `Notifications: ${this.count} open alerts`);
        $("#notifOpenCount").text(`${this.count.toLocaleString()} open`);
    },

    seenAt() {
        try {
            return Number(localStorage.getItem(this.seenKey)) || 0;
        } catch (e) {
            return 0;
        }
    },

    markSeen() {
        try {
            localStorage.setItem(this.seenKey, String(Date.now()));
        } catch (e) {
            // Storage unavailable: unread dots simply persist for this view
        }
        this.render();
    },

    isUnread(alert) {
        const created = Date.parse(alert.created_at);
        return !Number.isNaN(created) && created > this.seenAt();
    },

    close() {
        const btn = document.getElementById("notificationsDropdown");
        if (btn && window.bootstrap) {
            bootstrap.Dropdown.getOrCreateInstance(btn).hide();
        }
    },

    escape(value) {
        return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    },

    humanize(code) {
        return String(code || "").toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    },

    riskClass(score) {
        const s = Number(score) || 0;
        return s >= 70 ? "high" : s >= 40 ? "medium" : "low";
    },

    renderItems() {
        if (this.state === "loading") {
            return `<li class="kn-skeleton"></li><li class="kn-skeleton"></li><li class="kn-skeleton"></li>`;
        }
        if (this.state === "error") {
            return `
                <li class="kn-state">
                    <i class="fas fa-triangle-exclamation kn-state__icon kn-state__icon--warn"></i>
                    <strong>Couldn't load notifications</strong>
                    <a href="#" id="notifRetry">Try again</a>
                </li>`;
        }
        if (!this.items.length) {
            return `
                <li class="kn-state">
                    <img src="assets/template/shapes/check.svg" alt="" class="kn-state__img">
                    <strong>You're all caught up</strong>
                    <span>New alerts will appear here.</span>
                </li>`;
        }
        return this.items.map((a) => {
            const unread = this.isUnread(a);
            const time = typeof formatRelativeTime === "function" ? formatRelativeTime(a.created_at) : "";
            return `
                <li>
                    <a class="kn-item${unread ? " is-unread" : ""}" href="/case?id=${encodeURIComponent(a.id)}" data-page="cases" data-case="${escapeHtml(String(a.id))}">
                        <span class="kn-item__score kn-item__score--${this.riskClass(a.risk_score)}" title="Risk score">${Number(a.risk_score) || 0}</span>
                        <span class="kn-item__body">
                            <strong>${this.escape(a.customer_name || "Unknown customer")}</strong>
                            <small>${this.escape(this.humanize(a.alert_type))} &middot; ${this.escape(this.humanize(a.status || "OPEN"))}</small>
                        </span>
                        <span class="kn-item__meta">
                            <time datetime="${this.escape(a.created_at)}">${this.escape(time)}</time>
                            ${unread ? '<span class="kn-item__dot" aria-label="Unread"></span>' : ""}
                        </span>
                    </a>
                </li>`;
        }).join("");
    },

    render() {
        const unread = this.items.filter((a) => this.isUnread(a)).length;
        $("#notificationList").html(`
            <div class="kn-head">
                <div>
                    <strong>Notifications</strong>
                    <span class="kn-head__sub"><span id="notifOpenCount">${this.count.toLocaleString()} open</span>${unread ? ` &middot; <span class="kn-head__new">${unread} new</span>` : ""}</span>
                </div>
                ${unread ? '<button type="button" class="kn-head__action" id="notifMarkSeen">Mark all as read</button>' : ""}
            </div>
            <ul class="kn-items" aria-live="polite">${this.renderItems()}</ul>
            <a class="kn-foot" href="/cases" data-page="cases">View all alerts <i class="fas fa-arrow-right"></i></a>
        `);
    }
};

$(document).ready(() => {
    if (window.Auth && Auth.isAuthenticated && Auth.isAuthenticated()) {
        Notifications.init();
    }
});
