"""
core/config.py — Configuration loader with environment variable interpolation.
Loads pipeline.yaml and merges environment variables using ${VAR:default} syntax.
"""
from __future__ import annotations

import os
import re
import logging
from pathlib import Path
from functools import lru_cache
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ENV_RE = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")


def _interpolate(value: Any) -> Any:
    """Recursively resolve ${ENV_VAR:default} placeholders in config values."""
    if isinstance(value, str):
        def replacer(m: re.Match) -> str:
            key, default = m.group(1), m.group(2) or ""
            return os.environ.get(key, default)
        return _ENV_RE.sub(replacer, value)
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    return value


@lru_cache(maxsize=1)
def load_config(config_path: str | None = None) -> dict:
    """Load and cache pipeline configuration.

    Args:
        config_path: Path to YAML config file. Defaults to pipeline/config/pipeline.yaml.

    Returns:
        Fully interpolated configuration dictionary.
    """
    if config_path is None:
        config_path = str(
            Path(__file__).parent.parent / "config" / "pipeline.yaml"
        )
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    config = _interpolate(raw)
    logger.info("Config loaded from %s (env=%s)", path, config.get("pipeline", {}).get("environment"))
    return config


def get_db_url(config: dict | None = None, async_driver: bool = False) -> str:
    """Build SQLAlchemy database URL from config.

    Args:
        config: Pipeline config dict. Loaded automatically if None.
        async_driver: If True, use psycopg async driver URL format.

    Returns:
        SQLAlchemy-compatible database connection URL string.
    """
    cfg = config or load_config()
    db = cfg["database"]
    driver = "postgresql+psycopg" if not async_driver else "postgresql+psycopg_async"
    return (
        f"{driver}://{db['user']}:{db['password']}"
        f"@{db['host']}:{db['port']}/{db['name']}"
        f"?sslmode={db['ssl_mode']}"
    )


def get_raw_db_url(config: dict | None = None) -> str:
    """Build a plain psycopg3 conninfo string (no SQLAlchemy prefix)."""
    cfg = config or load_config()
    db = cfg["database"]
    return (
        f"host={db['host']} port={db['port']} dbname={db['name']} "
        f"user={db['user']} password={db['password']} sslmode={db['ssl_mode']}"
    )
