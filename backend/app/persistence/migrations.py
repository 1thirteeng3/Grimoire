from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import asyncpg

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations" / "sql"

_SQLITE_MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    applied_order INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL
);
"""

_POSTGRES_MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    applied_order BIGSERIAL PRIMARY KEY,
    version TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL
);
"""


def _discover_versions() -> list[str]:
    versions: list[str] = []
    for up_file in sorted(MIGRATIONS_DIR.glob("*.up.sql")):
        version = up_file.name.removesuffix(".up.sql")
        down_file = MIGRATIONS_DIR / f"{version}.down.sql"
        if not down_file.exists():
            raise RuntimeError(f"Migration sem rollback detectada: {version}")
        versions.append(version)
    return versions


def _script_for(version: str, direction: str) -> str:
    if direction not in {"up", "down"}:
        raise ValueError("direction must be 'up' or 'down'")
    path = MIGRATIONS_DIR / f"{version}.{direction}.sql"
    if not path.exists():
        raise RuntimeError(f"Migration ausente: {path.name}")
    return path.read_text(encoding="utf-8")


async def apply_migrations_sqlite(db_path: Path, target_version: str | None = None) -> list[str]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    versions = _discover_versions()
    applied: list[str] = []
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SQLITE_MIGRATION_TABLE_SQL)
        await db.commit()
        cur = await db.execute("SELECT version FROM schema_migrations")
        rows = await cur.fetchall()
        current = {str(row[0]) for row in rows}

        for version in versions:
            if target_version is not None and version > target_version:
                continue
            if version in current:
                continue
            await db.executescript(_script_for(version, "up"))
            await db.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()
            applied.append(version)
    return applied


async def rollback_migrations_sqlite(db_path: Path, steps: int = 1) -> list[str]:
    if steps <= 0:
        return []
    reverted: list[str] = []
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SQLITE_MIGRATION_TABLE_SQL)
        await db.commit()
        cur = await db.execute(
            "SELECT version FROM schema_migrations ORDER BY applied_order DESC LIMIT ?",
            (int(steps),),
        )
        rows = await cur.fetchall()
        for row in rows:
            version = str(row[0])
            await db.executescript(_script_for(version, "down"))
            await db.execute("DELETE FROM schema_migrations WHERE version = ?", (version,))
            await db.commit()
            reverted.append(version)
    return reverted


async def apply_migrations_postgres(
    pool: asyncpg.Pool,
    target_version: str | None = None,
) -> list[str]:
    versions = _discover_versions()
    applied: list[str] = []
    async with pool.acquire() as conn:
        await conn.execute(_POSTGRES_MIGRATION_TABLE_SQL)
        rows = await conn.fetch("SELECT version FROM schema_migrations")
        current = {str(row["version"]) for row in rows}
        for version in versions:
            if target_version is not None and version > target_version:
                continue
            if version in current:
                continue
            async with conn.transaction():
                await conn.execute(_script_for(version, "up"))
                await conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES ($1, $2)",
                    version,
                    datetime.now(timezone.utc).isoformat(),
                )
            applied.append(version)
    return applied


async def rollback_migrations_postgres(pool: asyncpg.Pool, steps: int = 1) -> list[str]:
    if steps <= 0:
        return []
    reverted: list[str] = []
    async with pool.acquire() as conn:
        await conn.execute(_POSTGRES_MIGRATION_TABLE_SQL)
        rows = await conn.fetch(
            "SELECT version FROM schema_migrations ORDER BY applied_order DESC LIMIT $1",
            int(steps),
        )
        for row in rows:
            version = str(row["version"])
            async with conn.transaction():
                await conn.execute(_script_for(version, "down"))
                await conn.execute("DELETE FROM schema_migrations WHERE version=$1", version)
            reverted.append(version)
    return reverted
