# jazz-life

> ジャズを軸にした個人ダッシュボード。アナログレコードのコレクション、フォロー中アーティストの新譜・来日公演、Spotify と連動したアーティスト管理を 1 つの画面に集約する。

「好きな本・音楽・場所をコンテキストとして溜めていって、そこから次の体験への提案をもらう」という長期ビジョン（[docs/999-vision.md](docs/999-vision.md)）の第 1 段階。ジャズ × レコード × ライブを最初のドメインに選び、MVP として作っている。

## スクリーンショット
> スクリーンショット内のアーティスト画像・アルバムアートは Spotify Web API 経由で取得したものです。
- ログイン画面

https://github.com/user-attachments/assets/c30f642d-b4ac-4f40-9923-3a624b55e9de



- レコードマトリクス（メイン画面）
<img width="1470" height="835" alt="Screenshot 2026-05-21 at 13 45 41" src="https://github.com/user-attachments/assets/f75368a6-d6dc-44e9-ac40-ec780e0771e0" />

アーティスト管理（Spotify 検索 + フォロー）
<img width="1470" height="835" alt="Screenshot 2026-05-21 at 13 46 02" src="https://github.com/user-attachments/assets/2dd03788-3092-4561-bb95-1c7f7de444bf" />

<img width="598" height="722" alt="Screenshot 2026-05-21 at 13 46 14" src="https://github.com/user-attachments/assets/f94d8e0e-88d5-4b0b-9d4a-10321e4844c1" />

- 新譜フィード
<img width="1470" height="835" alt="Screenshot 2026-05-21 at 13 47 20" src="https://github.com/user-attachments/assets/c5240787-23a6-45d8-afe9-98d938d681c6" />

<img width="424" height="334" alt="Screenshot 2026-05-21 at 13 53 50" src="https://github.com/user-attachments/assets/14aae45a-d555-44e2-97af-547471c05bb0" />

## ライブデモについて

Railway に本番デプロイ済み（backend / frontend / Postgres）。ただし**公開デモは提供していない**。

理由は Spotify Developer Dashboard の Users and Access による invite 制御をアプリ全体の認可ゲートとして採用しているため（[ADR-005](docs/005-railway-deploy-prep.md)）。アプリ側に独自の allowlist を持たないことで実装をシンプルに保つ代わりに、未登録の Spotify アカウントでは OAuth コールバックが完了しない。

評価のために動作確認したい場合は、ローカル起動（[セットアップ](#ローカルセットアップ)）か、選考担当者の Spotify アカウントを Dashboard 側で許可する形で対応できます。

## 技術ハイライト

ポートフォリオとして見てもらいたい設計判断・実装ポイント。

### 1. backend の 3 層クリーンアーキテクチャ

`routers → services → core/repositories` の単方向依存を厳格に守り、router は HTTP 変換のみ、ビジネスロジック（採番、部分更新、ドメインバリデーション）はすべて service 層に集約。`DomainError` を HTTPException にマップするのは router の `_handlers.py` だけが知っている。

- `app/backend/app/routers/` — FastAPI 薄い API 層
- `app/backend/app/services/` — ビジネスロジック（DomainError を投げる）
- `app/backend/app/core/repositories/` — DB アクセス（SQLModel `col()` スタイル）

判断の背景は [ADR-002 §2](docs/002-phase-b-decisions.md)。

### 2. 契約駆動の frontend（OpenAPI → orval）

backend が `openapi.json` を成果物として出力し（`make spec`）、frontend は orval で **型 + react-query hooks** を生成（`make gen`）。Phase A では `openapi-typescript` で型だけ生成していたが、hooks の手書きが冗長になったため Phase B-2 で orval に移行。

`src/api/client.ts` が `VITE_USE_MOCK` で実 API / モックを分岐する設計を維持しており、backend が止まっていてもフロントだけ開発できる。

### 3. Spotify OAuth + refresh token を Fernet で暗号化保存

OAuth 認可コードフローを backend で完結させ、refresh token は `REFRESH_TOKEN_KEY`（Fernet key）で対称鍵暗号化したうえで Postgres に永続化。access token はメモリのみ、ブラウザには httpOnly cookie で短命 JWT を発行する。

OAuth state は単一 process の in-memory で持っており、これに気づかず Railway を multi-replica で動かすと callback がランダムに別 process へ振られて state 検証が必ず失敗する — このトレードオフは [ADR-005](docs/005-railway-deploy-prep.md) と `railway.toml` のコメントに明示している。

### 4. ADR 駆動の意思決定記録

11 本の ADR が「いつ何を決めたか」を残している。特に:

- **000 → 002 の supersede 関係**: SQLite から PostgreSQL へ、フラットから 3 層クリーンアーキへ、UUID v4 から v7 へ、厳格 PUT から寛容 PUT へ、と Phase A 終了時に何を方針変更したかが追える
- **003**: artist を `artist_registry` / `user_follows` / `records` の 3 層に分離した理由
- **006**: 現在 `vinyl_records` が user_id でスコープされておらず multi-user 化できない自覚と、刷新計画
- **010**: Phase C の場所マスタを見越したスキーマ設計

「素早く動くものを作る」と「設計上の負債を自覚して残す」の両方を意識した記録になっている。

CI は `.github/workflows/backend.yml` で ruff (format / check) + mypy + pytest（unit / integration マトリクス）が走る。

## アーキテクチャ概要

```
┌─────────────────────────┐        ┌────────────────────────────┐
│  React 19 + Vite        │        │  FastAPI                   │
│  TanStack Query         │        │  ┌──────────────────────┐  │
│  orval-generated hooks  │  ───►  │  │ routers (薄)        │  │
│  (VITE_USE_MOCK で      │   HTTP │  │  → services         │  │
│   モック / 実 API 切替) │        │  │    → repositories   │  │
└─────────────────────────┘        │  └──────────────────────┘  │
                                   │  Alembic / SQLModel        │
                                   └─────────────┬──────────────┘
                                                 │
                                  ┌──────────────┼──────────────┐
                                  ▼              ▼              ▼
                            PostgreSQL 16   Spotify Web API   APScheduler
                                                              (新譜 sync)
```

詳細は [CLAUDE.md](CLAUDE.md) のディレクトリ構成節。

## 技術スタック

| Layer | Stack |
|---|---|
| Backend | Python 3.11, FastAPI, SQLModel, Alembic, psycopg3, uuid6, APScheduler, httpx, BeautifulSoup4, Fernet (cryptography) |
| Frontend | React 19, Vite 5, TypeScript, Tailwind v4 (`@tailwindcss/vite`), TanStack Query, React Router 6, dnd-kit |
| Tooling | uv (Python), npm, Docker / docker-compose, **orval**（OpenAPI → 型 + react-query hooks） |
| DB | PostgreSQL 16（`jazz` / `jazz_test` を同インスタンス内で分離） |
| Infra | Railway（backend / frontend / Postgres plugin）、GitHub Actions CI |

## 開発状況

| Phase | 状態 | 内容 |
|---|---|---|
| Phase A | ✅ | frontend モック完成（手書き型 / モック JSON / レコードマトリクス / dnd-kit） |
| Phase B-1 | ✅ | backend home 機能（vinyl_records CRUD + artists、PostgreSQL、3 層クリーンアーキ、Alembic） |
| Phase B-2 | ✅ | orval 化して home / artists / records を実 API 接続 |
| Phase B-3 | 🟡 | Spotify OAuth、album search + records 登録、artist follow / unfollow、releases 同期、records 削除、release 既読 backend 化、view all 拡大表示 が完了。jacket upload / reorder / concerts / 日次自動 sync は未着手 |
| Phase C  | ⬜ | concerts スクレイピング統合（ADR-010 の場所マスタを基盤に、5 会場 + sync_status） |

## AI 協働について

このプロジェクトは Claude Code との協働で開発している（リポジトリ直下の [CLAUDE.md](CLAUDE.md) がセッション規約）。**設計判断・ADR・スキーマ設計・トレードオフ評価は自分が主導**し、AI には主に「決めた設計に沿った実装」「テストの肉付け」「リファクタの実行」を任せている。

ADR と PR description（GitHub の merged PR を参照）に「なぜそう決めたか」を残しているのは、この透明性を担保するためでもある。

## ローカルセットアップ

GitHub Codespaces を使う場合:

1. [Codespaces user secrets](https://github.com/settings/codespaces) に `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` / `JWT_SECRET` / `REFRESH_TOKEN_KEY` を登録し、本リポジトリへの access を許可
2. Codespace を Stop → Start（secret は shell 起動時に注入される）
3. `cd app && make up`（db / backend / frontend が起動）

ローカル Docker のみで動かす場合は上記 env を host shell に export してから `make up`。

確認用エンドポイント:

| URL | 内容 |
|---|---|
| <http://localhost:8000/healthz> | `{"status":"ok"}` |
| <http://localhost:8000/docs> | Swagger UI |
| <http://localhost:5173> | フロントエンド |

### テスト

```bash
cd app/backend && make check       # ruff check + mypy + pytest（要 PostgreSQL）
cd app/frontend && npm run typecheck
```

詳細なコマンドは [CLAUDE.md](CLAUDE.md) の「よく使うコマンド」節、本番デプロイ手順は [ADR-005](docs/005-railway-deploy-prep.md)。

## ドキュメント

| ファイル | 内容 |
|---|---|
| [docs/000-pre-adr.md](docs/000-pre-adr.md) | 要件定義書 v1.7（機能要件・データモデル・画面仕様） |
| [docs/001-phase-a-revisions.md](docs/001-phase-a-revisions.md) | Phase A 終了時の確定事項 |
| [docs/002-phase-b-decisions.md](docs/002-phase-b-decisions.md) | Phase B 方針再評価（PostgreSQL / クリーンアーキ / orval / UUID v7 / 寛容 PUT）。**000 と矛盾時は 002 を正とする** |
| [docs/003-artist-management.md](docs/003-artist-management.md) | アーティスト管理の 3 層構造 |
| [docs/005-railway-deploy-prep.md](docs/005-railway-deploy-prep.md) | Railway デプロイ手順と env 駆動化 |
| [docs/006-records-user-scope-schema.md](docs/006-records-user-scope-schema.md) | records を catalog + ownership に 2 層分離する計画（Proposed） |
| [docs/010-place.md](docs/010-place.md) | 場所マスタと訪問体験の設計（Phase C 以降） |
| [docs/999-vision.md](docs/999-vision.md) | プロダクトの長期ビジョン |
| [CLAUDE.md](CLAUDE.md) | Claude Code セッション向け作業規約 |
