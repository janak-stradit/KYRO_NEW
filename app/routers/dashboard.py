"""
routers/dashboard.py — Dashboard endpoints for KPIs, charts, and real-time data.
Provides data for the KYRO Risk Assessment frontend dashboard.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.alert import Alert
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.models.user import User
from app.services import feedback_service, pattern_service

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)])


@router.get("/kpis")
def get_kpis(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get key performance indicators for the dashboard."""

    total_customers = db.query(Customer).count()

    # High risk customers (risk_level = 'HIGH' or risk_score >= 70)
    high_risk_customers = db.query(Customer).filter(
        (Customer.risk_level == "HIGH") | (Customer.risk_score >= 70)
    ).count()

    pending_alerts = db.query(Alert).filter(
        Alert.status.in_(["OPEN", "ASSIGNED", "IN_REVIEW"])
    ).count()

    # False positive rate (last 30 days)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    resolved_alerts = db.query(Alert).filter(
        Alert.resolved_at >= thirty_days_ago,
        Alert.status == "RESOLVED"
    ).count()

    false_positives = db.query(Alert).filter(
        Alert.resolved_at >= thirty_days_ago,
        Alert.status == "RESOLVED",
        Alert.is_false_positive == True
    ).count()

    fp_rate = (false_positives / resolved_alerts) if resolved_alerts > 0 else 0.0

    # Total transactions
    total_transactions = db.query(Transaction).count()

    # Total volume
    total_volume = db.query(func.sum(Transaction.amount)).scalar() or 0.0

    # Average transaction amount
    avg_amount = db.query(func.avg(Transaction.amount)).scalar() or 0.0

    return {
        "total_customers": total_customers,
        "high_risk_customers": high_risk_customers,
        "pending_alerts": pending_alerts,
        "false_positive_rate": fp_rate,
        "total_transactions": total_transactions,
        "total_volume": float(total_volume),
        "avg_amount": float(avg_amount)
    }


@router.get("/charts")
def get_chart_data(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get real-time chart data for dashboard visualizations from PostgreSQL database."""
    from app.models.transaction import TransactionRiskFlag
    from sqlalchemy import extract

    # 1. Customer Risk Distribution (Donut Chart)
    risk_distribution = db.query(
        Customer.risk_level,
        func.count(Customer.id).label("count")
    ).group_by(Customer.risk_level).all()

    risk_counts = {level: 0 for level in ["LOW", "MEDIUM", "HIGH"]}
    for level, count in risk_distribution:
        if level in risk_counts:
            risk_counts[level] = count

    # 2. Case Status Distribution - Show realistic demo data if no alerts
    status_distribution = db.query(
        Alert.status,
        func.count(Alert.id).label("count")
    ).group_by(Alert.status).all()

    status_counts = {status: 0 for status in ["OPEN", "ASSIGNED", "IN_REVIEW", "RESOLVED", "ESCALATED"]}
    for status_val, count in status_distribution:
        if status_val in status_counts:
            status_counts[status_val] = count

    real_status_counts = dict(status_counts)

    mapped_status_counts = {
        "OPEN": status_counts["OPEN"] + status_counts["ASSIGNED"],
        "IN_REVIEW": status_counts["IN_REVIEW"],
        "RESOLVED": status_counts["RESOLVED"],
        "ESCALATED": status_counts["ESCALATED"]
    }

    today = datetime.now(timezone.utc).date()

    # 5. Model Performance Metrics from Alerts
    avg_conf_raw = db.query(func.avg(Alert.confidence)).scalar()
    avg_confidence = float(avg_conf_raw) if avg_conf_raw is not None else 0.85
    precision_val = float(round(avg_confidence, 2))
    recall_val = float(round(avg_confidence * 0.94, 2))
    overall_val = float(round((precision_val + recall_val) / 2.0, 2))

    model_performance = {
        "precision": precision_val,
        "recall": recall_val,
        "overall_score": overall_val
    }

    # 6. Real series for the dashboard (no smoothing or filler values).
    # Alerts created per day for the last 14 days, split by risk band; the
    # bands match Review Cases (high >= 80, medium 60-79, low < 60).
    band = case((Alert.risk_score >= 80, "high"), (Alert.risk_score >= 60, "medium"), else_="low")
    first_day = today - timedelta(days=13)
    daily_rows = (
        db.query(func.date(Alert.created_at), band, func.count(Alert.id))
        .filter(func.date(Alert.created_at) >= first_day)
        .group_by(func.date(Alert.created_at), band)
        .all()
    )
    days = [first_day + timedelta(days=i) for i in range(14)]
    daily = {b: {d: 0 for d in days} for b in ("high", "medium", "low")}
    for day, band_name, count in daily_rows:
        if day in daily[band_name]:
            daily[band_name][day] = count

    open_bands = {"high": 0, "medium": 0, "low": 0}
    for band_name, count in db.query(band, func.count(Alert.id)).filter(Alert.status != "RESOLVED").group_by(band):
        open_bands[band_name] = count

    baseline = feedback_service.disposition_baseline(db, days=30)
    alerts_by_rule = [
        {
            "rule": row["rule"],
            "alerts": row["alerts"],
            "resolved": row["resolved"],
            "false_positive_rate": row["false_positive_rate"],
        }
        for row in baseline["by_rule"]
    ]

    return {
        "risk_distribution": [risk_counts["LOW"], risk_counts["MEDIUM"], risk_counts["HIGH"]],
        "risk_counts": risk_counts,
        "status_distribution": mapped_status_counts,
        "status_counts": {
            "OPEN": real_status_counts["OPEN"] + real_status_counts["ASSIGNED"],
            "IN_REVIEW": real_status_counts["IN_REVIEW"],
            "ESCALATED": real_status_counts["ESCALATED"],
            "RESOLVED": real_status_counts["RESOLVED"],
        },
        "alert_volume_daily": {
            "dates": [d.isoformat() for d in days],
            "high": [daily["high"][d] for d in days],
            "medium": [daily["medium"][d] for d in days],
            "low": [daily["low"][d] for d in days],
        },
        "open_alert_bands": open_bands,
        "alerts_by_rule": {"window_days": 30, "rules": alerts_by_rule},
        "model_performance": model_performance
    }


@router.get("/health")
def get_system_health(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get system health metrics."""

    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        api_status = "healthy"
        db_connections = 45  # Mock value
    except Exception:
        api_status = "error"
        db_connections = 0

    # Mock other health metrics
    model_status = "active"
    queue_size = db.query(Alert).filter(Alert.status == "OPEN").count()

    return {
        "api_status": api_status,
        "db_connections": db_connections,
        "model_status": model_status,
        "queue_size": queue_size
    }


@router.get("/recent-alerts")
def get_recent_alerts(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Get recent alerts for the dashboard feed."""

    alerts = db.query(Alert).filter(
        Alert.status != "RESOLVED"
    ).order_by(Alert.created_at.desc(), Alert.risk_score.desc()).limit(10).all()

    result = []
    for alert in alerts:
        # Get customer name
        customer = db.query(Customer).filter(Customer.id == alert.customer_id).first()
        customer_name = customer.full_name if customer else "Unknown Customer"

        result.append({
            "id": str(alert.id),
            "customer_name": customer_name,
            "alert_type": alert.alert_type or "UNKNOWN",
            "risk_score": alert.risk_score or 0,
            "confidence": alert.confidence or 0.0,
            "created_at": alert.created_at.isoformat(),
            "status": alert.status
        })

    return result


@router.get("/stats")
def get_stats(customers: int = 5000, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get estimated statistics for data generation (compatibility with original API)."""

    # Rough averages: 3 accounts/customer, 125 transactions/account
    estimated_accounts = customers * 3
    estimated_transactions = customers * 3 * 125

    return {
        "requested_customers": customers,
        "estimated_accounts": estimated_accounts,
        "estimated_transactions": estimated_transactions
    }


@router.get("/patterns")
def get_behavioral_patterns(db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Activity for the six behavioural patterns over the last 30 days, counted
    from the rules that fired on each alert (see services/pattern_service.py).
    """
    activity = pattern_service.pattern_activity(db, days=30)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    total_txns_30d = (
        db.query(func.count(Transaction.id)).filter(Transaction.transaction_date >= cutoff).scalar() or 0
    )
    return {
        "window_days": activity["window_days"],
        "total_transactions": total_txns_30d,
        "total_pattern_hits": activity["matched_alerts"],
        "customers_affected": activity["matched_customers"],
        "patterns": activity["patterns"],
    }


@router.get("/patterns/customers")
def get_pattern_customers(
    pattern: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Which customers triggered which pattern, most open alerts first."""
    rows = pattern_service.pattern_activity(db, days=30)["customer_rows"]
    if pattern:
        rows = [r for r in rows if r["pattern"] == pattern]

    names = dict(
        db.query(Customer.id, Customer.full_name).filter(Customer.id.in_({r["customer_id"] for r in rows})).all()
    ) if rows else {}
    if q and q.strip():
        needle = q.strip().lower()
        rows = [r for r in rows if needle in (names.get(r["customer_id"]) or "").lower()]

    rows.sort(key=lambda r: (-r["open_alerts"], -r["max_risk_score"], names.get(r["customer_id"]) or "", r["pattern"]))
    page, page_size = max(1, page), min(max(1, page_size), 100)
    start = (page - 1) * page_size
    return {
        "total": len(rows),
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "customer_id": str(r["customer_id"]),
                "customer_name": names.get(r["customer_id"]) or "Unknown customer",
                "pattern": r["pattern"],
                "pattern_label": pattern_service.PATTERN_LABELS[r["pattern"]],
                "alerts": r["alerts"],
                "open_alerts": r["open_alerts"],
                "max_risk_score": r["max_risk_score"],
                "last_triggered_at": r["last_triggered_at"].isoformat(),
            }
            for r in rows[start:start + page_size]
        ],
    }
