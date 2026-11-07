# Kiln — one command per task. `make help` lists them.
.DEFAULT_GOAL := help
.PHONY: help install lint format test e2e e2e-ui ci up down api worker recheck-models web storybook build migrate openapi blender-zip
SHELL := /bin/bash
API_PORT ?= 8000
WEB_PORT ?= 5173

help: ## Show this help
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- setup -------------------------------------------------------------------
install: ## Install Node workspaces (npm) and Python workspace (uv)
	npm install
	uv sync --all-packages

# --- run ---------------------------------------------------------------------
up: ## Start Postgres and SeaweedFS S3 (docker compose)
	docker compose up -d --wait

down: ## Stop local infrastructure
	docker compose down

api: ## Run the API with reload on :$(API_PORT)
	uv run --package kiln-api uvicorn kiln_api.main:app --reload --port $(API_PORT)

worker: ## Run the asset worker
	uv run --package kiln-worker python -m kiln_worker

recheck-models: ## Re-check every ready model under the current rules (KILN-36; safe to repeat)
	uv run --package kiln-worker python -m kiln_worker.recheck

web: ## Run the web app in development on :$(WEB_PORT)
	npm run dev --workspace apps/web

storybook: ## Run the design-system Storybook
	npm run storybook --workspace packages/ui

migrate: ## Apply database migrations
	uv run --package kiln-api alembic -c services/api/alembic.ini upgrade head

openapi: ## Export the API schema and regenerate the web client types
	uv run --package kiln-api python -m kiln_api.openapi > services/api/openapi.json
	npm run api:types --workspace apps/web

build: ## Production build of every Node workspace
	npm run build --workspaces --if-present

blender-zip: ## Package the Blender add-on as dist/kiln_blender.zip
	mkdir -p dist && cd dcc/blender-addon && zip -qr ../../dist/kiln_blender.zip kiln_blender -x '*__pycache__*'

# --- quality -----------------------------------------------------------------
lint: ## Format check, lint and typecheck everything
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	npm run lint --workspaces --if-present
	npm run typecheck --workspaces --if-present
	npx prettier --check .

format: ## Format everything
	uv run ruff format . && uv run ruff check --fix .
	npx prettier --write .

test: ## Unit, database and component tests with coverage (needs `make up`)
	uv run pytest
	npm test --workspaces --if-present

e2e: ## Browser journeys (Playwright) against the production build
	npm run e2e --workspace apps/web

e2e-ui: ## Every Storybook story in both themes through axe (builds Storybook first)
	npm run build --workspace packages/ui
	npm run e2e --workspace packages/ui

ci: lint test build ## Everything CI runs
