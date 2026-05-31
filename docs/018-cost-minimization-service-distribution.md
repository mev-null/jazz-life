# ADR-018: コスト最小化・脱 Railway（サービス分散で音声認識だけをボトルネック化）

**Status**: Proposed | **Date**: 2026-05-31
**Related**: [ADR-005](./005-railway-deploy-prep.md)（env 駆動デプロイ）, [ADR-016](./016-audio-recognition-on-the-hunt.md)（音声認識）, [ADR-002](./002-phase-b-decisions.md) §2.1（PostgreSQL 採用）, [ADR-006](./006-records-user-scope-schema.md) / [ADR-007](./007-releases-user-scope.md)（user-scope）

---

## 1. Context

[ADR-005](./005-railway-deploy-prep.md) で Railway に **backend（FastAPI）/ frontend（nginx 静的）/ managed PostgreSQL** の 3 サービスを常時起動する構成でデプロイした。音声認識は [ADR-016](./016-audio-recognition-on-the-hunt.md) で AudD をトライアル利用している。

このまま運用を続ける場合のコスト・ボトルネックは 2 つに集約される。

- **Railway**: 無料枠（クレジット）を超えると、常時起動の 3 リソースがすべて従量課金対象になる。とくに **managed PostgreSQL は「使っていなくても起きている」ので steady cost の主犯**。
- **AudD**: トライアル終了後は有料 API（無料の継続枠がない）。web 版のため iOS 専用の ShazamKit は使えない。

一方、本プロジェクトは **個人 + 身内（Spotify Developer Dashboard の dev mode 25 人枠）** の利用で、トラフィックは極めて低い。「常時起動」を前提にしている部分のほとんどは、**アイドル時に寝るサーバーレス無料枠 / CDN 静的配信**に逃がせる。

さらに好都合なことに、**現時点ではまだ Railway の無料クレジットが残っており出費は発生していない**。火が出てから慌てるのではなく、**クレジットがあるうちに落ち着いて移行し、枯れる頃には「音声認識だけを考えればいい」状態**にしておける。

そして [ADR-005](./005-railway-deploy-prep.md) が **「コードは 1 本・差分はすべて env」** という設計（`normalize_database_url()` による `postgres://` 吸収、CORS / Cookie / redirect の env 化）を済ませてくれているため、本移行は **コード変更を最小に抑え、設定の引っ越しが中心**になる。ADR-005 §5 自身が「Render / Supabase / Heroku 系に切り替えても同じコードで動く」と明言している。

**本 ADR の目的**: 各サービスを無料枠に分散し、**有料が残るのを「音声認識ただ一点」に絞る**。その上で音声認識については選択肢（差し替え / 継続 / 休止）を明文化し、最終判断を分離する。

---

## 2. Decision

構成を以下へ移す。[ADR-005](./005-railway-deploy-prep.md) の env 駆動原則を踏襲し、**コードに `if env == "production"` のような分岐は足さない**。

### 2.1 目標構成（到達点）

| 層 | 現行（Railway） | 移行先 | 月額 | アイドル時 |
|---|---|---|---|---|
| frontend（静的） | Railway service | **Cloudflare Pages**（or Netlify/Vercel 無料） | $0 | 常時 CDN（起動概念なし） |
| backend | Railway service | **Render 無料 Web** or **Fly.io（scale-to-zero）** | $0 | 寝る（cold start） |
| PostgreSQL | Railway managed PG | **Neon 無料枠**（自動サスペンド/再開） | $0 | 寝る（cold start） |
| 新譜の同期 | （変更なし）`POST /api/releases/sync` の**手動トリガーのまま** | — | — | ユーザー操作起点 |
| 音声認識 | AudD（トライアル） | **ACRCloud 無料 dev 枠** or AudD 継続 | ここだけ要検討 | — |
| — | — | **Railway は解約** | -$5+/月 | — |

→ うまくいけば **固定費は実質ゼロ**（音声認識を除く）。独自ドメインは任意（無料サブドメインでも成立）。

### 2.2 frontend は Cloudflare Pages へ（静的配信の無料化）

- prod ビルドは既に `dist/` を nginx で配信する形（[ADR-005](./005-railway-deploy-prep.md) §2.5）。中身は純粋な静的アセットなので、CDN 静的ホスティングに置けば常時起動サーバーは不要。
- `VITE_API_BASE` は **build time** に埋め込まれる（[ADR-005](./005-railway-deploy-prep.md) §2.5 / §3.4）。Cloudflare Pages の **build 環境変数**に新 backend ドメインを設定する。
- SPA の deep link 対策（`try_files $uri /index.html` 相当）は、Pages の `_redirects` に `/*  /index.html  200` を置いて代替する。
- nginx 配信用の Dockerfile prod ステージは Railway 用に残してよい（ローカル検証・別ホスト退避用）。Pages では使わない。

### 2.3 backend は scale-to-zero ホストへ

- **Render 無料 Web サービス**（アイドルで spin down、リクエストで起動）か **Fly.io（machines の auto stop/start）** を採用。どちらも Dockerfile デプロイに対応しており、現行 Dockerfile をそのまま使える。
- **Replicas = 1 を維持**する（[ADR-005](./005-railway-deploy-prep.md) §2.10: OAuth state がプロセスローカル `_state_store`）。scale-to-zero は「単一インスタンスが寝て起きる」だけなので、この制約と両立する。マルチレプリカ化は別作業（[ADR-005](./005-railway-deploy-prep.md) §2.10 / 既存 issue: backend マルチプロセス対応）。
- コールドスタート（初回アクセスが数秒〜数十秒）を許容する。個人 + 身内用途では実害が小さい。

### 2.4 PostgreSQL は Neon へ

- `DATABASE_URL` を Neon の接続文字列に差し替えるだけ。`normalize_database_url()` が `postgres://` / `postgresql://` を `postgresql+psycopg://` に正規化するため、**コード変更不要**（[ADR-005](./005-railway-deploy-prep.md) §2.3 / §3.3 / §5）。
- Neon は自動サスペンド/再開のサーバーレス PG。無料枠で個人利用は十分に収まる見込み（**現行の無料枠上限は移行時に必ず確認**）。
- 移行手順: Railway PG から `pg_dump` → Neon へ `pg_restore`（or `psql` 流し込み）。Alembic は entrypoint の `alembic upgrade head` を継続（[ADR-005](./005-railway-deploy-prep.md) §2.9）。
- 留意: backend と DB の両方が寝るため、長時間アイドル後の初回アクセスは **二重コールドスタート**になる。

### 2.5 新譜同期は手動トリガーのまま（cron も APScheduler も不要）

**現状の確認**（コードを精査した結果）:

- 新譜同期は `POST /api/releases/sync`（`trigger_sync`, **認証必須**）を、ユーザーが Digging の sync ボタンで叩く**手動方式**。`release_service.sync_for_user()` が follow 中アーティストの新譜を取得する。
- `pyproject.toml` に `apscheduler>=3.10` が依存として入り、[releases.py](../app/backend/app/routers/releases.py) に「APScheduler の日次バッチに移行する前提のため、ここは shim 実装」というコメントが残っているが、**スケジューラは実装されていない**（`main.py` の lifespan は `seed_artists_if_empty` のみで scheduler を起動しておらず、`add_job` / `BackgroundScheduler` のコードも存在しない）。＝**自動の日次バッチは現時点で動いていない**。

**帰結**: 同期はユーザー操作起点なので、**リクエストが来た瞬間だけ backend が起きていればよい**。これは scale-to-zero と**完全に相性が良い**（ユーザーがアプリを開いて sync を押す → その HTTP が backend を起こす → 同期 → また寝る）。→ **外部 cron も APScheduler も不要。本移行では同期まわりのコード変更ゼロ。**

**将来「自動日次同期」が欲しくなったら**: in-process の APScheduler は scale-to-zero では寝ている間に fire しないため不適。その場合は外部 cron（GitHub Actions の `schedule:` が `/api/releases/sync` を叩く + cron 用共有シークレットで保護）が定石になる。ただし**本 ADR のスコープ外**。あわせて、未配線の `apscheduler` 依存と shim コメントは「cron 方式に倒す」なら撤去候補（別タスク）。

### 2.6 音声認識を「唯一のボトルネック」として独立管理

recognition は [ADR-016](./016-audio-recognition-on-the-hunt.md) で **`audd_api_token` env・未設定なら 503**（`RecognitionService` 側で判定）と隔離されている。差し替えコストが 1 サービスに閉じているため、ここを唯一の有料検討ポイントとして切り出す。

選択肢を明文化する（**本 ADR では枠組みのみ確定し、最終選定は調査込みの別タスク**）：

- **(A) ACRCloud 無料 dev 枠へ差し替え** — `recognition_service` の HTTP 呼び出しとレスポンス mapping を書き換える。$0（1 日の認識回数上限の枠内。個人利用なら十分の見込み、要確認）。
- **(B) AudD を有料継続** — 差し替え不要。月額わずかで最小工数。
- **(C) Listen 機能を gate / 休止** — コストを完全にゼロにする最終手段。

→ **方針確定**: §2.2〜§2.5 の移行で**他をすべて $0 化**し、**音声認識だけ A/B/C を別途判断**する。これにより「有料が残るのは音声認識ただ一点」という到達状態が保証される。

### 2.7 ドメイン / Spotify redirect / CORS の更新

[ADR-005](./005-railway-deploy-prep.md) §3.7 の env 一覧を、新ホストのドメインに更新する（**値の差し替えのみ、項目は不変**）。

| env | 新しい値 |
|---|---|
| `FRONTEND_BASE_URL` | Cloudflare Pages のドメイン |
| `VITE_API_BASE`（build arg） | 新 backend ドメイン |
| `SPOTIFY_REDIRECT_URI` | `https://<new-backend>/api/auth/callback`（Spotify Dashboard に**完全一致**で登録） |
| `CORS_ALLOW_ORIGINS` | Cloudflare Pages のドメイン |
| `COOKIE_SECURE` / `COOKIE_SAMESITE` | `true` / `none`（cross-origin のため維持） |

frontend / backend が別オリジンになる点は Railway 構成と同じ（[ADR-005](./005-railway-deploy-prep.md) §2.1〜§2.2）。

---

## 3. Specification（変更点）

### 3.1 backend

- **移行そのものに backend のコード変更は不要**。新譜同期は手動トリガーのまま（§2.5）、env はすべて [ADR-005](./005-railway-deploy-prep.md) で外出し済み（値の差し替えのみ）。
- （任意・別タスク）recognition provider 切替: `recognition_service` を provider 抽象化し、`RECOGNITION_PROVIDER`（`audd` / `acrcloud`）env で切替可能にする。レスポンス形状（`RecognitionResult`）を維持すれば OpenAPI spec 不変。

### 3.2 frontend

- **コード変更なし**（ビルド先と build-time env の差し替えのみ）。
- `app/frontend/public/_redirects` に `/*  /index.html  200`（Cloudflare Pages の SPA fallback）。

### 3.3 infra

- `.github/workflows/daily-sync.yml`（`schedule:` cron, `curl -X POST` で `/api/releases/sync` を共有シークレットヘッダ付きで叩く）。
- Neon / Render（or Fly.io）/ Cloudflare Pages の各プロジェクト作成（手動・README に手順を追記）。

### 3.4 OpenAPI spec への影響

- sync のガード変更はパラメータ追加を伴わなければ spec 不変。
- recognition provider 切替も応答形状を維持すれば spec 不変。
- → `make spec` 再生成は基本不要、CI の `openapi-spec-check` も pass する見込み。

### 3.5 README

- デプロイ手順を「Railway 単体」→「Cloudflare Pages + Render/Fly + Neon + cron」の分散構成に更新。env 表（§2.7）、cron 設定、各サービスの作成手順、コールドスタートの注意を記載。

---

## 4. Out of scope

- **新譜の自動同期（日次バッチ）の導入**。現状は手動トリガーのみで、本移行でも手動のまま（§2.5）。自動化が必要になったら外部 cron 方式を別 ADR/タスクで検討。
- **OAuth state の Redis 外出し / マルチレプリカ化**（[ADR-005](./005-railway-deploy-prep.md) §2.10、既存 issue: backend マルチプロセス対応）。scale-to-zero（Replicas=1）では不要。
- **Jacket upload の永続ストレージ（R2 / Supabase Storage 等）**。未実装のため ephemeral FS で実害なし（[ADR-005](./005-railway-deploy-prep.md) §4）。実装段階で再検討。
- **音声認識プロバイダの最終選定・実装**（本 ADR は A/B/C の枠組みのみ確定。ACRCloud 無料枠の現行上限・API レスポンス形状の調査は別タスク）。
- **カスタムドメイン取得**（無料サブドメインで移行は成立する）。

---

## 5. Consequences

### Positive

- **固定費が実質 $0**（音声認識を除く）。Railway を解約できる。
- [ADR-005](./005-railway-deploy-prep.md) の env 設計のおかげで**コード変更が最小**（設定移行が主体）。
- backend も DB もサーバーレス化され、「使っていない時は課金されない」。
- **有料ポイントが音声認識 1 点に明確化**され、A/B/C を急がず落ち着いて選べる（無料クレジットが残っている今のうちに移行できる）。
- DATABASE_URL 正規化のおかげで、将来さらに別の managed PG へ移っても同じコードで動く。

### Negative / 留意事項

- **コールドスタート**: backend（Render/Fly）+ Neon の二重 sleep により、長時間アイドル後の初回アクセスが遅い（数秒〜数十秒）。
- **無料枠の変動**: 各社の無料枠は予告なく変わる / 上限がある。**移行前に現行値を必ず確認**。
- **監視ポイントの分散**: Railway 一括から複数サービスに分かれ、障害切り分けの手間が増える。
- **`VITE_API_BASE` は build-time 固定**のため、backend ドメインを変えると frontend の再ビルド/再デプロイが必要（[ADR-005](./005-railway-deploy-prep.md) 既知の留意点）。

---

## 6. Supersede notes（差し替えの対応関係）

| 原典 | 該当箇所 | 旧方針 | 新方針（本 ADR） |
|---|---|---|---|
| [ADR-005](./005-railway-deploy-prep.md) | デプロイ先 | Railway に 3 サービス常時起動 | Cloudflare Pages + Render/Fly（scale-to-zero）+ Neon に分散 |
| [ADR-005](./005-railway-deploy-prep.md) | §2.9 migrations | entrypoint で `alembic upgrade head` | 維持（Neon でも同様） |
| [ADR-005](./005-railway-deploy-prep.md) | 新譜同期 | （shim コメントは APScheduler 日次バッチを示唆）| 実態は手動トリガーのみ。**手動のまま維持**し scale-to-zero と両立。cron 不要（§2.5）|
| [ADR-016](./016-audio-recognition-on-the-hunt.md) | 音声認識 | AudD 固定 | provider 切替可能に（ACRCloud free 候補）。**唯一の有料ポイントとして独立管理**（§2.6） |

[ADR-005](./005-railway-deploy-prep.md) の **env 駆動原則そのものは supersede ではなく継承**する。原典の修正は行わず、デプロイ先に関しては本 ADR を参照される正規ソースとして扱う（[ADR-002](./002-phase-b-decisions.md) と同じ運用）。
