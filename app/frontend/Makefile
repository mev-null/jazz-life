# app/frontend/Makefile
# Usage: cd app/frontend && make <target>
#
# Normal development runs through the container. To run npm scripts directly on the
# host, call `npm run dev` / `npm run typecheck` / `npm run gen` etc. yourself.

COMPOSE_DIR := ..

.DEFAULT_GOAL := help
.PHONY: help dev dev-mobile shell logs restart typecheck gen

help:
	@echo "frontend targets:"
	@echo ""
	@echo "  Run (docker, the usual dev loop)"
	@echo "    dev                 Run the frontend container in the foreground (HMR + logs)"
	@echo "    dev-mobile          Run with VITE_API_BASE switched to the Codespaces public URL (for testing on a real iPhone)"
	@echo ""
	@echo "  Docker (running containers)"
	@echo "    shell               Open sh in the frontend container"
	@echo "    logs                Follow frontend logs"
	@echo "    restart             Restart only the frontend service"
	@echo ""
	@echo "  Quality / codegen (host npm)"
	@echo "    typecheck           npm run typecheck"
	@echo "    gen                 npm run gen (orval)"

# ---------- Run (docker, foreground) ----------
# The usual dev loop: run this in a separate terminal. Ctrl-C stops the container too.
# The first run builds the image (npm install), so it takes a while.
dev:
	cd $(COMPOSE_DIR) && docker compose up --build frontend

# ---------- Run (docker, bound to the Codespaces public URL) ----------
# For testing from a real device such as an iPhone. Codespaces only.
# Only VITE_API_BASE is swapped to the public URL (run the backend's `make dev-mobile` separately).
# Setup: in the VS Code PORTS tab, set the visibility of 5173 / 8000 to Public.
dev-mobile:
	@test -n "$$CODESPACE_NAME" || { echo "CODESPACE_NAME is not set (Codespaces-only target)"; exit 1; }
	@DOMAIN=$${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}; \
	echo "→ frontend public URL: https://$$CODESPACE_NAME-5173.$$DOMAIN (open this on iPhone Safari)"; \
	cd $(COMPOSE_DIR) && \
	VITE_API_BASE="https://$$CODESPACE_NAME-8000.$$DOMAIN" \
	docker compose up --build frontend

# ---------- Docker (running frontend container) ----------
shell:
	cd $(COMPOSE_DIR) && docker compose exec frontend sh

logs:
	cd $(COMPOSE_DIR) && docker compose logs -f frontend

restart:
	cd $(COMPOSE_DIR) && docker compose restart frontend

# ---------- Quality / codegen (host npm) ----------
typecheck:
	npm run typecheck

gen:
	npm run gen
