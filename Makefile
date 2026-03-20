.PHONY: setup download-models export-schema generate-types backend-dev frontend-dev test lint check-env

setup:
	cd backend && pip install uv && uv sync --extra dev
	cd frontend && npm install
	cd frontend && npm run generate-types
	@echo "✓ Setup completo. Execute: make download-models"

download-models:
	python scripts/download_models.py
	@echo "✓ Modelos ONNX prontos"

export-schema:
	cd backend && python -c "import json; from app.main import app; print(json.dumps(app.openapi()))" > openapi.json
	@echo "✓ Schema OpenAPI exportado"

generate-types: export-schema
	cd frontend && npm run generate-types
	@echo "✓ src/types/api.d.ts atualizado"

backend-dev:
	cd backend && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend-dev:
	cd frontend && npm run tauri:dev

test:
	cd backend && python -m pytest tests/ -v --cov=app --cov-report=term-missing

lint:
	cd backend && ruff check app tests && ruff format --check app tests
	cd frontend && npx tsc --noEmit

check-env:
	python scripts/setup_env.py
