import subprocess
from pathlib import Path

import pytest

from app.persistence import backup_restore


def test_backup_and_restore_sqlite(tmp_path: Path):
    db_path = tmp_path / "grimoire.db"
    db_path.write_text("seed-data", encoding="utf-8")
    backup_dir = tmp_path / "backups"

    backup_file = backup_restore.backup_sqlite(db_path, backup_dir)
    assert backup_file.exists()
    assert backup_file.read_text(encoding="utf-8") == "seed-data"

    db_path.write_text("changed", encoding="utf-8")
    backup_restore.restore_sqlite(backup_file, db_path)
    assert db_path.read_text(encoding="utf-8") == "seed-data"


def test_backup_postgres_builds_pg_dump_command(tmp_path: Path):
    calls: list[list[str]] = []

    def _runner(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    output = tmp_path / "postgres.dump"
    backup_restore.backup_postgres("postgresql://u:p@localhost:5432/grimoire", output, runner=_runner)
    assert output.parent.exists()
    assert calls
    assert calls[0][0] == "pg_dump"
    assert "--format=custom" in calls[0]


def test_restore_postgres_builds_pg_restore_command(tmp_path: Path):
    calls: list[list[str]] = []

    def _runner(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    backup_file = tmp_path / "postgres.dump"
    backup_file.write_bytes(b"dummy")
    backup_restore.restore_postgres(
        "postgresql://u:p@localhost:5432/grimoire",
        backup_file,
        runner=_runner,
    )
    assert calls
    assert calls[0][0] == "pg_restore"
    assert "--clean" in calls[0]


def test_restore_postgres_requires_existing_backup(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        backup_restore.restore_postgres(
            "postgresql://u:p@localhost:5432/grimoire",
            tmp_path / "missing.dump",
            runner=lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "", ""),
        )
