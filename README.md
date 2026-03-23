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
- Full audit trail is persisted in table `pact_audit_events` (SQLite or Postgres,
  according to backend setting).

## Persistence and scale (SQLite -> Postgres, backup/restore, retention)

### Backend selection

- `GRIMOIRE_PERSISTENCE_BACKEND=sqlite` (default) keeps local file persistence.
- `GRIMOIRE_PERSISTENCE_BACKEND=postgres` enables Postgres pool + schema init.
- For Postgres mode set `GRIMOIRE_POSTGRES_DSN` (e.g.
  `postgresql://user:pass@host:5432/grimoire`).

SQLite remains simpler for local/offline; Postgres is recommended for higher
concurrency, replicas/HA setups, and centralized backup operations.

### Backup and restore strategy (tested)

- `make backup-db` creates a backup using configured backend:
  - SQLite: copy of `data/grimoire.db` into `data/backups/*.db`
  - Postgres: `pg_dump --format=custom` into `data/backups/*.dump`
- `make restore-db BACKUP_FILE=/abs/path/file` restores backup:
  - SQLite: copies backup back to `data/grimoire.db`
  - Postgres: `pg_restore --clean --if-exists`

Equivalent scripts:

- `python3 scripts/backup_db.py`
- `python3 scripts/restore_db.py --input /abs/path/file`

### Retention policy

Retention is enforced by a periodic maintenance job (default each hour).

- `GRIMOIRE_RETENTION_AUDIT_DAYS` (default 90)
- `GRIMOIRE_RETENTION_ROUTING_DAYS` (default 30)
- `GRIMOIRE_RETENTION_SESSION_SUMMARY_DAYS` (default 30)
- `GRIMOIRE_RETENTION_MAINTENANCE_INTERVAL_SECONDS` (default 3600)
- `GRIMOIRE_METRICS_RETENTION_SECONDS` (default 86400, in-memory counters reset
  after inactivity window)

Manual run:

- `make retention-run`

### Schema versioning and safe migration rollback

- Migration files live in `backend/app/persistence/migrations/sql`:
  - `NNNN_name.up.sql`
  - `NNNN_name.down.sql`
- Startup applies pending migrations automatically via persistence init.
- Manual commands:
  - `make db-migrate`
  - `make db-rollback STEPS=1`
  - `python3 scripts/migrate_db.py --target-version 0001_initial`
  - `python3 scripts/rollback_db.py --steps 1`

Migration discovery enforces that each `up` has a matching `down` file, preventing
non-reversible schema changes from entering the main flow.

## Deploy and rollback strategy

Release control lives in `ops/deploy/deployctl.py` with support for:

- `blue-green` (switch active slot after healthcheck)
- `canary` (keep stable slot + optional promotion)
- rollback modes:
  - `auto` (prefer canary rollback if canary is active, otherwise blue/green)
  - explicit `canary` or `blue-green`

### Mirrored staging environment

Environment config keys are mirrored and validated between:

- `ops/deploy/environments/staging.env`
- `ops/deploy/environments/production.env`

Validation command:

- `make deploy-validate`

### Local operational commands

- `make release-staging VERSION=v1.2.3 STRATEGY=blue-green`
- `make release-production VERSION=v1.2.3 STRATEGY=canary CANARY_WEIGHT=10`
- `make rollback-deploy ENV=production STRATEGY=auto`

Inspect deployment state:

- `python3 ops/deploy/deployctl.py print-state --env staging`
- `python3 ops/deploy/deployctl.py print-state --env production`

### GitHub release pipeline

Workflow: `.github/workflows/release.yml`

- validates staging/production mirror configuration
- runs full verification before release
- generates release manifest artifact
- deploys to staging (mirrored path)
- promotes to production (configurable in `workflow_dispatch`)
- supports manual rollback execution from workflow inputs

## Security access controls

Backend supports real auth/authz for REST + WS, rate limiting, and secret vault rotation.

### Authentication / authorization

- Toggle with `GRIMOIRE_AUTH_REQUIRED=true`.
- Token sources:
  - keyring/local vault keys `auth_admin_token` and `auth_observer_token`
  - optional env overrides `GRIMOIRE_AUTH_ADMIN_TOKEN`, `GRIMOIRE_AUTH_OBSERVER_TOKEN`
- Scope model:
  - admin: `pacts:read`, `pacts:write`, `observability:read`, `metrics:read`, `ws:connect`, `ws:write`
  - observer: read-only (`pacts:read`, `observability:read`, `metrics:read`)

WS token can be provided via `Authorization: Bearer ...` or `?token=...` query param.

### Rate limiting / abuse protection

- REST per-IP limit: `GRIMOIRE_REST_RATE_LIMIT_PER_MINUTE` (default 120)
- WS per-IP limit: `GRIMOIRE_WS_RATE_LIMIT_PER_MINUTE_PER_IP` (default 240)
- WS per-session limit: `GRIMOIRE_WS_RATE_LIMIT_PER_MINUTE_PER_SESSION` (default 180)
- WS payload limit: `GRIMOIRE_WS_MAX_MESSAGE_CHARS` (default 20000)

### Secrets vault and periodic rotation

- Pact signing secrets are managed in vault keys:
  - current: `pact_hmac_secret_current`
  - previous: `pact_hmac_secret_previous`
- Rotation period: `GRIMOIRE_PACT_SECRET_ROTATION_SECONDS` (default 30 days)
- Signature verification accepts current + previous key for safe transition.

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

Prometheus retention defaults in compose:

- `--storage.tsdb.retention.time=15d`
- `--storage.tsdb.retention.size=2GB`

### SLI/SLO definitions (post-go-live, priority P2)

Machine-readable SLO spec:

- `ops/monitoring/slo.yml`

Current objectives (rolling 30d):

- WS availability >= 99.5%
- WS error ratio <= 1.0%
- RAG avg latency <= 1200 ms
- LLM avg latency <= 3500 ms

API endpoint for SLO observability:

- `GET /api/v1/observability/slo`

### Alert calibration with real traffic

Alerting rules now combine:

- dynamic 24h baseline (`avg_over_time`) with multipliers
- minimum traffic guards (avoid noisy low-volume windows)
- fallback absolute thresholds for cold start / baseline gaps

This keeps alerts sensitive to regression while adapting to real production load.

### Incident runbooks

Runbooks are available under `ops/runbooks`:

- `incident-availability.md`
- `incident-llm-timeout.md`
- `incident-prompt-bloat.md`
- `incident-rag-degradation.md`

These runbooks are scoped as **P2 short-term post-go-live** and include:

- detection signals
- immediate mitigation
- rollback trigger points
- stabilization and post-incident actions

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
