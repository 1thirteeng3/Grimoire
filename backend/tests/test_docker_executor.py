import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.sandbox.docker_executor import SandboxTimeoutError, run_isolated


@pytest.fixture
def mock_proc():
    proc = AsyncMock()
    proc.returncode = 0
    proc.communicate = AsyncMock(return_value=(b"hello", b""))
    return proc


@pytest.mark.asyncio
async def test_hard_limits_presentes_no_comando(mock_proc):
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        with patch("app.sandbox.docker_executor._force_kill_container", new=AsyncMock()):
            await run_isolated('print("ok")', timeout_seconds=5)
        cmd = list(mock_exec.call_args[0])
        cmd_str = " ".join(str(c) for c in cmd)

        assert "--user" in cmd_str and "1000:1000" in cmd_str
        assert "--network none" in cmd_str
        assert "--memory" in cmd_str
        assert "--memory-swap" in cmd_str
        assert "--cpus" in cmd_str
        assert "--pids-limit" in cmd_str
        assert "no-new-privileges" in cmd_str
        assert "--cap-drop ALL" in cmd_str


@pytest.mark.asyncio
async def test_timeout_levanta_excecao(mock_proc):
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("app.sandbox.docker_executor._force_kill_container", new=AsyncMock()):
            with pytest.raises(SandboxTimeoutError):
                await run_isolated("import time; time.sleep(999)", timeout_seconds=1)


@pytest.mark.asyncio
async def test_container_destruido_em_excecao(mock_proc):
    mock_proc.communicate = AsyncMock(side_effect=RuntimeError("crash"))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("app.sandbox.docker_executor._force_kill_container", new=AsyncMock()) as kill_mock:
            with pytest.raises(RuntimeError):
                await run_isolated("code", timeout_seconds=5)
            assert kill_mock.called
