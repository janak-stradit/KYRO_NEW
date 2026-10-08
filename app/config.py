"""
config.py — Application settings loaded from environment variables / .env.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "KYRO Risk Assessment"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://kyro_user:kyro_pass@localhost:5432/kyro_aml"
    redis_url: str = "redis://localhost:6380/0"

    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ── HTTP hardening ─────────────────────────────────────────────
    # Comma-separated list of origins allowed to make cross-origin calls.
    # The bundled frontend is served same-origin via nginx and needs none;
    # the defaults only cover local dev servers. Never use "*" here.
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    rate_limit_enabled: bool = True
    rate_limit_default: str = "300/minute"
    rate_limit_login: str = "10/minute"
    # Empty = per-process in-memory counters; set to e.g. redis://redis:6379/1
    # so limits are shared across API workers/replicas.
    rate_limit_storage_uri: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip() and o.strip() != "*"]

    # ── Local (non-Docker) run ─────────────────────────────────────
    # Path to frontend/phase3 to serve it from the API itself; empty in Docker,
    # where nginx serves the frontend.
    serve_frontend_dir: str = ""

    # ── ML (Phase 2) ─────────────────────────────────────────────
    # True = start without /api/v1/ml endpoints if the ML stack can't import.
    ml_optional: bool = False
    model_registry_path: str = "./models"
    default_risk_model_version: int | None = None
    default_anomaly_model_version: int | None = None
    retrain_threshold: int = 1000
    performance_threshold: float = 0.85
    training_data_days: int = 365
    shap_explanation_top_k: int = 5

    # ── Compliance AI (Phase 11, docs/plans/COMPLIANCE_AI_PLAN.md) ──
    # Off and mocked by default: nothing is sent to an LLM until both
    # KYRO_AI_ENABLED=true and KYRO_LLM_MOCK=false are set explicitly.
    kyro_ai_enabled: bool = False
    kyro_llm_mock: bool = True
    kyro_llm_base_url: str = ""
    kyro_llm_api_key: SecretStr = SecretStr("")
    kyro_llm_model: str = "claude-haiku-4-5-20251001"
    kyro_llm_timeout_seconds: int = 30

    # When true, PUT /rule-configs is refused and rule thresholds can only
    # change through an approved change request (/changes/rules).
    rule_changes_require_approval: bool = False

    # ── Watchlist screening (Phase 4.1) ─────────────────────────────
    watchlist_confirmed_match_score: float = 92.0
    watchlist_potential_match_score: float = 75.0
    watchlist_http_timeout_seconds: int = 60


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
