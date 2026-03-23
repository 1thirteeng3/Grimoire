from unittest.mock import AsyncMock, patch

import pytest

from app.memory.fallback_chain import _fetch_honcho_messages, get_episodic_context


@pytest.mark.asyncio
async def test_falls_back_to_sqlite_on_honcho_timeout():
    with patch("app.memory.fallback_chain._try_honcho", new=AsyncMock(return_value=None)), patch(
        "app.memory.fallback_chain._try_sqlite",
        new=AsyncMock(
            return_value=type(
                "Ctx",
                (),
                {
                    "messages": [{"role": "system", "content": "resumo"}],
                    "source": "sqlite",
                    "token_count": 100,
                },
            )()
        ),
    ):
        ctx = await get_episodic_context("sess_test_123")
        assert ctx.source == "sqlite"


@pytest.mark.asyncio
async def test_falls_back_to_degraded_on_all_failures():
    with patch("app.memory.fallback_chain._try_honcho", new=AsyncMock(return_value=None)), patch(
        "app.memory.fallback_chain._try_sqlite", new=AsyncMock(return_value=None)
    ):
        ctx = await get_episodic_context("sess_test_123")
        assert ctx.source == "degraded"
        assert ctx.messages == []


@pytest.mark.asyncio
async def test_no_silent_failure():
    with patch("app.memory.fallback_chain._try_honcho", side_effect=Exception("crash")), patch(
        "app.memory.fallback_chain._try_sqlite", side_effect=Exception("crash2")
    ):
        ctx = await get_episodic_context("any_session")
        assert ctx is not None
        assert ctx.source == "degraded"


@pytest.mark.asyncio
async def test_fetch_honcho_messages_via_direct_method():
    class FakeClient:
        async def get_session_messages(self, session_id, max_tokens):
            assert session_id == "sess"
            assert max_tokens > 0
            return [{"role": "user", "content": "oi"}]

    messages = await _fetch_honcho_messages(FakeClient(), "sess")
    assert messages and messages[0]["role"] == "user"


@pytest.mark.asyncio
async def test_fetch_honcho_messages_unknown_api_returns_none():
    class FakeClient:
        pass

    messages = await _fetch_honcho_messages(FakeClient(), "sess")
    assert messages is None
