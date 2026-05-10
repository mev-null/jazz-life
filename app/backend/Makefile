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
        run sync sync-dev add lock \
        test lint lint-fix fmt typecheck check \
        shell logs restart \
        alembic-revision alembic-upgrade alembic-downgrade

help:
	@echo "backend targets:"
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
	@echo "  Docker (稼働中の backend コンテナ)"
	@echo "    shell               コンテナに bash で入る"
	@echo "    logs                backend のログを follow"
	@echo "    restart             backend サービスのみ再起動"
	@echo ""
	@echo "  Alembic (Phase C-4 以降)"
	@echo "    alembic-revision name=...   autogenerate でマイグレーション生成"
	@echo "    alembic-upgrade             head までアップグレード"
	@echo "    alembic-downgrade           1 つダウングレード"

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

# ---------- Alembic（Phase C-4 以降） ----------
alembic-revision:
	@if [ -z "$(name)" ]; then echo "usage: make alembic-revision name=\"<msg>\""; exit 1; fi
	cd $(COMPOSE_DIR) && docker compose exec backend alembic revision --autogenerate -m "$(name)"

alembic-upgrade:
	cd $(COMPOSE_DIR) && docker compose exec backend alembic upgrade head

alembic-downgrade:
	cd $(COMPOSE_DIR) && docker compose exec backend alembic downgrade -1
