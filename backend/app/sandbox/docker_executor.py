import asyncio


async def run_isolated(command: list[str], image: str = "python:3.11-slim") -> tuple[int, str, str]:
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--cpus",
        "1.0",
        "--memory",
        "512m",
        image,
        *command,
    ]
    proc = await asyncio.create_subprocess_exec(
        *docker_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(), stderr.decode()
