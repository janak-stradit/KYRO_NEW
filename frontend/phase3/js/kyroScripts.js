/**
 * KYRO Scripts - Centralized Agent Dialogue Library
 * All agent messages and narration in one place for consistency
 */

const kyroScripts = {
    welcome: {
        firstVisit: "Hi, I'm Kyro, your AML autonomous agent.",
        capabilities: "I monitor compliance, investigate cases, and execute approved actions automatically.",
        safety: "You can pause or stop me anytime.",
        full: "Hi, I'm Kyro, your AML autonomous agent. I monitor compliance, investigate cases, and execute approved actions automatically. You can pause or stop me anytime."
    },

    status: {
        monitoring: "I'm monitoring system state and checking for the next best action.",
        monitoringGoals: (goalCount) => 
            `I'm monitoring ${goalCount} active goal${goalCount === 1 ? "" : "s"} and evaluating action triggers.`,
        noGoals: "I don't have active goals right now. I'm analyzing current metrics to generate new goals.",
        waitingForData: "I'm running, but I need more case or transaction data before meaningful actions can be executed.",
        standby: "I'm in standby mode. Click Start Kyro to begin autonomous operations."
    },

    autonomous: {
        start: {
            intro: "Hi, I'm Kyro, your AML autonomous agent.",
            capabilities: "I monitor compliance, investigate cases, and execute approved actions automatically.",
            safety: "You can pause or stop me anytime.",
            initialization: "System initialized. I am now running autonomously.",
            monitoring: "I'm screening live transaction events and monitoring for compliance violations.",
            ready: "I'm ready. Autonomous compliance monitoring is now active.",
            full: "Hi, I'm Kyro, your AML autonomous agent. I monitor compliance, investigate cases, and execute approved actions automatically. You can pause or stop me anytime. System initialized. I am now running autonomously, screening live transaction events and monitoring for compliance violations.",
            alreadyRunning: "I'm already running in autonomous mode.",
            failure: (reason) => `I couldn't start autonomous execution: ${reason}.`
        },
        stop: {
            success: "Autonomous monitoring has been stopped. I'm now in standby mode.",
            alreadyStopped: "I'm already stopped.",
            failure: (reason) => `I couldn't stop cleanly: ${reason}.`
        },
        pause: {
            success: "Autonomous operations have been paused. Click Resume to continue monitoring.",
            failure: (reason) => `Pause request failed: ${reason}.`
        },
        resume: {
            success: "Resuming autonomous compliance monitoring.",
            failure: (reason) => `Resume request failed: ${reason}.`
        }
    },

    actions: {
        reduce_backlog: {
            start: "I detected case backlog. Analyzing cases via two-layer risk scoring and LLM examination.",
            success: (count, resolved, escalated) => {
                const parts = [`Backlog analysis complete. I examined ${count} case${count === 1 ? "" : "s"} through risk scoring and LLM.`];
                if (resolved && resolved > 0) parts.push(`${resolved} resolved (low-risk, auto-approved).`);
                if (escalated && escalated > 0) parts.push(`${escalated} escalated (high-risk, requires analyst review).`);
                const remaining = count - (resolved || 0) - (escalated || 0);
                if (remaining > 0) parts.push(`${remaining} assessed and re-queued for further monitoring.`);
                return parts.join(" ");
            },
            failure: "I couldn't complete backlog analysis in this cycle. I'll retry with the next monitor pass."
        },
        
        assign_priority_cases: {
            start: "I found unassigned high-risk cases. I'm assigning priority workload now.",
            success: (count) => `Priority assignment complete. I assigned ${count} high-risk case${count === 1 ? "" : "s"}.`,
            failure: "I couldn't assign all priority cases in this pass. I'll retry the remaining cases."
        },
        
        process_low_risk_cases: {
            start: "I'm processing low-risk open cases for straight-through handling.",
            success: (count) => `Low-risk processing complete. I auto-processed ${count} case${count === 1 ? "" : "s"}.`,
            failure: "I couldn't finish low-risk processing in this cycle. I'll continue in the next pass."
        },
        
        resolve_escalated_cases: {
            start: "I detected escalated cases. Re-assessing each with LLM analysis to confirm or downgrade risk.",
            success: (count, downgraded) => {
                const parts = [`Escalation review complete. I re-assessed ${count} escalated case${count === 1 ? "" : "s"} via LLM.`];
                if (downgraded && downgraded > 0) parts.push(`${downgraded} downgraded after risk re-evaluation.`);
                const kept = count - (downgraded || 0);
                if (kept > 0) parts.push(`${kept} confirmed as high-risk and remain escalated.`);
                return parts.join(" ");
            },
            failure: "I couldn't complete escalated-case analysis this cycle. I'll retry shortly."
        },
        
        analyze_false_positives: {
            start: "I'm reviewing recently resolved cases to identify false-positive patterns.",
            success: (totalReviewed, falsePositives) => {
                if (totalReviewed && totalReviewed > 0) {
                    return `False-positive analysis complete. Reviewed ${totalReviewed} recent resolutions, found ${falsePositives || 0} likely false positives. I'll apply this context in upcoming decisions.`;
                }
                return "False-positive analysis complete. I'll apply this context in upcoming decisions.";
            },
            failure: "False-positive analysis was interrupted. I'll retry in a subsequent cycle."
        },
        
        trigger_behavior_reviews: {
            start: "I detected fresh anomaly signals and I'm triggering behavior-based reviews.",
            success: (count) => `Behavioral anomaly pass complete. I triggered ${count} behavior-based review case${count === 1 ? "" : "s"}.`,
            failure: "I couldn't complete anomaly-triggered review generation in this cycle. I'll retry shortly."
        }
    },

    handoff: {
        requested: (reason) => `Handoff requested: ${reason}. I'm now paused and awaiting your guidance.`,
        completed: "Handoff completed. Awaiting manual intervention.",
        packagedContext: "I've packaged the latest case and decision context for the human reviewer."
    },

    errors: {
        backendUnreachable: "I can't reach the backend service right now. I'll keep retrying and continue when connectivity is restored.",
        timeout: "A request timed out during autonomous execution. I'll retry with the next cycle.",
        actionFailure: (actionType, reason) => `I hit an issue while running ${actionType}: ${reason}. I'll retry or switch strategy.`,
        unknown: "Something went wrong. Please try again."
    },

    chat: {
        caseInfo: (openCases, highPriority) => 
            `Currently there are ${openCases} open cases in the backlog, with ${highPriority} high-priority alerts requiring immediate review. I can prioritize and start screening them autonomously.`,
        
        transactionInfo: (flaggedCount) =>
            `Transaction monitoring is active. I've flagged ${flaggedCount} unusual patterns in the last hour — mostly velocity spikes and cross-border transfers to high-risk jurisdictions.`,
        
        riskInfo: (elevatedPercent, modelConfidence) =>
            `${elevatedPercent}% of monitored accounts have elevated risk scores. ML model confidence is at ${modelConfidence}%. No drift detected in the last 24 hours.`,
        
        modelInfo: (modelName, precision, recall) =>
            `Active model: ${modelName} — Precision: ${precision}%, Recall: ${recall}%. Performing as expected.`,
        
        defaultResponse: "I'm here to help with AML compliance monitoring, case reviews, transaction analysis, and risk assessment. What would you like to explore?",
        
        greeting: "Hello! How can I assist you with compliance monitoring today?",
        
        caseSummary: (total, resolved, pending, escalated, failedCases = []) => {
            let summary = `Case Summary: ${total} total cases. ${resolved} resolved, ${pending} pending review, ${escalated} escalated to analysts.`;
            
            if (failedCases && failedCases.length > 0) {
                summary += ` ${failedCases.length} case${failedCases.length === 1 ? '' : 's'} failed processing.`;
            }
            
            return summary;
        },
        
        detailedCaseSummary: (data) => {
            const { total, resolved, pending, escalated, failedCases = [], assignedCases = [] } = data;
            
            const parts = [];
            parts.push(`📊 <strong>Case Processing Summary</strong>`);
            parts.push(`Total Cases Reviewed: ${total}`);
            parts.push(`✓ Successfully Resolved: ${resolved}`);
            parts.push(`⏳ Pending Review: ${pending}`);
            parts.push(`⚠️ Escalated: ${escalated}`);
            
            if (failedCases.length > 0) {
                parts.push(`❌ Failed: ${failedCases.length}`);
            }
            
            return parts.join('<br>');
        }
    },

    instructions: {
        stopped: "Click <strong>Start Kyro</strong> to begin automated monitoring.",
        running: "Kyro is actively monitoring compliance events.",
        paused: "Paused — click <strong>Resume Kyro</strong> to continue.",
        intervention: "Intervention required — please provide guidance."
    },

    notices: {
        intervention: "⚠️ Human intervention required — Kyro is waiting for guidance.",
        autonomous: "🟢 Autonomous mode active — monitoring compliance events.",
        paused: "⏸️ Operations paused — awaiting resume command."
    }
};

// Helper functions for formatting
const kyroFormatters = {
    shortCaseId: (caseId) => {
        const raw = String(caseId || "").trim();
        if (!raw) return "unknown-case";
        return raw.slice(0, 8);
    },

    formatCaseList: (caseIds, maxCases = 5) => {
        if (!Array.isArray(caseIds) || caseIds.length === 0) return null;
        const normalized = caseIds
            .map(id => kyroFormatters.shortCaseId(id))
            .filter(id => id.trim().length > 0);
        if (normalized.length === 0) return null;
        const shown = normalized.slice(0, maxCases);
        const remaining = normalized.length - shown.length;
        return remaining > 0
            ? `${shown.join(", ")} +${remaining} more`
            : shown.join(", ");
    },

    formatScore: (value) => {
        if (typeof value === "number" && Number.isFinite(value)) return value.toFixed(1);
        return "n/a";
    },

    compactCaseRef: (customerId, caseId) => {
        const customer = String(customerId || "unknown-customer");
        const shortId = kyroFormatters.shortCaseId(caseId);
        return `${customer} • ${shortId}`;
    }
};

// Export for use in other modules
window.kyroScripts = kyroScripts;
window.kyroFormatters = kyroFormatters;
