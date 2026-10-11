"""
tests/api/test_ai_attestation.py — AI summaries and narratives are checked by a
person before they count, and what the person did is recorded on the AI call.
"""
import uuid

import pytest

from app.models.ai_interaction import AIInteraction
from app.models.alert import Alert
from tests.api.conftest import _login, _make_user
from tests.api.test_alerts import _create_alert_via_sanctions_hit
from tests.api.test_case_workspace import mock_ai  # noqa: F401  (fixture)

pytestmark = pytest.mark.db


def test_a_new_summary_is_unchecked_until_an_investigator_confirms_it(client, auth_headers, db_session, mock_ai):  # noqa: F811
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "attest.summary@example.com")
    url = f"/api/v1/alerts/{alert['id']}"
    written = client.post(f"{url}/summary", headers=auth_headers).json()
    assert written["summary"] and written["summary_attested_at"] is None

    # Keeping it needs the confirmation
    assert client.put(f"{url}/summary/review", json={"decision": "ACCEPTED"}, headers=auth_headers).status_code == 422
    kept = client.put(f"{url}/summary/review", json={"decision": "ACCEPTED", "confirmed": True}, headers=auth_headers)
    assert kept.status_code == 200 and kept.json()["summary_attested_at"]

    row = db_session.get(Alert, uuid.UUID(alert["id"]))
    assert db_session.get(AIInteraction, row.summary_interaction_id).human_decision == "ACCEPTED"
    assert client.get(url, headers=auth_headers).json()["summary_attested_at"]
    events = client.get(f"{url}/timeline", headers=auth_headers).json()["events"]
    assert any(e["title"] == "Case summary checked against the records" for e in events)

    # Regenerating starts unchecked again
    assert client.post(f"{url}/summary", headers=auth_headers).json()["summary_attested_at"] is None


def test_a_summary_can_be_corrected_or_rejected(client, auth_headers, db_session, mock_ai):  # noqa: F811
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "attest.edit@example.com")
    url = f"/api/v1/alerts/{alert['id']}"
    client.post(f"{url}/summary", headers=auth_headers)
    corrected = client.put(f"{url}/summary/review", json={"decision": "EDITED", "text": "Corrected text.", "confirmed": True},
                           headers=auth_headers).json()
    assert corrected["summary"] == "Corrected text." and corrected["summary_attested_at"]

    client.post(f"{url}/summary", headers=auth_headers)
    interaction_id = db_session.get(Alert, uuid.UUID(alert["id"])).summary_interaction_id
    rejected = client.put(f"{url}/summary/review", json={"decision": "REJECTED", "notes": "Wrong dates"}, headers=auth_headers).json()
    assert rejected["summary"] is None
    assert db_session.get(AIInteraction, interaction_id).human_decision == "REJECTED"


def test_narratives_need_confirmation_and_a_sar_is_not_filed_on_an_unchecked_draft(client, auth_headers, db_session, mock_ai):  # noqa: F811
    mlro = _login(client, _make_user(db_session, username="attest.mlro", role="MLRO").username)
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "attest.narrative@example.com")
    url = f"/api/v1/alerts/{alert['id']}"
    sar = {"outcome": "SAR_FILED", "reasons": ["SANCTIONS_EXPOSURE"], "resolution_notes": "Filed", "sar_reference": "SAR-1"}

    draft = client.post(f"{url}/draft-narrative", headers=mlro).json()
    assert client.put(f"{url}/resolve", json=sar, headers=mlro).status_code == 409  # latest is an unchecked AI draft

    assert client.post(f"{url}/narratives", json={"text": draft["narrative"]}, headers=mlro).status_code == 422
    saved = client.post(f"{url}/narratives", json={"text": draft["narrative"], "confirmed": True}, headers=mlro)
    assert saved.status_code == 201
    assert db_session.get(AIInteraction, uuid.UUID(draft["interaction_id"])).human_decision == "ACCEPTED"

    assert client.put(f"{url}/resolve", json=sar, headers=mlro).status_code == 200


def test_oversight_counts_what_investigators_did(client, auth_headers, compliance_headers, db_session, mock_ai):  # noqa: F811
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "attest.oversight@example.com")
    url = f"/api/v1/alerts/{alert['id']}"
    client.post(f"{url}/summary", headers=auth_headers)
    client.put(f"{url}/summary/review", json={"decision": "REJECTED"}, headers=auth_headers)
    client.post(f"{url}/summary", headers=auth_headers)

    rows = {r["prompt_id"]: r for r in client.get("/api/v1/ai/oversight", headers=compliance_headers).json()}
    summary = next(r for pid, r in rows.items() if "summary" in pid)
    assert summary["outputs"] >= 2 and summary["rejected"] >= 1 and summary["not_reviewed"] >= 1
