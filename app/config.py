"""
config.py — Application settings loaded from environment variables / .env.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
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
    # Score every newly ingested transaction with the ML models, after the
    # rules engine. Skipped quietly where the models or libraries are missing.
    ml_auto_score: bool = True
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
    # KYRO_MOCK_LLM is accepted as another spelling of KYRO_LLM_MOCK
    kyro_llm_mock: bool = Field(default=True, validation_alias=AliasChoices("KYRO_LLM_MOCK", "KYRO_MOCK_LLM"))
    kyro_llm_base_url: str = ""
    kyro_llm_api_key: SecretStr = SecretStr("")
    kyro_llm_model: str = "claude-haiku-4-5-20251001"
    kyro_llm_timeout_seconds: int = Field(
        default=30, validation_alias=AliasChoices("KYRO_LLM_TIMEOUT_SECONDS", "KYRO_LLM_READ_TIMEOUT_SECONDS")
    )

    # When true, PUT /rule-configs is refused and rule thresholds can only
    # change through an approved change request (/changes/rules).
    rule_changes_require_approval: bool = False
    # Users are created by an administrator. Turn this on only for a demo
    # environment where anyone may register themselves as an analyst.
    allow_self_registration: bool = False
    # Lets the Data Feeds page start a live feed of synthetic transactions.
    # Demo and development only: never turn it on where real customers are held.
    synthetic_feed_enabled: bool = False
    # Days a case may stay open before the case page marks it overdue, by risk band.
    # Placeholders: set them to the firm's own policy.
    case_target_days_high: int = 5
    case_target_days_medium: int = 10
    case_target_days_low: int = 20
    # Longest emergency access an approver may grant to one case
    emergency_access_max_minutes: int = 240

    # ── Rules engine R1 (docs/plans/RULES_ENGINE_IMPLEMENTATION_PHASES.md) ──
    # Each switch changes what alerts; all start off until Compliance has reviewed a replay.
    base_currency: str = "USD"
    fx_rates_url: str = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
    rules_base_currency_enabled: bool = False   # compare amounts in the base currency
    rules_noise_reduction_enabled: bool = False  # no per-payment PEP/sanctions hits; weak indicators need a real hit; R010 looks back only
    rules_consolidate_daily: bool = False       # one open rules alert per customer per day

    # Automatic assignment of new alerts to teams (services/assignment_service.py).
    # With no teams or routing rules set up, nothing is assigned.
    auto_assign_enabled: bool = True
    auto_assign_method: str = "least_loaded"  # least_loaded | round_robin

    # Where uploaded KYC documents are kept (local disk in development; use
    # encrypted object storage in production). Never inside the repository tree.
    document_storage_dir: str = "var/documents"

    # ── Watchlist screening (Phase 4.1) ─────────────────────────────
    watchlist_confirmed_match_score: float = 92.0
    watchlist_potential_match_score: float = 75.0
    watchlist_http_timeout_seconds: int = 60


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
