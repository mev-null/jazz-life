# jazz-life

ジャズ・アーティスト ダッシュボード（個人用 MVP）。
詳細な要件定義は [docs/000-pre-adr.md](docs/000-pre-adr.md) を参照。

## クイックスタート

```bash
cd app
cp .env.example .env   # 値を埋める（Spotify クレデンシャル等）
make up                # backend (8000) と frontend (5173) が起動
```

確認:

- API: <http://localhost:8000/healthz> → `{"status":"ok"}`
- フロント: <http://localhost:5173>
- OpenAPI: <http://localhost:8000/openapi.json>（Phase B 以降の `make gen` 前提条件）

停止:

```bash
make down
```

## ディレクトリ構成

```
jazz-life/
├── docs/             # ADR・設計ドキュメント
├── app/              # 全アプリ成果物（compose の作業ディレクトリ）
│   ├── backend/      # FastAPI + APScheduler
│   ├── frontend/     # React 19 + Vite + Tailwind v4
│   ├── data/         # SQLite 永続化先（.gitkeep のみ追跡）
│   ├── docker-compose.yml
│   ├── docker-compose.override.yml
│   ├── Makefile
│   └── .env.example
└── README.md
```

## 開発フェーズ

ADR §16 に従う:

- **Step 0**: Docker 環境セットアップ ← **完了**（`make up` で空のスタックが起動）
- **Phase A**: フロントエンド モック開発（A-1〜A-21）
- **Phase B**: バックエンド設計・実装（B-1〜B-11）
- **Phase C**: スクレイピングと統合（C-1〜C-4）
