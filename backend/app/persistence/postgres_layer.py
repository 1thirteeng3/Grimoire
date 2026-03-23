import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import asyncpg
from app.persistence.migrations import apply_migrations_postgres, rollback_migrations_postgres

logger = logging.getLogger("grimoire.postgres")

_pool: asyncpg.Pool | None = None


def _ensure_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Postgres pool não inicializado. Chame init_db() no startup.")
    return _pool


async def init_db(dsn: str) -> None:
    global _pool
    if not dsn.strip():
        raise RuntimeError("GRIMOIRE_POSTGRES_DSN vazio para backend postgres.")
    _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)
    applied = await apply_migrations_postgres(_pool)
    logger.info("Postgres inicializado (migrations aplicadas=%s)", len(applied))


async def migrate(target_version: str | None = None) -> list[str]:
    pool = _ensure_pool()
    applied = await apply_migrations_postgres(pool, target_version=target_version)
    if applied:
        logger.info("Postgres migrations aplicadas: %s", applied)
    return applied


async def rollback_migrations(steps: int = 1) -> list[str]:
    pool = _ensure_pool()
    reverted = await rollback_migrations_postgres(pool, steps=steps)
    if reverted:
        logger.warning("Postgres rollback aplicado: %s", reverted)
    return reverted


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def save_pact(pact_json: str, pact_id: str) -> None:
    data = json.loads(pact_json)
    pool = _ensure_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO pending_pacts (
                pact_id, session_id, entity_manifest_hash, fsm_status, operator_proposal_raw,
                tool_intent_json, critic_report_json, created_at, ttl_timestamp, cryptographic_signature
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            """,
            pact_id,
            data["session_id"],
            data["entity_manifest_hash"],
            data["fsm_status"],
            data["operator_proposal_raw"],
            json.dumps(data["tool_intent"]),
            json.dumps(data["critic_report"]),
            data["created_at"],
            data["ttl_timestamp"],
            data["cryptographic_signature"],
        )


async def fetch_pact(pact_id: str) -> dict[str, Any] | None:
    pool = _ensure_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM pending_pacts WHERE pact_id=$1 AND fsm_status='PENDING_HUMAN_CONFLICT'",
            pact_id,
        )
    return dict(row) if row else None


async def fetch_pact_any_status(pact_id: str) -> dict[str, Any] | None:
    pool = _ensure_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM pending_pacts WHERE pact_id=$1", pact_id)
    return dict(row) if row else None


async def update_pact_status(pact_id: str, status: str) -> None:
    pool = _ensure_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE pending_pacts SET fsm_status=$1 WHERE pact_id=$2", status, pact_id)


async def fetch_session_summary(session_id: str) -> str | None:
    pool = _ensure_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT summary_text
            FROM session_summaries
            WHERE session_id=$1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            session_id,
        )
    return str(row["summary_text"]) if row else None


async def purge_expired_pacts() -> int:
    pool = _ensure_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "DELETE FROM pending_pacts WHERE (ttl_timestamp)::timestamptz < NOW() RETURNING pact_id"
        )
    deleted = len(rows)
    if deleted:
        logger.info("GC Postgres: %s pacto(s) expirado(s) purgado(s)", deleted)
    return deleted


async def record_pact_audit_event(
    pact_id: str, session_id: str, event_type: str, detail: dict[str, Any] | None = None
) -> None:
    payload = json.dumps(detail or {}, ensure_ascii=False)
    created_at = datetime.now(timezone.utc).isoformat()
    pool = _ensure_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO pact_audit_events (event_id, pact_id, session_id, event_type, detail_json, created_at)
            VALUES ($1,$2,$3,$4,$5,$6)
            """,
            str(uuid4()),
            pact_id,
            session_id,
            event_type,
            payload,
            created_at,
        )


async def fetch_pact_audit_events(pact_id: str) -> list[dict[str, Any]]:
    pool = _ensure_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT event_id, pact_id, session_id, event_type, detail_json, created_at
            FROM pact_audit_events
            WHERE pact_id=$1
            ORDER BY created_at ASC
            """,
            pact_id,
        )
    events: list[dict[str, Any]] = []
    for row in rows:
        event = dict(row)
        event["detail_json"] = json.loads(str(event.get("detail_json") or "{}"))
        events.append(event)
    return events


async def purge_old_audit_events(retention_days: int) -> int:
    if retention_days <= 0:
        return 0
    pool = _ensure_pool()
    async with pool.acquire() as conn:
        deleted = await conn.execute(
            """
            DELETE FROM pact_audit_events
            WHERE (created_at)::timestamptz < (NOW() - make_interval(days => $1::int))
            """,
            int(retention_days),
        )
    return int(str(deleted).split()[-1])


async def purge_old_routing_events(retention_days: int) -> int:
    if retention_days <= 0:
        return 0
    pool = _ensure_pool()
    async with pool.acquire() as conn:
        deleted = await conn.execute(
            """
            DELETE FROM routing_events
            WHERE (created_at)::timestamptz < (NOW() - make_interval(days => $1::int))
            """,
            int(retention_days),
        )
    return int(str(deleted).split()[-1])


async def purge_old_session_summaries(retention_days: int) -> int:
    if retention_days <= 0:
        return 0
    pool = _ensure_pool()
    async with pool.acquire() as conn:
        deleted = await conn.execute(
            """
            DELETE FROM session_summaries
            WHERE (created_at)::timestamptz < (NOW() - make_interval(days => $1::int))
            """,
            int(retention_days),
        )
    return int(str(deleted).split()[-1])
