#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "[devcontainer] Running repository bootstrap..."
make bootstrap-agent

echo "[devcontainer] Environment ready."
