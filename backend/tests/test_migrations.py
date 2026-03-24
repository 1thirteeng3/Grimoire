from pathlib import Path

import aiosqlite
import pytest

from app.persistence.migrations import apply_migrations_sqlite, rollback_migrations_sqlite


@pytest.mark.asyncio
async def test_sqlite_migrations_apply_and_rollback(tmp_path: Path):
    db_path = tmp_path / "migrations.db"

    applied = await apply_migrations_sqlite(db_path)
    assert "0001_initial" in applied

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pending_pacts'"
        )
        assert await cur.fetchone() is not None

    reverted = await rollback_migrations_sqlite(db_path, steps=1)
    assert reverted == ["0001_initial"]

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pending_pacts'"
        )
        assert await cur.fetchone() is None
        cur = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        )
        assert await cur.fetchone() is not None


@pytest.mark.asyncio
async def test_sqlite_migrations_idempotent(tmp_path: Path):
    db_path = tmp_path / "migrations-idempotent.db"
    first = await apply_migrations_sqlite(db_path)
    second = await apply_migrations_sqlite(db_path)
    assert first == ["0001_initial"]
    assert second == []
