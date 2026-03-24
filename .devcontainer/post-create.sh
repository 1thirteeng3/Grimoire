#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "[devcontainer] Ensuring uv + dependencies + generated schemas/types..."
make sync-backend
make sync-frontend
make export-schema
make export-ws-schema
cd frontend && npm run generate-types

echo "[devcontainer] Environment ready."
