"""
tests/api/test_role_matrix.py — The signed-off role matrix matches the code,
and no endpoint is left without the access check it needs.
"""
from fastapi.routing import APIRoute

from app.main import app
from scripts.role_matrix import MATRIX_PATH, render

# Endpoints that change something but need only a signed-in user: the user's own
# session and password, questions that read data the user may already see, and
# the chat/agent simulation.
SIGNED_IN_ONLY = {
    "/api/v1/auth/logout", "/api/v1/auth/change-password", "/api/v1/regulatory/ask",
    "/api/v1/ml/score-transaction", "/api/v1/ml/score-batch", "/api/v1/ml/score-customer/{customer_id}",
    "/api/v1/chat/message", "/api/v1/agent/autonomous/start", "/api/v1/agent/autonomous/stop",
    "/api/v1/agent/autonomous/pause", "/api/v1/agent/autonomous/resume", "/api/v1/agent/autonomous/handoff",
    "/api/v1/streaming/start", "/api/v1/streaming/stop", "/api/v1/tts/speak",
}
# Endpoints anyone may call: signing in, and registration (off unless enabled, and least-privileged)
PUBLIC = {"/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"}


def _routes(routes):
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):  # routers included lazily
            yield from _routes(route.original_router.routes)


def _dependencies(dependant):
    for dependency in dependant.dependencies:
        yield getattr(dependency.call, "__qualname__", "")
        yield from _dependencies(dependency)


def test_matrix_document_matches_the_code():
    assert MATRIX_PATH.read_text(encoding="utf-8") == render(), "Run python scripts/role_matrix.py and have the change reviewed"


def test_every_write_endpoint_checks_a_permission_or_is_listed():
    unguarded = set()
    for route in _routes(app.routes):
        if not route.methods - {"GET", "HEAD", "OPTIONS"}:
            continue
        names = set(_dependencies(route.dependant))
        if any(name.startswith("require_permission") for name in names):
            continue
        if route.path in PUBLIC or (route.path in SIGNED_IN_ONLY and "get_current_user" in names):
            continue
        unguarded.add(route.path)
    assert not unguarded, f"Write endpoints without a permission check: {sorted(unguarded)}"


def test_signed_in_only_list_has_no_stale_entries():
    paths = {route.path for route in _routes(app.routes)}
    assert (SIGNED_IN_ONLY | PUBLIC) <= paths
