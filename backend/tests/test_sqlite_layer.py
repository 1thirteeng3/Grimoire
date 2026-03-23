import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import aiosqlite
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


@pytest.mark.asyncio
async def test_purge_old_audit_events(test_db):
    del test_db
    pact_id = str(uuid4())
    await sqlite_layer.record_pact_audit_event(
        pact_id=pact_id,
        session_id="s1",
        event_type="PACT_CREATED",
        detail={"k": "v"},
    )
    deleted = await sqlite_layer.purge_old_audit_events(retention_days=0)
    assert deleted == 0

    # Force old timestamp to validate retention delete path.
    async with aiosqlite.connect(sqlite_layer.DB_PATH) as db:
        await db.execute(
            "UPDATE pact_audit_events SET created_at=datetime('now', '-3 day') WHERE pact_id=?",
            (pact_id,),
        )
        await db.commit()
    deleted = await sqlite_layer.purge_old_audit_events(retention_days=1)
    assert deleted == 1


@pytest.mark.asyncio
async def test_purge_old_routing_and_summaries(test_db):
    del test_db
    async with aiosqlite.connect(sqlite_layer.DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO routing_events (event_id, session_id, model_id, domain, feedback_score, edit_delta, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now', '-5 day'))
            """,
            (str(uuid4()), "sess", "model", "generic", 0.1, 0.0),
        )
        await db.execute(
            """
            INSERT INTO session_summaries (summary_id, session_id, created_at, summary_text, domain)
            VALUES (?, ?, datetime('now', '-5 day'), ?, ?)
            """,
            (str(uuid4()), "sess", "summary", "generic"),
        )
        await db.commit()

    routing_deleted = await sqlite_layer.purge_old_routing_events(retention_days=1)
    summary_deleted = await sqlite_layer.purge_old_session_summaries(retention_days=1)
    assert routing_deleted == 1
    assert summary_deleted == 1
