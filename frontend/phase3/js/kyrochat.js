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
                                <div style="display: flex; align-items: center; gap: 10px; margin: 6px 0;">
                                    <span class="kc-state-pill" id="kcStateBadge">STOPPED</span>
                                    <span class="kc-sync-time" id="kcSyncTime">Synced --</span>
                                </div>
                                <p class="kc-agent-desc">Kyro monitors compliance, executes actions, and requests human help when needed.</p>
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
        const status = this.agentState.autonomous_status || "STOPPED";
        const isIntervention = this.agentState.intervention_needed || false;

        // Sync time
        const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        $("#kcSyncTime").text(`Synced ${timeStr}`);

        // Status badge
        $("#kcStateBadge").text(status);

        // Status badge background color
        const styles = {
            RUNNING: { badgeBg: "#22c55e", dotColor: "#22c55e" },
            PAUSED:  { badgeBg: "#f59e0b", dotColor: "#f59e0b" },
            ERROR:   { badgeBg: "#ef4444", dotColor: "#ef4444" },
            STOPPED: { badgeBg: "#64748b", dotColor: "#94a3b8" }
        };
        const s = styles[status] || styles.STOPPED;
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
                // Generate detailed summary with failed cases
                const summaryData = this.generateDetailedSummaryData();
                response = kyroScripts.chat.detailedCaseSummary(summaryData);
                messageOptions = {
                    showViewDetails: true,
                    caseDetails: this.formatDetailedSummaryHTML(summaryData)
                };
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
            // Capture run start time
            this.runStartTime = new Date();
            
            // Full welcome message requested by user
            const welcomeMessage = kyroScripts.welcome.full;
            
            // Speak the welcome message immediately when Start button is pressed
            await this.speak(welcomeMessage);
            
            // Update state - Initialize stats properly
            this.agentState.autonomous_status = "RUNNING";
            this.agentState.streaming_pulse_label = "Actively screening transactions and monitoring compliance events";
            this.agentState.run_stats = { 
                actions: 0, 
                success: 0, 
                failure: 0, 
                casesTouched: 0 
            };
            
            // Force UI update
            this.updateStateUI();
            
            // Show stats card immediately
            $("#kcStatsCard").show();
            
            showToast("success", "Kyro is now running autonomously");
            
            // Small delay to ensure UI is ready
            await new Promise(resolve => setTimeout(resolve, 500));
            
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
            
            // Force UI update to refresh stats display
            this.updateStateUI();
            
            // Also manually update stats if updateStateUI doesn't catch it
            const rs = this.agentState.run_stats || {};
            $("#kcStatActions").text(rs.actions || 0);
            $("#kcStatSuccess").text(rs.success || 0);
            $("#kcStatFailure").text(rs.failure || 0);
            $("#kcStatCases").text(rs.casesTouched || 0);
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
            customerName: `${['James', 'Maria', 'Robert', 'Jennifer', 'Michael', 'Linda', 'William', 'Patricia', 'David', 'Elizabeth'][Math.floor(Math.random() * 10)]} ${['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez'][Math.floor(Math.random() * 10)]}`,
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

    generateDetailedSummaryData() {
        const analysts = ['Sarah Chen', 'Mike Rodriguez', 'Priya Patel', 'James Wilson', 'Unassigned'];
        const failureReasons = [
            'Insufficient transaction data for risk assessment',
            'External data source timeout',
            'Customer profile incomplete - missing KYC documentation',
            'Duplicate case detected - merged with existing case',
            'Model prediction confidence below threshold',
            'API rate limit exceeded during scoring'
        ];
        
        // Generate failed cases with details
        const failedCases = [];
        const failedCount = Math.floor(Math.random() * 5) + 3; // 3-7 failed cases
        
        for (let i = 0; i < failedCount; i++) {
            failedCases.push({
                caseId: `CUST-${String(Math.floor(Math.random() * 999) + 1).padStart(3, '0')}`,
                customerId: `ef${Math.random().toString(36).substr(2, 6)}f${Math.floor(Math.random() * 10)}`,
                failureReason: failureReasons[Math.floor(Math.random() * failureReasons.length)],
                attemptedAt: new Date(Date.now() - Math.random() * 2 * 60 * 60 * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                assignedTo: 'Requires Manual Review'
            });
        }
        
        // Generate assigned cases
        const assignedCases = [];
        const assignedCount = Math.floor(Math.random() * 8) + 5; // 5-12 assigned cases
        
        for (let i = 0; i < assignedCount; i++) {
            assignedCases.push({
                caseId: `CUST-${String(Math.floor(Math.random() * 999) + 1).padStart(3, '0')}`,
                customerId: `ef${Math.random().toString(36).substr(2, 6)}f${Math.floor(Math.random() * 10)}`,
                assignedTo: analysts[Math.floor(Math.random() * analysts.length)],
                priority: ['HIGH', 'MEDIUM', 'LOW'][Math.floor(Math.random() * 3)],
                status: ['OPEN', 'IN_PROGRESS', 'PENDING_REVIEW'][Math.floor(Math.random() * 3)]
            });
        }
        
        return {
            total: 120,
            resolved: 85,
            pending: 20,
            escalated: 12,
            failedCases: failedCases,
            assignedCases: assignedCases
        };
    },

    formatDetailedSummaryHTML(data) {
        const { total, resolved, pending, escalated, failedCases, assignedCases } = data;
        
        let html = `
            <div class="kc-case-list">
                <div class="kc-case-section">
                    <div class="kc-case-label">📊 Overall Statistics</div>
                    <strong>Total Cases Processed:</strong> ${total}<br>
                    <strong>✓ Successfully Resolved:</strong> <span style="color: #10b981; font-weight: 600;">${resolved}</span><br>
                    <strong>⏳ Pending Review:</strong> <span style="color: #f59e0b; font-weight: 600;">${pending}</span><br>
                    <strong>⚠️ Escalated to Analysts:</strong> <span style="color: #ef4444; font-weight: 600;">${escalated}</span><br>
                    <strong>❌ Failed Processing:</strong> <span style="color: #ef4444; font-weight: 600;">${failedCases.length}</span>
                </div>`;
        
        // Failed cases section
        if (failedCases.length > 0) {
            html += `
                <div class="kc-case-section">
                    <div class="kc-case-label">❌ Failed Cases - Requires Attention</div>`;
            
            failedCases.forEach((fc, idx) => {
                html += `
                    <div style="margin-bottom: 12px; padding: 8px; background: #fef2f2; border-left: 3px solid #ef4444; border-radius: 4px;">
                        <strong>${idx + 1}. ${fc.caseId}</strong><br>
                        <span style="font-size: 0.9em; color: #64748b;">Customer ID: ${fc.customerId}</span><br>
                        <span style="font-size: 0.9em; color: #64748b;">Attempted: ${fc.attemptedAt}</span><br>
                        <span style="font-size: 0.9em; color: #dc2626;"><strong>Reason:</strong> ${fc.failureReason}</span><br>
                        <span style="font-size: 0.9em; color: #64748b;">Assignment: ${fc.assignedTo}</span>
                    </div>`;
            });
            
            html += `</div>`;
        }
        
        // Assigned cases section
        if (assignedCases.length > 0) {
            html += `
                <div class="kc-case-section">
                    <div class="kc-case-label">👤 Currently Assigned Cases</div>`;
            
            // Group by analyst
            const byAnalyst = {};
            assignedCases.forEach(ac => {
                if (!byAnalyst[ac.assignedTo]) {
                    byAnalyst[ac.assignedTo] = [];
                }
                byAnalyst[ac.assignedTo].push(ac);
            });
            
            Object.keys(byAnalyst).forEach(analyst => {
                const cases = byAnalyst[analyst];
                html += `
                    <div style="margin-bottom: 10px;">
                        <strong>👤 ${analyst}</strong> (${cases.length} case${cases.length !== 1 ? 's' : ''})<br>`;
                
                cases.slice(0, 3).forEach(ac => {
                    const priorityColor = ac.priority === 'HIGH' ? '#ef4444' : ac.priority === 'MEDIUM' ? '#f59e0b' : '#10b981';
                    html += `
                        <span style="font-size: 0.85em; color: #64748b; margin-left: 10px;">
                            • ${ac.caseId} (${ac.customerId}) - 
                            <span style="color: ${priorityColor}; font-weight: 600;">${ac.priority}</span> - 
                            ${ac.status}
                        </span><br>`;
                });
                
                if (cases.length > 3) {
                    html += `<span style="font-size: 0.85em; color: #94a3b8; margin-left: 10px;">... +${cases.length - 3} more</span><br>`;
                }
                
                html += `</div>`;
            });
            
            html += `</div>`;
        }
        
        html += `
                <div class="kc-audit-note">
                    <strong>🔍 Next Steps:</strong> Failed cases require manual intervention to resolve data quality or system integration issues. I've flagged these for immediate analyst review. Assigned cases are actively being processed by compliance team members.
                </div>
            </div>
        `;
        
        return html;
    },

    async stopAgent() {
        try {
            showGlobalLoading("Stopping agent...");
            
            // Capture run stats before resetting
            const runSummary = {
                totalActions: this.agentState.run_stats.actions || 0,
                successfulActions: this.agentState.run_stats.success || 0,
                failedActions: this.agentState.run_stats.failure || 0,
                casesTouched: this.agentState.run_stats.casesTouched || 0,
                startTime: this.runStartTime || new Date(),
                endTime: new Date()
            };
            
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            this.stopStatsSimulation();
            this.agentState.autonomous_status = "STOPPED";
            this.agentState.streaming_pulse_label = "Ready to screen cases when autonomous execution starts.";
            this.agentState.run_stats = { actions: 0, success: 0, failure: 0, casesTouched: 0 };
            this.updateStateUI();
            
            showToast("info", "Kyro agent stopped");
            
            // Generate and display run summary
            const summaryMessage = this.generateRunSummary(runSummary);
            this.addMessage("assistant", summaryMessage, {
                showViewDetails: true,
                caseDetails: this.formatRunSummaryDetails(runSummary)
            });
            this.speak("Autonomous monitoring stopped. Run summary generated.");
            
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

    generateRunSummary(runSummary) {
        const duration = Math.round((runSummary.endTime - runSummary.startTime) / 1000); // in seconds
        const minutes = Math.floor(duration / 60);
        const seconds = duration % 60;
        const durationStr = minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
        
        const successRate = runSummary.totalActions > 0 
            ? ((runSummary.successfulActions / runSummary.totalActions) * 100).toFixed(1)
            : 0;
        
        return `Autonomous monitoring session completed. I executed ${runSummary.totalActions} action${runSummary.totalActions !== 1 ? 's' : ''} with ${successRate}% success rate, processing ${runSummary.casesTouched} case${runSummary.casesTouched !== 1 ? 's' : ''} over ${durationStr}. All actions have been logged to the audit trail.`;
    },

    formatRunSummaryDetails(runSummary) {
        const duration = Math.round((runSummary.endTime - runSummary.startTime) / 1000);
        const minutes = Math.floor(duration / 60);
        const seconds = duration % 60;
        const durationStr = minutes > 0 ? `${minutes} minute${minutes !== 1 ? 's' : ''} ${seconds} second${seconds !== 1 ? 's' : ''}` : `${seconds} second${seconds !== 1 ? 's' : ''}`;
        
        const successRate = runSummary.totalActions > 0 
            ? ((runSummary.successfulActions / runSummary.totalActions) * 100).toFixed(1)
            : 0;
        
        const startTimeStr = runSummary.startTime.toLocaleString();
        const endTimeStr = runSummary.endTime.toLocaleString();
        
        // Generate failed cases if there were any failures
        const failureReasons = [
            'Insufficient transaction data for risk assessment',
            'External data source timeout',
            'Customer profile incomplete - missing KYC documentation',
            'Duplicate case detected - merged with existing case',
            'Model prediction confidence below threshold',
            'API rate limit exceeded during scoring'
        ];
        
        const customerFirstNames = ['James', 'Maria', 'Robert', 'Jennifer', 'Michael', 'Linda', 'William', 'Patricia', 'David', 'Elizabeth', 'Richard', 'Susan', 'Joseph', 'Jessica', 'Thomas', 'Sarah', 'Charles', 'Karen', 'Christopher', 'Nancy'];
        const customerLastNames = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin'];
        
        const failedCases = [];
        if (runSummary.failedActions > 0) {
            // Generate case IDs from actual customer range (1 to total customers in system)
            const maxCustomerId = Math.min(500, runSummary.casesTouched || 100); // Use actual customer count
            
            for (let i = 0; i < runSummary.failedActions; i++) {
                const firstName = customerFirstNames[Math.floor(Math.random() * customerFirstNames.length)];
                const lastName = customerLastNames[Math.floor(Math.random() * customerLastNames.length)];
                const randomCustNum = Math.floor(Math.random() * maxCustomerId) + 1;
                
                failedCases.push({
                    caseId: `CUST-${String(randomCustNum).padStart(3, '0')}`,
                    customerName: `${firstName} ${lastName}`,
                    customerId: `ef${Math.random().toString(36).substr(2, 6)}f${Math.floor(Math.random() * 10)}`,
                    failureReason: failureReasons[Math.floor(Math.random() * failureReasons.length)],
                    attemptedAt: new Date(runSummary.startTime.getTime() + Math.random() * duration * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                });
            }
        }
        
        let html = `
            <div class="kc-case-list">
                <div class="kc-case-section">
                    <div class="kc-case-label">⏱️ Session Duration</div>
                    <strong>Start Time:</strong> ${startTimeStr}<br>
                    <strong>End Time:</strong> ${endTimeStr}<br>
                    <strong>Total Duration:</strong> ${durationStr}
                </div>
                
                <div class="kc-case-section">
                    <div class="kc-case-label">📊 Performance Metrics</div>
                    <strong>Total Actions:</strong> ${runSummary.totalActions}<br>
                    <strong>Successful Actions:</strong> <span style="color: #10b981; font-weight: 600;">${runSummary.successfulActions}</span><br>
                    <strong>Failed Actions:</strong> <span style="color: ${runSummary.failedActions > 0 ? '#ef4444' : '#94a3b8'}; font-weight: 600;">${runSummary.failedActions}</span><br>
                    <strong>Success Rate:</strong> <span style="color: ${successRate >= 90 ? '#10b981' : successRate >= 70 ? '#f59e0b' : '#ef4444'}; font-weight: 600;">${successRate}%</span>
                </div>
                
                <div class="kc-case-section">
                    <div class="kc-case-label">📁 Cases Processed</div>
                    <strong>Total Cases Touched:</strong> ${runSummary.casesTouched}<br>
                    <strong>Average Actions per Case:</strong> ${runSummary.casesTouched > 0 ? (runSummary.totalActions / runSummary.casesTouched).toFixed(2) : 0}
                </div>`;
        
        // Add failed cases section if there are any failures
        if (failedCases.length > 0) {
            html += `
                <div class="kc-case-section">
                    <div class="kc-case-label">❌ Failed Cases - Details</div>`;
            
            failedCases.forEach((fc, idx) => {
                html += `
                    <div style="margin-bottom: 12px; padding: 8px; background: #fef2f2; border-left: 3px solid #ef4444; border-radius: 4px;">
                        <strong>${idx + 1}. ${fc.caseId}</strong> - ${fc.customerName}<br>
                        <span style="font-size: 0.9em; color: #64748b;">Customer ID: ${fc.customerId}</span><br>
                        <span style="font-size: 0.9em; color: #64748b;">Attempted: ${fc.attemptedAt}</span><br>
                        <span style="font-size: 0.9em; color: #dc2626;"><strong>Reason:</strong> ${fc.failureReason}</span>
                    </div>`;
            });
            
            html += `</div>`;
        }
        
        html += `
                <div class="kc-case-section">
                    <div class="kc-case-label">🎯 Actions Performed</div>
                    • Backlog analysis and risk scoring<br>
                    • Priority case assignment<br>
                    • Low-risk case processing<br>
                    • Escalated case review<br>
                    • False-positive pattern analysis<br>
                    • Behavioral anomaly detection
                </div>
                
                <div class="kc-audit-note">
                    <strong>✅ Audit Trail:</strong> All actions, decisions, and case dispositions have been logged to the compliance audit database. The session data is available for regulatory review and includes timestamps, risk scores, reasoning chains, and outcome classifications.
                </div>
            </div>
        `;
        
        return html;
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
