# CLAUDE.md

このファイルは新しい Claude Code セッション開始時に自動で読み込まれる。
**目的**: 次のセッションが ADR や Makefile を網羅走査しなくても作業に入れるよう、要点だけを凝縮する。

## プロジェクト概要

個人用ジャズ・アーティスト ダッシュボード。
- **Home**: アナログレコードコレクションのマトリクス表示（メイン機能）
- **Feed**: フォロー中アーティストの新譜・日本公演情報
- **Artists**: アーティスト管理（Spotify 同期 + 手動追加 + エイリアス）

詳細仕様は [docs/000-pre-adr.md](docs/000-pre-adr.md)（v1.7）。Phase A 終了時の確定事項は [docs/001-phase-a-revisions.md](docs/001-phase-a-revisions.md)、Phase B 開始時の方針再評価（PostgreSQL / クリーンアーキ / orval 採用 / UUID v7 / 寛容 PUT 等）は [docs/002-phase-b-decisions.md](docs/002-phase-b-decisions.md)。**000 と 002 は一部 supersede 関係にあるため、矛盾時は 002 を正とする**。

## 現在のフェーズ

- ✅ **Step 0**: Docker 環境セットアップ完了（`make up` で起動）
- ✅ **Phase A**: 手書き型 / モック JSON / 共通レイアウト / レコードマトリクス / dnd-kit 等 完了
- ✅ **Phase B-1**: backend ホーム機能（vinyl_records CRUD + artists 参照、PostgreSQL 16、Alembic、3 層クリーンアーキテクチャ）完了
- 🟡 **Phase B-2**: frontend の orval 移行（型 + react-query hooks 生成）→ home 実 API 接続。`upsertVinylRecord` を POST/PUT に分解、`.env` の `VITE_USE_MOCK=false` 切替
- ⬜ **Phase B-3 以降**: jacket upload / reorder / releases / concerts / 既読 API / Spotify OAuth / 新譜バッチ
- ⬜ **Phase C**: スクレイピング統合

## 技術スタック

| Layer | Stack |
|---|---|
| Backend | Python 3.11, FastAPI, SQLModel, Alembic (autogenerate), APScheduler, httpx, BeautifulSoup4, psycopg3 (sync), uuid6 |
| Frontend | React 19, Vite 5, TypeScript, Tailwind v4 (`@tailwindcss/vite`), TanStack Query, React Router 6, dnd-kit |
| Tooling | uv (Python), npm, Docker / docker-compose, **orval** (`react-query` + `fetch` mode、Phase B-2 で openapi-typescript から切替) |
| DB | PostgreSQL 16（named volume `jazz-pgdata`、initdb で `jazz` / `jazz_test` 2 DB 作成） |

## ディレクトリ構成

```
jazz-life/
├── .devcontainer/              Codespaces / VS Code dev container 定義
│   ├── devcontainer.json       dockerComposeFile パターン (service=workspace、postStart で app stack を up)
│   ├── docker-compose.devcontainer.yml  workspace サービス定義 (sleep infinity)
│   └── Dockerfile              workspace イメージ (python:3.11-bookworm + node20 + uv + make)
├── docs/                       ADR・設計ドキュメント（要件のソース・オブ・トゥルース）
├── app/                        全アプリ成果物。docker compose の作業ディレクトリ
│   ├── docker-compose.yml      共通定義（db / backend / frontend）
│   ├── docker-compose.override.yml  dev 用上書き（HMR、bind mount）
│   ├── Makefile                up / down / logs / gen
│   (環境変数は .devcontainer/devcontainer.json で集約管理、.env は廃止)
│   ├── db/init/                Postgres initdb スクリプト（jazz_test 作成）
│   ├── data/                   永続化先（jacket 画像等。DB は named volume）
│   ├── backend/
│   │   ├── Makefile            host uv + docker compose のハイブリッド (migrate / migration / db-shell)
│   │   ├── pyproject.toml      uv 管理、`uv.lock` コミット対象
│   │   ├── alembic.ini         file_template は YYYYMMDD_HHMM_<slug>
│   │   ├── migrations/         Alembic 環境 (env.py + versions/)
│   │   ├── entrypoint.sh       コンテナ起動時に alembic upgrade head → uvicorn
│   │   ├── openapi.json        backend が所有する OpenAPI spec（`make spec` で更新、コミット対象）
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
│       ├── orval.config.ts     orval 設定（input は `../backend/openapi.json`、output は `src/api/generated/`）
│       └── src/
│           ├── api/client.ts   モック/実 API 切替（VITE_USE_MOCK で分岐、実 API は orval 経由）
│           ├── api/mutator.ts  orval fetch mode 用カスタム fetcher（API_BASE を組み合わせる）
│           ├── api/generated/  orval 生成物（型 + react-query hooks、tags-split。gitignore しない）
│           ├── api/mocks/      ダミー JSON（実 API レスポンスと shape 一致を維持）
│           ├── types/api.ts    既実装分は generated/ から re-export、未実装分は手書き
│           ├── pages/          HomePage / FeedPage / ArtistsPage
│           └── components/     records/ feed/ artists/
└── .claude/
    ├── settings.json           中間レベル allowlist
    └── skills/pr-summary/      `/pr-summary` で PR 概要生成
```

## よく使うコマンド

> Codespace 起動時に `.devcontainer/devcontainer.json` の postStartCommand が `docker compose up -d` を自動で実行するので、通常は `make up` を手動で叩く必要はない。再ビルドや停止のときだけ使う。

すべて `cd app` してから:

```bash
make up          # 全サービス起動（HMR 有効。手動で再起動したいときに使う）
make down        # 停止
make logs        # 全ログ follow
make spec        # 起動中の backend から OpenAPI spec を取得して backend/openapi.json に保存（要 backend 起動）
make gen         # backend/openapi.json から TS 型 + react-query hooks 生成（backend 不要）
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

### モック切替の維持（Phase B-2 以降も）
- フロントの全 API 呼び出しは [app/frontend/src/api/client.ts](app/frontend/src/api/client.ts) 経由
- `VITE_USE_MOCK=true` の間は `src/api/mocks/*.json` を返す
- 実 API への切替は `.env` の `VITE_USE_MOCK=false` だけで完結する設計を維持
- mock JSON の shape は実 API レスポンスと一致させること（id は UUID 文字列、`source` / `purchase_currency` 等を含める）。詳細は [docs/002-phase-b-decisions.md](docs/002-phase-b-decisions.md) §2.8

### 型契約戦略（ADR-002 §2.7）
- **Phase A 中**: `frontend/src/types/api.ts` を **手書き** で更新
- **Phase B-2 以降**: `make gen` で `src/api/generated/` 配下に **型 + react-query hooks** を生成
  - `types/api.ts` は **既実装分（artists / records）** を generated から re-export する形に縮小
  - **未実装分（releases / concerts / sync_status / auth）** は手書きを残し、対応する backend が実装されたら順次 generated 由来に置換
- **spec の取り回し**: 起動中の backend から `make spec` で `backend/openapi.json` を取得 → backend PR に同梱してコミット → frontend 側は `make gen` で型生成（backend 不要）。`openapi.json` を backend 配下に置くことで、API 変更の差分が frontend PR に漏れないようにしている。CI でも gen を走らせられる
- **`src/api/generated/` と `backend/openapi.json` は gitignore しない**
- 生成ツールは **orval**（`react-query` + `fetch` mode、output: `tags-split`）。`openapi-typescript` は使わない

## やってはいけないこと

- `.venv/` / `node_modules/` / `app/data/*.db` をコミットしない（`.gitignore` で防御済み）。シークレットは `.env` ではなく **Codespaces user secrets** に置き、`.devcontainer/devcontainer.json` の `secrets` 宣言経由で container に流す
- `src/api/generated/` を `.gitignore` に追加しない（ADR-002 §2.7）
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
  - **`make check` は `ruff format --check` を含まない**ので、CI 落ちを避けたければ `cd app/backend && uv run ruff format .` を別途実行する
- frontend を変えたら: `cd app/frontend && npm run typecheck`
  - API 形状が変わったら `cd app && make spec && make gen` で spec 更新 + 生成し直してから typecheck
- スタック全体: `cd app && make up && curl http://localhost:8000/healthz`
- CI (`.github/workflows/backend.yml`): backend 変更で ruff (format/check) + mypy + pytest (unit / integration マトリクス) が走る

## 参照すべき外部ファイル

| 何が知りたいか | どこ |
|---|---|
| 機能の要件・データモデル・画面仕様 | [docs/000-pre-adr.md](docs/000-pre-adr.md) |
| Phase A 終了時のスキーマ・既読・jacket 仕様 | [docs/001-phase-a-revisions.md](docs/001-phase-a-revisions.md) |
| Phase B 開始時の方針再評価（PostgreSQL / クリーンアーキ / orval / UUID v7 / 寛容 PUT） | [docs/002-phase-b-decisions.md](docs/002-phase-b-decisions.md) |
| 起動・依存・型生成コマンド | [app/Makefile](app/Makefile) / [app/backend/Makefile](app/backend/Makefile) |
| PR 概要のテンプレート | `.claude/skills/pr-summary/SKILL.md` 経由（`/pr-summary`） |
| 環境変数の意味 | [.devcontainer/devcontainer.json](.devcontainer/devcontainer.json)（公開デフォルト + Codespaces secret 宣言） |
