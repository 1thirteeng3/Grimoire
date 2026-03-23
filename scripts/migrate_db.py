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
    parser = argparse.ArgumentParser(description="Aplica migrations de persistência do Grimório.")
    parser.add_argument(
        "--target-version",
        required=False,
        help="Versão alvo (ex: 0001_initial). Se omitido, aplica até a mais recente.",
    )
    return parser.parse_args()


async def _run(target_version: str | None) -> list[str]:
    await db.init_db(settings.data_path / "grimoire.db")
    try:
        return await db.migrate(target_version=target_version)
    finally:
        await db.close_db()


def main() -> int:
    args = _parse_args()
    applied = asyncio.run(_run(target_version=args.target_version))
    if applied:
        print(f"Migrations aplicadas: {applied}")
    else:
        print("Nenhuma migration pendente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
