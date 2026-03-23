.PHONY: setup bootstrap-agent sync-backend sync-frontend download-models export-schema export-ws-schema generate-types backend-dev frontend-dev test backend-test-cov backend-e2e frontend-verify verify lint check-env

setup:
	$(MAKE) bootstrap-agent

bootstrap-agent:
	python3 -m pip install --upgrade pip uv
	$(MAKE) sync-backend
	$(MAKE) sync-frontend
	$(MAKE) generate-types
	@echo "✓ Ambiente pronto para backend+frontend"

sync-backend:
	if [ -f backend/uv.lock ]; then cd backend && python3 -m uv sync --extra dev --frozen; else cd backend && python3 -m uv sync --extra dev; fi

sync-frontend:
	if [ -f frontend/package-lock.json ]; then npm --prefix frontend ci; else npm --prefix frontend install; fi

download-models:
	python3 scripts/download_models.py
	@echo "✓ Modelos ONNX prontos"

export-schema: sync-backend
	cd backend && python3 -m uv run python3 -c "import json; from app.main import app; print(json.dumps(app.openapi()))" > openapi.json
	@echo "✓ Schema OpenAPI exportado"

export-ws-schema: sync-backend
	cd backend && python3 -m uv run python3 -m app.models.ws_schema_export > ws_events_schema.json
	@echo "✓ Schema WebSocket exportado"

generate-types: export-schema export-ws-schema sync-frontend
	cd frontend && npm run generate-types
	@echo "✓ tipos REST e WebSocket atualizados"

backend-dev: sync-backend
	cd backend && python3 -m uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend-dev:
	cd frontend && npm run tauri:dev

test: sync-backend
	cd backend && PYTHONPATH=. python3 -m uv run pytest tests/ -v --cov=app --cov-report=term-missing

backend-test-cov: sync-backend
	cd backend && PYTHONPATH=. python3 -m uv run pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=80

backend-e2e: sync-backend
	cd backend && PYTHONPATH=. python3 -m uv run pytest tests/e2e -v

frontend-verify: sync-frontend
	cd frontend && npm run generate-types && npm run typecheck && npm run build

verify: backend-test-cov frontend-verify

lint: sync-backend sync-frontend
	cd backend && python3 -m uv run ruff check app tests && python3 -m uv run ruff format --check app tests
	cd frontend && npx tsc --noEmit

check-env:
	python3 scripts/setup_env.py
