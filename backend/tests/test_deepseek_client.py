import json

import pytest

from app.llm import deepseek_client


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
