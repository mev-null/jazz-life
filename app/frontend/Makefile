# app/frontend/Makefile
# 使い方: cd app/frontend && make <target>
#
# 通常の開発はコンテナ経由で動かす。npm script を host で直接叩きたい時は
# `npm run dev` / `npm run typecheck` / `npm run gen` 等を直接実行する。

COMPOSE_DIR := ..

.DEFAULT_GOAL := help
.PHONY: help dev dev-mobile shell logs restart typecheck gen

help:
	@echo "frontend targets:"
	@echo ""
	@echo "  起動 (docker, 通常の開発はこっち)"
	@echo "    dev                 frontend コンテナをフォアグラウンドで起動 (HMR + ログ)"
	@echo "    dev-mobile          VITE_API_BASE を Codespaces 公開 URL に切替えて起動 (iPhone 実機確認用)"
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

# ---------- 起動（docker, Codespaces 公開 URL バインド） ----------
# iPhone 等の実機から確認したい時用。Codespaces 限定。
# VITE_API_BASE のみ公開 URL に差し替える (backend 側は `make dev-mobile` を別途叩く)。
# 事前準備: VS Code の PORTS タブで 5173 / 8000 の visibility を Public に変更。
dev-mobile:
	@test -n "$$CODESPACE_NAME" || { echo "CODESPACE_NAME 未設定 (Codespaces 専用 target)"; exit 1; }
	@DOMAIN=$${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}; \
	echo "→ frontend public URL: https://$$CODESPACE_NAME-5173.$$DOMAIN (open this on iPhone Safari)"; \
	cd $(COMPOSE_DIR) && \
	VITE_API_BASE="https://$$CODESPACE_NAME-8000.$$DOMAIN" \
	docker compose up --build frontend

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
