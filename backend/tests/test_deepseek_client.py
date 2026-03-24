import json

import pytest

from app.llm import deepseek_client
from app.config import settings


def test_extract_delta_from_sse_line_valid_payload():
    payload = {"choices": [{"delta": {"content": "Olá"}}]}
    line = "data: " + json.dumps(payload)
    assert deepseek_client._extract_delta_from_sse_line(line) == "Olá"


def test_extract_delta_from_sse_line_done_returns_none():
    assert deepseek_client._extract_delta_from_sse_line("data: [DONE]") is None


def test_resolve_api_key_from_env(monkeypatch):
    monkeypatch.setenv("GRIMOIRE_DEEPSEEK_API_KEY", "secret")
    assert deepseek_client._resolve_api_key() == "secret"


def test_resolve_api_key_raises_without_sources(monkeypatch):
    monkeypatch.delenv("GRIMOIRE_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("app.llm.deepseek_client.get_secret", lambda _: None)
    with pytest.raises(deepseek_client.LLMConfigurationError):
        deepseek_client._resolve_api_key()


@pytest.mark.asyncio
async def test_stream_operator_response_retries_then_succeeds(monkeypatch):
    attempts = {"count": 0}
    sleeps: list[float] = []

    async def fake_stream_once(**kwargs):
        del kwargs
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise deepseek_client.RetryableLLMProviderError("503")
        yield "ok"

    async def fake_sleep(seconds: float):
        sleeps.append(seconds)

    monkeypatch.setenv("GRIMOIRE_DEEPSEEK_API_KEY", "secret")
    monkeypatch.setattr(settings, "llm_retry_max_attempts", 3)
    monkeypatch.setattr(settings, "llm_retry_base_backoff_seconds", 0.25)
    monkeypatch.setattr(settings, "llm_retry_max_backoff_seconds", 1.0)
    monkeypatch.setattr(deepseek_client, "_stream_once", fake_stream_once)
    monkeypatch.setattr(deepseek_client.asyncio, "sleep", fake_sleep)

    chunks = [delta async for delta in deepseek_client.stream_operator_response("q", "", "")]
    assert chunks == ["ok"]
    assert attempts["count"] == 2
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_stream_operator_response_exhausts_retries(monkeypatch):
    attempts = {"count": 0}
    sleeps: list[float] = []

    async def always_fail(**kwargs):
        del kwargs
        attempts["count"] += 1
        raise deepseek_client.RetryableLLMProviderError("502")
        yield "never"  # pragma: no cover

    async def fake_sleep(seconds: float):
        sleeps.append(seconds)

    monkeypatch.setenv("GRIMOIRE_DEEPSEEK_API_KEY", "secret")
    monkeypatch.setattr(settings, "llm_retry_max_attempts", 3)
    monkeypatch.setattr(settings, "llm_retry_base_backoff_seconds", 0.25)
    monkeypatch.setattr(settings, "llm_retry_max_backoff_seconds", 0.5)
    monkeypatch.setattr(deepseek_client, "_stream_once", always_fail)
    monkeypatch.setattr(deepseek_client.asyncio, "sleep", fake_sleep)

    with pytest.raises(deepseek_client.LLMProviderError, match="após 3 tentativa"):
        _ = [delta async for delta in deepseek_client.stream_operator_response("q", "", "")]

    assert attempts["count"] == 3
    assert sleeps == [0.25, 0.5]
