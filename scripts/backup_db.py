#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.persistence.backup_restore import create_backup  # noqa: E402


def main() -> int:
    backup = create_backup()
    print(f"Backup criado: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
