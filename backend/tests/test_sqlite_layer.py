import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.persistence import sqlite_layer


@pytest.mark.asyncio
async def test_purge_expired_pacts_with_returning(test_db, monkeypatch):
    del test_db
    pact_id = str(uuid4())
    ttl = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    payload = {
        "pact_id": pact_id,
        "session_id": "sess_sqlite_expired",
        "entity_manifest_hash": "x",
        "fsm_status": "PENDING_HUMAN_CONFLICT",
        "operator_proposal_raw": "noop",
        "tool_intent": {"tool_name": "noop", "literal_arguments": {}},
        "critic_report": [],
        "created_at": ttl,
        "ttl_timestamp": ttl,
        "cryptographic_signature": "sha256=fake",
    }
    await sqlite_layer.save_pact(json.dumps(payload), pact_id)
    deleted = await sqlite_layer.purge_expired_pacts()
    assert deleted >= 1


@pytest.mark.asyncio
async def test_purge_expired_pacts_fallback_without_returning(test_db, monkeypatch):
    del test_db
    pact_id = str(uuid4())
    ttl = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    payload = {
        "pact_id": pact_id,
        "session_id": "sess_sqlite_expired_fallback",
        "entity_manifest_hash": "x",
        "fsm_status": "PENDING_HUMAN_CONFLICT",
        "operator_proposal_raw": "noop",
        "tool_intent": {"tool_name": "noop", "literal_arguments": {}},
        "critic_report": [],
        "created_at": ttl,
        "ttl_timestamp": ttl,
        "cryptographic_signature": "sha256=fake",
    }
    await sqlite_layer.save_pact(json.dumps(payload), pact_id)

    monkeypatch.setattr(sqlite_layer, "_HAS_RETURNING", False)
    deleted = await sqlite_layer.purge_expired_pacts()
    assert deleted >= 1
