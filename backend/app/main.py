import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.pacts_router import router as pacts_router
from app.api.ws_gateway import router as ws_router
from app.config import settings
from app.core.entity_loader import load_and_validate_entities
from app.persistence.sqlite_layer import check_sqlite_runtime_support, init_db
from app.rag.jit_prompting import DogmasWatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("grimoire")


@asynccontextmanager
async def lifespan(app: FastAPI):
    for path in [
        settings.data_path,
        settings.vault_path,
        settings.vault_path / "Dogmas_e_Falhas",
        settings.vault_path / "Registros_Diarios",
        settings.entities_path,
    ]:
        path.mkdir(parents=True, exist_ok=True)

    check_sqlite_runtime_support()
    await init_db(settings.data_path / "grimoire.db")
    logger.info("SQLite inicializado")

    app.state.entities = load_and_validate_entities(settings.entities_path)
    logger.info("%s entidades carregadas", len(app.state.entities))

    watcher = DogmasWatcher(settings.vault_path / "Dogmas_e_Falhas")
    app.state.dogmas_watcher = watcher
    watcher.start()
    logger.info("Dogmas Watcher iniciado")

    yield

    watcher.stop()
    logger.info("Grimório encerrado")


app = FastAPI(
    title="Grimório API",
    version="0.1.0",
    lifespan=lifespan,
    generate_unique_id_function=lambda route: route.name,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)
app.include_router(pacts_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "tier": settings.deployment_tier}
