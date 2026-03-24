import pytest

from app.persistence import db


@pytest.mark.asyncio
async def test_init_db_dispatches_to_sqlite(monkeypatch, tmp_path):
    from app.config import settings

    calls: list[str] = []
    monkeypatch.setattr(settings, "persistence_backend", "sqlite")

    async def _sqlite_init(path):
        calls.append(str(path))

    async def _postgres_init(dsn):
        calls.append(f"postgres:{dsn}")

    monkeypatch.setattr("app.persistence.sqlite_layer.init_db", _sqlite_init)
    monkeypatch.setattr("app.persistence.postgres_layer.init_db", _postgres_init)

    await db.init_db(tmp_path / "x.db")
    assert calls == [str(tmp_path / "x.db")]


@pytest.mark.asyncio
async def test_init_db_dispatches_to_postgres(monkeypatch, tmp_path):
    from app.config import settings

    calls: list[str] = []
    monkeypatch.setattr(settings, "persistence_backend", "postgres")
    monkeypatch.setattr(settings, "postgres_dsn", "postgresql://local/grimoire")

    async def _sqlite_init(path):
        calls.append(f"sqlite:{path}")

    async def _postgres_init(dsn):
        calls.append(f"postgres:{dsn}")

    monkeypatch.setattr("app.persistence.sqlite_layer.init_db", _sqlite_init)
    monkeypatch.setattr("app.persistence.postgres_layer.init_db", _postgres_init)

    await db.init_db(tmp_path / "x.db")
    assert calls == ["postgres:postgresql://local/grimoire"]


@pytest.mark.asyncio
async def test_purge_retention_dispatches(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "persistence_backend", "postgres")
    async def _purge(days):
        return days + 1

    monkeypatch.setattr("app.persistence.postgres_layer.purge_old_audit_events", _purge)
    deleted = await db.purge_old_audit_events(10)
    assert deleted == 11


@pytest.mark.asyncio
async def test_migrate_and_rollback_dispatch(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "persistence_backend", "sqlite")

    async def _migrate(*, target_version=None):
        return [target_version or "latest"]

    async def _rollback(*, steps=1):
        return [f"rollback-{steps}"]

    monkeypatch.setattr("app.persistence.sqlite_layer.migrate", _migrate)
    monkeypatch.setattr("app.persistence.sqlite_layer.rollback_migrations", _rollback)
    monkeypatch.setattr("app.persistence.postgres_layer.migrate", _migrate)
    monkeypatch.setattr("app.persistence.postgres_layer.rollback_migrations", _rollback)

    applied = await db.migrate(target_version="0001_initial")
    reverted = await db.rollback_migrations(steps=2)
    assert applied == ["0001_initial"]
    assert reverted == ["rollback-2"]
