#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [ ! -d "backend/.venv" ]; then
  echo "[devcontainer] backend/.venv missing. Syncing backend deps..."
  make sync-backend
fi

if [ ! -d "frontend/node_modules" ]; then
  echo "[devcontainer] frontend/node_modules missing. Syncing frontend deps..."
  make sync-frontend
fi

if [ ! -s "backend/openapi.json" ] || [ ! -s "backend/ws_events_schema.json" ]; then
  echo "[devcontainer] API/WS schema missing. Regenerating..."
  make export-schema
  make export-ws-schema
fi
