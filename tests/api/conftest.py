"""
tests/app/conftest.py — Shared fixtures for the app/ API test suite.

Requires a live PostgreSQL instance (see docker-compose.yml's `postgres`
service). Each test runs inside a SAVEPOINT that is rolled back afterwards,
so tests never leave data behind and can run in any order.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

# The suite logs in far more often than the production login limit allows;
# tests that exercise rate limiting re-enable the limiter explicitly.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
# Tests assert on the rules engine's alerts; the tests of automatic ML scoring
# turn it on themselves.
os.environ.setdefault("ML_AUTO_SCORE", "false")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://kyro_user:kyro_pass@localhost:5434/kyro_aml"
)

from app.deps import get_db
from app.main import app as fastapi_app
from app.models import Base
from app.models.user import User
from app.services.rule_config_service import invalidate_cache as _invalidate_rule_config_cache
from app.utils.security import hash_password

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def _require_live_db():
    try:
        with engine.connect():
            pass
    except OperationalError as exc:
        pytest.skip(f"Live PostgreSQL required for app/ tests (see docker-compose.yml): {exc}")
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db_session():
    connection = engine.connect()
    outer_txn = connection.begin()
    session = TestingSessionLocal(bind=connection)
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    # rule_config_service caches RuleConfig rows in a process-wide dict with
    # a short TTL, independent of this SAVEPOINT-per-test isolation — without
    # clearing it, one test's config row (or its absence) can leak into the
    # next test's cache hit.
    _invalidate_rule_config_cache()

    # Start every test from empty reference tables. A migrated database carries
    # seeded watchlist sources and rule configs (and may hold ingested watchlist
    # entities); tests assert against what they create themselves. This runs
    # inside the test's transaction, so it is rolled back with everything else.
    session.execute(text("DELETE FROM app.watchlist_sources"))
    session.execute(text("DELETE FROM app.rule_configs"))
    session.commit()

    yield session

    session.close()
    outer_txn.rollback()
    connection.close()
    _invalidate_rule_config_cache()


class _TestSession:
    """Stands in for SessionLocal(): the test's own session, which the caller must not close."""

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        pass


@pytest.fixture
def client(db_session, monkeypatch):
    fastapi_app.dependency_overrides[get_db] = lambda: db_session
    # Some endpoints open their own session instead of using get_db. Point them
    # at the test session too, so they see the test's data and cannot write to
    # (or run real ingestion against) the shared database.
    import app.database
    import app.routers.alerts

    modules = [app.database, app.routers.alerts]
    try:
        import app.ml.training.pipeline

        modules.append(app.ml.training.pipeline)
    except ImportError:
        # scikit-learn cannot be loaded on this machine (e.g. blocked by Windows
        # Smart App Control); everything except the ML tests can still run.
        pass
    for module in modules:
        monkeypatch.setattr(module, "SessionLocal", lambda: _TestSession(db_session))
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


def _make_user(db_session, *, username: str, role: str) -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        full_name=username.title(),
        hashed_password=hash_password("Str0ngPass!123"),
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def analyst_user(db_session) -> User:
    return _make_user(db_session, username="analyst1", role="ANALYST")


@pytest.fixture
def compliance_user(db_session) -> User:
    return _make_user(db_session, username="compliance1", role="COMPLIANCE_OFFICER")


@pytest.fixture
def admin_user(db_session) -> User:
    return _make_user(db_session, username="admin1", role="ADMIN")


def _login(client: TestClient, username: str) -> dict[str, str]:
    resp = client.post("/api/v1/auth/login", data={"username": username, "password": "Str0ngPass!123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def auth_headers(client, analyst_user) -> dict[str, str]:
    return _login(client, analyst_user.username)


@pytest.fixture
def compliance_headers(client, compliance_user) -> dict[str, str]:
    return _login(client, compliance_user.username)


@pytest.fixture
def admin_headers(client, admin_user) -> dict[str, str]:
    return _login(client, admin_user.username)


@pytest.fixture
def mlro_headers(client, db_session) -> dict[str, str]:
    return _login(client, _make_user(db_session, username="mlro1", role="MLRO").username)
