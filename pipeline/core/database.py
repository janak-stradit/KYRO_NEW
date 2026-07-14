"""
core/database.py — SQLAlchemy + psycopg3 engine factory with connection pooling.
Supports sync (SQLAlchemy ORM/Core) and async access patterns.
Implements retry logic, deadlock detection, and transaction management.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Generator

import psycopg
from psycopg.rows import dict_row
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from pipeline.core.config import get_db_url, get_raw_db_url, load_config
from pipeline.core.exceptions import (
    ConnectionPoolError,
    DatabaseError,
    DeadlockError,
    MaxRetriesExceededError,
)

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine(config: dict | None = None) -> Engine:
    """Return (or lazily create) the singleton SQLAlchemy engine.

    Uses QueuePool with settings from config, SSL-ready.
    """
    global _engine
    if _engine is not None:
        return _engine

    cfg = config or load_config()
    db_cfg = cfg["database"]
    url = get_db_url(cfg)

    _engine = create_engine(
        url,
        poolclass=QueuePool,
        pool_size=int(db_cfg["pool_size"]),
        max_overflow=int(db_cfg["max_overflow"]),
        pool_timeout=int(db_cfg["pool_timeout"]),
        pool_recycle=int(db_cfg["pool_recycle"]),
        pool_pre_ping=True,          # validate connections before use
        echo=db_cfg.get("echo_sql", False),
        connect_args={"sslmode": db_cfg["ssl_mode"]},
    )

    # Listener: log slow queries (>500ms)
    @event.listens_for(_engine, "after_cursor_execute")
    def _on_slow_query(conn, cursor, statement, parameters, context, executemany):
        elapsed = getattr(context, "_query_start_time", 0)
        if elapsed and (time.perf_counter() - elapsed) > 0.5:
            logger.warning("Slow query (>500ms): %.3fs — %s", time.perf_counter() - elapsed, statement[:120])

    @event.listens_for(_engine, "before_cursor_execute")
    def _before_query(conn, cursor, statement, parameters, context, executemany):
        context._query_start_time = time.perf_counter()

    logger.info("SQLAlchemy engine created: pool_size=%s, max_overflow=%s", db_cfg["pool_size"], db_cfg["max_overflow"])
    return _engine


def get_session_factory(config: dict | None = None) -> sessionmaker:
    """Return the singleton session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine(config)
        _SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    return _SessionLocal


@contextmanager
def get_db_session(config: dict | None = None) -> Generator[Session, None, None]:
    """Context manager yielding an auto-committing/rolling-back ORM session.

    Usage::

        with get_db_session() as session:
            session.add(some_model)
    """
    factory = get_session_factory(config)
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_psycopg_conn(config: dict | None = None) -> Generator[psycopg.Connection, None, None]:
    """Yield a raw psycopg3 connection with dict_row factory.
    Used for bulk COPY operations and prepared statements.
    """
    cfg = config or load_config()
    conninfo = get_raw_db_url(cfg)
    try:
        with psycopg.connect(conninfo, row_factory=dict_row) as conn:
            yield conn
    except psycopg.OperationalError as exc:
        raise ConnectionPoolError(f"Cannot connect to database: {exc}") from exc


import functools

def with_retry(
    max_retries: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
    config: dict | None = None,
    exceptions=(psycopg.errors.DeadlockDetected, psycopg.OperationalError),
):
    """Execute a callable with exponential backoff retry on transient DB errors."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            cfg = config or load_config()
            _max = int(cfg.get("pipeline", {}).get("max_retries", max_retries))
            _delay = float(cfg.get("pipeline", {}).get("retry_delay_seconds", delay))

            attempt = 0
            current_delay = _delay
            while attempt <= _max:
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    attempt += 1
                    logger.warning("Transient error (attempt %d/%d) in %s: %s", attempt, _max, func.__name__, exc)
                    if attempt > _max:
                        raise MaxRetriesExceededError(str(func), attempt) from exc
                    time.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator


def create_schemas(config: dict | None = None) -> None:
    """Create all pipeline schemas if they do not yet exist."""
    cfg = config or load_config()
    schemas = cfg.get("schemas", [])
    engine = get_engine(cfg)
    with engine.begin() as conn:
        for schema in schemas:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            logger.debug("Schema ready: %s", schema)
    logger.info("All schemas ensured: %s", schemas)


def dispose_engine() -> None:
    """Close all pool connections. Call on application shutdown."""
    global _engine, _SessionLocal
    if _engine:
        _engine.dispose()
        _engine = None
        _SessionLocal = None
        logger.info("Database engine disposed.")
