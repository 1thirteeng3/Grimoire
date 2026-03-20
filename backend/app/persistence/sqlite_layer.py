import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite

logger = logging.getLogger("grimoire.sqlite")
DB_PATH: Path | None = None
_SQLITE_VERSION = tuple(int(x) for x in sqlite3.sqlite_version.split("."))
_HAS_RETURNING = _SQLITE_VERSION >= (3, 35, 0)

SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_pacts (
    pact_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    entity_manifest_hash TEXT NOT NULL,
    fsm_status TEXT NOT NULL DEFAULT 'PENDING_HUMAN_CONFLICT',
    operator_proposal_raw TEXT NOT NULL,
    tool_intent_json TEXT NOT NULL,
    critic_report_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    ttl_timestamp TEXT NOT NULL,
    cryptographic_signature TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_summaries (
    summary_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    domain TEXT
);

CREATE TABLE IF NOT EXISTS routing_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    feedback_score REAL NOT NULL,
    edit_delta REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pact_audit_events (
    event_id TEXT PRIMARY KEY,
    pact_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pacts_ttl ON pending_pacts(ttl_timestamp);
CREATE INDEX IF NOT EXISTS idx_pacts_session ON pending_pacts(session_id);
CREATE INDEX IF NOT EXISTS idx_pact_audit_pact ON pact_audit_events(pact_id);
CREATE INDEX IF NOT EXISTS idx_pact_audit_session ON pact_audit_events(session_id);
"""


def _ensure_db_path() -> Path:
    if DB_PATH is None:
        raise RuntimeError("SQLite DB_PATH não inicializado. Chame init_db() no startup.")
    return DB_PATH


def check_sqlite_runtime_support() -> None:
    version = sqlite3.sqlite_version
    if _SQLITE_VERSION < (3, 31, 0):
        raise RuntimeError(
            f"SQLite {version} < 3.31.0 não suportado. "
            "Atualize o sistema ou use Python com SQLite mais recente."
        )
    if not _HAS_RETURNING:
        logger.warning(
            "SQLite %s < 3.35.0: purge de pactos usará fallback sem RETURNING.", version
        )


async def init_db(db_path: Path) -> None:
    global DB_PATH
    DB_PATH = db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    logger.info("Schema SQLite inicializado: %s", db_path)


async def save_pact(pact_json: str, pact_id: str) -> None:
    data = json.loads(pact_json)
    async with aiosqlite.connect(_ensure_db_path()) as db:
        await db.execute(
            "INSERT INTO pending_pacts VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
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
            ),
        )
        await db.commit()


async def fetch_pact(pact_id: str) -> dict[str, Any] | None:
    async with aiosqlite.connect(_ensure_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pending_pacts WHERE pact_id=? AND fsm_status='PENDING_HUMAN_CONFLICT'",
            (pact_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def fetch_pact_any_status(pact_id: str) -> dict[str, Any] | None:
    async with aiosqlite.connect(_ensure_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM pending_pacts WHERE pact_id=?", (pact_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def update_pact_status(pact_id: str, status: str) -> None:
    async with aiosqlite.connect(_ensure_db_path()) as db:
        await db.execute("UPDATE pending_pacts SET fsm_status=? WHERE pact_id=?", (status, pact_id))
        await db.commit()


async def fetch_session_summary(session_id: str) -> str | None:
    async with aiosqlite.connect(_ensure_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT summary_text
            FROM session_summaries
            WHERE session_id=?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
            return row["summary_text"] if row else None


async def purge_expired_pacts() -> int:
    async with aiosqlite.connect(_ensure_db_path()) as db:
        if _HAS_RETURNING:
            cur = await db.execute(
                "DELETE FROM pending_pacts WHERE datetime(ttl_timestamp) < datetime('now') RETURNING pact_id"
            )
            deleted = len(await cur.fetchall())
        else:
            count_cur = await db.execute(
                "SELECT COUNT(*) FROM pending_pacts WHERE datetime(ttl_timestamp) < datetime('now')"
            )
            count_row = await count_cur.fetchone()
            deleted = count_row[0] if count_row else 0
            await db.execute("DELETE FROM pending_pacts WHERE datetime(ttl_timestamp) < datetime('now')")
        await db.commit()
    if deleted:
        logger.info("GC: %s Pacto(s) expirado(s) purgado(s)", deleted)
    return deleted


async def record_pact_audit_event(
    pact_id: str, session_id: str, event_type: str, detail: dict[str, Any] | None = None
) -> None:
    payload = json.dumps(detail or {}, ensure_ascii=False)
    created_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(_ensure_db_path()) as db:
        await db.execute(
            """
            INSERT INTO pact_audit_events (event_id, pact_id, session_id, event_type, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(uuid4()), pact_id, session_id, event_type, payload, created_at),
        )
        await db.commit()


async def fetch_pact_audit_events(pact_id: str) -> list[dict[str, Any]]:
    async with aiosqlite.connect(_ensure_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT event_id, pact_id, session_id, event_type, detail_json, created_at
            FROM pact_audit_events
            WHERE pact_id=?
            ORDER BY created_at ASC
            """,
            (pact_id,),
        ) as cur:
            rows = await cur.fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        event = dict(row)
        event["detail_json"] = json.loads(event.get("detail_json") or "{}")
        events.append(event)
    return events
