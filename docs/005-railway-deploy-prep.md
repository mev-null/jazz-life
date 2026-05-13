# ADR-005: Railway デプロイ準備（env 駆動化 + Frontend 本番ビルド）

**Status**: Proposed | **Date**: 2026-05-13
**Related**: [ADR-000](./000-pre-adr.md) §11 / §14 / §15, [ADR-002](./002-phase-b-decisions.md) §2.1（PostgreSQL 採用）

---

## 1. Context

これまで開発は Codespaces + docker-compose に閉じており、本番デプロイ環境を持たなかった。Railway へ最初のデプロイを試すにあたり、現状のコードベースには以下のボトルネックがある。

- **Frontend Dockerfile が `npm run dev`（Vite dev server）を本番で起動する**形になっており、性能・セキュリティの両面で公開できない。
- **CORS の `allow_origins` がコード内に `["http://localhost:5173", "http://127.0.0.1:5173"]` でハードコード**されており、Railway の frontend domain を許可できない。
- **Cookie の `samesite` が `"lax"` でハードコード**されており、frontend / backend が別 origin になる Railway 構成では cross-site で送信されない。
- **`SPOTIFY_REDIRECT_URI` / `FRONTEND_BASE_URL` / `VITE_API_BASE` などは env 化されているが、`COOKIE_SAMESITE` や `CORS_ALLOW_ORIGINS` は未だコード内に固定値**。
- **Vite の `allowedHosts` が `[".app.github.dev", "localhost"]` のみ**で、Railway domain を許可していない。
- **`DATABASE_URL` のスキーム正規化が無い**。Railway managed PG は `postgres://...` 形式で渡してくるが、SQLAlchemy 2.x は dialect 不明として拒否する。
- **`docker-compose.yml` の `frontend.depends_on: backend`** が無駄な起動順序依存を作っており、Railway では別 service として独立に起動するため不要。
- **アプリ側の `ALLOWED_SPOTIFY_USER_ID` allowlist** が Spotify Developer Dashboard の Users and Access と二重管理になっており、招待のたびに env 更新 + redeploy が必要。MVP の "invite-only" 運用には過剰。

これらを「Railway 用の別経路」として分岐させると、ローカルと本番でコードが二重化する。**コードはひとつのまま、すべて env で切り替えられる形** に揃えるのが本 ADR の目的。

---

## 2. Decision

### 2.1 ローカルと Railway は同じコードで動く（env 駆動）

環境差はすべて環境変数で吸収する。コードに `if env == "production"` のような分岐は入れない。

| 設定 | env 名 | ローカル既定 | Railway での値 |
|---|---|---|---|
| 許可 origin | `CORS_ALLOW_ORIGINS` (CSV) | `http://localhost:5173,http://127.0.0.1:5173` | `https://<frontend>.up.railway.app` |
| Cookie Secure | `COOKIE_SECURE` | `false` | `true` |
| Cookie SameSite | `COOKIE_SAMESITE` | `lax` | `none`（cross-origin で送信） |
| Frontend base URL | `FRONTEND_BASE_URL` | `http://127.0.0.1:5173` | `https://<frontend>.up.railway.app` |
| Spotify redirect | `SPOTIFY_REDIRECT_URI` | `http://127.0.0.1:8000/api/auth/callback` | `https://<backend>.up.railway.app/api/auth/callback` |
| Frontend API base | `VITE_API_BASE` | `http://127.0.0.1:8000` | `https://<backend>.up.railway.app` |
| DB URL | `DATABASE_URL` | docker-compose 内の `db` | Railway managed PG（`postgres://...`） |

### 2.2 Cookie `SameSite=None` は `Secure=true` 必須をコードで保証

ブラウザ仕様により `SameSite=None` は `Secure=true` でない cookie を発行できない。Settings の `model_validator` で組み合わせ検証を行い、誤設定で起動時点で落とす。

```python
if self.cookie_samesite == "none" and not self.cookie_secure:
    raise ValueError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
```

### 2.3 DATABASE_URL のスキームを正規化する

Railway は `DATABASE_URL=postgres://...` を渡してくる。SQLAlchemy 2.x は `postgres://` を「dialect 不明」として拒否し、`postgresql://` 形式（driver 指定）が必要。

Settings の `field_validator(mode="before")` で:

- `postgres://` → `postgresql+psycopg://` に置換
- `postgresql://`（driver 未指定）→ `postgresql+psycopg://` に置換
- `postgresql+psycopg://`（driver 指定済み）→ そのまま

[migrations/env.py](../app/backend/migrations/env.py) は `os.environ["DATABASE_URL"]` を直読みしているため、同じ正規化ロジックを適用する。

### 2.4 Cookie SameSite に Literal 型を使わない

`typing.Literal["lax", "strict", "none"]` を使うと typing 依存が増える。**Settings 側は `str` で持ち、`field_validator` で値域チェック**する方針。Cookie 設定先（`response.set_cookie`）は starlette の Literal 型を期待するため、設定値を渡す箇所だけ `# type: ignore[arg-type]` で抑制する。

### 2.5 Frontend Dockerfile を multi-stage 化

`dev` ステージと `prod` ステージを分ける。

- `dev`: 既存の `npm run dev`（Vite dev server）。`docker-compose.override.yml` から `--target dev` で指定。
- `prod`: `npm run build` で `dist/` を生成し、軽量 web server（`nginx:alpine` または `caddy:alpine`）で静的配信。Railway はこの prod ターゲットを build する。

`docker-compose.yml` 側は `target: dev` を明示的に指定し、ローカルの `make up` 体験を一切変えない。

`VITE_API_BASE` は **build time** に Vite が `dist/` に埋め込むので、prod build 時の `--build-arg VITE_API_BASE=...` で渡す。Railway 側で build 時 env を設定する。

### 2.6 Vite の allowedHosts を env 駆動に

`VITE_ALLOWED_HOSTS` (CSV) を新規追加。既定は `localhost,127.0.0.1,.app.github.dev`。Railway の本番 build には allowedHosts は無関係（dev server 起動時のみ参照される設定）だが、Railway 上で dev server を試したいケースや別環境のドメインを足したい場合のために env 化しておく。

### 2.7 docker-compose: `frontend.depends_on: backend` を撤去

frontend は backend が居なくても起動できる（Vite dev server は API を叩く瞬間まで backend 不要）。`depends_on` で順序付けるメリットがほぼなく、Railway の別 service 構成とも整合しない。

### 2.8 アプリ側の Spotify allowlist を撤廃（Dashboard に集約）

[ADR-000](./000-pre-adr.md) §15 が定めていた `ALLOWED_SPOTIFY_USER_ID` による backend 側の 403 判定（[auth_service.py](../app/backend/app/services/auth_service.py) の `_enforce_allowlist`）を **撤廃** する。invite 制御は **Spotify Developer Dashboard の "Users and Access"** に一本化する。

#### 採用理由

- Spotify は app を "Development mode" にしている間、Dashboard に登録された Spotify アカウント以外は OAuth を完了できない（quota extension を申請しない限り）。つまり Dashboard が事実上の "招待リスト" として機能する。
- アプリ側で重ねて allowlist を持つと、招待のたびに **Dashboard 登録 + env 更新 + redeploy** の 3 工程が必要。Dashboard だけなら **email を 1 つ入れて 30 秒** で完了する。
- ADR-003 で `users` テーブル + multi-user 伏線が既に入っており、思想的にも「OAuth に成功した人は users にそのまま upsert」と整合する。
- 撤廃しても、Dashboard 制約があるため不特定多数が入れる状態にはならない。

#### 影響範囲（撤廃する箇所）

- `Settings.allowed_spotify_user_id` フィールド削除
- `AuthService._enforce_allowlist` メソッドおよび `complete_callback` 内の呼び出し削除
- `routers/auth.py` の `ForbiddenError` import / `except` 節削除（`ForbiddenError` クラス自体は ADR-003 のピン留め 5 人制限など将来用途で残す）
- env: `ALLOWED_SPOTIFY_USER_ID` を `docker-compose.yml` / `.devcontainer/devcontainer.json` / README から削除
- 関連 test: `test_settings.py::test_empty_allowlist_is_rejected`、`test_auth_service.py::test_allowlist_*` 2 本、`test_auth.py::test_callback_disallowed_user_returns_403`

#### 将来 allowlist を復活させる条件 / 手順

以下のいずれかが発生した時点で復活を検討する：

1. **Spotify Dashboard で quota extension を申請して app を一般公開した時** — Dashboard 制約が消えるため、アプリ側 gate を再導入する必要が出る。
2. **DB ベースの招待管理（admin endpoint）に移行する時** — env CSV ではなくテーブルベース、admin UI 前提。
3. **関係者外のアクセスが現実的に発生し始めた時** — log で異常検知 / brute-force 防御の必要性が見えた時。

復活の作業コストは **Case 1（env CSV 同等の復活）で 30 分以内・約 70 行**。git history（このブランチ以前のコミット）から `git show <commit>:path` で機械的に戻せる：

```
git log --oneline -- app/backend/app/services/auth_service.py
# 該当 commit を確認
git show <commit>:app/backend/app/services/auth_service.py > /tmp/old_auth_service.py
# 必要箇所だけ patch で戻す
```

複数 ID 許可（CSV → `list[str]`）に拡張するなら +30 分、合計 1 時間以内。DB + admin UI に移行するなら数百行・1–2 日の別タスク。

### 2.9 Migrations は entrypoint で実行を継続（Railway でも当面）

Railway の "release command" / "deploy hook" に分離するのが本来の作法だが、シングルインスタンス運用かつ migration が冪等な前提で、当面は [entrypoint.sh](../app/backend/entrypoint.sh) の `alembic upgrade head` を維持する。複数インスタンスでの競合は advisory lock で守る Alembic 構成は本 ADR のスコープ外。

### 2.10 Replicas は 1 必須 / Spotify Dashboard は自分のみ（運用ガード）

OAuth state を [auth_service.py](../app/backend/app/services/auth_service.py) の `_state_store` (process-local dict) で保持しているため、**Railway service の Replicas は 1 のまま運用する**。callback が別 replica にルーティングされると state 検証が破綻し、OAuth フロー全体が落ちる。マルチ replica 化する場合は state を Redis 等に外出しする別作業が必要。

加えて、`vinyl_records` が user_id でスコープされていない状態のため、**Spotify Developer Dashboard には自分の Spotify アカウントだけを登録する**。複数 user が OAuth を完了すると同じ records を共有・改竄できてしまう。schema 刷新で本問題を恒久解決する設計は [ADR-006](./006-records-user-scope-schema.md) で計画中、実装は別 PR で行う。

### 2.11 `/docs` / `/openapi.json` の露出を env で切り替え

FastAPI は既定で `/docs` (Swagger UI) と `/openapi.json` を晒す。本番ではこれを **`EXPOSE_OPENAPI_DOCS=false`** で塞ぐ。ローカル / CI では既定 true で残す (frontend orval や手動 API 探索のため)。

実装は [main.py](../app/backend/app/main.py) の `_resolve_docs_kwargs()` で env を直読み (CORS と同じく Settings 経由にすると test 環境で評価できなくなるため module-level の env 直読みに倒す)。

---

## 3. Specification

### 3.1 backend Settings 変更点

[app/backend/app/core/settings.py](../app/backend/app/core/settings.py):

- `cookie_samesite: str = "lax"` を追加（値域チェック付き）。
- `database_url` に `field_validator(mode="before")` でスキーム正規化を追加。`normalize_database_url(url)` を module-level 関数として切り出し、`migrations/env.py` からも共有する。
- `model_validator(mode="after")` で `cookie_samesite=="none"` → `cookie_secure=True` を強制。
- `typing.Literal` / `typing.Self` は使わない（forward reference で代用）。
- **CORS_ALLOW_ORIGINS は Settings に置かない**: CORSMiddleware は app 初期化時 (module-level) に登録する必要があり、Settings を module-level で評価すると test 環境 (env 未設定) で起動できなくなる。CORS だけは main.py 側で `os.environ` を直読みする `_resolve_cors_allow_origins()` ヘルパに集約する。

### 3.2 backend main.py / auth.py / auth_service.py

- [main.py](../app/backend/app/main.py): `CORSMiddleware(allow_origins=_resolve_cors_allow_origins(), ...)`。
- [auth.py](../app/backend/app/routers/auth.py): 両 `set_cookie` 呼び出しを `samesite=settings.cookie_samesite` に変更。`ForbiddenError` import / `except` 節を削除（§2.8）。
- [auth_service.py](../app/backend/app/services/auth_service.py): `_enforce_allowlist` メソッドと `complete_callback` 内の呼び出しを削除、`ForbiddenError` import を削除。docstring から allowlist 行を削除して「invite は Spotify Dashboard に集約」のメモを追加。

### 3.3 migrations env.py

[app/backend/migrations/env.py](../app/backend/migrations/env.py) で `DATABASE_URL` を読み込む際、Settings と同じ正規化ロジックを適用する。Settings を import すると alembic offline mode で副作用が出る可能性があるため、軽量なヘルパ関数を別途用意するか、settings の関数だけ抜き出して共用する。

### 3.4 frontend Dockerfile

[app/frontend/Dockerfile](../app/frontend/Dockerfile) を multi-stage 化:

```dockerfile
# --- base: 依存解決 ---
FROM node:20-alpine AS base
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# --- dev: Vite dev server ---
FROM base AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# --- builder: 本番ビルド ---
FROM base AS builder
ARG VITE_API_BASE
ARG VITE_USE_MOCK=false
ENV VITE_API_BASE=${VITE_API_BASE}
ENV VITE_USE_MOCK=${VITE_USE_MOCK}
COPY . .
RUN npm run build

# --- prod: nginx static 配信 ---
FROM nginx:alpine AS prod
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

`nginx.conf` で SPA のために `try_files $uri /index.html;` を設定し、React Router の deep link が 404 にならないようにする。

### 3.5 docker-compose

[app/docker-compose.yml](../app/docker-compose.yml):

- `frontend.build` に `target: dev` を明示。
- `frontend.depends_on: - backend` を削除。
- backend に `CORS_ALLOW_ORIGINS` / `COOKIE_SAMESITE` を追加（既定値はローカル用）。

### 3.6 OpenAPI spec への影響

本 ADR の変更は **OpenAPI 経路に影響しない**（router の追加・削除なし、schema 変更なし、cookie / CORS は middleware レイヤの設定差し替えのみ）。`make spec` の再生成は不要、CI の `openapi-spec-check` も pass する。

### 3.7 README

[README.md](../README.md) §「Railway デプロイ（最小手順）」に **env チェックリスト** を追加した。

```
SPOTIFY_CLIENT_ID
SPOTIFY_CLIENT_SECRET
JWT_SECRET (32+ chars)
REFRESH_TOKEN_KEY (Fernet 32-byte base64)
DATABASE_URL (Railway managed PG が自動注入、postgres:// 形式)
SPOTIFY_REDIRECT_URI (https://<backend>.up.railway.app/api/auth/callback)
FRONTEND_BASE_URL (https://<frontend>.up.railway.app)
CORS_ALLOW_ORIGINS (https://<frontend>.up.railway.app)
COOKIE_SECURE=true
COOKIE_SAMESITE=none
EXPOSE_OPENAPI_DOCS=false
```

`ALLOWED_SPOTIFY_USER_ID` は本 ADR §2.8 で撤廃したため env リストに含めない。

Spotify Developer Dashboard に上記 `SPOTIFY_REDIRECT_URI` を **完全一致** で事前登録する旨も明記。

加えて、本 PR 時点では **Replicas=1 / Dashboard に自分のみ登録 / `EXPOSE_OPENAPI_DOCS=false`** の 3 点を README の「Railway デプロイ手順」セクションで明示する (詳細は §2.10 / §2.11)。

---

## 4. Out of scope

- **Frontend 静的配信の置き場所**: 今回は frontend を別 service として nginx で配信する構成。将来 backend の StaticFiles で同一 origin にまとめる選択肢は残すが、本 ADR では採用しない（cookie cross-site の制約は SameSite=None で吸収する）。
- **Migrations の release command 化**: 複数インスタンス運用が現実化するまでは entrypoint 実行を維持。
- **Jacket upload など file 永続化機能**: 未実装のため Railway の ephemeral FS で実害なし。実装段階で外部ストレージ（R2 / Supabase Storage 等）を検討する。
- **APScheduler の worker 分離**: 未実装のため本 ADR では扱わない。

---

## 5. Consequences

### Positive

- ローカル開発と Railway 本番が **同じコードベース** で動く（env だけが違う）。
- Frontend の本番ビルドが軽量 nginx になり、攻撃面積と起動時間が削減される。
- Settings の `model_validator` で誤設定（SameSite=None + Secure=false 等）が起動時に検出される。
- DATABASE_URL のスキーム差を吸収するロジックが backend 側に閉じるため、Railway 以外の managed PG（Render / Supabase / Heroku 系）に切り替えても同じコードで動く。

### Negative / 留意事項

- Frontend Dockerfile が複数ステージになり、ローカル `docker compose build` のキャッシュ挙動を理解する必要が出る（`target: dev` を override で指定する点）。
- `VITE_API_BASE` が build time に固定されるため、Railway 本番の frontend service を別ドメインに移す場合は **再 build が必要**。
- 本 ADR は Railway の手順そのもの（プロジェクト作成、service 接続、env 登録）はカバーしない。README の env チェックリストを別途参照する運用。
- Spotify Dashboard を quota extension で一般公開した瞬間に、アプリ側 allowlist が無いため誰でも入れる状態になる。Dashboard を public 化する判断時に §2.8 の "復活手順" を実行する必要がある。

---

## 6. Supersede notes（差し替えの対応関係）

| 原典 | 該当箇所 | 旧方針 | 新方針（本 ADR） |
|---|---|---|---|
| [ADR-000](./000-pre-adr.md) | §15 認証方式 | `ALLOWED_SPOTIFY_USER_ID` で backend が 403 判定 | 撤廃。invite 制御は Spotify Developer Dashboard の Users and Access に集約（§2.8） |
| [ADR-000](./000-pre-adr.md) | §14 環境変数 | `.env` ファイル + `DATABASE_URL=sqlite:///...` | Railway は env を UI で設定。`DATABASE_URL` は `postgres://` 形式から正規化（§2.3） |
| [ADR-000](./000-pre-adr.md) | §14 Docker 構成 | frontend は Vite dev server / Nginx 配信を Dockerfile マルチステージで切替 | dev は `target: dev`、本番は `target: prod` で nginx static 配信に明示分離（§2.5） |

原典の修正は行わず、本 ADR を参照される正規ソースとして扱う（ADR-002 と同じ運用）。
