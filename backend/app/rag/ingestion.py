import logging

from app.integrations.obsidian_cli import ObsidianCliError, list_notes, read_note
from app.rag.vector_store import upsert_documents

logger = logging.getLogger("grimoire.rag.ingestion")


def index_obsidian_vault(domains: list[str] | None = None) -> int:
    domain = domains[0] if domains else "generic"
    try:
        note_paths = list_notes()
    except ObsidianCliError as exc:
        logger.warning("Obsidian CLI indisponível para indexação: %s", exc)
        return 0

    docs: list[dict[str, str]] = []
    for path in note_paths:
        try:
            content = read_note(path)
        except ObsidianCliError as exc:
            logger.warning("Falha ao ler nota durante indexação '%s': %s", path, exc)
            continue
        docs.append(
            {
                "text": content,
                "source": f"obsidian:{path}",
                "memory_type": "obsidian_vault",
                "domain": domain,
            }
        )

    if not docs:
        return 0
    if not upsert_documents(docs):
        return 0
    logger.info("Indexação Obsidian concluída: %d documento(s).", len(docs))
    return len(docs)
