# Grimoire

## Cloud agent environment bootstrap

This repository now includes a reproducible environment setup for cloud agents and
devcontainer-based runs.

### What is preconfigured

- Python **3.11** base image via `.devcontainer/devcontainer.json`
- Node.js **20** via Dev Container feature and `.nvmrc`
- `uv` install + backend sync (`uv sync --extra dev`)
- Frontend dependency install (`npm ci` when lockfile exists)
- REST and WebSocket type generation on startup (`make generate-types`)

### Files

- `.devcontainer/devcontainer.json` — base image + features + bootstrap hook
- `.devcontainer/post-create.sh` — one-shot bootstrap for backend/frontend
- `Makefile` — `bootstrap-agent`, `backend-test-cov`, `frontend-verify`, `verify`
- `backend/.python-version` — Python runtime pin for local tooling

### Fast commands

- `make bootstrap-agent` — install tooling and dependencies + generate types
- `make backend-test-cov` — backend tests with coverage gate (>=80%)
- `make frontend-verify` — generate-types + typecheck + build
- `make verify` — backend + frontend verification pipeline

### Frontend build behavior

- `npm run build` runs `generate-types` first.
- If `backend/openapi.json` or `backend/ws_events_schema.json` are missing, the generator
  will try to produce them from backend code using `python3 -m uv run ...`.
- If backend generation is unavailable, REST schema generation falls back to
  `http://localhost:8000/openapi.json`.
