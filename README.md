# jazz-life

ジャズ・アーティスト ダッシュボード（個人用 MVP）。
要件定義は [docs/000-pre-adr.md](docs/000-pre-adr.md)。Phase B 開始時の方針再評価（PostgreSQL / クリーンアーキ / orval / UUID v7 / 寛容 PUT 等）は [docs/002-phase-b-decisions.md](docs/002-phase-b-decisions.md) を正とする。

## クイックスタート

環境変数は [.devcontainer/devcontainer.json](.devcontainer/devcontainer.json) で集約管理する。公開デフォルトは `containerEnv`、Spotify / JWT 等のシークレットは Codespaces user secrets を `secrets` 経由で取り込む（`.env` は使わない）。

GitHub Codespaces で開く場合:

1. https://github.com/settings/codespaces で `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` / `ALLOWED_SPOTIFY_USER_ID` / `JWT_SECRET` / `REFRESH_TOKEN_KEY` を登録し、本リポジトリに access 許可
2. codespace を Stop → Start（secret は shell 起動時に注入される）

そのうえで:

```bash
cd app
make up                # db (5432) / backend (8000) / frontend (5173) が起動
```

ローカル Docker のみで動かしたい場合は、上記 env を host shell に export してから `make up`。

確認:

| URL | 内容 |
|---|---|
| <http://localhost:8000/healthz> | `{"status":"ok"}` |
| <http://localhost:8000/api/artists> | seed 投入済みの 6 件が返る |
| <http://localhost:8000/api/records> | 空または手動投入分 |
| <http://localhost:8000/openapi.json> | OpenAPI 仕様（`make spec` で `backend/openapi.json` に保存 → `make gen` で型生成） |
| <http://localhost:8000/docs> | Swagger UI |
| <http://localhost:5173> | フロントエンド（`VITE_USE_MOCK=true` の間はモック） |

停止:

```bash
make down                  # コンテナ停止（DB は named volume に残る）
docker volume rm app_jazz-pgdata   # DB ごと完全リセットしたい時のみ
```

## ディレクトリ構成

```
jazz-life/
├── .devcontainer/    # Codespaces 設定 (containerEnv + secrets 宣言)
├── docs/             # ADR・設計ドキュメント（要件のソース・オブ・トゥルース）
├── app/              # 全アプリ成果物（compose の作業ディレクトリ）
│   ├── backend/      # FastAPI + 3 層クリーンアーキ + Alembic
│   ├── frontend/     # React 19 + Vite + Tailwind v4 + TanStack Query
│   ├── db/init/      # Postgres initdb スクリプト（jazz_test 作成）
│   ├── data/         # jacket 画像等の bind mount 永続化先（DB は named volume `jazz-pgdata`）
│   ├── docker-compose.yml
│   ├── docker-compose.override.yml
│   └── Makefile
├── CLAUDE.md         # Claude Code セッション向け作業規約
└── README.md
```

## 技術スタック

| Layer | Stack |
|---|---|
| Backend | Python 3.11, FastAPI, SQLModel, Alembic, psycopg3, uuid6, APScheduler, httpx, BeautifulSoup4 |
| Frontend | React 19, Vite 5, TypeScript, Tailwind v4, TanStack Query, React Router 6, dnd-kit |
| Tooling | uv (Python), npm, Docker / docker-compose, **orval**（Phase B-2 以降の型 + react-query hooks 生成） |
| DB | PostgreSQL 16（同インスタンス内に `jazz` / `jazz_test` を分離） |

## 開発フェーズ

| Phase | 状態 | 内容 |
|---|---|---|
| Step 0 | ✅ | Docker 環境セットアップ |
| Phase A | ✅ | frontend モック完成（手書き型 / モック JSON / レコードマトリクス / dnd-kit） |
| Phase B-1 | ✅ | backend home 機能（vinyl_records CRUD + artists 参照、PostgreSQL 16、3 層クリーンアーキ、Alembic） |
| Phase B-2 | 🟡 | frontend の orval 移行 → home 実 API 接続（POST/PUT 分解、`VITE_USE_MOCK=false` 切替） |
| Phase B-3+ | ⬜ | jacket upload / reorder / releases / concerts / 既読 API / Spotify OAuth / 新譜バッチ |
| Phase C | ⬜ | スクレイピング統合（5 会場 + sync_status） |

詳細は [docs/000-pre-adr.md](docs/000-pre-adr.md) §16 と [docs/002-phase-b-decisions.md](docs/002-phase-b-decisions.md) §6。

## テスト

backend:

```bash
cd app/backend
make sync-dev          # host venv 構築（IDE 補完用）
make check             # ruff check + mypy + pytest（要 PostgreSQL 起動）
```

frontend:

```bash
cd app/frontend
npm run typecheck
```

CI（[.github/workflows/backend.yml](.github/workflows/backend.yml)）: backend 変更で ruff format/check + mypy + pytest (unit / integration マトリクス) が走る。

## ドキュメント

| ファイル | 内容 |
|---|---|
| [docs/000-pre-adr.md](docs/000-pre-adr.md) | 要件定義書（v1.7）。機能要件・データモデル・画面仕様 |
| [docs/001-phase-a-revisions.md](docs/001-phase-a-revisions.md) | Phase A 終了時の確定事項（VinylRecord スキーマ改訂、既読、jacket 仕様等） |
| [docs/002-phase-b-decisions.md](docs/002-phase-b-decisions.md) | Phase B 開始時の方針再評価（PostgreSQL / クリーンアーキ / orval / UUID v7 / 寛容 PUT 等）。**000 と矛盾時は 002 を正とする** |
| [docs/999-vision.md](docs/999-vision.md) | プロダクトビジョン |
| [CLAUDE.md](CLAUDE.md) | Claude Code セッション向け作業規約 |
