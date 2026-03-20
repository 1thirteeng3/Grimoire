from unittest.mock import AsyncMock, patch

import pytest

from app.memory.fallback_chain import get_episodic_context


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
