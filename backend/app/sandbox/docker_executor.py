import asyncio
import logging
import shutil
import uuid
from pathlib import Path

logger = logging.getLogger("grimoire.sandbox")


_MEMORY_LIMIT = "2g"
_CPU_LIMIT = "2.0"
_PIDS_LIMIT = "64"
_SANDBOX_USER = "1000:1000"
_BASE_IMAGE = "python:3.11-slim"
_WORKSPACE_DIR = "/workspace"


class SandboxTimeoutError(Exception):
    pass


async def run_isolated(
    code: str,
    timeout_seconds: int = 30,
    image: str = _BASE_IMAGE,
    allow_network: bool = False,
) -> tuple[int, str, str]:
    run_id = str(uuid.uuid4())[:8]
    container_name = f"grimoire_sandbox_{run_id}"
    tmp_dir = Path(f"/tmp/grimoire_run_{run_id}")
    tmp_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    exec_file = tmp_dir / "execution.py"
    exec_file.write_text(code, encoding="utf-8")
    network_flag = "bridge" if allow_network else "none"

    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--user",
        _SANDBOX_USER,
        "--network",
        network_flag,
        "--memory",
        _MEMORY_LIMIT,
        "--memory-swap",
        _MEMORY_LIMIT,
        "--cpus",
        _CPU_LIMIT,
        "--pids-limit",
        _PIDS_LIMIT,
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
        "--read-only",
        "--tmpfs",
        f"{_WORKSPACE_DIR}:rw,size=100m,mode=1777",
        "-v",
        f"{tmp_dir}:{_WORKSPACE_DIR}:ro",
        "-w",
        _WORKSPACE_DIR,
        image,
        "python3",
        "execution.py",
    ]
    logger.info("Sandbox %s iniciado: image=%s network=%s", run_id, image, network_flag)

    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=5.0,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=float(timeout_seconds))
        rc = proc.returncode or 0
        logger.info("Sandbox %s encerrado: exit_code=%d", run_id, rc)
        return rc, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
    except asyncio.TimeoutError as exc:
        logger.warning("Sandbox %s timeout após %ds", run_id, timeout_seconds)
        raise SandboxTimeoutError(f"Execução excedeu {timeout_seconds}s") from exc
    finally:
        await _force_kill_container(container_name)
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def _force_kill_container(name: str) -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "rm",
            "-f",
            name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
    except Exception as exc:  # pragma: no cover - best effort cleanup
        logger.error("Falha ao destruir container %s: %s", name, exc)
