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
- ✅ **Phase A-1〜A-3**: 手書き型 / モック JSON / API クライアント雛形 完了
- ⬜ **Phase A-4 以降**: 共通レイアウト、レコードマトリクス、フリップ、dnd-kit 等
- ⬜ **Phase B**: バックエンド本実装（Pydantic / SQLModel / FastAPI エンドポイント / `make gen`）
- ⬜ **Phase C**: スクレイピング統合

## 技術スタック

| Layer | Stack |
|---|---|
| Backend | Python 3.11, FastAPI, SQLModel, Alembic, APScheduler, httpx, BeautifulSoup4 |
| Frontend | React 19, Vite 5, TypeScript, Tailwind v4 (`@tailwindcss/vite`), TanStack Query, React Router 6, dnd-kit |
| Tooling | uv (Python), npm, Docker / docker-compose, openapi-typescript |
| DB | SQLite（ホスト `app/data/jazz.db` を Volume マウント。Phase 2 で PostgreSQL 検討） |

## ディレクトリ構成

```
jazz-life/
├── docs/                       ADR・設計ドキュメント（要件のソース・オブ・トゥルース）
├── app/                        全アプリ成果物。docker compose の作業ディレクトリ
│   ├── docker-compose.yml      共通定義
│   ├── docker-compose.override.yml  dev 用上書き（HMR、bind mount）
│   ├── Makefile                up / down / logs / gen / migrate
│   ├── .env / .env.example     Spotify クレデンシャル等
│   ├── data/                   SQLite 永続化先（.gitkeep のみ追跡）
│   ├── backend/
│   │   ├── Makefile            host uv + docker compose のハイブリッド
│   │   ├── pyproject.toml      uv 管理、`uv.lock` コミット対象
│   │   └── app/main.py         FastAPI エントリ（現状 / と /healthz のみ）
│   └── frontend/
│       └── src/
│           ├── api/client.ts   モック/実 API 切替（VITE_USE_MOCK で分岐）
│           ├── api/mocks/      Phase A 用ダミー JSON
│           ├── types/api.ts    Phase A 手書き型（Phase B-2 で `api.generated.ts` に置換）
│           ├── pages/          HomePage / FeedPage / ArtistsPage
│           └── components/     records/ feed/ artists/（A-5 以降で本格実装）
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
- backend と frontend を同一 PR で混ぜない
- ホスト直接実行は `cd app/backend` してから（`uv` は host にもインストール済み、pyproject は backend ディレクトリ）
- Tailwind v4 設定: `@tailwindcss/vite` プラグイン構成。`postcss.config` / `tailwind.config` は **作らない**
- `--no-verify` / `--no-edit` 等のフックバイパスはしない

## 検証チェックリスト（変更後の最低限）

- backend を変えたら: `cd app/backend && make check`（lint + mypy + pytest）
- frontend を変えたら: `cd app/frontend && npm run typecheck`（コンテナ内なら `docker compose exec frontend npm run typecheck`）
- スタック全体: `cd app && make up && curl http://localhost:8000/healthz`

## 参照すべき外部ファイル

| 何が知りたいか | どこ |
|---|---|
| 機能の要件・データモデル・画面仕様 | [docs/000-pre-adr.md](docs/000-pre-adr.md) |
| 起動・依存・型生成コマンド | [app/Makefile](app/Makefile) / [app/backend/Makefile](app/backend/Makefile) |
| PR 概要のテンプレート | `.claude/skills/pr-summary/SKILL.md` 経由（`/pr-summary`） |
| 環境変数の意味 | [app/.env.example](app/.env.example) |
