# Grimoire

## Cloud agent environment bootstrap

This repository now includes a reproducible environment setup for cloud agents and
devcontainer-based runs.

### What is preconfigured

- Python **3.11** base image via `.devcontainer/devcontainer.json`
- Node.js **20** via Dev Container feature and `.nvmrc`
- `uv` auto-ensure + backend sync (`uv sync --extra dev`)
- Frontend dependency install (`npm ci` when lockfile exists)
- REST and WebSocket schema/type generation on create/update (`make export-schema`, `make export-ws-schema`, frontend `generate-types`)
- Startup guard (`.devcontainer/post-start.sh`) that repairs missing `.venv`, `node_modules`, or schema files automatically

### Files

- `.devcontainer/devcontainer.json` — base image + features + bootstrap hook
- `.devcontainer/post-create.sh` — pre-installs backend/frontend deps and generates schemas/types
- `.devcontainer/post-start.sh` — lightweight self-healing checks on container start
- `Makefile` — `ensure-uv`, `sync-backend`, `backend-test-cov`, `backend-e2e`, `frontend-verify`, `verify`
- `backend/.python-version` — Python runtime pin for local tooling

### Fast commands

- `make bootstrap-agent` — explicit full bootstrap (optional)
- `make sync-backend` — backend deps (auto-installs uv if missing)
- `make backend-test-cov` — backend tests with coverage gate (>=80%)
- `make backend-e2e` — backend E2E suite
- `make frontend-verify` — generate-types + typecheck + build
- `make verify` — backend + frontend verification pipeline

### Cloud agent expectation

After container creation (or content update), agents can run:

- `make backend-test-cov`
- `make backend-e2e`
- `make frontend-verify`

without any manual bootstrap step.

### Frontend build behavior

- `npm run build` runs `generate-types` first.
- If `backend/openapi.json` or `backend/ws_events_schema.json` are missing, the generator
  will try to produce them from backend code using `python3 -m uv run ...`.
- If backend generation is unavailable, REST schema generation falls back to
  `http://localhost:8000/openapi.json`.

### Obsidian integration

- Grimoire <-> Obsidian integration is implemented through **Obsidian CLI** adapters
  in `backend/app/integrations/obsidian_cli.py`.
- The CLI binary is configurable via `GRIMOIRE_OBSIDIAN_CLI_BINARY`
  (default: `obsidian`).

### LLM E2E (DeepSeek)

- WebSocket `INTENT_SUBMIT` now executes full flow:
  `PERCEPTION_ROUTING -> RAG_RETRIEVAL -> INTERNAL_ITERATION -> OPERATOR_READY -> EXECUTION`
  with streamed `STREAM_TOKEN` events from DeepSeek.
- Required API key sources (in priority order):
  1. `GRIMOIRE_DEEPSEEK_API_KEY` environment variable
  2. keyring entry `deepseek_api_key` (service `grimoire`)
- Optional runtime parameters:
  - `GRIMOIRE_DEEPSEEK_API_URL` (default `https://api.deepseek.com/v1`)
  - `GRIMOIRE_DEFAULT_OPERATOR_MODEL` (default `deepseek-chat`)
  - `GRIMOIRE_LLM_TIMEOUT_SECONDS`, `GRIMOIRE_LLM_MAX_TOKENS`, `GRIMOIRE_LLM_TEMPERATURE`

### Human-in-the-loop pact loop

- `INTENT_SUBMIT` now emits `PACT_REQUEST` when risk is detected (e.g. shadowed chunks,
  dangerous command pattern, or `force_human_approval=true`).
- `PACT_RESOLVE` now applies decision effectively:
  - `APPROVE_AS_IS`: executes stored proposal
  - `MODIFY_AND_APPROVE`: executes overridden arguments and marks pact as `FORCED`
  - `ABORT`: cancels execution
- Full audit trail is persisted in SQLite table `pact_audit_events`.

## Operational alerts (Prometheus + Alertmanager)

Monitoring stack files are under `ops/monitoring`:

- `ops/monitoring/prometheus.yml`
- `ops/monitoring/alert_rules.yml`
- `ops/monitoring/alertmanager.yml`
- `ops/monitoring/docker-compose.monitoring.yml`

Quick commands:

- `make monitoring-up` — start Prometheus + Alertmanager
- `make monitoring-logs` — tail monitoring logs
- `make monitoring-down` — stop monitoring stack

Configured alert rules:

- `GrimoireLLMProviderTimeoutHigh`
  - triggers when `LLM_PROVIDER_TIMEOUT` is above threshold (>=3 in 10 minutes)
- `GrimoirePromptBloatRecurring`
  - triggers when `PROMPT_BLOAT` is recurrent (>=5 in 15 minutes)
- `GrimoireRAGAverageLatencyHigh`
  - triggers when average RAG latency stays above threshold
- `GrimoireLLMAverageLatencyHigh`
  - triggers when average LLM latency stays above threshold

Prometheus scrapes `http://host.docker.internal:8000/metrics` (from inside the
monitoring containers). Run backend on port `8000` before enabling alerts.
