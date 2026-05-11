.PHONY: up down logs ps spec gen migrate db

# db だけ起動（devcontainer の postStartCommand と同じ動作。手動で再起動したい時用）
# backend / frontend は cd app/backend && make dev / cd app/frontend && make dev で個別に起動する。
db:
	docker compose up -d db

# 全サービスを detached でまとめて起動したい時の従来動作（CI や検証用）。
up:
	docker compose up -d --build

# 全サービス停止
down:
	docker compose down

# ログを追う（detached で動かしてる時用）
logs:
	docker compose logs -f

# プロセス状態
ps:
	docker compose ps

# 起動中の backend から OpenAPI 仕様を取得して backend/openapi.json に保存する。
# spec を更新したい時に明示的に呼ぶ（API 変更があった時など）。
# 事前条件: backend が起動していること（make up 後）
spec:
	curl -sf http://localhost:8000/openapi.json | jq --indent 2 . > backend/openapi.json

# OpenAPI 仕様から TypeScript 型 + react-query hooks を自動生成（ホスト側で実行）。
# spec は backend/openapi.json をローカルから読むため、backend 未起動でも実行できる。
# spec を更新するには事前に `make spec` を呼ぶこと。
# 事前条件: `cd frontend && npm install` が一度走っていること（orval が devDependency）
# 出力: frontend/src/api/generated/<tag>/<tag>.ts と generated/model/*.ts
gen:
	cd frontend && npm run gen

# Alembic マイグレーション（Phase C-4 以降で本格運用）
# 使い方: make migrate name="add vinyl_records"
migrate:
	docker compose exec backend alembic revision --autogenerate -m "$(name)"
	docker compose exec backend alembic upgrade head
