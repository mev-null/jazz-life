# app/backend/Makefile
# 使い方: cd app/backend && make <target>
#
# - 依存管理 / 品質チェック / 単発スクリプトはホストの uv で動かす
# - 起動・ログ・シェル・Alembic は docker compose 経由で稼働中の backend コンテナを叩く
# 前提: ホストに uv (https://docs.astral.sh/uv/) と Python 3.11+ が入っていること

# docker-compose.yml は app/ にある。-f を毎回書かずに cd で吸収する
COMPOSE_DIR := ..

# codespace 等で事前に設定された VIRTUAL_ENV が .venv と競合する警告を抑止
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
	@echo "  起動 (docker, 通常の開発はこっち)"
	@echo "    dev                 backend コンテナをフォアグラウンドで起動 (HMR + ログ)"
	@echo "    dev-mobile          Codespaces 公開 URL でバインドして起動 (iPhone 実機確認用)"
	@echo ""
	@echo "  起動 (host, no docker)"
	@echo "    run                 uvicorn を host で --reload 起動"
	@echo ""
	@echo "  依存管理 (host uv)"
	@echo "    sync                uv sync (本番依存のみ)"
	@echo "    sync-dev            uv sync --group dev (dev 依存込み、IDE 補完用)"
	@echo "    add pkg=NAME        uv add NAME"
	@echo "    lock                uv lock --upgrade"
	@echo ""
	@echo "  品質 (host uv run)"
	@echo "    test                pytest"
	@echo "    lint                ruff check"
	@echo "    lint-fix            ruff check --fix"
	@echo "    fmt                 ruff format"
	@echo "    typecheck           mypy app"
	@echo "    check               lint + typecheck + test"
	@echo ""
	@echo "  Docker (稼働中のコンテナ)"
	@echo "    shell               backend に bash で入る"
	@echo "    logs                backend のログを follow"
	@echo "    restart             backend サービスのみ再起動"
	@echo "    db-shell            db に psql で入る"
	@echo ""
	@echo "  Alembic"
	@echo "    migration MSG=...   autogenerate でマイグレーション生成"
	@echo "    migrate             head までアップグレード"
	@echo "    migrate-down        1 つダウングレード"

# ---------- 起動（docker, foreground） ----------
# 通常の開発はこれを別ターミナルで叩いて動かす。Ctrl-C で停止すると container も止まる。
# 初回は image build が走るので時間がかかる。db は devcontainer postStartCommand で既に上がっている前提。
dev:
	cd $(COMPOSE_DIR) && docker compose up --build backend

# ---------- 起動（docker, Codespaces 公開 URL バインド） ----------
# iPhone 等の実機から確認したい時用。Codespaces 限定。
# 事前準備:
#   1. Spotify Dashboard で Redirect URI に
#      `https://<CODESPACE_NAME>-8000.app.github.dev/api/auth/callback` を追加
#   2. VS Code の PORTS タブで 5173 / 8000 の visibility を Public に変更
# 5173 と 8000 は別ホスト扱いになるため SameSite=None; Secure cookie が必須。
dev-mobile:
	@test -n "$$CODESPACE_NAME" || { echo "CODESPACE_NAME 未設定 (Codespaces 専用 target)"; exit 1; }
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

# ---------- 起動（host） ----------
run:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# ---------- 依存管理（host uv） ----------
sync:
	uv sync --no-dev

sync-dev:
	uv sync

add:
	@if [ -z "$(pkg)" ]; then echo "usage: make add pkg=<package>"; exit 1; fi
	uv add $(pkg)

lock:
	uv lock --upgrade

# ---------- 品質（host uv run） ----------
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

# ---------- Docker（稼働中の backend コンテナ） ----------
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
