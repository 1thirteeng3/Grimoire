from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GRIMOIRE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deployment_tier: str = "cloud"

    data_path: Path = Path("./data")
    onnx_model_path: Path = Path("./models/bge-reranker-v2-m3-onnx")
    vault_path: Path = Path("./vault")
    entities_path: Path = Path("./cognitive_core/entities")

    qdrant_mode: str = "path"
    qdrant_url: str = "http://localhost:6333"

    honcho_api_url: str = "https://demo.honcho.dev"
    honcho_app_id: str = ""
    honcho_user_id: str = ""

    pact_ttl_seconds: int = 3600
    max_constitution_tokens: int = 4096

    default_operator_model: str = "claude-3-5-sonnet-20241022"
    default_inquisitor_model: str = "claude-3-haiku-20240307"


settings = Settings()
