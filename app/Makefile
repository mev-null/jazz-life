.PHONY: up down logs ps spec gen migrate db deploy deploy-backend deploy-frontend deploy-logs-backend deploy-logs-frontend

# Start only db (same as the devcontainer postStartCommand; use it to restart the db by hand).
# backend / frontend are started individually with `cd app/backend && make dev` / `cd app/frontend && make dev`.
db:
	docker compose up -d db

# Legacy behaviour: bring up every service detached at once (CI / verification).
up:
	docker compose up -d --build

# Stop all services
down:
	docker compose down

# Follow logs (when running detached)
logs:
	docker compose logs -f

# Container status
ps:
	docker compose ps

# Import the FastAPI app directly, dump the OpenAPI spec and save it to backend/openapi.json.
# Formatting uses Python's json.dumps rather than jq: jq 1.6 (local devcontainer) turns
# floats into integers (5.0 -> 5), so the output is not byte-identical to jq 1.7+ in CI
# (Pydantic's Field(ge=1, le=5) emits 5.0/1.0 in the OpenAPI output).
# CI (openapi-spec-check in .github/workflows/backend.yml) also imports the app directly
# via Python, so this stays aligned with it. No backend server is needed (no DB
# connection is made, so lifespan never runs).
spec:
	cd backend && uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2, ensure_ascii=False))" > openapi.json

# Generate TypeScript types + react-query hooks from the OpenAPI spec (runs on the host).
# The spec is read locally from backend/openapi.json, so the backend does not need to be running.
# Run `make spec` first to refresh the spec.
# Prerequisite: `cd frontend && npm install` has been run once (orval is a devDependency).
# Output: frontend/src/api/generated/<tag>/<tag>.ts and generated/model/*.ts
gen:
	cd frontend && npm run gen

# Alembic migrations
# Usage: make migrate name="add vinyl_records"
migrate:
	docker compose exec backend alembic revision --autogenerate -m "$(name)"
	docker compose exec backend alembic upgrade head

# ===== Railway deploy =====
# Manual deploy to Railway, independent of git push.
# Assumes `railway login --browserless` has been run once so the token is stored in
# ~/.railway/config.json. Rebuilding the devcontainer wipes it; log in again.
#
# --path-as-root makes `backend/` alone the build context (the Dockerfile's cwd is
# `app/backend/`). --detach returns without waiting for the deploy to finish (follow
# the logs with `make deploy-logs-backend` or the Railway dashboard).
deploy-backend:
	railway up backend --path-as-root --service backend --detach

deploy-frontend:
	railway up frontend --path-as-root --service frontend --detach

# Both at once (VITE_API_BASE is baked into the frontend build, so when the backend URL
# changes, deploy backend first and frontend second).
deploy: deploy-backend deploy-frontend

# Follow container logs on Railway
deploy-logs-backend:
	railway logs --service backend

deploy-logs-frontend:
	railway logs --service frontend
