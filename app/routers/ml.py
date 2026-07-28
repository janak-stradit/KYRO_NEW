"""
routers/ml.py — Real-time/batch ML scoring, training, model status, and
performance-monitoring endpoints.

score-transaction scores an already-ingested transaction (fetched by ID)
rather than an ad-hoc payload — feature engineering depends on the
transaction's persisted history, so there's no meaningful way to score a
transaction that doesn't exist in the database yet. POST /transactions
(Phase 1) is still what creates it; this endpoint adds the ML layer on top.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_role
from app.ml.registry.model_registry import ModelNotFoundError, ModelRegistry
from app.ml.scoring.batch_scorer import score_batch
from app.ml.scoring.real_time_scorer import RealTimeScorer, ScoringUnavailableError
from app.ml.training.pipeline import MODEL_NAMES, run_training_pipeline
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.ml import (
    ModelStatus,
    PerformanceResponse,
    ScoreBatchItem,
    ScoreBatchRequest,
    ScoreCustomerResponse,
    ScoreTransactionRequest,
    ScoreTransactionResponse,
    TrainRequest,
    TrainResponse,
)
from app.services import feedback_service
from app.services.alert_service import LOW_MAX, MEDIUM_MAX, AlertRouter

router = APIRouter(prefix="/api/v1/ml", tags=["ml"], dependencies=[Depends(get_current_user)])


def _risk_level_for(score: float) -> str:
    if score <= LOW_MAX:
        return "LOW"
    if score <= MEDIUM_MAX:
        return "MEDIUM"
    return "HIGH"


@router.post("/score-transaction", response_model=ScoreTransactionResponse)
def score_transaction(data: ScoreTransactionRequest, db: Session = Depends(get_db)) -> ScoreTransactionResponse:
    txn = db.get(Transaction, data.transaction_id)
    if txn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    customer = db.get(Customer, txn.customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")

    try:
        result = RealTimeScorer().score_transaction(db, txn, customer)
    except ScoringUnavailableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Models not trained yet: {exc}") from exc

    alert = AlertRouter().route(
        db,
        customer=customer,
        risk_score=result["risk_score"],
        confidence=result["anomaly_probability"],
        explanation=result["explanation"],
    )
    db.commit()

    return ScoreTransactionResponse(
        transaction_id=txn.id,
        risk_score=result["risk_score"],
        anomaly_flag=result["anomaly_flag"],
        confidence=result["anomaly_probability"],
        ml_explanation=result["explanation"],
        alert_created=alert is not None,
        alert_id=alert.id if alert else None,
        recommended_action=alert.recommended_action if alert else "NONE",
    )


@router.post("/score-batch", response_model=list[ScoreBatchItem])
def score_batch_endpoint(data: ScoreBatchRequest, db: Session = Depends(get_db)) -> list[ScoreBatchItem]:
    transactions = db.query(Transaction).filter(Transaction.id.in_(data.transaction_ids)).all()
    if len(transactions) != len(data.transaction_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One or more transactions not found")
    try:
        results = score_batch(db, transactions)
    except ScoringUnavailableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Models not trained yet: {exc}") from exc
    db.commit()
    return [ScoreBatchItem(**r) for r in results]


@router.post("/score-customer/{customer_id}", response_model=ScoreCustomerResponse)
def score_customer(customer_id: uuid.UUID, db: Session = Depends(get_db)) -> ScoreCustomerResponse:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent_txns = (
        db.query(Transaction)
        .filter(Transaction.customer_id == customer_id, Transaction.transaction_date >= cutoff)
        .order_by(Transaction.transaction_date.asc())
        .all()
    )

    if not recent_txns:
        return ScoreCustomerResponse(
            customer_id=customer_id,
            overall_risk=float(customer.risk_score),
            risk_level=customer.risk_level,
            behavioral_anomalies=[],
            trend_summary="No recent transaction activity",
            recommendation=None,
        )

    try:
        results = score_batch(db, recent_txns)
    except ScoringUnavailableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Models not trained yet: {exc}") from exc

    overall_risk = sum(r["risk_score"] for r in results) / len(results)
    risk_level = _risk_level_for(overall_risk)
    behavioral_anomalies = [r for r in results if r["anomaly_flag"]]

    midpoint = cutoff + (datetime.now(timezone.utc) - cutoff) / 2
    first_half = [r for t, r in zip(recent_txns, results) if t.transaction_date < midpoint]
    second_half = [r for t, r in zip(recent_txns, results) if t.transaction_date >= midpoint]
    avg_first = sum(r["risk_score"] for r in first_half) / len(first_half) if first_half else overall_risk
    avg_second = sum(r["risk_score"] for r in second_half) / len(second_half) if second_half else overall_risk
    if avg_second > avg_first * 1.1:
        trend = "Risk trending upward over the last 30 days"
    elif avg_second < avg_first * 0.9:
        trend = "Risk trending downward over the last 30 days"
    else:
        trend = "Risk stable over the last 30 days"

    customer.risk_score = round(overall_risk)
    customer.risk_level = risk_level
    db.commit()

    recommendation = None
    if risk_level == "HIGH":
        recommendation = "Escalate for enhanced due diligence"
    elif behavioral_anomalies:
        recommendation = "Review flagged transactions for behavioral anomalies"

    return ScoreCustomerResponse(
        customer_id=customer_id,
        overall_risk=round(overall_risk, 2),
        risk_level=risk_level,
        behavioral_anomalies=[{"transaction_id": r["transaction_id"], "risk_score": r["risk_score"]} for r in behavioral_anomalies],
        trend_summary=trend,
        recommendation=recommendation,
    )


@router.post("/train", response_model=TrainResponse)
def train(data: TrainRequest, user: User = Depends(require_role("ADMIN"))) -> TrainResponse:
    if data.run_async:
        from app.tasks.ml_tasks import run_training_pipeline_task

        task = run_training_pipeline_task.delay(
            as_candidate=data.as_candidate, candidate_traffic_pct=data.candidate_traffic_pct, limit=data.limit
        )
        return TrainResponse(status="QUEUED", task_id=task.id)

    try:
        result = run_training_pipeline(
            as_candidate=data.as_candidate, candidate_traffic_pct=data.candidate_traffic_pct, limit=data.limit
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return TrainResponse(status="COMPLETED", versions=result["versions"], metrics=result["metrics"])


@router.get("/models", response_model=list[ModelStatus])
def list_models() -> list[ModelStatus]:
    registry = ModelRegistry()
    statuses = []
    for name in MODEL_NAMES:
        versions = registry.list_versions(name)
        try:
            routing = registry.get_routing(name)
            active, candidate, traffic = routing["active"], routing.get("candidate"), routing.get("candidate_traffic_pct", 0)
        except ModelNotFoundError:
            active, candidate, traffic = None, None, 0
        statuses.append(
            ModelStatus(name=name, active_version=active, candidate_version=candidate, candidate_traffic_pct=traffic, available_versions=versions)
        )
    return statuses


@router.get("/performance", response_model=PerformanceResponse)
def performance(window_days: int = 30, db: Session = Depends(get_db)) -> PerformanceResponse:
    feedback = feedback_service.collect_feedback(db, days=window_days)
    result = feedback_service.evaluate_performance(feedback)
    return PerformanceResponse(**result, window_days=window_days)
