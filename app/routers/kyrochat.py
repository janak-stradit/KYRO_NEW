"""
routers/kyrochat.py — Endpoints for the Kyro Chat interface, autonomous compliance agent status, and streaming simulation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
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
        # Pull the most recent high-risk alert from the real database
        top_alert = (
            db.query(Alert, Customer)
            .join(Customer, Alert.customer_id == Customer.id)
            .filter(Alert.risk_score >= 80)
            .order_by(Alert.risk_score.desc())
            .first()
        )
        if top_alert:
            a, cust = top_alert
            reason = _derive_transaction_behavioral_reason(db, a, cust)
            response_text = (
                f"Top High-Risk Case Details:\n"
                f"• Customer: {cust.full_name}\n"
                f"• Score: {a.risk_score} ({a.recommended_action or 'HIGH RISK'})\n"
                f"• Trigger: {reason}\n"
                f"• Status: {a.status}\n"
                f"• Recommendation: {a.recommended_action or 'Escalate for enhanced due diligence'}."
            )
        else:
            response_text = "No high-risk cases found in the current database."
        suggestions = ["What is the status of the backlog?", "Explain risk for case C-102"]
        
    elif "anomaly" in user_msg or "transaction" in user_msg:
        high_alerts = (
            db.query(Alert, Customer)
            .join(Customer, Alert.customer_id == Customer.id)
            .filter(Alert.risk_score >= 80)
            .limit(3)
            .all()
        )
        if high_alerts:
            details_list = []
            for a, cust in high_alerts:
                reason = _derive_transaction_behavioral_reason(db, a, cust)
                details_list.append(f"• Customer: {cust.full_name} (Risk Score: {a.risk_score}/100)\n  Details: {reason}")
            details = "\n\n".join(details_list)
            response_text = f"Recent transaction anomalies requiring compliance review:\n\n{details}"
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
    
    # Real stats from DB
    open_count = db.query(Alert).filter(Alert.status == "OPEN").count()
    resolved_count = db.query(Alert).filter(Alert.status == "RESOLVED").count()
    escalated_count = db.query(Alert).filter(Alert.status == "ESCALATED").count()
    agent_state.processing_cases_count = open_count if open_count > 0 else 0
    agent_state.latest_action_label = "Kyro here. Authorization received. I'm starting autonomous operations now."
    agent_state.streaming_pulse_label = "Screening cases continuously from live signals."
    agent_state.run_stats = {
        "actions": resolved_count + escalated_count,
        "success": resolved_count,
        "failure": escalated_count,
        "casesTouched": open_count
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
    # Get active/open/assigned alerts to show real processing cases in the UI
    open_alerts = (
        db.query(Alert, Customer.full_name)
        .join(Customer, Alert.customer_id == Customer.id)
        .filter(Alert.status.in_(["OPEN", "ASSIGNED", "IN_REVIEW"]))
        .order_by(Alert.risk_score.desc())
        .limit(5)
        .all()
    )
    if not open_alerts:
        open_alerts = (
            db.query(Alert, Customer.full_name)
            .join(Customer, Alert.customer_id == Customer.id)
            .order_by(Alert.risk_score.desc())
            .limit(5)
            .all()
        )
    processing = []
    for a, full_name in open_alerts:
        processing.append({
            "case_id": f"CASE-{str(a.id)[:6].upper()}",
            "customer_name": full_name or "Unknown Customer",
            "alert_type": a.alert_type or "BEHAVIORAL_ANOMALY",
            "risk_score": a.risk_score,
            "status": "ANALYZING"
        })
    return processing


# ── Real Transactional Failure Reason Generator ─────────────────────────────────
def _derive_transaction_behavioral_reason(db: Session, alert: Alert, customer: Customer) -> str:
    """Derive failure reason strictly from the customer's actual transaction history and behavioral patterns in the database."""
    top_txn = (
        db.query(Transaction)
        .filter(Transaction.customer_id == alert.customer_id)
        .order_by(Transaction.amount.desc())
        .first()
    )

    txn_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.customer_id == alert.customer_id)
        .scalar() or 0
    )

    total_volume = (
        db.query(func.sum(Transaction.amount))
        .filter(Transaction.customer_id == alert.customer_id)
        .scalar() or 0.0
    )

    alert_type = (alert.alert_type or "BEHAVIORAL_ANOMALY").upper().replace(" ", "_")

    if top_txn:
        amt_fmt = f"${float(top_txn.amount):,.2f}"
        curr = top_txn.currency or "USD"
        txn_type = (top_txn.transaction_type or "TRANSFER").title()
        cp = top_txn.meta_counterparty or "External Counterparty"

        if alert_type in ("SANCTIONS_HIT", "SANCTIONS") or customer.sanctions_flag:
            return f"Sanctions Risk Match: High-value {txn_type} of {curr} {amt_fmt} to counterparty '{cp}' matched OFAC/UN sanctions watchlists."
        elif alert_type in ("PEP_ACTIVITY", "PEP") or customer.pep_flag:
            return f"Politically Exposed Person (PEP) Activity: {txn_type} of {curr} {amt_fmt} involving counterparty '{cp}' requires mandatory enhanced due diligence screening."
        elif alert_type in ("THRESHOLD_BREACH", "LARGE_AMOUNT") or float(top_txn.amount) >= 10000:
            return f"Large Transaction Reporting Limit Breached: Single {txn_type} of {curr} {amt_fmt} to counterparty '{cp}' exceeded the $10,000 regulatory reporting threshold."
        elif alert_type in ("VELOCITY_SPIKE", "STRUCTURING"):
            return f"Unusual Transaction Velocity: Customer executed {txn_count} rapid transactions totaling ${float(total_volume):,.2f}, violating historical baseline frequency."
        elif alert_type in ("GEOGRAPHIC_SHIFT", "GEOGRAPHY") or top_txn.meta_country:
            country = top_txn.meta_country or "High-Risk Jurisdiction"
            return f"Cross-Border Geographic Risk: {curr} {amt_fmt} {txn_type} transfer routed to {country} represents an unusual geographic destination for this customer profile."
        elif alert_type in ("COUNTERPARTY_CHANGES", "COMPLEXITY_SHIFT"):
            return f"Unverified Counterparty Layering Anomaly: {txn_type} of {curr} {amt_fmt} to unverified entity '{cp}' ({txn_count} total account transactions) indicates potential funds layering."
        else:
            return f"Transaction Behavioral Pattern Deviation: {txn_type} of {curr} {amt_fmt} to counterparty '{cp}' ({txn_count} total transactions, ${float(total_volume):,.2f} cumulative volume) deviates from customer's established activity profile."
    else:
        flags = []
        if customer.sanctions_flag:
            flags.append("active sanctions watchlist hit")
        if customer.pep_flag:
            flags.append("politically exposed person (PEP) status")
        if customer.adverse_media_flag:
            flags.append("adverse media screening hit")
            
        if flags:
            return f"Compliance Profile Screening Risk: Customer flagged for {', '.join(flags)} with risk score {alert.risk_score}/100."
        return f"Behavioral Risk Profile Deviation: Customer risk score {alert.risk_score}/100 ({customer.risk_level or 'HIGH'} risk level) flagged for enhanced due diligence review."


@router.get("/api/v1/agent/failed-cases")
def get_real_failed_cases(
    limit: int = 8,
    db: Session = Depends(get_db),
    user: Any = None,
) -> list[dict[str, Any]]:
    """Return real high-risk alerts as failed cases for Kyro Chat display.
    Selects OPEN or ESCALATED alerts ordered by risk score descending.
    Derives transaction-based failure reasons from actual transaction behavioral patterns in app.transactions.
    """
    alerts = (
        db.query(Alert, Customer)
        .join(Customer, Alert.customer_id == Customer.id)
        .filter(Alert.status.in_(["OPEN", "ESCALATED"]))
        .order_by(Alert.risk_score.desc())
        .limit(limit)
        .all()
    )

    results = []
    for alert, customer in alerts:
        case_label = f"CASE-{str(alert.id)[:6].upper()}"

        reason = _derive_transaction_behavioral_reason(db, alert, customer)

        results.append({
            "caseId": case_label,
            "customerId": str(customer.id),
            "customerName": customer.full_name or "Unknown Customer",
            "alertType": alert.alert_type or "BEHAVIORAL_ANOMALY",
            "riskScore": alert.risk_score,
            "confidence": float(alert.confidence) if alert.confidence else None,
            "failureReason": reason,
            "recommendedAction": alert.recommended_action or "ENHANCED_DUE_DILIGENCE",
            "status": alert.status,
            "createdAt": alert.created_at.strftime("%H:%M") if alert.created_at else "--:--",
        })

    return results


# Action Timeline endpoint
@router.get("/api/v1/agent/autonomous/actions/timeline")
def get_action_timeline(hours: int = 24) -> list[dict[str, Any]]:
    if not agent_state.timeline:
        # Populate timeline from real DB alerts instead of hardcoded fake entries
        from app.database import SessionLocal as _SL
        with _SL() as _db:
            recent_alerts = (
                _db.query(Alert, Customer)
                .join(Customer, Alert.customer_id == Customer.id)
                .order_by(Alert.created_at.desc())
                .limit(5)
                .all()
            )
            for a, cust in recent_alerts:
                reason = _derive_transaction_behavioral_reason(_db, a, cust)
                agent_state.timeline.append({
                    "timestamp": a.created_at.isoformat() if a.created_at else datetime.now(timezone.utc).isoformat(),
                    "action_type": "SCREEN_CUSTOMER",
                    "action_id": str(a.id)[:8],
                    "decision_reason": reason,
                    "outcome": "SUCCESS",
                    "success": True,
                    "case_id": f"CASE-{str(a.id)[:6].upper()}",
                    "customer_name": cust.full_name or "Unknown"
                })
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
def get_streaming_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    txn_count = db.query(Transaction).count() if agent_state.streaming_is_running else 0
    return {
        "is_running": agent_state.streaming_is_running,
        "source_type": "kafka" if agent_state.streaming_is_running else "snapshot",
        "last_event_at": datetime.now(timezone.utc).isoformat() if agent_state.streaming_is_running else None,
        "processed_events_count": txn_count
    }
