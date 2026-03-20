import json
import os
from collections.abc import AsyncIterator

import httpx

from app.config import settings
from app.core.secrets import get_secret


class LLMConfigurationError(Exception):
    pass


class LLMProviderError(Exception):
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

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
            if response.status_code in {401, 403}:
                raise LLMConfigurationError("Falha de autenticação no DeepSeek (401/403).")
            if response.status_code >= 400:
                body = await response.aread()
                raise LLMProviderError(
                    f"DeepSeek retornou {response.status_code}: {body.decode('utf-8', errors='replace')}"
                )
            async for line in response.aiter_lines():
                maybe_delta = _extract_delta_from_sse_line(line)
                if maybe_delta is not None:
                    yield maybe_delta
