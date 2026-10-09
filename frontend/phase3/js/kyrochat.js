/**
 * KYRO Chat - a floating assistant available on every page. Ask Kyro about
 * the work queue, a customer, reviews, patterns or the regulations; every
 * answer is read from KYRO's live data, and when Kyro has no data for a
 * question it says so.
 */

const KyroChat = {
    speechEnabled: false,
    currentUtterance: null,
    customerCodes: null,   // display code (CUST-001) -> customer UUID
    mounted: false,

    /** Add the launcher button and the (closed) chat panel to the page, once. */
    mount() {
        if (this.mounted || document.getElementById("kyroWidget")) return;
        this.mounted = true;
        // Reading answers aloud is opt-in: a chat panel that talks by default is intrusive
        this.speechEnabled = localStorage.getItem("kyro_speech_enabled") === "true";
        $("body").append(`
            <div class="kw" id="kyroWidget">
                <section class="kw-panel" id="kyroPanel" role="dialog" aria-label="Ask Kyro" aria-hidden="true">
                    <header class="kw-head">
                        <img src="assets/Kyro1.png" alt="" class="kw-head__avatar" onerror="this.style.display='none'">
                        <div class="kw-head__text">
                            <strong>Ask Kyro</strong>
                            <small>Answers from KYRO's live data</small>
                        </div>
                        <button type="button" class="kw-icon" id="kwSpeech" aria-pressed="false" title="Read answers aloud"><i class="fas fa-volume-xmark"></i></button>
                        <button type="button" class="kw-icon" id="kwClear" title="Start a new conversation" aria-label="Start a new conversation"><i class="fas fa-rotate-right"></i></button>
                        <button type="button" class="kw-icon" id="kwClose" title="Close" aria-label="Close chat"><i class="fas fa-xmark"></i></button>
                    </header>
                    <div class="kc-messages kw-messages" id="kcMessages" aria-live="polite"></div>
                    <div class="kw-composer">
                        <div class="kc-suggestions kw-suggestions" id="kcSuggestions" aria-label="Suggested questions"></div>
                        <div class="kw-input">
                            <input type="text" id="kcInput" autocomplete="off" aria-label="Message Kyro" placeholder="Ask about the queue, a customer, a regulation...">
                            <button type="button" id="sendBtn" aria-label="Send message"><i class="fas fa-paper-plane" aria-hidden="true"></i></button>
                        </div>
                    </div>
                </section>
                <button type="button" class="kw-launcher" id="kyroLauncher" aria-expanded="false" aria-controls="kyroPanel" title="Ask Kyro">
                    <i class="fas fa-comment-dots" aria-hidden="true"></i>
                    <span class="visually-hidden">Ask Kyro</span>
                </button>
            </div>
        `);
        this.setupListeners();
        this.reset();
        this.syncSpeechButton();
    },

    SUGGESTIONS: [
        ["What needs my attention today?", "What needs my attention?"],
        ["Which open cases are high risk?", "High-risk cases"],
        ["Which periodic reviews are overdue?", "Overdue reviews"],
        ["Which patterns are firing?", "Patterns firing"],
        ["What are the suspicious activity reporting requirements for broker-dealers?", "SAR requirements"]
    ],

    /** Start a new conversation. */
    reset() {
        this.stopSpeaking();
        $("#kcMessages").empty();
        $("#kcSuggestions").removeClass("is-hidden").html(this.SUGGESTIONS.map(([prompt, label]) =>
            `<button type="button" class="kc-suggestion" data-prompt="${escapeHtml(prompt)}">${escapeHtml(label)}</button>`).join(''));
        this.addMessage("assistant",
            "Hi, I'm Kyro. Ask me what's waiting in the queue, about a customer (for example CUST-001), "
            + "which reviews are overdue, which patterns are firing, or what a regulation requires.");
    },

    isOpen() {
        return $("#kyroPanel").hasClass("is-open");
    },

    open() {
        this.mount();
        $("#kyroPanel").addClass("is-open").attr("aria-hidden", "false");
        $("#kyroLauncher").attr("aria-expanded", "true").addClass("is-open").find("i").attr("class", "fas fa-chevron-down");
        const el = document.getElementById("kcMessages");
        if (el) el.scrollTop = el.scrollHeight;
        setTimeout(() => $("#kcInput").trigger("focus"), 150);
    },

    close() {
        $("#kyroPanel").removeClass("is-open").attr("aria-hidden", "true");
        $("#kyroLauncher").attr("aria-expanded", "false").removeClass("is-open").find("i").attr("class", "fas fa-comment-dots");
        this.stopSpeaking();
    },

    syncSpeechButton() {
        $("#kwSpeech").attr("aria-pressed", String(this.speechEnabled))
            .attr("title", this.speechEnabled ? "Stop reading answers aloud" : "Read answers aloud")
            .find("i").attr("class", this.speechEnabled ? "fas fa-volume-high" : "fas fa-volume-xmark");
    },

    setupListeners() {
        $("#kyroLauncher").on("click", () => (this.isOpen() ? this.close() : this.open()));
        $("#kwClose").on("click", () => { this.close(); $("#kyroLauncher").trigger("focus"); });
        $("#kwClear").on("click", () => this.reset());
        $("#kwSpeech").on("click", () => {
            this.speechEnabled = !this.speechEnabled;
            localStorage.setItem("kyro_speech_enabled", String(this.speechEnabled));
            if (!this.speechEnabled) this.stopSpeaking();
            this.syncSpeechButton();
        });
        $("#kyroPanel").on("keydown", (e) => { if (e.key === "Escape") { this.close(); $("#kyroLauncher").trigger("focus"); } });
        $("#kcInput").on("keydown", (e) => {
            if (e.which === 13) { e.preventDefault(); this.sendMessage(); }
        });
        $("#sendBtn").on("click", () => this.sendMessage());
        $("#kcSuggestions").on("click", ".kc-suggestion", (e) => {
            $("#kcInput").val($(e.currentTarget).data("prompt"));
            this.sendMessage();
        });
        // Links inside answers open the relevant page; the chat stays open beside it
        $("#kcMessages").on("click", ".kc-link", (e) => {
            const $link = $(e.currentTarget);
            const params = $link.data("customer") ? { customer: $link.data("customer") } : {};
            App.navigateTo($link.data("goto"), params);
        });
    },

    async sendMessage() {
        const input = $("#kcInput").val().trim();
        if (!input) return;

        $("#kcInput").val("");
        $("#kcSuggestions").addClass("is-hidden");
        this.addMessage("user", input);

        const loadId = "kc-loading-" + Date.now();
        $("#kcMessages").append(`
            <div class="kc-msg kc-msg-bot" id="${loadId}">
                <img src="assets/Kyro1.png" class="kc-msg-avatar" alt="">
                <div class="kc-bubble kc-bubble-bot kc-typing" aria-label="Kyro is typing">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `);
        const el = document.getElementById("kcMessages");
        if (el) el.scrollTop = el.scrollHeight;

        let answer;
        try {
            answer = await this.answer(input);
        } catch (error) {
            console.error("Kyro answer failed:", error);
            answer = { html: "I couldn't reach KYRO's data just now. Please try again." };
        }
        $(`#${loadId}`).remove();
        this.addMessage("assistant", answer.html, answer.details ? { showViewDetails: true, caseDetails: answer.details } : {});
        this.speak(answer.speech || $("<div>").html(answer.html).text());
    },

    // ── Answering from live data ────────────────────────────────────────

    link(page, label, customer) {
        return `<button type="button" class="kc-link" data-goto="${page}"${customer ? ` data-customer="${escapeHtml(customer)}"` : ''}>${escapeHtml(label)} <i class="fas fa-arrow-right"></i></button>`;
    },

    n(value) { return Number(value || 0).toLocaleString(); },

    /** Route a question to the data that can answer it. */
    async answer(input) {
        const q = input.toLowerCase();
        const code = (input.match(/CUST-\d+/i) || [])[0];
        if (code) return this.answerCustomer(code.toUpperCase());

        if (this.REGULATORY_QUESTION.test(input)) {
            const regulatory = await this.askRegulatory(input);
            if (regulatory) return { html: regulatory.html, speech: regulatory.speech, details: regulatory.details };
        }
        if (/\breviews?\b|overdue|due diligence|kyc/.test(q)) return this.answerReviews();
        if (/pattern|velocity|threshold|geograph|counterpart|complexity|reactivation/.test(q)) return this.answerPatterns(q);
        if (/false.?positive|rule performance|tuning/.test(q)) return this.answerFalsePositives();
        if (/high.?risk|urgent|priorit/.test(q)) return this.answerHighRisk();
        if (/queue|backlog|alert|case|attention|today|unassigned|escalat|summar|status|workload/.test(q)) return this.answerQueue();

        const byName = await this.answerCustomerByName(input);
        if (byName) return byName;
        return {
            html: "I don't have data to answer that. I can tell you about the work queue, a customer (by name or ID such as CUST-001), "
                + "overdue reviews, the patterns that are firing, false-positive rates by rule, or what a loaded regulation requires."
        };
    },

    async answerQueue() {
        const s = await API.get('/alerts/queue/summary');
        if (!s.unresolved) return { html: "The queue is clear: there are no unresolved alerts." };
        const waiting = s.oldest_created_at ? Math.floor((Date.now() - new Date(s.oldest_created_at)) / 3600000) : null;
        const html = `There are <strong>${this.n(s.unresolved)}</strong> unresolved alerts across ${this.n(s.customers_with_alerts)} customers. `
            + `<strong>${this.n(s.high_risk)}</strong> are high risk, <strong>${this.n(s.unassigned)}</strong> have no owner and ${this.n(s.escalated)} ${s.escalated === 1 ? 'is' : 'are'} escalated.`
            + (waiting != null ? ` The oldest has waited ${waiting < 48 ? `${waiting} hours` : `${Math.floor(waiting / 24)} days`}.` : '')
            + `<div class="kc-reg-cites">${this.link('cases', 'Open the work queue')}</div>`;
        const details = `
            <div class="kc-reg-source"><div class="kc-reg-source__head"><strong>Customers with the most open alerts</strong></div>
                ${s.top_customers.map(c => `<p>${escapeHtml(c.customer_name)}: ${this.n(c.open_alerts)} open, highest score ${c.max_risk_score}</p>`).join('')}</div>
            <div class="kc-reg-source"><div class="kc-reg-source__head"><strong>Open alerts by rule</strong></div>
                ${s.by_rule.slice(0, 6).map(r => `<p>${escapeHtml(r.rule)} ${escapeHtml(this.ruleName(r.rule))}: ${this.n(r.alerts)}</p>`).join('')}</div>`;
        return { html, details };
    },

    async answerHighRisk() {
        const data = await API.get('/alerts/queue', { risk: 'high', page_size: 5 });
        if (!data.total) return { html: "No unresolved alert has a risk score of 80 or more right now." };
        const html = `<strong>${this.n(data.total)}</strong> unresolved alerts are high risk (score 80 or more). The top ${data.items.length}, highest score first, are in the details.`
            + `<div class="kc-reg-cites">${this.link('cases', 'Open the work queue')}</div>`;
        const details = data.items.map(a => `
            <div class="kc-reg-source">
                <div class="kc-reg-source__head"><strong>${escapeHtml(a.customer_name)}</strong><span>score ${a.risk_score}</span></div>
                <div class="kc-reg-source__meta">${escapeHtml(this.rulesText(a))} &middot; ${a.assigned_to_name ? `owner ${escapeHtml(a.assigned_to_name)}` : 'unassigned'}${a.customer_pep ? ' &middot; PEP' : ''}${a.customer_sanctions ? ' &middot; sanctions match' : ''}</div>
            </div>`).join('');
        return { html, details };
    },

    async answerReviews() {
        const [overdue, scheduled] = await Promise.all([
            API.get('/kyc-reviews', { review_status: 'OVERDUE', page_size: 1 }),
            API.get('/kyc-reviews', { page_size: 5000 })
        ]);
        const now = Date.now();
        const open = (scheduled.items || []).filter(r => r.review_status !== 'COMPLETED');
        const late = open.filter(r => new Date(r.scheduled_date || r.created_at) < now);
        const soon = open.filter(r => { const d = new Date(r.scheduled_date || r.created_at) - now; return d >= 0 && d <= 7 * 86400000; });
        const count = Math.max(late.length, Number(overdue.total || 0));
        if (!open.length) return { html: "No periodic reviews are scheduled." };
        return {
            html: `<strong>${this.n(count)}</strong> periodic reviews are past their review date and <strong>${this.n(soon.length)}</strong> more are due in the next 7 days, out of ${this.n(open.length)} scheduled.`
                + `<div class="kc-reg-cites">${this.link('periodic-reviews', 'Open Periodic Reviews')}</div>`
        };
    },

    async answerPatterns(q) {
        const data = await API.get('/dashboard/patterns');
        const patterns = data.patterns || [];
        const named = patterns.find(p => q.includes(p.label.toLowerCase().split(' ')[0]));
        if (named) {
            return {
                html: `<strong>${escapeHtml(named.label)}</strong>: ${escapeHtml(named.description)} `
                    + (named.customers ? `In the last ${data.window_days} days <strong>${this.n(named.customers)}</strong> customer${named.customers === 1 ? ' shows' : 's show'} it (${this.n(named.hit_count)} ${escapeHtml(named.hit_unit)}).`
                                       : `No customer shows it in the last ${data.window_days} days.`)
                    + `<div class="kc-reg-cites">${this.link('patterns', 'Open Patterns')}</div>`
            };
        }
        const active = patterns.filter(p => p.customers > 0).sort((a, b) => b.customers - a.customers);
        if (!active.length) return { html: `No customer's behaviour in the last ${data.window_days} days departs from their previous ${data.baseline_days} days.` };
        return {
            html: `<strong>${this.n(data.customers_affected)}</strong> of ${this.n(data.customers_active)} active customers behaved differently in the last ${data.window_days} days than in their previous ${data.baseline_days}. `
                + `The most common change is <strong>${escapeHtml(active[0].label)}</strong>, for ${this.n(active[0].customers)} customers.`
                + `<div class="kc-reg-cites">${this.link('patterns', 'Open Patterns')}</div>`,
            details: active.map(p => `<div class="kc-reg-source"><div class="kc-reg-source__head"><strong>${escapeHtml(p.label)}</strong><span>${this.n(p.customers)} customers</span></div><p>${escapeHtml(p.description)}</p></div>`).join('')
        };
    },

    async answerFalsePositives() {
        let data;
        try {
            data = await API.get('/alerts/disposition-baseline', { days: 90 });
        } catch (xhr) {
            return { html: "False-positive rates are available to compliance officers and admins." };
        }
        const o = data.overall;
        if (!o.resolved) {
            return { html: `No alerts have been resolved in the last ${data.window_days} days, so there is no false-positive rate yet. It will appear once outcomes are recorded with the Resolve action.` };
        }
        const rated = data.by_rule.filter(r => r.false_positive_rate != null).sort((a, b) => b.false_positive_rate - a.false_positive_rate);
        return {
            html: `Of ${this.n(o.resolved)} alerts resolved in the last ${data.window_days} days, <strong>${(o.false_positive_rate * 100).toFixed(0)}%</strong> were false positives.`
                + `<div class="kc-reg-cites">${this.link('cases', 'See the baseline on Review Cases')}</div>`,
            details: rated.map(r => `<div class="kc-reg-source"><div class="kc-reg-source__head"><strong>${escapeHtml(r.rule)} ${escapeHtml(this.ruleName(r.rule))}</strong><span>${(r.false_positive_rate * 100).toFixed(0)}% of ${this.n(r.resolved)} resolved</span></div></div>`).join('')
        };
    },

    async loadCustomerCodes() {
        if (this.customerCodes) return;
        const response = await API.get("/customers", { page_size: 10000 });
        this.customerCodes = {};
        this.customerList = response.items || [];
        this.customerList.forEach((c, idx) => { this.customerCodes[`CUST-${String(idx + 1).padStart(3, '0')}`] = c.id; });
    },

    async answerCustomer(code) {
        await this.loadCustomerCodes();
        const id = this.customerCodes[code];
        if (!id) return { html: `I can't find a customer with the ID ${escapeHtml(code)}.` };
        return this.customerSummary(id, code);
    },

    /** A question that is just a customer's name (or contains one). */
    async answerCustomerByName(input) {
        await this.loadCustomerCodes();
        const q = input.toLowerCase();
        const idx = this.customerList.findIndex(c => c.full_name && c.full_name.length > 3 && q.includes(c.full_name.toLowerCase()));
        if (idx < 0) return null;
        return this.customerSummary(this.customerList[idx].id, `CUST-${String(idx + 1).padStart(3, '0')}`);
    },

    async customerSummary(id, code) {
        const [customer, queue, profile] = await Promise.all([
            API.get(`/customers/${id}`),
            API.get('/alerts/queue', { customer_id: id, page_size: 5 }),
            API.get(`/customers/${id}/risk-profile`).catch(() => [])
        ]);
        const flags = [customer.pep_flag ? 'a PEP' : null, customer.sanctions_flag ? 'a sanctions match' : null, customer.adverse_media_flag ? 'adverse media' : null].filter(Boolean);
        const human = (v) => String(v || 'not set').replace(/_/g, ' ').toLowerCase();
        const html = `<strong>${escapeHtml(customer.full_name)}</strong> (${escapeHtml(code)}) is rated <strong>${escapeHtml(human(customer.risk_level))}</strong> risk with KYC status ${escapeHtml(human(customer.kyc_status))}. `
            + (flags.length ? `Flagged as ${escapeHtml(flags.join(' and '))}. ` : 'No PEP, sanctions or adverse-media flags. ')
            + (queue.total ? `There ${queue.total === 1 ? 'is' : 'are'} <strong>${this.n(queue.total)}</strong> unresolved alert${queue.total === 1 ? '' : 's'}; the highest score is ${queue.items[0].risk_score}.`
                           : 'There are no unresolved alerts.')
            + (queue.total ? `<div class="kc-reg-cites">${this.link('cases', 'Review this customer\'s cases', code)}</div>` : '');
        const why = profile.length ? `
            <div class="kc-reg-source">
                <div class="kc-reg-source__head"><strong>Why this rating (score ${customer.risk_score})</strong></div>
                ${profile.map(f => `<p>${escapeHtml(f.risk_factor)}: +${Number(f.risk_weight)}</p>`).join('')}
            </div>` : '';
        const details = why + queue.items.map(a => `
            <div class="kc-reg-source">
                <div class="kc-reg-source__head"><strong>Alert score ${a.risk_score}</strong><span>${escapeHtml(human(a.status))}</span></div>
                <div class="kc-reg-source__meta">${escapeHtml(this.rulesText(a))} &middot; created ${escapeHtml(formatDateTime(a.created_at))}</div>
            </div>`).join('');
        return { html, details: details || null };
    },

    ruleName(code) {
        return typeof Cases !== 'undefined' && Cases.RULES && Cases.RULES[code] ? Cases.RULES[code][0] : '';
    },

    rulesText(alert) {
        const codes = (alert.triggered_rules && (alert.triggered_rules.rules || alert.triggered_rules)) || [];
        const names = (Array.isArray(codes) ? codes : []).map(c => this.ruleName(c) || c);
        return names.length ? names.join(', ') : 'no rule recorded';
    },

    addMessage(role, content, options = {}) {
        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const isUser = role === "user";
        const detailsId = 'details-' + Date.now() + '-' + Math.floor(Math.random() * 1000);

        let html;
        if (isUser) {
            html = `<div class="kc-msg kc-msg-user">
                <div class="kc-bubble kc-bubble-user">
                    <div class="kc-msg-text">${escapeHtml(content)}</div>
                    <div class="kc-msg-time kc-time-user">${timestamp}</div>
                </div>
               </div>`;
        } else {
            // Check if this message should have expandable details
            if (options.showViewDetails && options.caseDetails) {
                html = `<div class="kc-msg kc-msg-bot">
                    <img src="assets/Kyro1.png" class="kc-msg-avatar" alt=""
                         onerror="this.style.display='none'">
                    <div class="kc-bubble kc-bubble-bot">
                        <div class="kc-msg-text">${content}</div>
                        <div class="kc-view-details" data-details-id="${detailsId}">
                            <span class="kc-view-details-icon">▼</span> View details
                        </div>
                        <div class="kc-case-details" id="${detailsId}" style="display:none;">
                            ${options.caseDetails}
                        </div>
                        <div class="kc-msg-time kc-time-bot">${timestamp}</div>
                    </div>
                   </div>`;
            } else {
                html = `<div class="kc-msg kc-msg-bot">
                    <img src="assets/Kyro1.png" class="kc-msg-avatar" alt=""
                         onerror="this.style.display='none'">
                    <div class="kc-bubble kc-bubble-bot">
                        <div class="kc-msg-text">${content}</div>
                        <div class="kc-msg-time kc-time-bot">${timestamp}</div>
                    </div>
                   </div>`;
            }
        }

        $("#kcMessages").append(html);
        
        // Setup click handler for view details toggle
        if (!isUser && options.showViewDetails) {
            $(`[data-details-id="${detailsId}"]`).on('click', function() {
                const $details = $(`#${detailsId}`);
                const $icon = $(this).find('.kc-view-details-icon');
                
                if ($details.is(':visible')) {
                    $details.slideUp(200);
                    $icon.text('▼');
                    $(this).removeClass('expanded');
                } else {
                    $details.slideDown(200);
                    $icon.text('▲');
                    $(this).addClass('expanded');
                }
            });
        }
        
        const el = document.getElementById("kcMessages");
        if (el) el.scrollTop = el.scrollHeight;
    },

    // Words that mark a question about regulations rather than about cases or data
    REGULATORY_QUESTION: /\b(regulat\w*|cfr|finra|fincen|bsa|sar|ctr|cip|requirements?|required|obligations?|must|beneficial owner\w*|recordkeeping|retain\w*|retention|threshold|suspicious|customer identification|due diligence|currency transaction\w*)\b|§/i,

    /**
     * Asks the regulatory knowledge base. Returns null when nothing relevant is
     * loaded, so the caller can fall back to the other chat answers.
     */
    async askRegulatory(question) {
        let result;
        try {
            result = await API.post('/regulatory/ask', { question });
        } catch (error) {
            return null;
        }
        if (!result || result.mode === 'NOT_FOUND' || !result.sources.length) return null;

        // One entry per cited section, in ranked order
        const sections = [];
        result.sources.forEach(s => { if (!sections.some(x => x.source_ref === s.source_ref)) sections.push(s); });
        const cited = result.citations.length ? sections.filter(s => result.citations.includes(s.source_ref)) : sections;
        const shown = (cited.length ? cited : sections).slice(0, 3);
        const refs = shown.map(s => s.source_ref).join(', ');

        let html, speech;
        if (result.mode === 'GENERATED') {
            html = `${escapeHtml(result.answer)}<div class="kc-reg-cites">${result.verified
                ? `Sources: ${escapeHtml(refs)}`
                : 'Unverified: this answer could not be tied to a loaded source. Check the passages below.'}</div>`;
            speech = result.answer;
        } else {
            html = `I found this in the regulatory sources: <strong>${escapeHtml(refs)}</strong>. `
                + `AI summarisation is off, so open the details to read the source text.`;
            speech = `I found this in ${refs}. Open the details to read the source text.`;
        }

        const details = shown.map(s => `
            <div class="kc-reg-source">
                <div class="kc-reg-source__head">
                    <strong>${escapeHtml(s.source_ref)}</strong>
                    <span>${escapeHtml(s.title || '')}</span>
                </div>
                <div class="kc-reg-source__meta">
                    As amended ${escapeHtml(s.version)}${/^https:\/\//.test(s.url || '')
                        ? ` &middot; <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">Open on eCFR</a>` : ''}
                </div>
                <p>${escapeHtml(s.excerpt.length > 700 ? s.excerpt.slice(0, 700) + '…' : s.excerpt)}</p>
            </div>`).join('');

        return { html, speech, details };
    },

    speechQueue: [],
    isSpeakingProcessing: false,

    speak(text) {
        if (!this.speechEnabled) return Promise.resolve();

        const cleanText = text.replace(/[*•]/g, "").replace(/\n+/g, ". ").trim();
        if (!cleanText) return Promise.resolve();

        return new Promise((resolve) => {
            this.speechQueue.push({ text: cleanText, resolve });
            this._processSpeechQueue();
        });
    },

    async _processSpeechQueue() {
        if (this.isSpeakingProcessing || this.speechQueue.length === 0) return;
        this.isSpeakingProcessing = true;

        const currentItem = this.speechQueue.shift();
        try {
            await this._speakSingleText(currentItem.text);
        } catch (err) {
            console.error("Speech queue error:", err);
        } finally {
            currentItem.resolve();
            this.isSpeakingProcessing = false;
            if (this.speechQueue.length > 0) {
                this._processSpeechQueue();
            }
        }
    },

    _speakSingleText(cleanText) {
        // Show speaking state immediately
        this._setSpeakingState(true);

        // Pre-create Audio element immediately in current event loop
        const audio = new Audio();
        audio.volume = 1.0;
        this._currentAudio = audio;

        return new Promise((resolve) => {
            // Try backend TTS with ElevenLabs
            fetch(`${API.baseUrl}/tts/speak`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${localStorage.getItem("access_token") || ""}`
                },
                body: JSON.stringify({ text: cleanText })
            })
            .then(res => {
                if (!res.ok) {
                    console.warn(`TTS API unavailable (${res.status}), using browser TTS`);
                    throw new Error(`TTS API ${res.status}`);
                }
                return res.blob();
            })
            .then(blob => {
                const url = URL.createObjectURL(blob);
                audio.src = url;

                audio.onended = () => {
                    URL.revokeObjectURL(url);
                    this._setSpeakingState(false);
                    this._currentAudio = null;
                    resolve();
                };
                audio.onerror = (err) => {
                    console.error("Audio playback error:", err);
                    URL.revokeObjectURL(url);
                    this._setSpeakingState(false);
                    this._currentAudio = null;
                    // Fallback to browser TTS
                    this._browserSpeak(cleanText, resolve);
                };

                audio.play().catch((err) => {
                    console.error("Audio play failed:", err);
                    URL.revokeObjectURL(url);
                    this._currentAudio = null;
                    // Fallback to browser TTS
                    this._browserSpeak(cleanText, resolve);
                });
            })
            .catch((err) => {
                console.log("Falling back to browser TTS:", err.message);
                this._browserSpeak(cleanText, resolve);
            });
        });
    },

    stopSpeaking() {
        this.speechQueue = [];
        this.isSpeakingProcessing = false;
        // Stop API audio
        if (this._currentAudio) {
            this._currentAudio.pause();
            this._currentAudio = null;
        }
        // Stop browser TTS
        if (window.speechSynthesis) window.speechSynthesis.cancel();
        this.currentUtterance = null;
        this._setSpeakingState(false);
    },

    _setSpeakingState(speaking) {
        $("#kwSpeech").toggleClass("is-speaking", !!speaking);
    },

    _browserSpeak(text, resolveCallback) {
        console.log("🔊 Browser TTS starting:", text.substring(0, 50));
        
        if (!window.speechSynthesis) {
            console.error("❌ Speech synthesis not supported in this browser");
            if (resolveCallback) resolveCallback();
            return;
        }
        
        const utterance = new SpeechSynthesisUtterance(text);
        this.currentUtterance = utterance;
        
        // Wait for voices to load
        let voices = window.speechSynthesis.getVoices();
        if (!voices.length) {
            console.log("⏳ Waiting for voices to load...");
            window.speechSynthesis.onvoiceschanged = () => {
                voices = window.speechSynthesis.getVoices();
                console.log(`✓ Loaded ${voices.length} voices`);
            };
            voices = window.speechSynthesis.getVoices();
        }
        
        const v = voices.find(v => v.lang.includes("en-US") || v.lang.includes("en-GB")) || voices[0];
        if (v) {
            utterance.voice = v;
            console.log(`🎤 Using voice: ${v.name} (${v.lang})`);
        }
        
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        utterance.volume = 1.0;
        
        utterance.onstart = () => {
            console.log("▶️ Speech started");
            this._setSpeakingState(true);
        };
        utterance.onend = () => {
            console.log("⏹️ Speech ended");
            this._setSpeakingState(false);
            if (resolveCallback) resolveCallback();
        };
        utterance.onerror = (e) => {
            console.error("❌ Speech error:", e);
            this._setSpeakingState(false);
            if (resolveCallback) resolveCallback();
        };
        
        window.speechSynthesis.speak(utterance);
        console.log("✓ Speech queued");
    }
};

// Initialize speech synthesis
if (typeof speechSynthesis !== 'undefined' && speechSynthesis.onvoiceschanged !== undefined) {
    speechSynthesis.onvoiceschanged = () => {};
}

// Cleanup on page unload
$(window).on("beforeunload", () => {
    KyroChat.stopSpeaking();
});

window.KyroChat = KyroChat;

// The assistant is part of the application shell: available on every page once signed in
$(document).ready(() => {
    try {
        if (localStorage.getItem("access_token")) KyroChat.mount();
    } catch (e) { /* storage unavailable: no widget */ }
});
