/**
 * KYRO Process - the whole AML flow, from onboarding a customer to closing a
 * case, as an animated diagram with an explanation of each step: what happens,
 * who does it, which part of KYRO does it, what is recorded and which controls
 * apply. For administrators; the written version is
 * docs/TRANSACTION_TO_RESOLUTION_WORKFLOW.md.
 */

const Process = {
    STEPS: [
        {
            key: 'onboard', icon: 'fa-user-check', title: 'Customer onboarded', short: 'Screened against watchlists',
            who: 'KYC Analyst, Team Lead', system: 'customer_service, screening_service',
            what: [
                'A customer is created or their name, date of birth or country changes.',
                'They are screened against OFAC, UN and UK sanctions lists and PEP lists: by name, alias, spelling variant, sound and identifiers such as passport numbers.',
                'A confirmed match sets the sanctions flag and opens one sanctions case; a potential match waits for an analyst.',
                'The whole book is screened again every night after the lists refresh.',
            ],
            recorded: 'CUSTOMER / CREATE, screening results, CUSTOMER / REVIEW for analyst decisions',
            controls: 'Sound-alike matches never confirm on their own; a different passport number lowers a match and is flagged.',
        },
        {
            key: 'ingest', icon: 'fa-right-to-bracket', title: 'Transaction arrives', short: 'API, data feed or live feed',
            who: 'Source systems, Data operations', system: 'routers/transactions.py: _ingest_one, feed_service',
            what: [
                'Transactions come in one at a time or in batches through the API, from a client CSV feed, or from the demo live feed.',
                'Every path goes through the same function, so every transaction gets the same checks.',
                'The source\'s own transaction code is mapped to a KYRO type, direction (money in or out) and channel (cash, wire, card…).',
                'Feed rows are checked for data quality and each load is reconciled: rows received = loaded + rejected + already present.',
            ],
            recorded: 'TRANSACTION / CREATE; a reconciliation record per feed load',
            controls: 'Unknown transaction codes are refused, not guessed; a daily job catches anything loaded around the API.',
        },
        {
            key: 'rules', icon: 'fa-list-check', title: 'Rules engine', short: 'R001–R010 score the payment',
            who: 'Automatic; thresholds owned by the Rules Owner', system: 'services/rules_engine.py',
            what: [
                'Ten rules look at the payment and the customer\'s recent history: large amounts, velocity, high-risk countries, PEP and sanctions status, new counterparties, weekend activity, round amounts and rapid succession.',
                'Each rule that fires adds its severity weight; at the alert threshold (50) an alert opens, and a critical rule always opens one.',
                'Amounts can be compared in the base currency using the day\'s ECB exchange rate.',
                'Thresholds are set per jurisdiction and changed only through a proposal, a backtest and a second person\'s approval.',
            ],
            recorded: 'A risk flag per rule fired on the transaction; rule changes in the change log',
            controls: 'Every switch that changes alerting is replayed over past data first, and blocked if a productive case would be lost.',
        },
        {
            key: 'ml', icon: 'fa-brain', title: 'ML scoring', short: 'Anomaly models add a view',
            who: 'Automatic', system: 'services/auto_scoring_service.py, app/ml',
            what: [
                'Three models (risk scorer, anomaly classifier, isolation forest) score the transaction.',
                'If the rules opened an alert, the model\'s explanation is added to it; if not, an anomaly can open an alert of its own.',
                'Scoring never blocks a transaction: if the models are unavailable, the rules result stands.',
            ],
            recorded: 'An ml_scores row per transaction',
            controls: 'A retrain that would learn from changed rule scoring is refused unless someone approves the change.',
        },
        {
            key: 'alert', icon: 'fa-bell', title: 'Alert opened', short: 'Clock starts, customer re-rated',
            who: 'Automatic', system: 'models/alert.py, deadline_service, customer_risk_service',
            what: [
                'The alert records which rule version fired, the values and thresholds used and the transactions behind it ("Why this alert").',
                'The case clock starts: 5, 10 or 20 days by risk band, fixed when the alert opens.',
                'The customer\'s risk rating is recalculated.',
                'With consolidation on, further hits the same day join the customer\'s open alert.',
            ],
            recorded: 'The alert with its provenance',
            controls: 'Deadlines are policy, changed through maker-checker; a policy change does not move clocks already running.',
        },
        {
            key: 'queue', icon: 'fa-inbox', title: 'Work queue', short: 'Riskiest and oldest first',
            who: 'Team Lead assigns; analysts pick up', system: 'Review Cases page, /alerts/queue',
            what: [
                'Alerts are grouped by customer so one review settles several, ordered by highest risk and longest wait.',
                'Filters show overdue cases, cases waiting on information, unassigned work and alerts by rule.',
                'Team Leads assign one case or many at once.',
            ],
            recorded: 'ALERT / UPDATE on assignment',
            controls: 'L1, L2 and KYC analysts see only their own cases and the unassigned pool; SAR-filed cases are invisible without SAR access.',
        },
        {
            key: 'investigate', icon: 'fa-magnifying-glass', title: 'Investigation', short: 'Case file, notes, AI help',
            who: 'L1 Analyst, L2 Investigator', system: 'Case page, routers/case_file.py',
            what: [
                'One page holds the timeline, notes, requests for information, earlier cases, activity against the customer\'s own baseline, counterparties, accounts, screening matches and KYC documents.',
                'AI writes a case summary and a draft narrative from the facts on file; names, addresses, IDs and account numbers are masked before anything leaves KYRO.',
                'An AI summary stays "Not checked" until an investigator keeps, corrects or rejects it against the records.',
            ],
            recorded: 'Notes (never edited), requests, every AI call with its redacted input and the human decision',
            controls: 'AI proposes, a person decides: nothing AI-written counts until it has been checked.',
        },
        {
            key: 'decide', icon: 'fa-code-branch', title: 'Decision', short: 'Close, or escalate to the MLRO',
            who: 'L1 (false positive), L2 / Team Lead (close or escalate)', system: 'PUT /alerts/{id}/resolve, /escalate',
            what: [
                'False positive: the rule fired wrongly (L1 and above).',
                'True positive, no SAR: the activity is real but explained (L2, Team Lead).',
                'Escalated: suspicion goes to the MLRO, with reason codes and notes.',
                'Ticking "Potential SAR" starts the MLRO decision clock and the filing deadline, and restricts the case notes.',
            ],
            recorded: 'ALERT / APPROVE or UPDATE, with outcome, reasons and notes',
            controls: 'Every outcome needs reason codes; only the outcomes a role may record are offered to it.',
        },
        {
            key: 'mlro', icon: 'fa-gavel', title: 'MLRO decision', short: 'File a SAR, or not',
            who: 'MLRO only', system: 'Dashboard, case page, sar_confidentiality',
            what: [
                'The MLRO\'s dashboard lists escalations, open potential SARs, overdue decisions and filings due.',
                'Team Leads follow the case as "With the MLRO" without seeing SAR content.',
                'A SAR cannot be recorded while the latest narrative is an unchecked AI draft.',
                'Once filed, the case and the fact a SAR exists are hidden from every role without SAR access.',
            ],
            recorded: 'SAR / VIEW each time a SAR case is opened; the decision and SAR reference',
            controls: 'Administrators cannot see or decide SARs; emergency access is time-limited, approved by the MLRO and audited.',
        },
        {
            key: 'qa', icon: 'fa-clipboard-check', title: 'Quality check', short: 'A second person reviews',
            who: 'QA Reviewer, MLRO', system: 'PUT /alerts/{id}/qa',
            what: [
                'A sample of resolved cases is checked against policy: pass or fail, with notes.',
                'The quality check never changes the outcome, and nobody may check a case they resolved.',
            ],
            recorded: 'ALERT / REVIEW',
            controls: 'Four-eyes on decisions; QA results feed training and tuning.',
        },
        {
            key: 'learn', icon: 'fa-arrows-rotate', title: 'After closure', short: 'Re-rate, tune, retrain',
            who: 'Rules Owner, MLRO, Administrator', system: 'Rules page, change management, ML pipeline',
            what: [
                'The customer is re-rated on every decision.',
                'False-positive rates per rule show which settings to review; a proposed change is backtested and replayed, then approved by someone else.',
                'Analyst outcomes are used to retrain the models, as a candidate first.',
            ],
            recorded: 'Rule changes, approvals and activations; model versions with their training labels',
            controls: 'No detection change goes live without a replay showing no lost true positives.',
        },
    ],

    step: 0,
    playing: false,
    timer: null,
    DWELL_MS: 7000,

    async init() {
        this.stop();
        this.step = 0;
        const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        $("#mainContent").html(`
            <div class="kyro-page">
                <div class="kyro-page-head">
                    <div>
                        <span class="kyro-kicker">Administration</span>
                        <h1 class="kyro-page-title">How KYRO works</h1>
                        <p class="kyro-page-sub">The whole AML process, from onboarding a customer to closing a case. Play it, or step through and read what happens at each stage.</p>
                    </div>
                    <div class="kyro-page-actions pf-controls" role="group" aria-label="Walk through the process">
                        <button type="button" class="btn btn-outline-primary" id="pfPrev" aria-label="Previous step"><i class="fas fa-chevron-left"></i></button>
                        <button type="button" class="btn btn-primary" id="pfPlay"><i class="fas fa-play me-2"></i>Play</button>
                        <button type="button" class="btn btn-outline-primary" id="pfNext" aria-label="Next step"><i class="fas fa-chevron-right"></i></button>
                    </div>
                </div>
                <section class="card kd-panel pf-stage mb-4">
                    <div class="pf-progress" aria-hidden="true"><span id="pfBar"></span></div>
                    <div class="pf-diagram" id="pfDiagram"></div>
                    <ol class="pf-dots" id="pfDots" aria-label="Steps"></ol>
                </section>
                <section class="card kd-panel pf-detail" id="pfDetail" aria-live="polite"></section>
                <p class="kx-note mt-3">The written version, with every endpoint and audit entry: <code>docs/TRANSACTION_TO_RESOLUTION_WORKFLOW.md</code>.</p>
            </div>`);
        this.reduced = reduced;
        this.drawDiagram();
        $("#pfDots").html(this.STEPS.map((s, i) => `<li><button type="button" class="pf-dot" data-step="${i}" aria-label="Step ${i + 1}: ${escapeHtml(s.title)}"></button></li>`).join(''));
        $("#pfPrev").on("click", () => { this.stop(); this.go(this.step - 1); });
        $("#pfNext").on("click", () => { this.stop(); this.go(this.step + 1); });
        $("#pfPlay").on("click", () => (this.playing ? this.stop() : this.play()));
        $("#pfDots").on("click", ".pf-dot", (e) => { this.stop(); this.go(Number($(e.currentTarget).data("step"))); });
        $("#pfDiagram").on("click", ".pf-node", (e) => { this.stop(); this.go(Number($(e.currentTarget).data("step"))); });
        $("#pfDiagram").on("keydown", ".pf-node", (e) => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.stop(); this.go(Number($(e.currentTarget).data("step"))); }
        });
        $(document).off("keydown.process").on("keydown.process", (e) => {
            if (App.currentPage !== 'process' || $(e.target).is("input, textarea, select")) return;
            if (e.key === 'ArrowRight') { this.stop(); this.go(this.step + 1); }
            if (e.key === 'ArrowLeft') { this.stop(); this.go(this.step - 1); }
        });
        this.go(0, true);
        this.loadFigures();
    },

    // ── Diagram: 11 steps in a snake of three rows (4, 4, 3), joined by one path ──
    layout() {
        const W = 1200, colW = 300, rowH = 150, boxW = 244, boxH = 100, top = 22;
        const order = [[0, 1, 2, 3], [7, 6, 5, 4], [8, 9, 10]];
        const pos = [];
        order.forEach((row, r) => row.forEach((stepIndex, c) => {
            const offset = r === 2 ? colW * 0.5 : 0;  // centre the short last row
            const cx = offset + colW * c + colW / 2;
            pos[stepIndex] = { cx, cy: top + rowH * r + boxH / 2, x: cx - boxW / 2, y: top + rowH * r, w: boxW, h: boxH };
        }));
        return { W, H: top + rowH * 2 + boxH + 22, pos };
    },

    /** Where the marker rests on a step: around its number, so it never covers the text. */
    anchor(i) {
        const p = this.L.pos[i];
        return [p.x + 26, p.y + 28];
    },

    /** Points along the connector from step i to step i + 1 (orthogonal turns between rows). */
    route(i) {
        const a = this.L.pos[i], b = this.L.pos[i + 1];
        if (a.cy === b.cy) {
            const dir = b.cx > a.cx ? 1 : -1;
            return [[a.cx + dir * a.w / 2, a.cy], [b.cx - dir * b.w / 2, b.cy]];
        }
        const midY = (a.y + a.h + b.y) / 2;
        return [[a.cx, a.y + a.h], [a.cx, midY], [b.cx, midY], [b.cx, b.y]];
    },

    drawDiagram() {
        this.L = this.layout();
        const { W, H, pos } = this.L;
        const links = this.STEPS.slice(0, -1).map((_, i) => {
            const pts = this.route(i).map(p => p.join(',')).join(' ');
            return `<polyline class="pf-link" id="pfLink${i}" points="${pts}" marker-end="url(#pfArrow)"/>`;
        }).join('');
        const nodes = this.STEPS.map((s, i) => {
            const p = pos[i];
            return `
                <g class="pf-node" data-step="${i}" tabindex="0" role="button" aria-label="Step ${i + 1}: ${escapeHtml(s.title)}">
                    <rect x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" rx="14"/>
                    <circle class="pf-num" cx="${p.x + 26}" cy="${p.y + 28}" r="15"/>
                    <text class="pf-num-text" x="${p.x + 26}" y="${p.y + 33}" text-anchor="middle">${i + 1}</text>
                    <text class="pf-title" x="${p.x + 50}" y="${p.y + 34}">${escapeHtml(s.title)}</text>
                    <text class="pf-short" x="${p.x + 20}" y="${p.y + 64}">${escapeHtml(s.short)}</text>
                    <text class="pf-figure" id="pfFig${i}" x="${p.x + 20}" y="${p.y + 88}"></text>
                </g>`;
        }).join('');
        $("#pfDiagram").html(`
            <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="KYRO process flow, ${this.STEPS.length} steps">
                <defs>
                    <marker id="pfArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                        <path d="M0,0 L10,5 L0,10 z" class="pf-arrowhead"/>
                    </marker>
                </defs>
                <g>${links}</g>
                <g>${nodes}</g>
                <circle class="pf-token" id="pfToken" r="20" cx="${pos[0].x + 26}" cy="${pos[0].y + 28}"/>
            </svg>`);
    },

    // ── Moving between steps ────────────────────────────────────────────
    go(target, instant = false) {
        const n = this.STEPS.length;
        target = Math.max(0, Math.min(n - 1, target));
        const from = this.step;
        this.step = target;
        $(".pf-node").each((_, el) => {
            const i = Number($(el).data("step"));
            $(el).toggleClass("is-current", i === target).toggleClass("is-done", i < target);
        });
        $(".pf-link").each((i, el) => $(el).toggleClass("is-done", i < target));
        $(".pf-dot").each((i, el) => $(el).toggleClass("is-current", i === target).toggleClass("is-done", i < target)
            .attr("aria-current", i === target ? "step" : null));
        $("#pfBar").css("width", `${(100 * (target + 1)) / n}%`);
        $("#pfPrev").prop("disabled", target === 0);
        $("#pfNext").prop("disabled", target === n - 1);
        this.renderDetail();
        if (instant || this.reduced || Math.abs(target - from) !== 1) {
            this.placeToken(...this.anchor(target));
        } else {
            this.animateToken(Math.min(from, target), target > from);
        }
    },

    placeToken(x, y) {
        cancelAnimationFrame(this.frame);
        $("#pfToken").attr({ cx: x, cy: y });
    },

    /** Move the marker along the connector between step i and i + 1 (forwards or backwards). */
    animateToken(i, forward) {
        let pts = [this.anchor(i), ...this.route(i), this.anchor(i + 1)];
        if (!forward) pts = pts.reverse();
        const segs = pts.slice(1).map((p, k) => ({ from: pts[k], to: p, len: Math.hypot(p[0] - pts[k][0], p[1] - pts[k][1]) }));
        const total = segs.reduce((sum, s) => sum + s.len, 0);
        const duration = 900;
        const started = performance.now();
        cancelAnimationFrame(this.frame);
        const tick = (now) => {
            const t = Math.min(1, (now - started) / duration);
            let d = (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2) * total;  // ease in-out
            for (const s of segs) {
                if (d <= s.len || s === segs[segs.length - 1]) {
                    const k = s.len ? Math.min(1, d / s.len) : 1;
                    $("#pfToken").attr({ cx: s.from[0] + (s.to[0] - s.from[0]) * k, cy: s.from[1] + (s.to[1] - s.from[1]) * k });
                    break;
                }
                d -= s.len;
            }
            if (t < 1) this.frame = requestAnimationFrame(tick);
        };
        this.frame = requestAnimationFrame(tick);
    },

    play() {
        if (this.step === this.STEPS.length - 1) this.go(0, true);
        this.playing = true;
        $("#pfPlay").html('<i class="fas fa-pause me-2"></i>Pause');
        clearInterval(this.timer);
        this.timer = setInterval(() => {
            if (App.currentPage !== 'process') return this.stop();
            if (this.step >= this.STEPS.length - 1) return this.stop();
            this.go(this.step + 1);
        }, this.DWELL_MS);
    },

    stop() {
        this.playing = false;
        clearInterval(this.timer);
        $("#pfPlay").html('<i class="fas fa-play me-2"></i>Play');
    },

    renderDetail() {
        const s = this.STEPS[this.step];
        $("#pfDetail").html(`
            <div class="pf-detail__head">
                <span class="pf-detail__icon" aria-hidden="true"><i class="fas ${s.icon}"></i></span>
                <div>
                    <span class="kx-label">Step ${this.step + 1} of ${this.STEPS.length}</span>
                    <h2 class="pf-detail__title">${escapeHtml(s.title)}</h2>
                </div>
                ${this.figures[s.key] ? `<span class="pf-detail__live">${escapeHtml(this.figures[s.key])}</span>` : ''}
            </div>
            <div class="pf-detail__body">
                <div><h3>What happens</h3><ul>${s.what.map(w => `<li>${escapeHtml(w)}</li>`).join('')}</ul></div>
                <dl class="pf-facts">
                    <div><dt>Who</dt><dd>${escapeHtml(s.who)}</dd></div>
                    <div><dt>In KYRO</dt><dd><code>${escapeHtml(s.system)}</code></dd></div>
                    <div><dt>Recorded</dt><dd>${escapeHtml(s.recorded)}</dd></div>
                    <div><dt>Control</dt><dd>${escapeHtml(s.controls)}</dd></div>
                </dl>
            </div>`);
    },

    // ── Live figures on the diagram, where the data is at hand ──────────
    figures: {},

    async loadFigures() {
        const [summary, options, fx] = await Promise.all([
            API.get('/alerts/queue/summary').catch(() => null),
            API.get('/rules/options').catch(() => null),
            API.get('/rules/fx').catch(() => null),
        ]);
        const f = {};
        if (summary) {
            f.alert = `${summary.unresolved.toLocaleString()} unresolved alerts`;
            f.queue = `${summary.unassigned.toLocaleString()} unassigned · ${summary.overdue.toLocaleString()} overdue`;
            f.investigate = `${summary.awaiting_information.toLocaleString()} waiting on information`;
            f.decide = `${summary.escalated.toLocaleString()} escalated to the MLRO`;
        }
        if (options) {
            const on = [options.base_currency && 'base currency', options.noise_reduction && 'noise reduction', options.consolidate_daily && 'daily merge'].filter(Boolean);
            f.rules = on.length ? `Switches on: ${on.join(', ')}` : 'R1 switches: all off';
        }
        if (fx) f.ingest = `${Number(fx.transactions_without_base_amount).toLocaleString()} without a base amount`;
        this.figures = f;
        this.STEPS.forEach((s, i) => $(`#pfFig${i}`).text(f[s.key] || ''));
        this.renderDetail();
    }
};
