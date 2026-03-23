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
    qdrant_collection: str = "grimoire_notes"
    qdrant_local_path: Path = Path("./data/qdrant")
    embedding_model_id: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    retrieval_top_k: int = 20
    retrieval_min_score: float = 0.15

    obsidian_cli_binary: str = "obsidian"
    obsidian_cli_timeout_seconds: int = 15
    obsidian_note_max_chars: int = 8000

    deepseek_api_url: str = "https://api.deepseek.com/v1"
    llm_timeout_seconds: int = 60
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024
    llm_retry_max_attempts: int = 3
    llm_retry_base_backoff_seconds: float = 1.0
    llm_retry_max_backoff_seconds: float = 8.0

    honcho_api_url: str = "https://demo.honcho.dev"
    honcho_app_id: str = ""
    honcho_user_id: str = ""

    pact_ttl_seconds: int = 3600
    max_constitution_tokens: int = 4096

    default_operator_model: str = "deepseek-chat"
    default_inquisitor_model: str = "deepseek-reasoner"


settings = Settings()
