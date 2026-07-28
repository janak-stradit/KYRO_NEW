"""
security/secrets.py — Secrets management and SQL injection prevention.
Provides parameterized query builders and environment-based secret loading.
"""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

# Characters that must NEVER appear in identifiers (schema/table/column names)
_SAFE_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def safe_identifier(name: str) -> str:
    """
    Validate and return a safe SQL identifier (table/column/schema name).
    Raises ValueError if the name contains invalid characters.
    This is the primary SQL injection prevention for dynamic SQL construction.

    Args:
        name: Proposed SQL identifier.

    Returns:
        The original name if safe.

    Raises:
        ValueError: If the name contains non-identifier characters.
    """
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Unsafe SQL identifier detected: '{name}'. "
            "Only alphanumeric characters and underscores are allowed."
        )
    return name


def quote_identifier(name: str) -> str:
    """Return a safely double-quoted SQL identifier after validation."""
    return f'"{safe_identifier(name)}"'


@lru_cache(maxsize=64)
def get_secret(key: str, default: str | None = None) -> str | None:
    """
    Retrieve a secret from environment variables.
    Supports Docker secrets via /run/secrets/<key> (Docker Swarm pattern).

    Args:
        key: Environment variable name.
        default: Default value if not found.

    Returns:
        Secret value or default.
    """
    # Try environment variable first
    val = os.environ.get(key)
    if val is not None:
        return val

    # Try Docker secret file
    secret_file = f"/run/secrets/{key.lower()}"
    if os.path.exists(secret_file):
        try:
            with open(secret_file, "r") as f:
                return f.read().strip()
        except IOError as exc:
            logger.warning("Failed to read secret file %s: %s", secret_file, exc)

    if default is None:
        logger.warning("Secret '%s' not found in environment or secrets files", key)
    return default


def build_db_url_from_secrets() -> str:
    """Build PostgreSQL connection URL using individually stored secrets."""
    host = get_secret("DB_HOST", "localhost")
    port = get_secret("DB_PORT", "5432")
    name = get_secret("DB_NAME", "kyro_aml")
    user = get_secret("DB_USER", "kyro_user")
    password = get_secret("DB_PASSWORD", "kyro_pass")
    ssl = get_secret("DB_SSL_MODE", "prefer")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}?sslmode={ssl}"


def mask_sensitive(data: dict, keys: list[str] | None = None) -> dict:
    """Return a copy of dict with sensitive keys masked for safe logging."""
    sensitive = keys or ["password", "token", "secret", "key", "api_key", "credential"]
    return {
        k: ("***MASKED***" if any(s in k.lower() for s in sensitive) else v)
        for k, v in data.items()
    }
