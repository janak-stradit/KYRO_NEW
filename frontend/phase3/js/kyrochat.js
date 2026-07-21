/**
 * KYRO Chat - AI Powered AML Agent Page Implementation
 * Handles autonomous operations, state sync, and interactive chat interface.
 */

const KyroChat = {
    messages: [],
    statusPollInterval: null,
    speechEnabled: true,
    currentUtterance: null,
    currentCaseContext: null, // Track current case being discussed
    agentState: {
        autonomous_status: "STOPPED",
        intervention_needed: false,
        processing_cases_count: 20,
        next_cycle_eta_sec: 30,
        latest_action_label: "Standby",
        streaming_pulse_label: "Ready to screen cases when autonomous execution starts.",
        run_stats: {
            actions: 0,
            success: 0,
            failure: 0,
            casesTouched: 0
        }
    },

    async init() {
        console.log("🤖 Initializing Kyro Chat interface...");
        this.messages = [];
        this.speechEnabled = localStorage.getItem("kyro_speech_enabled") !== "false";
        
        // Render page template
        this.renderLayout();
        
        // Fetch initial welcome message
        await this.loadWelcomeMessage();
        
        // Fetch initial state & populate components
        await this.fetchAgentState();
        
        // Setup event handlers
        this.setupListeners();
        
        // Start periodic state polling (every 4 seconds)
        this.startPolling();
    },

    renderLayout() {
            const html = `
            <div class="kc-wrapper bg-[#F9FBFF]">

                <!-- Page Title -->
                <div class="kc-page-header max-w-7xl mx-auto px-6">
                    <div class="kc-page-icon"><i class="fas fa-comment-dots"></i></div>
                    <div>
                        <h2 class="kc-page-title">Kyro - AI powered AML agent</h2>
                        <p class="kc-page-subtitle">Chat with AI &bull; Autonomous operations &bull; Background compliance automation</p>
                    </div>
                </div>

                <!-- Main two-col layout -->
                <div class="kc-layout max-w-7xl mx-auto px-6 py-8">

                    <!-- ── LEFT: single bordered card ── -->
                    <div class="kc-left-panel">
                    <div class="kc-main-card">

                        <!-- Agent info row -->
                        <div class="kc-agent-card">
                            <img src="assets/Kyro1.png" class="kc-agent-avatar" alt="Kyro"
                                 onerror="this.style.display='none'">
                            <div class="kc-agent-info">
                                <div class="kc-agent-name-row">
                                    <span class="kc-agent-name">Kyro &nbsp;– AI powered AML agent</span>
                                    <span class="kc-v-badge">v2.0</span>
                                </div>
                                <div class="kc-neural">✦ Neural network active</div>
                                <span class="kc-state-pill" id="kcStateBadge">STOPPED</span>
                                <p class="kc-agent-desc">Kyro monitors compliance, executes actions, and requests human help when needed.</p>
                            </div>
                        </div>

                        <!-- Live status box (inset, grey bg) -->
                        <div class="kc-status-card" id="kcStatusCard">
                            <div class="kc-status-row">
                                <div class="kc-status-lhs">
                                    <span class="kc-live-dot" id="kcLiveDot"></span>
                                    <span class="kc-status-label" id="kcStatusLabel">Kyro Live &bull; STOPPED</span>
                                </div>
                                <span class="kc-sync-time" id="kcSyncTime">Synced --</span>
                            </div>
                            <div class="kc-processing">Processing now: <strong id="kcProcessingCount">20 cases</strong></div>
                            <div class="kc-pulse-label" id="kcPulseLabel">
                                Ready to screen when you start Kyro.<br>
                                Ready to screen cases when autonomous execution starts.
                            </div>
                        </div>

                        <!-- Run stats (hidden until RUNNING) -->
                        <div class="kc-stats-card" id="kcStatsCard" style="display:none;">
                            <div class="kc-stats-title">Run Statistics</div>
                            <div class="kc-stats-grid">
                                <div><div class="kc-sl">Actions</div><div class="kc-sv" id="kcStatActions">0</div></div>
                                <div><div class="kc-sl">Success</div><div class="kc-sv kc-sv-ok" id="kcStatSuccess">0</div></div>
                                <div><div class="kc-sl">Failure</div><div class="kc-sv kc-sv-err" id="kcStatFailure">0</div></div>
                                <div><div class="kc-sl">Cases</div><div class="kc-sv" id="kcStatCases">0</div></div>
                            </div>
                        </div>

                        <!-- Chat messages -->
                        <div class="kc-messages" id="kcMessages"></div>

                        <!-- Notices -->
                        <div class="kc-notice kc-notice-int"  id="kcInterventionNotice" style="display:none;">
                            ⚠️ Human intervention required — Kyro is waiting for guidance.
                        </div>
                        <div class="kc-notice kc-notice-auto" id="kcAutonomousNotice" style="display:none;">
                            🟢 Autonomous mode active — monitoring compliance events.
                        </div>

                        <!-- Control buttons -->
                        <div class="kc-controls">
                            <button class="kc-btn kc-btn-start"   id="startBtn">Start Kyro</button>
                            <button class="kc-btn kc-btn-pause"   id="pauseBtn"   style="display:none;">Pause Kyro</button>
                            <button class="kc-btn kc-btn-resume"  id="resumeBtn"  style="display:none;">Resume Kyro</button>
                            <button class="kc-btn kc-btn-stop"    id="stopBtn"    style="display:none;">Stop Kyro</button>
                            <button class="kc-btn kc-btn-handoff" id="handoffBtn" style="display:none;">Handoff</button>
                        </div>

                        <!-- Instruction -->
                        <p class="kc-instruction" id="kcInstruction">
                            Click <strong>Start Kyro</strong> to begin automated monitoring.
                        </p>

                        <!-- Input row -->
                        <div class="kc-input-row">
                            <input type="text" class="kc-input" id="kcInput"
                                   placeholder="Ask about cases, transactions, compliance...">
                            <button class="kc-send-btn" id="sendBtn">
                                <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                          d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/>
                                </svg>
                            </button>
                        </div>

                    </div><!-- /kc-main-card -->
                    </div><!-- /kc-left-panel -->

                    <!-- ── RIGHT: video character — paused idle, plays on speak ── -->
                    <div class="kc-right-panel">
                        <div class="kc-video-card">
                            <div class="kc-idle-pill" id="kcIdlePill">
                                <span class="kc-idle-dot" id="kcIdleDot"></span>
                                <span id="kcIdleText">IDLE</span>
                            </div>
                            <video class="kc-char-video" id="kyroCharVideo"
                                   muted loop playsinline preload="auto">
                                <source src="assets/kyrochat.mp4" type="video/mp4">
                            </video>
                        </div>
                    </div>

                </div><!-- /kc-layout -->
            </div><!-- /kc-wrapper -->
            `;
            $("#mainContent").html(html);
        },

    async loadWelcomeMessage() {
        try {
            // Add welcome message using kyroScripts
            this.addMessage("assistant", kyroScripts.welcome.full);
        } catch (error) {
            console.error("Welcome message setup failed:", error);
        }
    },

    async fetchAgentState() {
        try {
            // Mock state for demo - in production this would call API
            this.agentState = {
                autonomous_status: "STOPPED",
                intervention_needed: false,
                processing_cases_count: 20,
                next_cycle_eta_sec: 30,
                latest_action_label: "Standby",
                streaming_pulse_label: "Ready to screen cases when autonomous execution starts.",
                run_stats: {
                    actions: 0,
                    success: 0,
                    failure: 0,
                    casesTouched: 0
                }
            };
            this.updateStateUI();
        } catch (error) {
            console.error("Agent state fetch failed:", error);
        }
    },

    updateStateUI() {
        if (!document.getElementById("kcStatusCard")) return;

        const status = this.agentState.autonomous_status || "STOPPED";
        const isIntervention = this.agentState.intervention_needed || false;

        // Sync time
        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        $("#kcSyncTime").text(`Synced ${timeStr}`);

        // Status label
        $("#kcStatusLabel").text(`Kyro Live • ${status}`);
        $("#kcStateBadge").text(status);

        // Processing count
        $("#kcProcessingCount").text(`${this.agentState.processing_cases_count || 0} cases`);

        // Pulse label
        $("#kcPulseLabel").html((this.agentState.streaming_pulse_label || "Ready to screen cases when autonomous execution starts.").replace(/\n/g, "<br>"));

        // Status card bg + dot color
        const styles = {
            RUNNING: { bg: "#f0fdf4", border: "#bbf7d0", dotColor: "#22c55e", badgeBg: "#22c55e" },
            PAUSED:  { bg: "#fffbeb", border: "#fde68a", dotColor: "#f59e0b", badgeBg: "#f59e0b" },
            ERROR:   { bg: "#fef2f2", border: "#fecaca", dotColor: "#ef4444", badgeBg: "#ef4444" },
            STOPPED: { bg: "#f8fafc", border: "#e2e8f0", dotColor: "#94a3b8", badgeBg: "#64748b" }
        };
        const s = styles[status] || styles.STOPPED;
        $("#kcStatusCard").css({ background: s.bg, "border-color": s.border });
        $("#kcLiveDot").css("background-color", s.dotColor);
        $("#kcStateBadge").css("background-color", s.badgeBg);

        // Idle pill on right panel
        $("#kcIdleDot").css("background-color", s.dotColor);
        $("#kcIdleText").text(status === "RUNNING" ? "RUNNING" : status === "PAUSED" ? "PAUSED" : "IDLE");

        // Buttons
        $("#startBtn, #pauseBtn, #resumeBtn, #stopBtn, #handoffBtn").hide();
        if (status === "STOPPED")       { $("#startBtn").show(); }
        else if (status === "RUNNING")  { $("#pauseBtn, #stopBtn, #handoffBtn").show(); }
        else if (status === "PAUSED")   { $("#resumeBtn, #stopBtn").show(); }

        // Instruction text
        const instrMap = {
            RUNNING: kyroScripts.instructions.running,
            PAUSED: kyroScripts.instructions.paused
        };
        $("#kcInstruction").html(
            isIntervention ? kyroScripts.instructions.intervention
            : (instrMap[status] || kyroScripts.instructions.stopped)
        );

        // Notices
        $("#kcInterventionNotice").toggle(isIntervention);
        $("#kcAutonomousNotice").toggle(status === "RUNNING" && !isIntervention);

        // Run stats (show only when RUNNING and hide when STOPPED)
        if (status === "RUNNING") {
            const rs = this.agentState.run_stats || {};
            $("#kcStatsCard").show();
            $("#kcStatActions").text(rs.actions || 0);
            $("#kcStatSuccess").text(rs.success || 0);
            $("#kcStatFailure").text(rs.failure || 0);
            $("#kcStatCases").text(rs.casesTouched || 0);
        } else {
            $("#kcStatsCard").hide();
        }

        // Connection indicator (reuse spinner if present)
        $("#connectionSpinner").hide();
        $("#connectionText").text("Connected");

        // Removed matchVideoHeight() call to prevent zoom
    },


    addMessage(role, content, options = {}) {
        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const isUser = role === "user";
        const detailsId = 'details-' + Date.now() + '-' + Math.floor(Math.random() * 1000);

        let html;
        if (isUser) {
            html = `<div class="kc-msg kc-msg-user">
                <div class="kc-bubble kc-bubble-user">
                    <div class="kc-msg-text">${content}</div>
                    <div class="kc-msg-time kc-time-user">${timestamp}</div>
                </div>
               </div>`;
        } else {
            // Check if this message should have expandable details
            if (options.showViewDetails && options.caseDetails) {
                html = `<div class="kc-msg kc-msg-bot">
                    <img src="assets/Kyro1.png" class="kc-msg-avatar" alt="Kyro"
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
                    <img src="assets/Kyro1.png" class="kc-msg-avatar" alt="Kyro"
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

    setupListeners() {
        const self = this;

        // Send on Enter
        $("#kcInput").on("keydown", function(e) {
            if (e.which === 13) { e.preventDefault(); self.sendMessage(); }
        });

        // Send button
        $("#sendBtn").on("click", () => this.sendMessage());

        // Control buttons
        $("#startBtn").on("click",   () => this.startAgent());
        $("#pauseBtn").on("click",   () => this.pauseAgent());
        $("#resumeBtn").on("click",  () => this.resumeAgent());
        $("#stopBtn").on("click",    () => this.stopAgent());
        $("#handoffBtn").on("click", () => this.requestHandoff());

        // Match video card height to left panel
        this.matchVideoHeight();
        $(window).on("resize", () => this.matchVideoHeight());
    },

    matchVideoHeight() {
        // Disabled to prevent unwanted zoom/resize on state updates
        // Video card will maintain its natural height based on CSS grid
        return;
    },

    startPolling() {
        this.statusPollInterval = setInterval(async () => {
            if (App.getCurrentPage() === "kyrochat") {
                await this.fetchAgentState();
            } else {
                this.stopPolling();
            }
        }, 4000);
    },

    stopPolling() {
        if (this.statusPollInterval) {
            clearInterval(this.statusPollInterval);
            this.statusPollInterval = null;
        }
    },

    async sendMessage() {
        const input = $("#kcInput").val().trim();
        if (!input) return;

        $("#kcInput").val("");
        this.addMessage("user", input);

        // Loading indicator
        const loadId = "kc-loading-" + Date.now();
        $("#kcMessages").append(`
            <div class="kc-msg kc-msg-bot" id="${loadId}">
                <div class="kc-bubble kc-bubble-bot">
                    <span class="spinner-border spinner-border-sm text-secondary me-2" style="width:10px;height:10px;"></span>
                    <span style="font-size:12px;color:#64748b;">Kyro is typing...</span>
                </div>
            </div>
        `);
        const el = document.getElementById("kcMessages");
        if (el) el.scrollTop = el.scrollHeight;

        try {
            await new Promise(r => setTimeout(r, 1200));
            $(`#${loadId}`).remove();

            let response = "";
            let messageOptions = {};
            const q = input.toLowerCase();
            
            // Check if user is asking about a specific case
            const caseIdMatch = input.match(/CUST-(\d+)/i);
            if (caseIdMatch) {
                const caseId = `CUST-${caseIdMatch[1]}`;
                // Store the case context for potential handoff
                this.currentCaseContext = this.generateCustomerCaseDetail(caseId);
                response = this.getCaseDetailsResponse(caseId, this.currentCaseContext);
                messageOptions = {
                    showViewDetails: true,
                    caseDetails: this.formatCaseDetailsHTML(this.currentCaseContext)
                };
            }
            // Use kyroScripts for other responses
            else if (q.includes("case") || q.includes("alert") || q.includes("backlog")) {
                response = kyroScripts.chat.caseInfo(20, 3);
            } else if (q.includes("transaction")) {
                response = kyroScripts.chat.transactionInfo(5);
            } else if (q.includes("risk")) {
                response = kyroScripts.chat.riskInfo(15, 87);
            } else if (q.includes("model") || q.includes("ml")) {
                response = kyroScripts.chat.modelInfo("Random Forest v2.1", 94.8, 91.2);
            } else if (q.includes("hello") || q.includes("hi")) {
                response = kyroScripts.chat.greeting;
            } else if (q.includes("summary")) {
                response = kyroScripts.chat.caseSummary(120, 85, 20, 15);
            } else {
                response = kyroScripts.chat.defaultResponse;
            }

            this.addMessage("assistant", response, messageOptions);
            this.speak(response);
        } catch (err) {
            $(`#${loadId}`).remove();
            this.addMessage("assistant", kyroScripts.errors.unknown);
        }
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

    async startAgent() {
        try {
            // Full welcome message requested by user
            const welcomeMessage = kyroScripts.welcome.full;
            
            // Speak the welcome message immediately when Start button is pressed
            await this.speak(welcomeMessage);
            
            // Update state
            this.agentState.autonomous_status = "RUNNING";
            this.agentState.streaming_pulse_label = "Actively screening transactions and monitoring compliance events";
            this.agentState.run_stats = { 
                actions: 1, 
                success: 1, 
                failure: 0, 
                casesTouched: 5 
            };
            this.updateStateUI();
            
            showToast("success", "Kyro is now running autonomously");
            
            // Simulate progressive stats update & actions
            this.startStatsSimulation();
            
        } catch (error) {
            console.error(error);
            showToast("error", "Failed to start agent");
            this.addMessage("assistant", kyroScripts.autonomous.start.failure("system error"));
        }
    },

    startStatsSimulation() {
        // Clear any existing simulation
        if (this.statsSimulationInterval) {
            clearInterval(this.statsSimulationInterval);
        }
        
        // Predefined actions that Kyro will perform
        const actions = [
            { type: "reduce_backlog", msg: kyroScripts.actions.reduce_backlog.start },
            { type: "assign_priority", msg: kyroScripts.actions.assign_priority_cases.start },
            { type: "process_low_risk", msg: kyroScripts.actions.process_low_risk_cases.start },
            { type: "escalation_review", msg: kyroScripts.actions.resolve_escalated_cases.start },
            { type: "anomaly_detection", msg: kyroScripts.actions.trigger_behavior_reviews.start },
            { type: "false_positive_analysis", msg: kyroScripts.actions.analyze_false_positives.start }
        ];
        
        let actionIndex = 0;
        
        // Async function to perform action
        const performAction = async () => {
            if (this.agentState.autonomous_status !== "RUNNING") {
                clearInterval(this.statsSimulationInterval);
                return;
            }
            
            // Select action
            const action = actions[actionIndex % actions.length];
            actionIndex++;
            
            // Add action start message to chat and speak it completely
            this.addMessage("assistant", action.msg);
            await this.speak(action.msg);
            
            // Update stats
            this.agentState.run_stats.actions += 1;
            const isSuccess = Math.random() > 0.15; // 85% success rate
            
            // Wait for action to "complete"
            await new Promise(resolve => setTimeout(resolve, 2000));
            
            if (isSuccess) {
                this.agentState.run_stats.success += 1;
                const casesProcessed = Math.floor(Math.random() * 5) + 3; // 3-7 cases
                this.agentState.run_stats.casesTouched += casesProcessed;
                
                let resultMsg = "";
                let messageOptions = {};
                
                if (action.type === "reduce_backlog") {
                    const resolved = Math.floor(casesProcessed * 0.6);
                    const escalated = Math.floor(casesProcessed * 0.3);
                    resultMsg = kyroScripts.actions.reduce_backlog.success(casesProcessed, resolved, escalated);
                    
                    // Generate case details for backlog analysis
                    messageOptions = {
                        showViewDetails: true,
                        caseDetails: this.generateCaseDetails(casesProcessed, resolved, escalated)
                    };
                } else if (action.type === "assign_priority") {
                    resultMsg = kyroScripts.actions.assign_priority_cases.success(casesProcessed);
                } else if (action.type === "process_low_risk") {
                    resultMsg = kyroScripts.actions.process_low_risk_cases.success(casesProcessed);
                } else if (action.type === "escalation_review") {
                    const downgraded = Math.floor(casesProcessed * 0.4);
                    resultMsg = kyroScripts.actions.resolve_escalated_cases.success(casesProcessed, downgraded);
                } else if (action.type === "anomaly_detection") {
                    resultMsg = kyroScripts.actions.trigger_behavior_reviews.success(casesProcessed);
                } else if (action.type === "false_positive_analysis") {
                    const falsePos = Math.floor(casesProcessed * 0.3);
                    resultMsg = kyroScripts.actions.analyze_false_positives.success(casesProcessed, falsePos);
                }
                
                // Add result message with optional details and speak it completely
                this.addMessage("assistant", resultMsg, messageOptions);
                await this.speak(resultMsg);
            } else {
                this.agentState.run_stats.failure += 1;
                const failMsg = kyroScripts.actions[action.type.replace(/_/g, '_')]?.failure || 
                               "Action failed. I'll retry in the next cycle.";
                this.addMessage("assistant", failMsg);
                await this.speak(failMsg);
            }
            
            this.updateStateUI();
        };
        
        // Start first action immediately
        performAction();
        
        // Then repeat every 12-20 seconds
        this.statsSimulationInterval = setInterval(() => {
            performAction();
        }, Math.random() * 8000 + 12000); // Between 12-20 seconds
    },

    stopStatsSimulation() {
        if (this.statsSimulationInterval) {
            clearInterval(this.statsSimulationInterval);
            this.statsSimulationInterval = null;
        }
    },

    generateCaseDetails(totalCases, resolved, escalated) {
        const remaining = totalCases - resolved - escalated;
        
        // Generate sample cases with realistic data
        const riskTypes = ['MANUAL', 'BEHAVIOR_BASED', 'TIME_BASED'];
        const riskLevels = ['MEDIUM', 'HIGH', 'LOW'];
        const caseList = [];
        
        for (let i = 0; i < totalCases && i < 15; i++) {
            const caseId = `CUST-${String(Math.floor(Math.random() * 999) + 1).padStart(3, '0')}`;
            const customerId = `ef${Math.random().toString(36).substr(2, 6)}f`;
            const riskType = riskTypes[Math.floor(Math.random() * riskTypes.length)];
            const riskLevel = riskLevels[Math.floor(Math.random() * riskLevels.length)];
            const score = (Math.random() * 60 + 20).toFixed(1);
            
            caseList.push(`- ${caseId} • ${customerId} • ${riskType} • ${riskLevel}`);
        }
        
        const assessedCases = [];
        for (let i = 0; i < Math.min(3, totalCases); i++) {
            const caseId = `CUST-${String(Math.floor(Math.random() * 999) + 1).padStart(3, '0')}`;
            const customerId = `ef${Math.random().toString(36).substr(2, 6)}f`;
            const riskType = riskTypes[Math.floor(Math.random() * riskTypes.length)];
            const riskLevel = riskLevels[Math.floor(Math.random() * riskLevels.length)];
            const score = (Math.random() * 60 + 20).toFixed(1);
            
            assessedCases.push(`- ${caseId} • ${customerId}f [${riskType} | ${riskLevel} | ${score}]`);
        }
        
        const moreCount = totalCases - caseList.length;
        
        let html = `
            <div class="kc-case-list">
                <div class="kc-case-section">
                    <div class="kc-case-label">Cases:</div>
                    ${caseList.join('<br>')}
                    ${moreCount > 0 ? `<br>- +${moreCount} more` : ''}
                </div>
                
                <div class="kc-case-section">
                    <div class="kc-case-label">Assessed:</div>
                    ${assessedCases.join('<br>')}
                </div>
                
                <div class="kc-audit-note">
                    Out-of-cycle urgent review: behavioral anomalies crossed policy sensitivity and require immediate review. 
                    Audit confirmation: I logged trigger rationale, scores, tier decision, and action outcome to the compliance audit trail.
                </div>
            </div>
        `;
        
        return html;
    },

    generateCustomerCaseDetail(caseId) {
        const riskTypes = ['MANUAL', 'BEHAVIOR_BASED', 'TIME_BASED'];
        const riskLevels = ['MEDIUM', 'HIGH', 'LOW'];
        const statuses = ['OPEN', 'UNDER_REVIEW', 'ESCALATED'];
        
        return {
            caseId: caseId,
            customerId: `ef${Math.random().toString(36).substr(2, 6)}f${Math.floor(Math.random() * 10)}`,
            customerName: `Customer ${caseId.split('-')[1]}`,
            riskType: riskTypes[Math.floor(Math.random() * riskTypes.length)],
            riskLevel: riskLevels[Math.floor(Math.random() * riskLevels.length)],
            riskScore: (Math.random() * 60 + 20).toFixed(1),
            status: statuses[Math.floor(Math.random() * statuses.length)],
            createdDate: new Date(Date.now() - Math.random() * 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
            lastActivity: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
            transactionCount: Math.floor(Math.random() * 50) + 5,
            totalAmount: `$${(Math.random() * 500000 + 50000).toFixed(2)}`,
            flags: [
                'Unusual transaction velocity',
                'Cross-border transfers to high-risk jurisdiction',
                'Pattern deviation detected'
            ].slice(0, Math.floor(Math.random() * 2) + 1),
            assignee: Math.random() > 0.5 ? 'Unassigned' : 'Analyst Team',
            priority: riskLevels[Math.floor(Math.random() * riskLevels.length)]
        };
    },

    getCaseDetailsResponse(caseId, caseDetails) {
        return `I found case ${caseId} for customer ${caseDetails.customerId}. This is a ${caseDetails.riskLevel} risk ${caseDetails.riskType} case with a risk score of ${caseDetails.riskScore}. Status: ${caseDetails.status}. The case involves ${caseDetails.transactionCount} transactions totaling ${caseDetails.totalAmount}. Would you like me to provide more details or initiate a handoff for human review?`;
    },

    formatCaseDetailsHTML(caseDetails) {
        return `
            <div class="kc-case-list">
                <div class="kc-case-section">
                    <div class="kc-case-label">Case Information:</div>
                    - Case ID: ${caseDetails.caseId}<br>
                    - Customer ID: ${caseDetails.customerId}<br>
                    - Customer Name: ${caseDetails.customerName}<br>
                    - Risk Type: ${caseDetails.riskType}<br>
                    - Risk Level: ${caseDetails.riskLevel}<br>
                    - Risk Score: ${caseDetails.riskScore}<br>
                    - Status: ${caseDetails.status}
                </div>
                
                <div class="kc-case-section">
                    <div class="kc-case-label">Transaction Details:</div>
                    - Transaction Count: ${caseDetails.transactionCount}<br>
                    - Total Amount: ${caseDetails.totalAmount}<br>
                    - Created Date: ${caseDetails.createdDate}<br>
                    - Last Activity: ${caseDetails.lastActivity}
                </div>
                
                <div class="kc-case-section">
                    <div class="kc-case-label">Risk Flags:</div>
                    ${caseDetails.flags.map(flag => `- ${flag}`).join('<br>')}
                </div>
                
                <div class="kc-case-section">
                    <div class="kc-case-label">Assignment:</div>
                    - Assignee: ${caseDetails.assignee}<br>
                    - Priority: ${caseDetails.priority}
                </div>
            </div>
        `;
    },

    async stopAgent() {
        try {
            showGlobalLoading("Stopping agent...");
            
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            this.stopStatsSimulation();
            this.agentState.autonomous_status = "STOPPED";
            this.agentState.streaming_pulse_label = "Ready to screen cases when autonomous execution starts.";
            this.agentState.run_stats = { actions: 0, success: 0, failure: 0, casesTouched: 0 };
            this.updateStateUI();
            
            showToast("info", "Kyro agent stopped");
            this.addMessage("assistant", kyroScripts.autonomous.stop.success);
            this.speak("Compliance agent stopped.");
            
        } catch (error) {
            console.error(error);
            showToast("error", "Failed to stop agent");
            this.addMessage("assistant", kyroScripts.autonomous.stop.failure("system error"));
        } finally {
            hideLoading();
        }
    },

    async pauseAgent() {
        try {
            this.stopStatsSimulation();
            this.agentState.autonomous_status = "PAUSED";
            this.agentState.streaming_pulse_label = "Monitoring paused - awaiting resume command";
            this.updateStateUI();
            
            showToast("warning", "Agent paused");
            this.addMessage("assistant", kyroScripts.autonomous.pause.success);
            this.speak("Operations paused.");
            
        } catch (error) {
            console.error(error);
            this.addMessage("assistant", kyroScripts.autonomous.pause.failure("system error"));
        }
    },

    async resumeAgent() {
        try {
            this.agentState.autonomous_status = "RUNNING";
            this.agentState.streaming_pulse_label = "Resuming active monitoring of compliance events";
            this.updateStateUI();
            
            showToast("success", "Agent resumed");
            this.addMessage("assistant", kyroScripts.autonomous.resume.success);
            this.speak("Resuming active screening cycles.");
            
            // Restart stats simulation
            this.startStatsSimulation();
            
        } catch (error) {
            console.error(error);
            this.addMessage("assistant", kyroScripts.autonomous.resume.failure("system error"));
        }
    },

    async requestHandoff() {
        try {
            const reason = prompt("Enter reason for handoff:", "Manual intervention required");
            if (!reason) return;
            
            this.agentState.autonomous_status = "PAUSED";
            this.agentState.intervention_needed = true;
            this.agentState.streaming_pulse_label = "Human intervention requested - awaiting guidance";
            this.updateStateUI();
            
            showToast("info", "Handoff requested - agent paused");
            
            // If we have case context, include detailed information in handoff
            if (this.currentCaseContext) {
                const handoffMsg = `Handoff requested: ${reason}\n\nI've packaged the case context for ${this.currentCaseContext.caseId}. A human analyst should review the flagged transactions and risk indicators.`;
                this.addMessage("assistant", handoffMsg, {
                    showViewDetails: true,
                    caseDetails: this.formatHandoffCaseDetails(this.currentCaseContext)
                });
                this.speak(`Handoff completed for case ${this.currentCaseContext.caseId}. Awaiting manual intervention.`);
            } else {
                this.addMessage("assistant", kyroScripts.handoff.requested(reason));
                this.speak("Handoff completed. Awaiting manual intervention.");
            }
            
        } catch (error) {
            console.error(error);
        }
    },

    formatHandoffCaseDetails(caseDetails) {
        return `
            <div class="kc-case-list">
                <div class="kc-case-section">
                    <div class="kc-case-label">📋 Case Summary</div>
                    <strong>Case ID:</strong> ${caseDetails.caseId}<br>
                    <strong>Customer ID:</strong> ${caseDetails.customerId}<br>
                    <strong>Customer Name:</strong> ${caseDetails.customerName}<br>
                    <strong>Status:</strong> <span style="color: #f59e0b; font-weight: 600;">${caseDetails.status}</span>
                </div>
                
                <div class="kc-case-section">
                    <div class="kc-case-label">⚠️ Risk Assessment</div>
                    <strong>Risk Type:</strong> ${caseDetails.riskType}<br>
                    <strong>Risk Level:</strong> <span style="color: ${caseDetails.riskLevel === 'HIGH' ? '#ef4444' : caseDetails.riskLevel === 'MEDIUM' ? '#f59e0b' : '#10b981'}; font-weight: 600;">${caseDetails.riskLevel}</span><br>
                    <strong>Risk Score:</strong> ${caseDetails.riskScore}/100<br>
                    <strong>Priority:</strong> ${caseDetails.priority}
                </div>
                
                <div class="kc-case-section">
                    <div class="kc-case-label">💰 Transaction Activity</div>
                    <strong>Transaction Count:</strong> ${caseDetails.transactionCount}<br>
                    <strong>Total Amount:</strong> ${caseDetails.totalAmount}<br>
                    <strong>Created Date:</strong> ${caseDetails.createdDate}<br>
                    <strong>Last Activity:</strong> ${caseDetails.lastActivity}
                </div>
                
                <div class="kc-case-section">
                    <div class="kc-case-label">🚩 Risk Flags</div>
                    ${caseDetails.flags.map(flag => `• ${flag}`).join('<br>')}
                </div>
                
                <div class="kc-case-section">
                    <div class="kc-case-label">👤 Assignment</div>
                    <strong>Current Assignee:</strong> ${caseDetails.assignee}<br>
                    <strong>Recommended Action:</strong> Human review required
                </div>
                
                <div class="kc-audit-note">
                    <strong>🔍 AI Analysis:</strong> I've performed automated risk scoring and pattern analysis. The case exhibits behavioral anomalies that exceed my autonomous decision threshold. Human expertise is needed to assess context-specific factors and make the final disposition decision.
                </div>
            </div>
        `;
    },

    _setSpeakingState(speaking) {
        const video    = document.getElementById("kyroCharVideo");
        const pillDot  = document.getElementById("kcIdleDot");
        const pillText = document.getElementById("kcIdleText");

        if (speaking) {
            // When speaking - play video
            if (video) { 
                video.currentTime = 0; 
                video.play().catch(err => console.log("Video play error:", err)); 
            }
            if (pillDot)  pillDot.style.backgroundColor = "#06b6d4";
            if (pillText) pillText.textContent = "SPEAKING";
        } else {
            // When not speaking - pause video and reset
            if (video) { 
                video.pause(); 
                video.currentTime = 0; 
            }
            const status = this.agentState.autonomous_status;
            const dotColors = { RUNNING: "#22c55e", PAUSED: "#f59e0b", ERROR: "#ef4444" };
            if (pillDot)  pillDot.style.backgroundColor = dotColors[status] || "#94a3b8";
            if (pillText) pillText.textContent = status === "RUNNING" ? "RUNNING" : status === "PAUSED" ? "PAUSED" : "IDLE";
        }
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
