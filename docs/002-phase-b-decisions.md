# 002. Phase B 開始時の方針再評価（PostgreSQL / クリーンアーキ / orval）

**Status**: Accepted（Phase B-1 完了時点でのスナップショット）
**Date**: 2026-05-10
**Relates to**: [000-pre-adr.md](./000-pre-adr.md) §11（アーキテクチャ）, §12（データモデル）, §13（技術スタック）, §14（Docker 構成）, §16（開発手順）/ [001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.3（書き込み API の確定）

---

## 1. Context

Phase B-1（home 機能のバックエンド実装）に着手するにあたり、Phase A までに想定していた以下の前提を見直す必要が生じた。

- **DB**: 000-pre-adr.md §13 / §14 では「MVP は SQLite、Phase 2 で PostgreSQL 移行」と規定していた。
- **マイグレーション**: 同 §12 では「初期は `create_all()`、Phase C-4 で Alembic 導入」と段階的アプローチを定めていた。
- **vinyl_records.id**: 同 §12 および 001-phase-a-revisions.md §2.3 で「サーバ側 auto-increment（int）」と確定していた。
- **PUT セマンティクス**: 001-phase-a-revisions.md §2.3 で「PUT body は `VinylRecord` 全体」と定めていた。
- **型生成ツール**: 000-pre-adr.md §13 / §17 では `openapi-typescript` による型のみの自動生成を前提としていた。

これらは Phase A 終了時点での暫定方針であり、Phase B-1 の実装過程で「将来の負債を先回りして潰す」観点から複数項目を再決定した。本 ADR はその決定事項を集約する。

集約しない場合、以下の問題が想定される。

- Phase B-2 以降のセッションで、各前提が依然有効か都度ソースから判断する必要が生じる。
- 000-pre-adr.md / 001-phase-a-revisions.md の記述と実装の差異が顕在化し、Phase 2 のクラウド移行時に手戻りとなる可能性がある。
- 後続作業（frontend の `make gen` 切替、jacket upload 実装等）で前提を読み違える。

---

## 2. Decision

### 2.1 PostgreSQL 16 を Phase B 開始時点で採用（SQLite 計画を破棄）

[000-pre-adr.md](./000-pre-adr.md) §13 / §14 の「MVP は SQLite」を撤回し、Phase B-1 開始時点から **PostgreSQL 16 (alpine)** を採用する。

- docker-compose に `db` サービスを追加し、named volume `jazz-pgdata` で永続化する。
- 同インスタンス内に `jazz`（dev）と `jazz_test`（test）の 2 データベースを initdb script (`app/db/init/01-create-test-db.sql`) で分離する。
- 接続には `psycopg[binary]` 3.x（同期）を使用する。

#### 採用理由

- `vinyl_records.id` に UUID v7 を採用する（§2.3）。SQLite でも理論上は可能だが、Postgres の `uuid` 型 / `gen_random_uuid()` 互換のエコシステムに乗る方が将来の拡張で齟齬が出ない。
- Phase 2 のクラウドデプロイでも Postgres を継続使用する想定であり、開発と本番の境界条件（trailing whitespace の比較、case sensitivity、トランザクション分離レベル等）を初期から揃える方が、後段のデバッグコストが小さい。
- Postgres の `pg_advisory_xact_lock` を `display_order` 採番のシリアライズに使用する（§2.5）。SQLite では同等の機構が存在しない。
- ローカル開発でも実 DB が立ち上がるコストは Docker により隠蔽されており、SQLite との優位差は小さい。

### 2.2 3 層クリーンアーキテクチャ

[000-pre-adr.md](./000-pre-adr.md) にはバックエンド内部のモジュール構造に関する規定がなかった。Phase B-1 で以下の 3 層構造を採用する。

```
app/backend/app/
├── core/
│   ├── db.py                    # engine / get_session
│   ├── exceptions.py            # DomainError / NotFoundError
│   └── repositories/            # DB アクセス層（SQLModel exec、col() スタイル）
├── services/                    # ビジネスロジック層（採番 / 部分更新 / DomainError raise）
├── schemas/                     # Pydantic API DTO（Read / Create / Update 分離）
├── models/                      # SQLModel ORM
└── routers/                     # FastAPI 薄い API 層（DTO ↔ service 変換、http_errors マッピング）
```

#### 採用理由および規約

- 依存方向は `routers → services → repositories → models` の一方向に固定する。逆方向の import は禁ずる。
- 例外マッピングは routers 層の `http_errors()` context manager に集約する。service が `NotFoundError` を raise すれば 404 に、追加の DomainError サブクラスを定義すれば対応する HTTP ステータスへマップする運用とする。
- 依存性注入は FastAPI の `Depends` チェーンで構築する（`get_session → get_*_repository → get_*_service`）。同一リクエスト内で `get_session` がキャッシュされるため、複数 repository が同じ session を共有する。
- API DTO は `*Read` / `*Create` / `*Update` に分離する。`*Update` は全フィールド optional とし、§2.4 の部分更新セマンティクスを支える。

### 2.3 vinyl_records.id を UUID v7 に変更

[000-pre-adr.md](./000-pre-adr.md) §12 の「`id: int`（auto increment）」および [001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.3 の「サーバ側 auto-increment に統一する」を撤回し、**UUID v7** を採用する。

- 生成は backend 側で行う（`uuid6` ライブラリの `uuid7()`）。クライアント生成は将来 offline 編集対応を入れるときに検討する。
- artists 系（`artists.spotify_id`, `concerts.id` 等）は文字列 PK のままとする。本決定は `vinyl_records.id` および将来の純粋アプリ内エンティティに限定する。

#### 採用理由

- UUID v7 は時刻順にソート可能であり、`display_order` を介さない一覧でも安定した並びを得られる。
- マルチクライアント・将来の同期機能を見据えた採番衝突回避。
- BIGINT auto-increment と異なり、id を URL に含めても序数が露出しない（個人用アプリでは弱い理由だが、副次的メリット）。

#### 既知の留意点

- 開発時の URL コピペ・curl 動作確認では int に比べて煩雑となる。Phase B-1 の `.claude/settings.json` allowlist にはダミー UUID（`00000000-0000-7000-8000-000000000000`）を含めて対応した。

### 2.4 PUT の寛容セマンティクス（部分更新）

[001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.3 の「PUT body は `VinylRecord` 全体」を撤回し、**送られたフィールドのみ更新する部分更新セマンティクス** を採用する。

- Pydantic の `model_dump(exclude_unset=True)` により「明示的に送られたフィールド」のみを抽出する。
- `null` を明示的に送れば null へクリアできる。送らなければ従前の値を保持する。
- `updated_at` はサーバ側で常に上書きする。`created_at` は不変。
- `artist_id` の張り替えは許容するが、新 `artist_id` の存在検証を行い、未存在なら `NotFoundError` を raise する（404）。

#### 採用理由

- フロントエンドの編集モーダルが「変更したフィールドだけ送る」設計と自然に整合する。
- HTTP セマンティクス的には PATCH が厳密だが、本 API は単一クライアント前提・冪等性も担保されるため、PUT の寛容運用とした。RFC 7396 (JSON Merge Patch) に準拠した PATCH への移行余地は残す。

### 2.5 display_order 採番のシリアライズ（pg_advisory_xact_lock 採用）

[000-pre-adr.md](./000-pre-adr.md) §12 の「新規追加は `display_order = MAX + 1`」のレース条件対策として、`pg_advisory_xact_lock` を service 層の create 経路で取得する。

```python
# RecordRepository
def lock_for_display_order(self) -> None:
    self.session.execute(
        text("SELECT pg_advisory_xact_lock(:k)"),
        {"k": self._DISPLAY_ORDER_LOCK_KEY},
    )
```

#### 不採用案

- **`SELECT max(display_order) ... FOR UPDATE`**: Postgres は aggregate に対する FOR UPDATE を構文エラーで拒否する。
- **`SELECT ... ORDER BY display_order DESC LIMIT 1 FOR UPDATE`**: READ COMMITTED 分離下で、ロック解放後に「元クエリで選ばれていた行（旧 MAX）」を再ロックする挙動となる。新たに COMMIT された MAX 行を読み直さないため、後発トランザクションが旧 MAX の `+1` を採番してしまい、回帰テストで重複が発生した。

#### advisory lock 採用の利点

- transaction-scoped であり COMMIT / ROLLBACK で自動解放される。
- 空テーブルでも有効（FOR UPDATE 系はロック対象行が無いため空テーブル時にレースが残る）。
- aggregate query (`SELECT max(...)`) をそのまま使える。

#### キー定数

`0x1A22_DE51_0001`（任意の固定値）を使用する。将来、別箇所で advisory lock を導入する際は衝突回避のため定数集約を検討する（現時点では単独使用）。

### 2.6 Alembic を Phase B-1 から導入

[000-pre-adr.md](./000-pre-adr.md) §16 Phase C-4 の「Alembic 導入 + 初期マイグレーション生成」を Phase B-1 に前倒しする。

- `app/backend/migrations/` に Alembic 環境を配置する。
- migration ファイル名は `alembic.ini` の `file_template` で `YYYYMMDD_HHMM_<slug>` 形式に固定する。
- 初期マイグレーション (`0001_initial`) で全 8 テーブル（artists / artist_aliases / venues / concerts / concert_artists / releases / vinyl_records / sync_status）を一括定義する。`releases.read_at` / `concerts.read_at`（[001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.2）も含む。
- コンテナ起動時の `entrypoint.sh` で `alembic upgrade head` を実行してから uvicorn を起動する。

#### 採用理由

- Postgres 採用と同時に複数テーブルを定義する都合上、`SQLModel.metadata.create_all()` 運用では本番との差が出やすい。
- CI で `alembic upgrade head` を走らせる前提が整うため、後続 PR でスキーマ変更が安全に追跡できる。

### 2.7 型生成ツールチェーン: openapi-typescript → orval

[000-pre-adr.md](./000-pre-adr.md) §4 / §13 / §16 の `make gen` における **`openapi-typescript`** を、Phase B-2 frontend 接続のタイミングで **`orval`** に置き換える。

#### 採用理由

- `openapi-typescript` は型スキーマのみを生成する。React Query (TanStack Query v5) の `useQuery` / `useMutation` hooks および fetch wrapper はすべて手書きとなる。
- `orval` は **型 + HTTP client + React Query hooks** を一括生成する。mutation 後の `queryClient.invalidateQueries` を type-safe に記述でき、API 変更時の追従漏れが型エラーで検出される。
- spec 変更からフロント実装への伝播経路が短縮される。

#### 採用設定

- **client mode**: `react-query` + 純粋 `fetch`（axios 依存を追加しない）
- **output mode**: `tags-split`（FastAPI の tag 別にディレクトリを分割）
- **生成先**: `app/frontend/src/api/generated/`（`gitignore` しない）
- **mock 生成**: 当 ADR では採用しない。orval の msw 連携機能は Phase 2 候補とする（§2.8 と整合）。

#### Phase B-2 への段階的移行

frontend 側の置換は backend と独立した PR として扱う。

- **PR-A（型基盤）**: orval 導入、`make gen` 差し替え、**既実装エンドポイント (artists / records) の型のみ generated 由来に切替**（未実装の releases / concerts / sync_status / auth は `types/api.ts` に手書きで残す）、モック JSON の id を UUID 文字列化。OpenAPI spec は `app/backend/openapi.json` に backend が所有する形でコミットし、frontend は orval から `../backend/openapi.json` を読む。これにより API 変更の差分が backend PR 内で完結し、frontend PR には混入しない。backend 未起動でも `make gen` / CI が走る構成は変わらない。挙動は `VITE_USE_MOCK=true` のまま据え置き。
- **PR-B（実 API 接続）**: `upsertVinylRecord` を `createVinylRecord` (POST) / `updateVinylRecord` (PUT) に分解、`.env.example` の `VITE_USE_MOCK` を `false` に切替、ブラウザでの golden path 動作確認。

### 2.8 モック切替機構の維持

[000-pre-adr.md](./000-pre-adr.md) §4 の「`VITE_USE_MOCK` による mock / 実 API 切替」を Phase B-2 以降も維持する。

- `client.ts` に相当する分岐レイヤーを残し、orval が生成した実 API hooks と、既存の `mocks/*.json` を上層で出し分ける。
- orval 生成 hooks は実 API 経路のみを担う。mock 経路は `if (USE_MOCK)` のままとする。
- 当面は手書きの mock JSON を維持する。orval msw 機能（spec から msw handler を自動生成）は Phase 2 候補。

#### 採用理由

- backend 未起動でも frontend を触れる開発体験を残す。
- backend 障害時のフォールバック確認に使える。
- 完全削除は「モック前提のドキュメントを大量に書き換える」コストが大きく、便益に見合わない。

### 2.9 テスト戦略（unit / integration マトリクス）

CI (`.github/workflows/backend.yml`) で 3 ジョブを並走させる。

- **lint-and-typecheck**: `ruff format --check` + `ruff check` + `mypy app`
- **test (unit)**: `pytest tests/unit -v`
- **test (integration)**: `pytest tests/integration -v`

#### 採用方針

- どちらの suite も実 PostgreSQL（GitHub Actions services container）を使用する。`tests/unit` も service 層を実 DB で叩くため、厳密な意味での unit ではない（純粋 mock-based unit との区別は維持しないコスト判断）。
- conftest で `app.dependency_overrides[get_session]` によりテスト session を注入する。
- `TestClient(app)` を `with` 構文 **無し** で構築することで FastAPI の lifespan を発火させず、dev DB への seed 投入を抑止する。
- engine fixture は function-scoped で `drop_all → create_all → drop_all`。テスト数の増加に伴い遅くなり始めたら session-scoped + `TRUNCATE ... CASCADE` への移行を検討する。

---

## 3. Out of scope

以下の項目は本 ADR では扱わず、後続 PR / ADR に委ねる。

- **frontend の orval 移行実装**: §2.7 の方針に従い PR-A / PR-B として独立に実装する。
- **jacket 画像アップロード API 実装**: [001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.4 の仕様に従い Phase B-2 で実装する。
- **`PATCH /api/records/reorder`**: ドラッグ&ドロップ並び替えの bulk update。Phase B-2 で実装する。
- **releases / concerts API 実装**: Phase B-2 以降。
- **既読 API 実装**: [001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.2 の仕様に従い後続 PR で実装する。
- **Spotify OAuth / 新譜バッチ**: Phase B-3 以降。
- **AI 補完** (`POST /api/records/lookup`): [000-pre-adr.md](./000-pre-adr.md) §19.2。
- **マルチユーザ化**: 当面単一ユーザ前提を維持する。

---

## 4. Consequences

### Positive

- Phase 2 のクラウド移行時に DB エンジンの切替が不要となり、本番との挙動差を初期から潰せる。
- UUID v7 採用により、将来のマルチクライアント対応・分散シナリオで採番衝突を回避できる。
- 3 層分離により service / repository の単体テストが組みやすく、`http_errors()` 経由で例外マッピングが集約される。
- orval 採用により mutation の cache invalidation を type-safe に記述でき、spec 変更時の frontend 追従漏れが型エラーで検出される。
- Alembic 早期導入により、Phase B-2 以降のスキーマ変更を YYYYMMDD_HHMM_<slug> 形式で安全に追跡できる。

### Negative / 留意事項

- docker compose の必須サービスが db 1 個増え、起動コストおよびメモリ使用量が上がる（個人開発では許容）。
- UUID v7 は curl での動作確認・URL コピペが int 比で煩雑となる。`.claude/settings.json` allowlist にダミー UUID を登録する運用で対応する。
- orval 生成コードの量が増える（`gitignore` はしない）。生成物の差分は PR レビュー対象に含める。
- advisory lock のキー定数 `0x1A22_DE51_0001` はマジックナンバーであり、将来別箇所で advisory lock を導入する際は集約管理を検討する必要がある。
- [000-pre-adr.md](./000-pre-adr.md) §12 / §13 / §14 / §16 および [001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.3 の関連記述は本 ADR で supersede される。原典の修正は行わず、本 ADR を参照される正規ソースとして扱う。

---

## 5. Supersede notes（差し替えの対応関係）

| 原典 | 該当箇所 | 旧方針 | 新方針（本 ADR） |
|---|---|---|---|
| [000-pre-adr.md](./000-pre-adr.md) | §12 vinyl_records | `id: int`（auto increment） | UUID v7（§2.3） |
| [000-pre-adr.md](./000-pre-adr.md) | §13 / §14 | DB は SQLite、Phase 2 で Postgres 移行 | PostgreSQL 16 を Phase B-1 から採用（§2.1） |
| [000-pre-adr.md](./000-pre-adr.md) | §12 / §16 C-4 | `create_all()` 運用、Phase C-4 で Alembic 導入 | Phase B-1 から Alembic 運用（§2.6） |
| [000-pre-adr.md](./000-pre-adr.md) | §4 / §13 / §16 | `make gen` は `openapi-typescript` | `make gen` は `orval`（react-query + fetch mode）（§2.7） |
| [001-phase-a-revisions.md](./001-phase-a-revisions.md) | §2.3 id 採番 | サーバ側 auto-increment | サーバ側 UUID v7（§2.3） |
| [001-phase-a-revisions.md](./001-phase-a-revisions.md) | §2.3 PUT body | `VinylRecord` 全体 | 部分更新セマンティクス（`exclude_unset`）（§2.4） |

---

## 6. Phase B-2 実装チェックリスト

本 ADR から派生する Phase B-2 の作業項目を以下にまとめる。

### frontend: orval 導入と型置換（PR-A）

- [ ] `app/frontend` に `orval` を devDependency として追加（`openapi-typescript` は削除）
- [ ] `orval.config.ts` を作成（input: `../backend/openapi.json`、client: `react-query`、httpClient: `fetch`、output mode: `tags-split`、output path: `src/api/generated/`）
- [ ] OpenAPI spec を `app/backend/openapi.json` にコミットする（backend が所有。jq で 2-space indent に整形）
- [ ] `app/Makefile` に `make spec`（backend から spec を再取得）と `make gen`（spec ファイルから生成）を分離
- [ ] orval 用カスタム mutator (`src/api/mutator.ts`) を実装し、`API_BASE` を env から取って fetch する
- [ ] `src/types/api.ts` から既実装分（`Artist` / `VinylRecord`）を削除し、generated/ から re-export する形に縮小（未実装の `Release` / `Concert` / `SyncStatus` / `AuthUser` 等は手書きのまま残す）
- [ ] `src/api/mocks/*.json` の `id` を UUID 文字列化（vinyl_records）
- [ ] `src/api/mocks/*.json` に `source` / `purchase_currency` フィールドを補完（実 API レスポンスと shape を一致させる）
- [ ] `RecordFormModal` の `Date.now()` 採番を `crypto.randomUUID()` に変更（VinylRecord.id が string 化したため）
- [ ] `client.ts` の `VITE_USE_MOCK` 分岐は維持（実 API 側のみ orval 生成 fetcher を経由）
- [ ] `npm run typecheck` が green

### frontend: home の実 API 接続（PR-B）

- [ ] `upsertVinylRecord` を `createVinylRecord` (POST) / `updateVinylRecord` (PUT) に分解
- [ ] `RecordFormModal` の保存ロジックを「新規 → create、編集 → update」で振り分け
- [ ] `app/.env.example` の `VITE_USE_MOCK` を `false` に変更
- [ ] `make up` でスタックを起動し、ブラウザでレコードの一覧 / 追加 / 編集の golden path を確認
- [ ] react-query の cache invalidation が正しく走り、追加・編集後に一覧が更新されることを確認
- [ ] エラーケース（不正な日付、存在しない artist、422 / 404 レスポンス）の UI 挙動を確認

### backend / docs（Out of scope の準備、別 PR で順次）

- [ ] jacket upload API 実装（[001-phase-a-revisions.md](./001-phase-a-revisions.md) §2.4 の仕様）
- [ ] `PATCH /api/records/reorder` 実装
- [ ] releases / concerts API 実装
- [ ] 既読 API（`releases.read_at` / `concerts.read_at` の更新）実装
