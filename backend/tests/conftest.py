from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def isolated_settings(tmp_path: Path):
    from app.config import settings
    from app.observability import reset_telemetry
    from app.security import reset_rate_limiters

    original = {
        "data_path": settings.data_path,
        "backup_path": settings.backup_path,
        "vault_path": settings.vault_path,
        "entities_path": settings.entities_path,
        "persistence_backend": settings.persistence_backend,
        "postgres_dsn": settings.postgres_dsn,
        "enable_file_logging": settings.enable_file_logging,
    }
    reset_telemetry()
    reset_rate_limiters()
    settings.data_path = tmp_path / "data"
    settings.backup_path = tmp_path / "backups"
    settings.vault_path = tmp_path / "vault"
    settings.entities_path = tmp_path / "entities"
    settings.persistence_backend = "sqlite"
    settings.postgres_dsn = ""
    settings.enable_file_logging = False
    yield settings
    reset_telemetry()
    reset_rate_limiters()
    for key, value in original.items():
        setattr(settings, key, value)


@pytest.fixture
async def test_db(isolated_settings):
    from app.persistence import sqlite_layer

    db_path = isolated_settings.data_path / "test_grimoire.db"
    await sqlite_layer.init_db(db_path)
    sqlite_layer.DB_PATH = db_path
    yield db_path
    sqlite_layer.DB_PATH = None


@pytest.fixture
async def client(test_db: Path, isolated_settings, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GRIMOIRE_DATA_PATH", str(isolated_settings.data_path))
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
