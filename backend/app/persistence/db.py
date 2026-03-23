from pathlib import Path
from typing import Any, Awaitable, Callable

from app.config import settings
from app.persistence import postgres_layer, sqlite_layer

_DBFn = Callable[..., Awaitable[Any]]


def _use_postgres() -> bool:
    return settings.persistence_backend.lower().strip() == "postgres"


def check_runtime_support() -> None:
    if _use_postgres():
        return
    sqlite_layer.check_sqlite_runtime_support()


async def init_db(db_path: Path) -> None:
    if _use_postgres():
        await postgres_layer.init_db(settings.postgres_dsn)
        return
    await sqlite_layer.init_db(db_path)


async def close_db() -> None:
    if _use_postgres():
        await postgres_layer.close_db()


async def migrate(target_version: str | None = None) -> list[str]:
    fn = _op(sqlite_layer.migrate, postgres_layer.migrate)
    return list(await fn(target_version=target_version))


async def rollback_migrations(steps: int = 1) -> list[str]:
    fn = _op(sqlite_layer.rollback_migrations, postgres_layer.rollback_migrations)
    return list(await fn(steps=steps))


def _op(sqlite_fn: _DBFn, postgres_fn: _DBFn) -> _DBFn:
    return postgres_fn if _use_postgres() else sqlite_fn


async def save_pact(pact_json: str, pact_id: str) -> None:
    fn = _op(sqlite_layer.save_pact, postgres_layer.save_pact)
    await fn(pact_json, pact_id)


async def fetch_pact(pact_id: str) -> dict[str, Any] | None:
    fn = _op(sqlite_layer.fetch_pact, postgres_layer.fetch_pact)
    return await fn(pact_id)


async def fetch_pact_any_status(pact_id: str) -> dict[str, Any] | None:
    fn = _op(sqlite_layer.fetch_pact_any_status, postgres_layer.fetch_pact_any_status)
    return await fn(pact_id)


async def update_pact_status(pact_id: str, status: str) -> None:
    fn = _op(sqlite_layer.update_pact_status, postgres_layer.update_pact_status)
    await fn(pact_id, status)


async def fetch_session_summary(session_id: str) -> str | None:
    fn = _op(sqlite_layer.fetch_session_summary, postgres_layer.fetch_session_summary)
    return await fn(session_id)


async def purge_expired_pacts() -> int:
    fn = _op(sqlite_layer.purge_expired_pacts, postgres_layer.purge_expired_pacts)
    return int(await fn())


async def record_pact_audit_event(
    pact_id: str, session_id: str, event_type: str, detail: dict[str, Any] | None = None
) -> None:
    fn = _op(sqlite_layer.record_pact_audit_event, postgres_layer.record_pact_audit_event)
    await fn(pact_id, session_id, event_type, detail)


async def fetch_pact_audit_events(pact_id: str) -> list[dict[str, Any]]:
    fn = _op(sqlite_layer.fetch_pact_audit_events, postgres_layer.fetch_pact_audit_events)
    rows = await fn(pact_id)
    return list(rows)


async def purge_old_audit_events(retention_days: int) -> int:
    fn = _op(sqlite_layer.purge_old_audit_events, postgres_layer.purge_old_audit_events)
    return int(await fn(retention_days))


async def purge_old_routing_events(retention_days: int) -> int:
    fn = _op(sqlite_layer.purge_old_routing_events, postgres_layer.purge_old_routing_events)
    return int(await fn(retention_days))


async def purge_old_session_summaries(retention_days: int) -> int:
    fn = _op(sqlite_layer.purge_old_session_summaries, postgres_layer.purge_old_session_summaries)
    return int(await fn(retention_days))
