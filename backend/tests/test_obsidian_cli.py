import subprocess

import pytest

from app.integrations.obsidian_cli import ObsidianCliError, list_notes, read_note, write_note


def _ok(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["obsidian"], returncode=0, stdout=stdout, stderr="")


def test_read_note_uses_obsidian_cli(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.obsidian_cli.subprocess.run",
        lambda *args, **kwargs: _ok("conteudo"),
    )
    result = read_note("Dogmas_e_Falhas/regra.md")
    assert "conteudo" in result


def test_write_note_uses_obsidian_cli(monkeypatch):
    calls = {"count": 0}

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        return _ok()

    monkeypatch.setattr("app.integrations.obsidian_cli.subprocess.run", fake_run)
    write_note("Registros_Diarios/hoje.md", "texto")
    assert calls["count"] == 1


def test_list_notes_parses_lines(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.obsidian_cli.subprocess.run",
        lambda *args, **kwargs: _ok("a.md\nb.md\n"),
    )
    assert list_notes() == ["a.md", "b.md"]


def test_obsidian_cli_error_raises(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.obsidian_cli.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=["obsidian"], returncode=1, stdout="", stderr="erro"
        ),
    )
    with pytest.raises(ObsidianCliError):
        read_note("x.md")


def test_obsidian_cli_missing_binary_raises(monkeypatch):
    def raise_not_found(*args, **kwargs):
        raise FileNotFoundError("obsidian")

    monkeypatch.setattr("app.integrations.obsidian_cli.subprocess.run", raise_not_found)
    with pytest.raises(ObsidianCliError):
        read_note("x.md")
