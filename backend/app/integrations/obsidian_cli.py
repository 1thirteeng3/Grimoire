import subprocess
import tempfile
from pathlib import Path

from app.config import settings


class ObsidianCliError(Exception):
    pass


def _run_obsidian_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = [settings.obsidian_cli_binary, *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=settings.obsidian_cli_timeout_seconds,
    )
    if result.returncode != 0:
        raise ObsidianCliError(result.stderr.strip() or f"Obsidian CLI failed: {' '.join(cmd)}")
    return result


def read_note(note_path: str) -> str:
    result = _run_obsidian_cli(
        [
            "note",
            "get",
            "--vault",
            str(settings.vault_path),
            "--path",
            note_path,
        ]
    )
    return result.stdout


def write_note(note_path: str, content: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(content)
    try:
        _run_obsidian_cli(
            [
                "note",
                "put",
                "--vault",
                str(settings.vault_path),
                "--path",
                note_path,
                "--file",
                str(tmp_path),
            ]
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def list_notes() -> list[str]:
    result = _run_obsidian_cli(
        [
            "note",
            "list",
            "--vault",
            str(settings.vault_path),
        ]
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]
