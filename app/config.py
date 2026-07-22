"""
config.py — Application settings loaded from environment variables / .env.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "KYRO Risk Assessment"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "sqlite:///./kyro_aml.db"
    redis_url: str = "redis://localhost:6380/0"

    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ── ML (Phase 2) ─────────────────────────────────────────────
    model_registry_path: str = "./models"
    default_risk_model_version: int | None = None
    default_anomaly_model_version: int | None = None
    retrain_threshold: int = 1000
    performance_threshold: float = 0.85
    training_data_days: int = 365
    shap_explanation_top_k: int = 5


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
