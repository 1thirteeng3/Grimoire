"""
NOTA CRÍTICA: Este módulo requer `honcho-ai` da Plastic Labs.
NÃO instalar o pacote `honcho` de Procfile manager.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.persistence.sqlite_layer import fetch_session_summary

logger = logging.getLogger("grimoire.memory")

HONCHO_TIMEOUT_SECONDS = 0.8
MAX_EPISODIC_TOKENS = 4000

try:
    from honcho_ai import AsyncHoncho as HonchoClient  # type: ignore[import-not-found]

    HONCHO_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on optional runtime setup
    HonchoClient = None  # type: ignore[assignment]
    HONCHO_AVAILABLE = False


@dataclass
class EpisodicContext:
    messages: list[dict[str, Any]] = field(default_factory=list)
    source: str = "degraded"
    token_count: int = 0
    is_degraded: bool = False


async def _try_honcho(session_id: str) -> EpisodicContext | None:
    if not HONCHO_AVAILABLE or HonchoClient is None:
        logger.debug("honcho-ai não disponível — pulando nível 1")
        return None
    try:
        client = HonchoClient(api_url=settings.honcho_api_url)
        messages = await asyncio.wait_for(
            _fetch_honcho_messages(client, session_id),
            timeout=HONCHO_TIMEOUT_SECONDS,
        )
        if messages is None:
            return None
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


async def _fetch_honcho_messages(client: Any, session_id: str) -> list[dict[str, Any]] | None:
    """
    Adaptador do SDK honcho-ai para reduzir acoplamento da API.

    Mantém compatibilidade com variações entre versões iniciais:
    - client.get_session_messages(session_id, max_tokens=...)
    - client.apps.users.sessions.messages.list(...)
    """
    if hasattr(client, "get_session_messages"):
        maybe_coro = client.get_session_messages(session_id, max_tokens=MAX_EPISODIC_TOKENS)
        return await maybe_coro if asyncio.iscoroutine(maybe_coro) else maybe_coro

    if hasattr(client, "apps"):
        app_id = getattr(settings, "honcho_app_id", "")
        user_id = getattr(settings, "honcho_user_id", session_id)
        if app_id:
            maybe_coro = client.apps.users.sessions.messages.list(
                app_id=app_id,
                user_id=user_id,
                session_id=session_id,
                max_tokens=MAX_EPISODIC_TOKENS,
            )
            return await maybe_coro if asyncio.iscoroutine(maybe_coro) else maybe_coro

    logger.warning("SDK honcho-ai sem API de mensagens compatível; fallback SQLite ativado")
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
    return EpisodicContext(messages=[], source="degraded", token_count=0, is_degraded=True)


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
