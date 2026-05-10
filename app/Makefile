.PHONY: up down logs ps gen migrate

# 開発環境を起動（HMR 有効、override.yml が自動マージされる）
up:
	docker compose up -d --build

# 全サービス停止
down:
	docker compose down

# ログを追う
logs:
	docker compose logs -f

# プロセス状態
ps:
	docker compose ps

# OpenAPI 仕様から TypeScript 型を自動生成（ホスト側 npx を使う）
# 事前条件: backend が起動していること（make up 後）
gen:
	npx --yes openapi-typescript http://localhost:8000/openapi.json -o frontend/src/types/api.generated.ts

# Alembic マイグレーション（Phase C-4 以降で本格運用）
# 使い方: make migrate name="add vinyl_records"
migrate:
	docker compose exec backend alembic revision --autogenerate -m "$(name)"
	docker compose exec backend alembic upgrade head
