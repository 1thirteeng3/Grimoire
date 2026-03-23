#!/usr/bin/env python3
import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.persistence import db  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rollback de migrations do Grimório.")
    parser.add_argument(
        "--steps",
        type=int,
        default=1,
        help="Quantidade de versões para rollback (padrão: 1).",
    )
    return parser.parse_args()


async def _run(steps: int) -> list[str]:
    await db.init_db(settings.data_path / "grimoire.db")
    try:
        return await db.rollback_migrations(steps=steps)
    finally:
        await db.close_db()


def main() -> int:
    args = _parse_args()
    reverted = asyncio.run(_run(steps=max(1, int(args.steps))))
    if reverted:
        print(f"Migrations revertidas: {reverted}")
    else:
        print("Nenhuma migration para rollback.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
