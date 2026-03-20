import asyncio
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_db(tmp_path: Path):
    from app.persistence.sqlite_layer import init_db

    db_path = tmp_path / "test_grimoire.db"
    await init_db(db_path)
    return db_path


@pytest.fixture
async def client(test_db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GRIMOIRE_DATA_PATH", str(test_db.parent))

    from app.config import settings

    settings.data_path = test_db.parent
    settings.vault_path = test_db.parent / "vault"
    settings.entities_path = test_db.parent / "entities"

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
