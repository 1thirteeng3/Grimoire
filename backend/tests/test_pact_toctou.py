import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


def _sign(session_id: str, tool_name: str, args: dict) -> str:
    payload = json.dumps(
        {"session_id": session_id, "tool_name": tool_name, "args": args},
        sort_keys=True,
    )
    digest = hmac.new(b"dev-insecure-secret", payload.encode(), hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.mark.asyncio
async def test_expired_pact_returns_410(client: AsyncClient, test_db):
    del test_db
    from app.persistence.sqlite_layer import save_pact

    pact_id = str(uuid.uuid4())
    past_ttl = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    args = {}
    expired_pact = {
        "pact_id": pact_id,
        "session_id": "sess_expired_test",
        "entity_manifest_hash": "abc123",
        "fsm_status": "PENDING_HUMAN_CONFLICT",
        "operator_proposal_raw": "print('danger')",
        "tool_intent": {"tool_name": "execute_python", "literal_arguments": args},
        "critic_report": [],
        "created_at": past_ttl,
        "ttl_timestamp": past_ttl,
        "cryptographic_signature": _sign("sess_expired_test", "execute_python", args),
    }
    await save_pact(json.dumps(expired_pact), pact_id)

    response = await client.post(
        f"/api/v1/pacts/{pact_id}/resolve",
        json={"action": "APPROVE_AS_IS", "modified_arguments": {}},
    )
    assert response.status_code == 410
    assert "PACT_EXPIRED" in response.json()["error_code"]


@pytest.mark.asyncio
async def test_valid_pact_resolves_normally(client: AsyncClient, test_db):
    del test_db
    from app.persistence.sqlite_layer import save_pact

    pact_id = str(uuid.uuid4())
    future_ttl = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    args = {"code": "print('safe')"}
    session_id = "sess_valid_test_001"
    pact = {
        "pact_id": pact_id,
        "session_id": session_id,
        "entity_manifest_hash": "abc123",
        "fsm_status": "PENDING_HUMAN_CONFLICT",
        "operator_proposal_raw": "print('safe')",
        "tool_intent": {"tool_name": "execute_python", "literal_arguments": args},
        "critic_report": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ttl_timestamp": future_ttl,
        "cryptographic_signature": _sign(session_id, "execute_python", args),
    }
    await save_pact(json.dumps(pact), pact_id)

    response = await client.post(
        f"/api/v1/pacts/{pact_id}/resolve",
        json={"action": "APPROVE_AS_IS", "modified_arguments": {}},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
