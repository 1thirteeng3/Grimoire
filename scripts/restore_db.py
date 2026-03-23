#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.persistence.backup_restore import restore_backup  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restaura backup de persistência do Grimório.")
    parser.add_argument("--input", required=True, help="Caminho do arquivo de backup.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    restored = restore_backup(Path(args.input).expanduser().resolve())
    print(f"Backup restaurado: {restored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
