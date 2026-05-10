# CLAUDE.md

このファイルは新しい Claude Code セッション開始時に自動で読み込まれる。
**目的**: 次のセッションが ADR や Makefile を網羅走査しなくても作業に入れるよう、要点だけを凝縮する。

## プロジェクト概要

個人用ジャズ・アーティスト ダッシュボード。
- **Home**: アナログレコードコレクションのマトリクス表示（メイン機能）
- **Feed**: フォロー中アーティストの新譜・日本公演情報
- **Artists**: アーティスト管理（Spotify 同期 + 手動追加 + エイリアス）

詳細仕様は [docs/000-pre-adr.md](docs/000-pre-adr.md)。**変更や追加検討時は必ず ADR を参照** すること（v1.7）。

## 現在のフェーズ

- ✅ **Step 0**: Docker 環境セットアップ完了（`make up` で起動）
- ✅ **Phase A**: 手書き型 / モック JSON / 共通レイアウト / レコードマトリクス / dnd-kit 等 完了
- 🟡 **Phase B-1**: backend ホーム機能（vinyl_records CRUD + artists 参照、PostgreSQL 16、Alembic、3 層クリーンアーキテクチャ）
- ⬜ **Phase B-2 以降**: jacket upload / reorder / releases / concerts / Spotify OAuth / 新譜バッチ
- ⬜ **Phase C**: スクレイピング統合

## 技術スタック

| Layer | Stack |
|---|---|
| Backend | Python 3.11, FastAPI, SQLModel, Alembic (autogenerate), APScheduler, httpx, BeautifulSoup4, psycopg3 (sync), uuid6 |
| Frontend | React 19, Vite 5, TypeScript, Tailwind v4 (`@tailwindcss/vite`), TanStack Query, React Router 6, dnd-kit |
| Tooling | uv (Python), npm, Docker / docker-compose, openapi-typescript |
| DB | PostgreSQL 16（named volume `jazz-pgdata`、initdb で `jazz` / `jazz_test` 2 DB 作成） |

## ディレクトリ構成

```
jazz-life/
├── docs/                       ADR・設計ドキュメント（要件のソース・オブ・トゥルース）
├── app/                        全アプリ成果物。docker compose の作業ディレクトリ
│   ├── docker-compose.yml      共通定義（db / backend / frontend）
│   ├── docker-compose.override.yml  dev 用上書き（HMR、bind mount）
│   ├── Makefile                up / down / logs / gen
│   ├── .env / .env.example     Spotify クレデンシャル / DATABASE_URL
│   ├── db/init/                Postgres initdb スクリプト（jazz_test 作成）
│   ├── data/                   永続化先（jacket 画像等。DB は named volume）
│   ├── backend/
│   │   ├── Makefile            host uv + docker compose のハイブリッド (migrate / migration / db-shell)
│   │   ├── pyproject.toml      uv 管理、`uv.lock` コミット対象
│   │   ├── alembic.ini         file_template は YYYYMMDD_HHMM_<slug>
│   │   ├── migrations/         Alembic 環境 (env.py + versions/)
│   │   ├── entrypoint.sh       コンテナ起動時に alembic upgrade head → uvicorn
│   │   └── app/                3 層クリーンアーキテクチャ
│   │       ├── main.py         lifespan で artists seed 投入、include_router
│   │       ├── core/           DB アクセス層
│   │       │   ├── db.py / exceptions.py
│   │       │   └── repositories/ (artist_repository / record_repository, col() スタイル)
│   │       ├── services/       ビジネスロジック層 (採番 / 部分更新 / DomainError)
│   │       ├── schemas/        Pydantic API DTO (ListResponse[T], Literal source)
│   │       ├── models/         SQLModel ORM 全 8 テーブル
│   │       ├── routers/        FastAPI 薄い API 層 (try/except → HTTPException)
│   │       └── seeds/          artists.json (frontend mocks の複製)
│   └── frontend/
│       └── src/
│           ├── api/client.ts   モック/実 API 切替（VITE_USE_MOCK で分岐）
│           ├── api/mocks/      Phase A 用ダミー JSON
│           ├── types/api.ts    Phase A 手書き型（Phase B-2 で `api.generated.ts` に置換）
│           ├── pages/          HomePage / FeedPage / ArtistsPage
│           └── components/     records/ feed/ artists/
└── .claude/
    ├── settings.json           中間レベル allowlist
    └── skills/pr-summary/      `/pr-summary` で PR 概要生成
```

## よく使うコマンド

すべて `cd app` してから:

```bash
make up          # 全サービス起動（HMR 有効）
make down        # 停止
make logs        # 全ログ follow
make gen         # OpenAPI から TS 型自動生成（Phase B 以降、backend 起動中であること）
```

backend 単体（`cd app/backend`）:

```bash
make help            # ターゲット一覧
make sync-dev        # host venv 構築（IDE 補完用にも必須）
make check           # lint + typecheck + test 一括
make logs            # backend だけのログ
make shell           # コンテナに bash で入る
```

## 開発ルール（守る）

### 1 PR = 1 機能 × 1 レイヤ
**backend と frontend を跨いだ PR は作らない**。型契約のすり合わせは `make gen` の生成型を別 PR でコミットして橋渡しする。詳細は memory の `feedback_pr_workflow.md`。

### モックファースト（Phase A 中）
- フロントの全 API 呼び出しは [app/frontend/src/api/client.ts](app/frontend/src/api/client.ts) 経由
- `VITE_USE_MOCK=true` の間は `src/api/mocks/*.json` を返す
- 実 API への切替は `.env` の `VITE_USE_MOCK=false` だけで完結する設計を維持

### 型契約のハイブリッド戦略（ADR §4）
- **Phase A 中**: `frontend/src/types/api.ts` を **手書き** で更新
- **Phase B-2 以降**: `make gen` で `api.generated.ts` を生成、手書き版を破棄
- **`api.generated.ts` は gitignore しない**（CI で生成不要にするため）

## やってはいけないこと

- `.env` / `.venv/` / `node_modules/` / `app/data/*.db` をコミットしない（`.gitignore` で防御済み）
- `api.generated.ts` を `.gitignore` に追加しない（ADR §4）
- backend と frontend を同一 PR で混ぜない（例外: 機能完結 1 PR は許容、PR description で明示）
- ホスト直接実行は `cd app/backend` してから（`uv` は host にもインストール済み、pyproject は backend ディレクトリ）
- backend models/ では `from sqlalchemy import ...` を直接 import しない（`from sqlmodel import ...` で完結）
- Alembic migration ファイル名は autogenerate にお任せ（`alembic.ini` の `file_template` で YYYYMMDD_HHMM_slug 形式）
- Tailwind v4 設定: `@tailwindcss/vite` プラグイン構成。`postcss.config` / `tailwind.config` は **作らない**
- `--no-verify` / `--no-edit` 等のフックバイパスはしない

## 検証チェックリスト（変更後の最低限）

- backend を変えたら: `cd app/backend && make check`（lint + mypy + pytest）
  - テストは `tests/unit/`（service 単体）と `tests/integration/`（FastAPI TestClient + 実 DB）の 2 種別
  - 実行には PostgreSQL（`make up` で起動 or `docker compose up -d db`）と `TEST_DATABASE_URL` が必要
- frontend を変えたら: `cd app/frontend && npm run typecheck`
- スタック全体: `cd app && make up && curl http://localhost:8000/healthz`
- CI (`.github/workflows/backend.yml`): backend 変更で ruff (format/check) + mypy + pytest (unit / integration マトリクス) が走る

## 参照すべき外部ファイル

| 何が知りたいか | どこ |
|---|---|
| 機能の要件・データモデル・画面仕様 | [docs/000-pre-adr.md](docs/000-pre-adr.md) |
| 起動・依存・型生成コマンド | [app/Makefile](app/Makefile) / [app/backend/Makefile](app/backend/Makefile) |
| PR 概要のテンプレート | `.claude/skills/pr-summary/SKILL.md` 経由（`/pr-summary`） |
| 環境変数の意味 | [app/.env.example](app/.env.example) |
