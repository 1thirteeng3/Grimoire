.PHONY: setup download-models export-schema export-ws-schema generate-types backend-dev frontend-dev test lint check-env

setup:
	cd backend && python3 -m pip install uv && python3 -m uv sync --extra dev
	cd frontend && npm install
	$(MAKE) generate-types
	@echo "✓ Setup completo. Execute: make download-models"

download-models:
	python3 scripts/download_models.py
	@echo "✓ Modelos ONNX prontos"

export-schema:
	cd backend && python3 -m uv run python3 -c "import json; from app.main import app; print(json.dumps(app.openapi()))" > openapi.json
	@echo "✓ Schema OpenAPI exportado"

export-ws-schema:
	cd backend && python3 -m uv run python3 -m app.models.ws_schema_export > ws_events_schema.json
	@echo "✓ Schema WebSocket exportado"

generate-types: export-schema export-ws-schema
	cd frontend && npm run generate-types
	@echo "✓ tipos REST e WebSocket atualizados"

backend-dev:
	cd backend && python3 -m uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend-dev:
	cd frontend && npm run tauri:dev

test:
	cd backend && python3 -m pytest tests/ -v --cov=app --cov-report=term-missing

lint:
	cd backend && python3 -m uv run ruff check app tests && python3 -m uv run ruff format --check app tests
	cd frontend && npx tsc --noEmit

check-env:
	python3 scripts/setup_env.py
