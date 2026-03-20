from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def isolated_settings(tmp_path: Path):
    from app.config import settings

    original = {
        "data_path": settings.data_path,
        "vault_path": settings.vault_path,
        "entities_path": settings.entities_path,
    }
    settings.data_path = tmp_path / "data"
    settings.vault_path = tmp_path / "vault"
    settings.entities_path = tmp_path / "entities"
    yield settings
    for key, value in original.items():
        setattr(settings, key, value)


@pytest.fixture
async def test_db(isolated_settings):
    from app.persistence.sqlite_layer import init_db

    db_path = isolated_settings.data_path / "test_grimoire.db"
    await init_db(db_path)
    return db_path


@pytest.fixture
async def client(test_db: Path, isolated_settings, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GRIMOIRE_DATA_PATH", str(isolated_settings.data_path))
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
