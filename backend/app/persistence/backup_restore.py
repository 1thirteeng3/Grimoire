import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.config import settings

_Runner = Callable[..., subprocess.CompletedProcess[str]]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_sqlite(db_path: Path, backup_dir: Path) -> Path:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB não encontrado: {db_path}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    output = backup_dir / f"grimoire-sqlite-{_timestamp()}.db"
    shutil.copy2(db_path, output)
    return output


def restore_sqlite(backup_file: Path, db_path: Path) -> Path:
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup SQLite não encontrado: {backup_file}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_file, db_path)
    return db_path


def backup_postgres(dsn: str, output_file: Path, runner: _Runner = subprocess.run) -> Path:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    runner(
        [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--dbname",
            dsn,
            "--file",
            str(output_file),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return output_file


def restore_postgres(dsn: str, backup_file: Path, runner: _Runner = subprocess.run) -> Path:
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup Postgres não encontrado: {backup_file}")
    runner(
        [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "--dbname",
            dsn,
            str(backup_file),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return backup_file


def create_backup() -> Path:
    if settings.persistence_backend.lower().strip() == "postgres":
        target = settings.backup_path / f"grimoire-postgres-{_timestamp()}.dump"
        return backup_postgres(settings.postgres_dsn, target)
    return backup_sqlite(settings.data_path / "grimoire.db", settings.backup_path)


def restore_backup(backup_file: Path) -> Path:
    if settings.persistence_backend.lower().strip() == "postgres":
        return restore_postgres(settings.postgres_dsn, backup_file)
    return restore_sqlite(backup_file, settings.data_path / "grimoire.db")
