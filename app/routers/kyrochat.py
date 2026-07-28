"""
routers/kyrochat.py — Endpoints for the Kyro Chat interface, autonomous compliance agent status, and streaming simulation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.alert import Alert
from app.models.customer import Customer
from app.models.transaction import Transaction

router = APIRouter(tags=["kyrochat"])

# In-memory agent & streaming state
class AgentState:
    def __init__(self):
        self.autonomous_status = "STOPPED"  # STOPPED, RUNNING, PAUSED, ERROR
        self.streaming_is_running = False
        self.intervention_needed = False
        self.processing_cases_count = 0
        self.next_cycle_eta_sec = 30
        self.latest_action_label = "Standby"
        self.streaming_pulse_label = "Ready to screen cases when autonomous execution starts."
        self.last_sync_at = None
        self.run_stats = {
            "actions": 0,
            "success": 0,
            "failure": 0,
            "casesTouched": 0
        }
        self.timeline = []

agent_state = AgentState()

# Pydantic Schemas
class ChatMessage(BaseModel):
    role: str
    content: str
    message_kind: str | None = None
    action_meta: dict[str, Any] | None = None
    timestamp: str | None = None

class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    context: dict[str, Any] | None = None
    conversation_id: str | None = None
    save_history: bool | None = None

class ChatResponse(BaseModel):
    content: str
    role: str = "assistant"
    message_kind: str | None = "text"
    action_meta: dict[str, Any] | None = None
    suggestions: list[str] | None = None

class StartAgentRequest(BaseModel):
    budget_id: str | None = None
    generate_goals: bool | None = None
    time_budget_seconds: int | None = None
    action_budget: int | None = None
    api_call_budget: int | None = None

class HandoffRequest(BaseModel):
    reason: str
    context: dict[str, Any] | None = None

class StartStreamingRequest(BaseModel):
    event_types: list[str] | None = None
    duration_minutes: int | None = None


# Welcome endpoint
@router.get("/api/v1/chat/welcome")
def get_welcome() -> dict[str, Any]:
    return {
        "message": "Hi, I'm Kyro, your KYC/AML autonomous agent. I monitor compliance, investigate cases, and execute approved actions automatically. You can pause or stop me anytime.",
        "is_welcome": True,
        "options": [
            "What is the status of the backlog?",
            "Explain risk for case C-102",
            "Show recent transaction anomalies",
            "How is the ML model performing?"
        ]
    }


# Message endpoint
@router.post("/api/v1/chat/message", response_model=ChatResponse)
def send_message(req: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    if not req.messages:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No messages provided")
    
    user_msg = req.messages[-1].content.strip().lower()
    
    # NLP and context-aware responses
    if "backlog" in user_msg or "status" in user_msg or "cases" in user_msg:
        open_count = db.query(Alert).filter(Alert.status == "OPEN").count()
        assigned_count = db.query(Alert).filter(Alert.status == "ASSIGNED").count()
        response_text = (
            f"Currently, there are {open_count} open alerts and {assigned_count} assigned alerts "
            f"in the KYRO database. When autonomous mode is active, I continuously process the backlog."
        )
        suggestions = ["Show recent transaction anomalies", "How is the ML model performing?"]
        
    elif "c-102" in user_msg or "case c-102" in user_msg:
        response_text = (
            "Case C-102 Details:\n"
            "• Customer: Apex Global Corp\n"
            "• Score: 87.5 (HIGH RISK)\n"
            "• Trigger: Out-of-pattern cross-border wire transfers totaling $250k.\n"
            "• Recommendation: Escalate to Level-2 Analyst for detailed investigation."
        )
        suggestions = ["What is the status of the backlog?", "Explain risk for case C-102"]
        
    elif "anomaly" in user_msg or "transaction" in user_msg:
        high_alerts = db.query(Alert).filter(Alert.risk_score >= 80).limit(3).all()
        if high_alerts:
            details = "\n".join([f"• Alert ID: {a.id} | Score: {a.risk_score} | Rec: {a.recommended_action}" for a in high_alerts])
            response_text = f"Found high-risk alerts that require human verification:\n{details}"
        else:
            response_text = "No critical transaction anomalies detected in the current queue."
        suggestions = ["What is the status of the backlog?", "How is the ML model performing?"]
        
    elif "ml" in user_msg or "model" in user_msg or "performance" in user_msg:
        response_text = (
            "KYRO Classifier Metrics:\n"
            "• Active Model: Random Forest v2.1\n"
            "• Precision: 94.8% | Recall: 91.2%\n"
            "• Challenger Model: XGBoost v2.2 (10% Traffic Allocation)\n"
            "• Performance: Stable, no abnormal drift detected."
        )
        suggestions = ["What is the status of the backlog?", "Show recent transaction anomalies"]
        
    else:
        response_text = (
            "I'm on standby monitoring compliance signals. Ask me about the case backlog, "
            "specific case risks, recent transaction anomalies, or the ML models."
        )
        suggestions = [
            "What is the status of the backlog?",
            "Explain risk for case C-102",
            "Show recent transaction anomalies"
        ]
        
    return ChatResponse(
        content=response_text,
        suggestions=suggestions
    )


# Agent Status endpoint
@router.get("/api/v1/agent/autonomous/status")
def get_agent_status() -> dict[str, Any]:
    return {
        "status": agent_state.autonomous_status,
        "agent_available": True,
        "is_checking_connection": False,
        "autonomousStatus": agent_state.autonomous_status,
        "interventionNeeded": agent_state.intervention_needed,
        "processingCasesCount": agent_state.processing_cases_count,
        "nextCycleEtaSec": agent_state.next_cycle_eta_sec,
        "latestActionLabel": agent_state.latest_action_label,
        "streamingPulseLabel": agent_state.streaming_pulse_label,
        "lastSyncAt": datetime.now(timezone.utc).isoformat(),
        "runStats": agent_state.run_stats
    }


# Agent Start endpoint
@router.post("/api/v1/agent/autonomous/start")
def start_agent(req: StartAgentRequest | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    agent_state.autonomous_status = "RUNNING"
    agent_state.streaming_is_running = True
    agent_state.intervention_needed = False
    
    # Populate mock stats
    open_count = db.query(Alert).filter(Alert.status == "OPEN").count()
    agent_state.processing_cases_count = open_count if open_count > 0 else 5
    agent_state.latest_action_label = "Kyro here. Authorization received. I'm starting autonomous operations now."
    agent_state.streaming_pulse_label = "Screening cases continuously from live signals."
    agent_state.run_stats = {
        "actions": 4,
        "success": 3,
        "failure": 1,
        "casesTouched": agent_state.processing_cases_count
    }
    
    # Log timeline action
    agent_state.timeline.insert(0, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": "START_AGENT",
        "action_id": str(uuid.uuid4())[:8],
        "decision_reason": "Manual start by compliance user.",
        "outcome": "SUCCESS",
        "success": True
    })
    
    return {"success": True, "status": "RUNNING"}


# Agent Stop endpoint
@router.post("/api/v1/agent/autonomous/stop")
def stop_agent(reason: str | None = None) -> dict[str, Any]:
    agent_state.autonomous_status = "STOPPED"
    agent_state.streaming_is_running = False
    agent_state.processing_cases_count = 0
    agent_state.latest_action_label = "Standby"
    agent_state.streaming_pulse_label = "Ready to screen cases when autonomous execution starts."
    
    # Log timeline action
    agent_state.timeline.insert(0, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": "STOP_AGENT",
        "action_id": str(uuid.uuid4())[:8],
        "decision_reason": reason or "Manual stop by user.",
        "outcome": "SUCCESS",
        "success": True
    })
    
    return {"success": True, "status": "STOPPED"}


# Agent Pause endpoint
@router.post("/api/v1/agent/autonomous/pause")
def pause_agent() -> dict[str, Any]:
    agent_state.autonomous_status = "PAUSED"
    agent_state.latest_action_label = "Paused autonomous operations."
    
    # Log timeline action
    agent_state.timeline.insert(0, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": "PAUSE_AGENT",
        "action_id": str(uuid.uuid4())[:8],
        "decision_reason": "Manual pause.",
        "outcome": "SUCCESS",
        "success": True
    })
    
    return {"success": True, "status": "PAUSED"}


# Agent Resume endpoint
@router.post("/api/v1/agent/autonomous/resume")
def resume_agent() -> dict[str, Any]:
    agent_state.autonomous_status = "RUNNING"
    agent_state.latest_action_label = "Resuming autonomous operations..."
    agent_state.intervention_needed = False
    
    # Log timeline action
    agent_state.timeline.insert(0, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": "RESUME_AGENT",
        "action_id": str(uuid.uuid4())[:8],
        "decision_reason": "Manual resume.",
        "outcome": "SUCCESS",
        "success": True
    })
    
    return {"success": True, "status": "RUNNING"}


# Agent Handoff endpoint
@router.post("/api/v1/agent/autonomous/handoff")
def handoff_agent(req: HandoffRequest) -> dict[str, Any]:
    agent_state.autonomous_status = "PAUSED"
    agent_state.intervention_needed = True
    agent_state.latest_action_label = f"Handoff to human. Reason: {req.reason}"
    
    # Log timeline action
    agent_state.timeline.insert(0, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": "HANDOFF",
        "action_id": str(uuid.uuid4())[:8],
        "decision_reason": req.reason,
        "outcome": "SUCCESS",
        "success": True
    })
    
    return {"success": True, "reason": req.reason, "status": "PAUSED"}


# Processing Cases endpoint
@router.get("/api/v1/agent/autonomous/cases/processing")
def get_processing_cases(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    # Get active/open alerts to show real processing cases in the UI
    open_alerts = (
        db.query(Alert, Customer.full_name)
        .join(Customer, Alert.customer_id == Customer.id)
        .filter(Alert.status == "OPEN")
        .limit(5)
        .all()
    )
    processing = []
    for a, full_name in open_alerts:
        processing.append({
            "case_id": f"C-{a.id}",
            "customer_name": full_name or "Unknown Customer",
            "alert_type": a.alert_type or "Behavioral Anomaly",
            "risk_score": a.risk_score,
            "status": "ANALYZING"
        })
    
    # Fallback to defaults if no cases in database
    if not processing:
        processing = [
            {"case_id": "C-101", "customer_name": "Apex Global Corp", "alert_type": "Velocity Spike", "risk_score": 87.5, "status": "ANALYZING"},
            {"case_id": "C-102", "customer_name": "John Doe LLC", "alert_type": "Geo Shift", "risk_score": 62.0, "status": "REVIEWING"},
            {"case_id": "C-103", "customer_name": "Sino Trade Ltd", "alert_type": "Structuring Flag", "risk_score": 95.0, "status": "PREPARING_ACTION"}
        ]
    return processing


# ── Real Failed Cases endpoint ────────────────────────────────────────────────
# Maps alert_type and triggered_rules to a business-readable transaction reason
_RULE_REASON_MAP = {
    "R001": "Threshold breach: Single high-value transaction exceeds $10,000 reporting limit",
    "R002": "Velocity spike: More than 5 transactions within a 24-hour window",
    "R003": "Rapid velocity: More than 3 transactions within a single hour",
    "R004": "Geographic risk: Transaction routed through sanctioned or high-risk jurisdiction",
    "R005": "PEP exposure: Customer identified as a Politically Exposed Person",
    "R006": "Sanctions match: Customer matched against active sanctions screening list",
    "R007": "New counterparty: First-time transfer to previously unseen counterparty",
    "R008": "Off-hours activity: High-value transaction initiated on weekend",
    "R009": "Structuring detected: Round-figure transaction amount consistent with layering pattern",
    "R010": "Rapid succession: Multiple transactions within 60-second window indicating burst activity",
}

_ALERT_TYPE_REASON_MAP = {
    "VELOCITY_SPIKE":        "Unusual velocity spike — transaction frequency far exceeds customer's 90-day baseline",
    "GEOGRAPHIC_SHIFT":      "Geographic shift detected — cross-border transfers to previously unseen high-risk regions",
    "GEOGRAPHY":             "Geographic risk — transaction originates from or routes through a sanctioned jurisdiction",
    "THRESHOLD_BREACH":      "Threshold breach — single wire transfer exceeds mandatory reporting threshold",
    "COUNTERPARTY_CHANGES":  "Counterparty anomaly — rapid introduction of multiple new unverified counterparties",
    "COMPLEXITY_SHIFT":      "Complexity shift — sudden layering pattern with multiple intermediary accounts detected",
    "INACTIVE_REACTIVATION": "Dormant account reactivation — sudden high-value activity on long-inactive account",
    "BEHAVIORAL_ANOMALY":    "Behavioral deviation — transaction pattern significantly diverges from established customer baseline",
    "HIGH_RISK_CUSTOMER":    "High-risk customer flag — customer profile carries PEP, sanctions, or adverse media indicators",
    "PEP":                   "PEP exposure — customer is a Politically Exposed Person; enhanced due diligence required",
    "SANCTIONS":             "Sanctions match — customer or counterparty matched on active OFAC/UN sanctions screening list",
    "STRUCTURING":           "Structuring pattern — multiple near-threshold deposits consistent with deliberate split structuring",
}


def _derive_failure_reason(alert_type: str | None, triggered_rules: dict | None) -> str:
    """Derive a transaction-centric human-readable failure reason from alert metadata."""
    # First try triggered rules — most specific
    if triggered_rules and isinstance(triggered_rules, dict):
        rules_list = triggered_rules.get("rules") or triggered_rules.get("triggered_rules") or []
        if rules_list:
            # Use the highest-severity rule's reason
            for rule_id in ["R006", "R005", "R010", "R004", "R002", "R003", "R009", "R001", "R007", "R008"]:
                if rule_id in rules_list:
                    return _RULE_REASON_MAP.get(rule_id, "")
            # Fallback: first rule in list
            return _RULE_REASON_MAP.get(rules_list[0], "")

    # Fall back to alert_type mapping
    if alert_type:
        normalized = alert_type.upper().replace(" ", "_")
        return _ALERT_TYPE_REASON_MAP.get(normalized, _ALERT_TYPE_REASON_MAP["BEHAVIORAL_ANOMALY"])

    return _ALERT_TYPE_REASON_MAP["BEHAVIORAL_ANOMALY"]


@router.get("/api/v1/agent/failed-cases")
def get_real_failed_cases(
    limit: int = 8,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return real high-risk alerts as failed cases for Kyro Chat display.
    Selects OPEN or ESCALATED alerts ordered by risk score descending.
    Derives a transaction-based failure reason from alert_type and triggered_rules.
    """
    alerts = (
        db.query(Alert, Customer.full_name)
        .join(Customer, Alert.customer_id == Customer.id)
        .filter(Alert.status.in_(["OPEN", "ESCALATED"]))
        .order_by(Alert.risk_score.desc())
        .limit(limit)
        .all()
    )

    # Build sequential CUST-XXX lookup per customer in result set
    cust_seq: dict[str, int] = {}
    seq_counter = 1

    results = []
    for alert, full_name in alerts:
        cust_id_str = str(alert.customer_id)
        if cust_id_str not in cust_seq:
            cust_seq[cust_id_str] = seq_counter
            seq_counter += 1
        cust_label = f"CUST-{cust_seq[cust_id_str]:03d}"
        case_label = f"CASE-{str(alert.id)[:6].upper()}"

        reason = _derive_failure_reason(alert.alert_type, alert.triggered_rules)

        # Also pull SHAP top feature description if available
        ml_expl = alert.ml_explanation
        if ml_expl and isinstance(ml_expl, dict):
            top_features = ml_expl.get("top_features") or []
            if top_features and isinstance(top_features, list):
                risk_increasing = [f for f in top_features if f.get("direction") == "INCREASES_RISK"]
                if risk_increasing:
                    feat_desc = risk_increasing[0].get("description", "")
                    if feat_desc:
                        reason = feat_desc  # Use SHAP explanation as the most precise reason

        results.append({
            "caseId": case_label,
            "customerId": cust_label,
            "customerName": full_name or "Unknown Customer",
            "alertType": alert.alert_type or "BEHAVIORAL_ANOMALY",
            "riskScore": alert.risk_score,
            "confidence": float(alert.confidence) if alert.confidence else None,
            "failureReason": reason,
            "recommendedAction": alert.recommended_action,
            "status": alert.status,
            "createdAt": alert.created_at.strftime("%H:%M") if alert.created_at else "--:--",
        })

    return results


# Action Timeline endpoint
@router.get("/api/v1/agent/autonomous/actions/timeline")
def get_action_timeline(hours: int = 24) -> list[dict[str, Any]]:
    if not agent_state.timeline:
        agent_state.timeline = [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action_type": "SCREEN_CUSTOMER",
                "action_id": "a1b2c3d4",
                "decision_reason": "Risk score above medium threshold (72.0)",
                "outcome": "SUCCESS",
                "success": True,
                "case_id": "C-101"
            },
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action_type": "RESOLVE_ALERT",
                "action_id": "x9y8z7w6",
                "decision_reason": "Verified false-positive pattern matching historical approvals.",
                "outcome": "SUCCESS",
                "success": True,
                "case_id": "C-103"
            }
        ]
    return agent_state.timeline[:10]


# Streaming endpoints
@router.post("/api/v1/streaming/start")
def start_streaming(req: StartStreamingRequest | None = None) -> dict[str, Any]:
    agent_state.streaming_is_running = True
    agent_state.streaming_pulse_label = "Screening cases continuously from live signals."
    return {
        "status": "running",
        "message": "Data stream ingestion initialized.",
        "event_types": (req.event_types if req else None) or ["transaction", "kyc_update"],
        "duration_minutes": (req.duration_minutes if req else None) or 60
    }

@router.post("/api/v1/streaming/stop")
def stop_streaming() -> dict[str, Any]:
    agent_state.streaming_is_running = False
    agent_state.streaming_pulse_label = "Screening services are warming up."
    return {"status": "stopped", "message": "Data stream ingestion stopped."}

@router.get("/api/v1/streaming/status")
def get_streaming_status() -> dict[str, Any]:
    return {
        "is_running": agent_state.streaming_is_running,
        "source_type": "kafka" if agent_state.streaming_is_running else "snapshot",
        "last_event_at": datetime.now(timezone.utc).isoformat() if agent_state.streaming_is_running else None,
        "processed_events_count": 142 if agent_state.streaming_is_running else 0
    }
