.PHONY: up down logs ps spec gen migrate db deploy deploy-backend deploy-frontend deploy-logs-backend deploy-logs-frontend

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

# FastAPI app を直接 import して openapi 仕様を出力し backend/openapi.json に保存する。
# 整形は jq ではなく Python の json.dumps を使う: jq 1.6 (ローカル devcontainer) は
# 5.0 → 5 と float を integer 化してしまい、CI の jq 1.7+ と byte 不一致になる
# (Pydantic の Field(ge=1, le=5) は openapi で 5.0/1.0 を出力する仕様)。
# CI 側 (.github/workflows/backend.yml の openapi-spec-check) も Python 直叩きなので、
# こちらに揃える。backend サーバ起動は不要 (DB 接続もしないので lifespan が走らない)。
spec:
	cd backend && uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2, ensure_ascii=False))" > openapi.json

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

# ===== Railway deploy =====
# Railway への手動 deploy。git push とは独立 (push しても自動 deploy はしない)。
# 認証は `railway login --browserless` を 1 度実行して ~/.railway/config.json に
# トークンが保存されている前提。devcontainer を作り直すと消えるので再ログイン要。
#
# --path-as-root で `backend/` 以下だけを build context にする (= Dockerfile から
# 見たカレントが `app/backend/`)。--detach で deploy 完了を待たずに戻る (ログは
# `make deploy-logs-backend` か Railway dashboard で追える)。
deploy-backend:
	railway up backend --path-as-root --service backend --detach

deploy-frontend:
	railway up frontend --path-as-root --service frontend --detach

# 両方まとめて (frontend は VITE_API_BASE が build に焼き込まれるので、backend URL を
# 変えた時は backend → frontend の順で deploy する)。
deploy: deploy-backend deploy-frontend

# Railway 上のコンテナログ follow
deploy-logs-backend:
	railway logs --service backend

deploy-logs-frontend:
	railway logs --service frontend
