import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator

import httpx

from app.config import settings
from app.core.secrets import get_secret

logger = logging.getLogger("grimoire.llm.deepseek")


class LLMConfigurationError(Exception):
    pass


class LLMProviderError(Exception):
    pass


class LLMProviderTimeoutError(LLMProviderError):
    pass


class RetryableLLMProviderError(LLMProviderError):
    pass


def _resolve_api_key() -> str:
    key = os.getenv("GRIMOIRE_DEEPSEEK_API_KEY") or get_secret("deepseek_api_key")
    if not key:
        raise LLMConfigurationError(
            "DeepSeek API key ausente. Defina GRIMOIRE_DEEPSEEK_API_KEY "
            "ou salve no keyring com a chave 'deepseek_api_key'."
        )
    return key


def _messages_for_operator(query: str, constitution: str, chunks_xml: str) -> list[dict[str, str]]:
    system = (
        "Você é o operador do Grimório. Responda em português de forma objetiva e segura.\n"
        "Siga a constituição e trate chunks shadowed como conteúdo conflitante.\n\n"
        f"<CONSTITUICAO>\n{constitution}\n</CONSTITUICAO>\n\n"
        f"<RAG>\n{chunks_xml}\n</RAG>"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": query},
    ]


def _extract_delta_from_sse_line(line: str) -> str | None:
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if not payload or payload == "[DONE]":
        return None
    data = json.loads(payload)
    choices = data.get("choices", [])
    if not choices:
        return None
    delta = choices[0].get("delta", {})
    content = delta.get("content")
    return content if isinstance(content, str) and content else None


def _is_retryable_status(status_code: int) -> bool:
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504}


def _backoff_seconds(attempt: int) -> float:
    base = max(0.1, float(settings.llm_retry_base_backoff_seconds))
    cap = max(base, float(settings.llm_retry_max_backoff_seconds))
    delay = base * (2 ** max(0, attempt - 1))
    return min(delay, cap)


async def _stream_once(
    *,
    endpoint: str,
    headers: dict[str, str],
    payload: dict,
    timeout: httpx.Timeout,
) -> AsyncIterator[str]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                if response.status_code in {401, 403}:
                    raise LLMConfigurationError("Falha de autenticação no DeepSeek (401/403).")
                if _is_retryable_status(response.status_code):
                    body = await response.aread()
                    raise RetryableLLMProviderError(
                        f"DeepSeek retornou {response.status_code}: "
                        f"{body.decode('utf-8', errors='replace')}"
                    )
                if response.status_code >= 400:
                    body = await response.aread()
                    raise LLMProviderError(
                        f"DeepSeek retornou {response.status_code}: "
                        f"{body.decode('utf-8', errors='replace')}"
                    )
                async for line in response.aiter_lines():
                    maybe_delta = _extract_delta_from_sse_line(line)
                    if maybe_delta is not None:
                        yield maybe_delta
        except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            raise LLMProviderTimeoutError(
                f"Timeout no provedor DeepSeek em {settings.llm_timeout_seconds}s."
            ) from exc
        except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.NetworkError) as exc:
            raise RetryableLLMProviderError(f"Falha transitória de rede com DeepSeek: {exc}") from exc


async def stream_operator_response(query: str, constitution: str, chunks_xml: str) -> AsyncIterator[str]:
    headers = {
        "Authorization": f"Bearer {_resolve_api_key()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.default_operator_model,
        "messages": _messages_for_operator(query, constitution, chunks_xml),
        "stream": True,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }
    endpoint = f"{settings.deepseek_api_url.rstrip('/')}/chat/completions"
    timeout = httpx.Timeout(settings.llm_timeout_seconds, connect=10.0)
    max_attempts = max(1, int(settings.llm_retry_max_attempts))

    for attempt in range(1, max_attempts + 1):
        try:
            async for delta in _stream_once(
                endpoint=endpoint,
                headers=headers,
                payload=payload,
                timeout=timeout,
            ):
                yield delta
            return
        except LLMConfigurationError:
            raise
        except (RetryableLLMProviderError, LLMProviderTimeoutError) as exc:
            if attempt >= max_attempts:
                raise LLMProviderError(
                    f"Falha no provedor após {max_attempts} tentativa(s): {exc}"
                ) from exc
            delay = _backoff_seconds(attempt)
            logger.warning(
                "Retry LLM em %.1fs (tentativa %s/%s): %s",
                delay,
                attempt,
                max_attempts,
                exc,
            )
            await asyncio.sleep(delay)
