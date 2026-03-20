import logging
import re

from app.config import settings
from app.integrations.obsidian_cli import ObsidianCliError, list_notes, read_note
from app.rag.vector_store import search_documents, upsert_documents

logger = logging.getLogger("grimoire.rag.retrieval")


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _lexical_rank(query: str, candidates: list[dict[str, str]], top_k: int) -> list[dict[str, str]]:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return candidates[:top_k]

    scored: list[tuple[float, dict[str, str]]] = []
    for candidate in candidates:
        text_tokens = _tokenize(candidate.get("text", ""))
        if not text_tokens:
            continue
        overlap = len(query_tokens & text_tokens)
        score = overlap / max(1, len(query_tokens))
        scored.append((score, candidate))

    scored.sort(key=lambda item: item[0], reverse=True)
    ranked = [candidate for _, candidate in scored]
    return ranked[:top_k]


def _dedupe_chunks(chunks: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for chunk in chunks:
        key = (chunk.get("source", "unknown"), chunk.get("text", ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return unique


def _load_obsidian_chunks(note_paths: list[str] | None, domains: list[str]) -> list[dict[str, str]]:
    if note_paths is None:
        try:
            note_paths = list_notes()
        except ObsidianCliError as exc:
            logger.warning("Falha ao listar notas Obsidian: %s", exc)
            return []
    chunks: list[dict[str, str]] = []
    for path in note_paths:
        try:
            content = read_note(path)
        except ObsidianCliError as exc:
            logger.warning("Falha ao ler nota Obsidian '%s': %s", path, exc)
            continue
        domain = domains[0] if domains else "generic"
        chunks.append(
            {
                "text": content[: settings.obsidian_note_max_chars],
                "source": f"obsidian:{path}",
                "memory_type": "obsidian_vault",
                "domain": domain,
            }
        )
    return chunks


def retrieve_relevant_chunks(
    query: str,
    domains: list[str],
    manual_chunks: list[dict[str, str]] | None = None,
    obsidian_note_paths: list[str] | None = None,
    top_k: int | None = None,
) -> list[dict[str, str]]:
    top_k = int(top_k or settings.retrieval_top_k)
    effective_domains = list(dict.fromkeys([*domains, "generic"]))
    candidates: list[dict[str, str]] = []
    if manual_chunks:
        candidates.extend(manual_chunks)
    if obsidian_note_paths is not None:
        obsidian_chunks = _load_obsidian_chunks(obsidian_note_paths, effective_domains)
        candidates.extend(obsidian_chunks)
    candidates = _dedupe_chunks(candidates)

    if candidates:
        upsert_documents(candidates)

    retrieved = search_documents(query=query, domains=effective_domains, top_k=top_k)
    if retrieved:
        return [
            {
                "text": chunk.text,
                "source": chunk.source,
                "memory_type": chunk.memory_type,
            }
            for chunk in retrieved
        ]

    if not candidates:
        return []

    logger.info("Usando fallback lexical para retrieval (%d candidatos).", len(candidates))
    return _lexical_rank(query=query, candidates=candidates, top_k=top_k)
