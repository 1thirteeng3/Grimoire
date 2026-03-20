"""
NOTA CRÍTICA: Este módulo requer `honcho-ai` da Plastic Labs.
NÃO instalar o pacote `honcho` de Procfile manager.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.persistence.sqlite_layer import fetch_session_summary

logger = logging.getLogger("grimoire.memory")

HONCHO_TIMEOUT_SECONDS = 0.8
MAX_EPISODIC_TOKENS = 4000


@dataclass
class EpisodicContext:
    messages: list[dict[str, Any]]
    source: str
    token_count: int


async def _try_honcho(session_id: str) -> EpisodicContext | None:
    try:
        try:
            from honcho import Honcho  # type: ignore[import-not-found]
        except Exception:
            from honcho_ai import Honcho  # type: ignore[import-not-found]

        client = Honcho(api_url=settings.honcho_api_url)
        messages = await asyncio.wait_for(
            client.get_session_messages(session_id, max_tokens=MAX_EPISODIC_TOKENS),
            timeout=HONCHO_TIMEOUT_SECONDS,
        )
        return EpisodicContext(
            messages=messages,
            source="honcho",
            token_count=max(1, len(str(messages)) // 4),
        )
    except asyncio.TimeoutError:
        logger.warning("Honcho timeout (>%.1fs) — fallback para SQLite", HONCHO_TIMEOUT_SECONDS)
        return None
    except Exception as exc:
        logger.warning("Honcho erro: %s — fallback para SQLite", exc)
        return None


async def _try_sqlite(session_id: str) -> EpisodicContext | None:
    try:
        summary = await fetch_session_summary(session_id)
        if summary:
            return EpisodicContext(
                messages=[{"role": "system", "content": summary}],
                source="sqlite",
                token_count=max(1, len(summary) // 4),
            )
        return None
    except Exception as exc:
        logger.error("SQLite fallback falhou: %s", exc)
        return None


def _degraded_context() -> EpisodicContext:
    logger.error("FALLBACK DEGRADADO ATIVADO — memória episódica indisponível")
    return EpisodicContext(messages=[], source="degraded", token_count=0)


async def get_episodic_context(session_id: str) -> EpisodicContext:
    try:
        ctx = await _try_honcho(session_id)
    except Exception as exc:
        logger.warning("Falha inesperada no fallback Honcho: %s", exc)
        ctx = None
    if ctx:
        return ctx
    try:
        ctx = await _try_sqlite(session_id)
    except Exception as exc:
        logger.warning("Falha inesperada no fallback SQLite: %s", exc)
        ctx = None
    if ctx:
        return ctx
    return _degraded_context()
