"""
ml/training/pipeline.py — Orchestrates a full training run: pull data, train
all three models, persist to the registry. First-ever run activates the
models directly (nothing to A/B against); subsequent runs default to staging
as a traffic-split candidate so a bad retrain can't silently replace a good
model in production.
"""
from __future__ import annotations

from app.database import SessionLocal
from app.ml.registry.model_registry import ModelNotFoundError, ModelRegistry
from app.ml.training.trainer import train_all

MODEL_NAMES = ("risk_scorer", "anomaly_classifier", "isolation_detector")


def run_training_pipeline(
    *, as_candidate: bool = False, candidate_traffic_pct: float = 10.0, limit: int | None = None
) -> dict:
    registry = ModelRegistry()
    db = SessionLocal()
    try:
        result = train_all(db, limit=limit)
    finally:
        db.close()

    models = {
        "risk_scorer": result.risk_scorer,
        "anomaly_classifier": result.anomaly_classifier,
        "isolation_detector": result.isolation_detector,
    }

    versions: dict[str, int] = {}
    for name, model in models.items():
        version = registry.next_version(name)
        registry.save_model(model, name, version, result.metrics)
        versions[name] = version

        try:
            registry.get_routing(name)
            has_active = True
        except ModelNotFoundError:
            has_active = False

        if as_candidate and has_active:
            registry.set_candidate(name, version, candidate_traffic_pct)
        else:
            registry.set_active(name, version)

    return {"versions": versions, "metrics": result.metrics}
