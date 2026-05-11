# app/frontend/Makefile
# 使い方: cd app/frontend && make <target>
#
# 通常の開発はコンテナ経由で動かす。npm script を host で直接叩きたい時は
# `npm run dev` / `npm run typecheck` / `npm run gen` 等を直接実行する。

COMPOSE_DIR := ..

.DEFAULT_GOAL := help
.PHONY: help dev shell logs restart typecheck gen

help:
	@echo "frontend targets:"
	@echo ""
	@echo "  起動 (docker, 通常の開発はこっち)"
	@echo "    dev                 frontend コンテナをフォアグラウンドで起動 (HMR + ログ)"
	@echo ""
	@echo "  Docker (稼働中のコンテナ)"
	@echo "    shell               frontend に sh で入る"
	@echo "    logs                frontend のログを follow"
	@echo "    restart             frontend サービスのみ再起動"
	@echo ""
	@echo "  品質 / 生成 (host npm)"
	@echo "    typecheck           npm run typecheck"
	@echo "    gen                 npm run gen (orval)"

# ---------- 起動（docker, foreground） ----------
# 通常の開発はこれを別ターミナルで叩いて動かす。Ctrl-C で停止すると container も止まる。
# 初回は image build (npm install) が走るので時間がかかる。
dev:
	cd $(COMPOSE_DIR) && docker compose up --build frontend

# ---------- Docker（稼働中の frontend コンテナ） ----------
shell:
	cd $(COMPOSE_DIR) && docker compose exec frontend sh

logs:
	cd $(COMPOSE_DIR) && docker compose logs -f frontend

restart:
	cd $(COMPOSE_DIR) && docker compose restart frontend

# ---------- 品質 / 生成（host npm） ----------
typecheck:
	npm run typecheck

gen:
	npm run gen
