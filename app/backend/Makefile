# app/backend/Makefile
# Usage: cd app/backend && make <target>
#
# - Dependency management / quality checks / one-off scripts run with uv on the host
# - Start / logs / shell / Alembic go through docker compose to the running backend container
# Prerequisite: uv (https://docs.astral.sh/uv/) and Python 3.11+ installed on the host

# docker-compose.yml lives in app/. cd there instead of passing -f every time
COMPOSE_DIR := ..

# Suppress the warning when a VIRTUAL_ENV preset by Codespaces etc. conflicts with .venv
unexport VIRTUAL_ENV

.DEFAULT_GOAL := help
.PHONY: help \
        dev dev-mobile run sync sync-dev add lock \
        test lint lint-fix fmt typecheck check \
        shell logs restart db-shell \
        migrate migration migrate-down

help:
	@echo "backend targets:"
	@echo ""
	@echo "  Run (docker, the usual dev loop)"
	@echo "    dev                 Run the backend container in the foreground (HMR + logs)"
	@echo "    dev-mobile          Bind to the Codespaces public URL (for testing on a real iPhone)"
	@echo ""
	@echo "  Run (host, no docker)"
	@echo "    run                 Run uvicorn on the host with --reload"
	@echo ""
	@echo "  Dependencies (host uv)"
	@echo "    sync                uv sync (production deps only)"
	@echo "    sync-dev            uv sync --group dev (includes dev deps, for IDE completion)"
	@echo "    add pkg=NAME        uv add NAME"
	@echo "    lock                uv lock --upgrade"
	@echo ""
	@echo "  Quality (host uv run)"
	@echo "    test                pytest"
	@echo "    lint                ruff check"
	@echo "    lint-fix            ruff check --fix"
	@echo "    fmt                 ruff format"
	@echo "    typecheck           mypy app"
	@echo "    check               lint + typecheck + test"
	@echo ""
	@echo "  Docker (running containers)"
	@echo "    shell               Open bash in the backend container"
	@echo "    logs                Follow backend logs"
	@echo "    restart             Restart only the backend service"
	@echo "    db-shell            Open psql in the db container"
	@echo ""
	@echo "  Alembic"
	@echo "    migration MSG=...   Autogenerate a migration"
	@echo "    migrate             Upgrade to head"
	@echo "    migrate-down        Downgrade one revision"

# ---------- Run (docker, foreground) ----------
# The usual dev loop: run this in a separate terminal. Ctrl-C stops the container too.
# The first run builds the image, so it takes a while. Assumes db is already up via the
# devcontainer postStartCommand.
dev:
	cd $(COMPOSE_DIR) && docker compose up --build backend

# ---------- Run (docker, bound to the Codespaces public URL) ----------
# For testing from a real device such as an iPhone. Codespaces only.
# Setup:
#   1. In the Spotify Dashboard, add
#      `https://<CODESPACE_NAME>-8000.app.github.dev/api/auth/callback` as a Redirect URI
#   2. In the VS Code PORTS tab, set the visibility of 5173 / 8000 to Public
# 5173 and 8000 count as different hosts, so SameSite=None; Secure cookies are required.
dev-mobile:
	@test -n "$$CODESPACE_NAME" || { echo "CODESPACE_NAME is not set (Codespaces-only target)"; exit 1; }
	@DOMAIN=$${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}; \
	echo "→ frontend public URL: https://$$CODESPACE_NAME-5173.$$DOMAIN"; \
	echo "→ backend  public URL: https://$$CODESPACE_NAME-8000.$$DOMAIN"; \
	echo "  (verify the redirect URI is registered in Spotify Dashboard / PORTS are set to Public)"; \
	cd $(COMPOSE_DIR) && \
	SPOTIFY_REDIRECT_URI="https://$$CODESPACE_NAME-8000.$$DOMAIN/api/auth/callback" \
	FRONTEND_BASE_URL="https://$$CODESPACE_NAME-5173.$$DOMAIN" \
	CORS_ALLOW_ORIGINS="https://$$CODESPACE_NAME-5173.$$DOMAIN" \
	COOKIE_SECURE=true \
	COOKIE_SAMESITE=none \
	docker compose up --build backend

# ---------- Run (host) ----------
run:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# ---------- Dependencies (host uv) ----------
sync:
	uv sync --no-dev

sync-dev:
	uv sync

add:
	@if [ -z "$(pkg)" ]; then echo "usage: make add pkg=<package>"; exit 1; fi
	uv add $(pkg)

lock:
	uv lock --upgrade

# ---------- Quality (host uv run) ----------
test:
	@uv run pytest; ec=$$?; if [ $$ec -eq 5 ]; then echo "(no tests collected)"; exit 0; else exit $$ec; fi

lint:
	uv run ruff check .

lint-fix:
	uv run ruff check --fix .

fmt:
	uv run ruff format .

typecheck:
	uv run mypy app

check: lint typecheck test

# ---------- Docker (running backend container) ----------
shell:
	cd $(COMPOSE_DIR) && docker compose exec backend bash

logs:
	cd $(COMPOSE_DIR) && docker compose logs -f backend

restart:
	cd $(COMPOSE_DIR) && docker compose restart backend

db-shell:
	cd $(COMPOSE_DIR) && docker compose exec db psql -U jazz -d jazz

# ---------- Alembic ----------
migration:
	@if [ -z "$(MSG)" ]; then echo "usage: make migration MSG=\"<message>\""; exit 1; fi
	cd $(COMPOSE_DIR) && docker compose exec backend alembic revision --autogenerate -m "$(MSG)"

migrate:
	cd $(COMPOSE_DIR) && docker compose exec backend alembic upgrade head

migrate-down:
	cd $(COMPOSE_DIR) && docker compose exec backend alembic downgrade -1
