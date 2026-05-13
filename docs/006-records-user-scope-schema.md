# ADR-006: records を catalog + user_collections に 2 層分離する

**Status**: Proposed | **Date**: 2026-05-13
**Related**: [ADR-000](./000-pre-adr.md) §F-H2 / §7（裏面メタファー）, [ADR-001](./001-phase-a-revisions.md) §2.1（favorite_tracks の元意図）, [ADR-002](./002-phase-b-decisions.md) §2.1（PostgreSQL 採用）, [ADR-003](./003-artist-management.md) §1.2 原則 7（物質性の度合いがメモの粒度を決める）, [ADR-005](./005-railway-deploy-prep.md) §2.10（運用ガード）

---

## 1. Context

[ADR-005](./005-railway-deploy-prep.md) でデプロイ準備中に判明した致命的問題:

- 現状の `vinyl_records` テーブルは **user_id 列を持たない**。`RecordService.list_all / update_partial / delete` は user で絞らない。
- ADR-005 §2.8 で「invite 制御を Spotify Developer Dashboard の Users and Access に集約」と決めたため、**Dashboard に登録された複数 user は同じ records を共有・改竄できる**状態。
- 単純に `vinyl_records.user_id` を追加するだけでも記録は user-scope できるが、それでは「将来 `record_favorite_tracks` のような per-user 拡張テーブルを増やす」設計余地が狭い。
- ユーザの要望: **album メタ情報と所有関係を 2 層に分離**したい。"Spotify dedup できる catalog" と "user の collection" は責務が違う。将来 `user_collections.id` を FK 先にして per-user の派生テーブル (favorite tracks 等) を生やしたい。

本 ADR の運用ガード (ADR-005 §2.10): Spotify Dashboard に**自分の Spotify アカウントだけ**を登録する。本 ADR の実装が入るまで複数 user 招待を行わない。

---

## 2. Decision

### 2.1 2 層スキーマに分割

```
artists (既存・変更なし)
   ↑
   │ artist_id
   │
vinyl_records (catalog: album メタ情報)
  - source='spotify' の行: spotify_album_id 非 NULL、全 user 間で dedup
  - source='manual'  の行: spotify_album_id NULL、重複可
   ↑
   │ vinyl_record_id
   │
user_collections (ownership: per-user 所有関係)
  - UNIQUE(user_id, vinyl_record_id) で「同じ catalog 行を 2 度所有」を拒否
```

### 2.2 Spotify dedup は partial UNIQUE INDEX で

`vinyl_records.spotify_album_id` には:

```sql
CREATE UNIQUE INDEX uq_vinyl_records_spotify_album_id_not_null
  ON vinyl_records (spotify_album_id)
  WHERE spotify_album_id IS NOT NULL;
```

Postgres の partial UNIQUE INDEX により、

- `source='spotify'` 行 (`spotify_album_id` 非 NULL) は全 user 間で 1 album = 1 row に強制される
- `source='manual'` 行 (`spotify_album_id` NULL) は重複可 (NULL は partial index に入らない)

### 2.3 Manual record は重複許可

同じ手書きタイトル ("Self-Recorded Live 2026-01-15" のような) を異なる user が、あるいは同じ user が複数枚、登録するケースを許す。`manual` 行は `spotify_album_id` を持たないので catalog dedup は効かず、**毎回新しい vinyl_records 行を作る**。

### 2.4 user_collections の二重所有防止

```sql
CREATE UNIQUE INDEX uq_user_collections_user_vinyl_record
  ON user_collections (user_id, vinyl_record_id);
```

これにより、同じ Spotify album を同じ user が 2 回 POST した場合は、catalog が dedup されて 1 つの `vinyl_records.id` に集約された結果、user_collections 側の UNIQUE 違反として 4xx を返せる。

### 2.5 API 表面は完全に維持

- `/api/records` の URL / レスポンス shape は **変えない**
- レスポンスの `id` は **`user_collections.id`** を返す (frontend は無変更で動く)
- POST のリクエスト shape も `VinylRecordCreate` を維持。内部で `spotify_album_id` の有無を見て catalog 分岐
- PUT のフィールド受付も維持。catalog 側 (title / image_url / original_release_date / artist_id) の更新は `source='manual'` 行に限り反映、`source='spotify'` 行は silently ignore（共有メタなので）

### 2.6 Display order は user 単位

`display_order` は `user_collections` 側に持つ。`pg_advisory_xact_lock(k1, k2)` の 2 引数版で `k2 = hash(user_id)` を使い、**user 単位で直列化**する。他 user の POST はブロックされない。

### 2.7 Catalog orphan の扱い

User が user_collections 行を削除した時、`source='manual'` の vinyl_records 行は他 user から参照されない (dedup されないため必ず 1:1) → 実質 orphan になるが、本 ADR ではあえて残す。理由:

- 実害が無い (`/api/records` は user_collections 経由の JOIN なので見えない)
- 後から「やっぱり同じ album を持つ」と再登録した時、UUID は別になるが title 含めユーザ側からはなんら違和感が無い
- 将来クリーンナップを入れたければ service 層に delete-after hook を生やせば足りる

`source='spotify'` 側は catalog なので絶対に物理削除しない。

### 2.8 record_favorite_tracks（本 ADR で実装）

user_collections に紐づく per-user の「お気に入り曲」テーブルを本 ADR の一部として実装する。当初は別 ADR で扱う Future 扱いだったが、レビューで「Spotify 検索結果を 1 曲ずつ追加 + 各曲に短い所感 (`note`) を書く」体験を確定したため本 ADR に取り込む。

```sql
CREATE TABLE record_favorite_tracks (
  user_collection_id UUID NOT NULL REFERENCES user_collections(id) ON DELETE CASCADE,
  position INT NOT NULL,
  spotify_track_id TEXT NULL,        -- Spotify 検索結果由来、manual 時は NULL
  track_name TEXT NOT NULL,
  note TEXT NULL,                    -- track 単位の短い所感（裏ジャケに走り書きしたメモ）
  PRIMARY KEY (user_collection_id, position),
  UNIQUE (user_collection_id, spotify_track_id)
);

CREATE INDEX ix_record_favorite_tracks_spotify_track_id
  ON record_favorite_tracks (spotify_track_id)
  WHERE spotify_track_id IS NOT NULL;
```

採用理由:

- ADR-003 §1.2 原則 7「物質性の度合いがメモの粒度を決める」に照らし、レコードは「フルセット（グラビア）」側に分類されており、track を構造化することは原則と整合する。公演メモが「コラム（自由記述）」側だったのに対し、レコードのお気に入り曲は「グラビア（構造化）」側
- ADR-001 §2.1 の「自由記述形式で『好きな曲』を残す」意図は `note` 列で保持。`user_collections.memo` がアルバム全体への所感（雑誌コラム）、`record_favorite_tracks.note` が曲ごとの走り書き、という二段構成で「ストーリーを書きたくなる UX」（vision.md）を担保
- Spotify からの曲取得は **Get Album Tracks** (`/v1/albums/{album_id}/tracks`) → frontend の checkbox 選択 → 本表に INSERT
- `track_name` を非正規化保持し、`tracks` catalog テーブルは作らない。理由: 現時点で「全 user 横断の人気 track」「Spotify Liked Songs 同期」など catalog 共有が活きる需要が無く、孤児管理を増やさないため。将来必要になれば `spotify_track_id` を partial INDEX 経由で参照しつつ局所 migration で外出し可能（partial INDEX を本 ADR で先んじて貼っているのはこの布石）
- 並び順は `position` 列で持ち、編集時は user_collection 単位で advisory lock すれば足りる（user 全体の display_order ロックとは独立）

### 2.9 Manual → Spotify への promote

User が manual で登録した盤を後から「Spotify にあった」と気付き、`spotify_album_id` を埋め直すフローを許容する。実装フェーズで必ず踏むシナリオなので本 ADR で明文化する。

仕様:

1. `PUT /api/records/{id}` body に `spotify_album_id` を非 NULL で含めた時に発火
2. Service 層で当該 `spotify_album_id` を持つ catalog 行を `SELECT FOR UPDATE` で検索:
   - 既存行なし → 現在の `vinyl_records` 行を UPDATE (`source='manual'` → `'spotify'`、`spotify_album_id` 設定)。partial UNIQUE INDEX が SQL 層で重複を防ぐので冪等性が担保される
   - 既存行あり（他 user が同じ Spotify album を catalog 化済み）→ `user_collections.vinyl_record_id` を既存 catalog 行に付け替え、元の manual catalog 行は §2.7 の orphan として残す
3. `source='spotify'` 行への promote リクエストは silently ignore（既に promote 済み）
4. `record_favorite_tracks` は `user_collection_id` 経由で紐づくため、catalog 行の付け替えがあっても影響なし

Frontend 側は response shape を維持するため変更不要。

---

## 3. Specification

### 3.1 `vinyl_records` (catalog) の列

| 列 | 型 | 備考 |
|---|---|---|
| id | UUID v7 | PK |
| artist_id | text(64) | FK → artists.spotify_id, ON DELETE RESTRICT |
| spotify_album_id | text(64) NULL | partial UNIQUE INDEX `WHERE spotify_album_id IS NOT NULL` |
| source | text(20) | `'spotify'` \| `'manual'` |
| title | text(300) |  |
| image_url | text(500) NULL |  |
| original_release_date | text(10) NULL |  |
| created_at | timestamptz |  |
| updated_at | timestamptz | manual 行の title 修正等で更新 |

現状の `vinyl_records` から **status / purchase_* / rating / memo / favorite_tracks / pressing_info / display_order** を抜く。

### 3.2 `user_collections` (新規) の列

| 列 | 型 | 備考 |
|---|---|---|
| id | UUID v7 | PK |
| user_id | UUID | FK → users.id ON DELETE CASCADE, INDEX |
| vinyl_record_id | UUID | FK → vinyl_records.id ON DELETE CASCADE |
| status | text(20) | `'owned'` \| `'wanted'`、default `'owned'` |
| pressing_info | text(200) NULL | 物理盤の情報 (per-copy) |
| purchase_date | date NULL |  |
| purchase_store | text(200) NULL |  |
| purchase_price | int NULL |  |
| purchase_currency | text(3) | default `'JPY'` |
| rating | int NULL | 1..5 |
| memo | text(2000) NULL | アルバム全体への所感（雑誌コラム / 裏面の手書きノート本文）。曲単位の所感は `record_favorite_tracks.note` で別途持つ |
| display_order | int |  |
| created_at | timestamptz |  |
| updated_at | timestamptz |  |

UNIQUE INDEX `uq_user_collections_user_vinyl_record` on (`user_id`, `vinyl_record_id`)。

### 3.3 Migration プラン

Pre-deploy 前提で**既存 dev データは捨てる**。手書き migration を 1 本切る:

1. `DELETE FROM vinyl_records` (本番には何も投入されていない)
2. `vinyl_records` から不要列を DROP (status / purchase_* / rating / memo / favorite_tracks / pressing_info / display_order)
3. partial UNIQUE INDEX `uq_vinyl_records_spotify_album_id_not_null` を作成
4. `user_collections` テーブルを CREATE (列 + FK + UNIQUE INDEX)
5. インデックス: `ix_user_collections_user_id`、`ix_user_collections_vinyl_record_id`
6. `record_favorite_tracks` テーブルを CREATE (FK + 複合 PRIMARY KEY + UNIQUE INDEX + `spotify_track_id` 非 NULL 限定の partial INDEX)

Alembic autogenerate は partial UNIQUE INDEX の `postgresql_where` で安定しない (差分が毎回出る) ので **手書きで書く**。SQLModel 側の `__table_args__` には対応する `Index(..., postgresql_where=text("..."))` を入れて model と DB を一致させる。

### 3.4 API レイヤの実装方針

- **`RecordService.create(data, user_id)`**:
  - `data.spotify_album_id` が非 NULL → `vinyl_records` を `spotify_album_id` で `SELECT FOR UPDATE` / 無ければ INSERT (find-or-create)
  - NULL → 常に新 `vinyl_records` 行を INSERT
  - 続いて `user_collections` INSERT (`display_order` を advisory lock 下で採番)
  - IntegrityError on `user_collections` UNIQUE → 既存 user_collection を返す or 409 (どちらにするかは PR で決定)
- **`RecordService.list_for_user(user_id)`**: `user_collections` ← LEFT JOIN `vinyl_records` で flat row を作って `VinylRecordRead` に adapt
- **`RecordService.update_partial(id, patch, user_id)`**: `user_collections` を user_id で引いて catalog id を得る。catalog 系フィールド (title / image_url / original_release_date / artist_id) は `source='manual'` のみ書く
- **`RecordService.delete(id, user_id)`**: `user_collections` を物理削除。`record_favorite_tracks` は CASCADE で自動削除、`vinyl_records` は触らない
- **`RecordService.set_favorite_tracks(record_id, tracks, user_id)`**: `user_collections.id` を user_id で引いた上で、`record_favorite_tracks` を当該 collection について全削除 → 新規 INSERT で置換する。`position` は配列順で 0/1 始まりは実装フェーズで決定。同一 collection 内で同じ `spotify_track_id` を 2 回送られた時は UNIQUE 違反として 4xx を返す。新規 API endpoint にするか PUT body に含めるかは別 PR で決定（OpenAPI への影響範囲が違うため）
- **`RecordService.list_for_user`** のレスポンスに `favorite_tracks: list[FavoriteTrack]` を含める（position 昇順）。frontend で N+1 にならないよう、collection 一覧クエリと同じ TX 内でまとめてロードする

### 3.5 影響するテスト

ほぼ全ての records 関連テストが書き換え対象:

- `tests/integration/test_records.py`: 直 INSERT 箇所を「catalog + user_collections」 2 段挿入ヘルパに / cross-user 隔離テストを追加 / Spotify dedup を 2 user で検証 / manual 重複が成功すること / partial UNIQUE 違反は SQL レベルで検証
- `tests/integration/test_releases.py`: `VinylRecord(...)` 直 INSERT を新 2 段挿入に
- `tests/integration/test_user_follows.py`: 同上
- `tests/unit/test_record_service.py`: 全ケース書き直し (create が spotify / manual で分岐、display_order が user 単位、cross-user delete/update が 404)
- `tests/unit/test_release_service.py`: `_seed_record` ヘルパを 2 段挿入に
- `tests/integration/test_records.py` に追加ケース: `record_favorite_tracks` の CRUD（順序保持、cross-user 隔離、同一 collection 内の `spotify_track_id` UNIQUE 違反、user_collection 削除時の CASCADE）
- `tests/unit/test_record_service.py` に追加ケース: `set_favorite_tracks` の全置換ロジック、空配列で全削除、`note` の null 許容、`spotify_track_id` が NULL の manual 行を複数追加できることの確認

---

## 4. Out of scope

- **Jacket upload** (`PUT /api/records/{id}/jacket`): Phase B-3+ で未実装。本 ADR では vinyl_records.image_url を Spotify cover で固定。user 個別の jacket 上書きを許す場合は将来 `user_collections.custom_image_url` 列を追加するか、別テーブルを切る (別 ADR)
- **`source='spotify'` 行の catalog 編集**: ユーザに silently ignore する仕様。明示的に 409 を返す案もあるが UI 変更が必要になるのでスコープ外
- **Manual record の orphan クリーンナップ**: §2.7 の通り当面放置
- **Spotify album の "primary artist" の選定**: 1 album に複数 artist が紐づく compilation 等は既存と同じく `vinyl_records.artist_id` 1 つで表現 (Spotify search の最初の artist を採用)
- **tracks catalog 化**: 「全 user 横断の人気 track」「Spotify Liked Songs 同期」など catalog 共有が活きる需要が出てきた時点で別 ADR を起こす。本 ADR では `record_favorite_tracks` が `track_name` を非正規化保持する形に留める

---

## 5. Consequences

### Positive

- Records が user_id でスコープされ、Dashboard に複数 user を登録しても安全に動く
- Spotify album の dedup により、データ重複が減り将来の release sync / jacket 共有が楽になる
- `user_collections.id` を FK 先にして per-user の派生テーブル (favorite tracks 等) を生やせる土台ができる
- Catalog と ownership の責務が明確になり、edit 仕様の混乱 (誰の title を誰が編集できるか) が解消される
- `record_favorite_tracks` を本 ADR で実装することで、Phase 4（全コレクション全文検索 / タグ横断）で track 単位の検索が将来可能になる
- ADR-000 §F-H2 の「裏面=メモ・購入情報」の手書きノート的メタファーを、`user_collections.memo`（アルバム全体）と `record_favorite_tracks.note`（曲ごと）の二段で維持しつつ、track 単位の構造化を導入できる

### Negative / 留意

- スキーマ変更が大きく、移行 PR は backend のみで `model / repo / service / router / seed / 全 record 関連 test` を一気に書き換える必要がある
- API 表面は維持するが、内部で `_FlatRow` dataclass を 1 段挟むため service 層が少しふくらむ
- `source='spotify'` 行の catalog は全 user で共有されるため、title 修正は他 user にも反映される (本 ADR は silently ignore で逃げる)
- 手書き migration が必要 (autogenerate の partial UNIQUE INDEX が不安定なため)
- Frontend は catalog/ownership 分離部分は 0 変更（response shape を維持）。`record_favorite_tracks` 追加分のみ frontend に新規 UI / 型追記が発生し、orval 差分はその範囲に限定される

### Migration リスク

- Pre-deploy の今しか「既存データ DELETE」で済む手法を取れない。**本番投入後は本 ADR の migration は使えない**ので、デプロイ前にマージするか、デプロイ後なら別の段階移行プランが必要

---

## 6. Implementation 計画

別 PR で以下の順に実装する (本 ADR とは別ブランチ):

1. SQLModel: `VinylRecord` 縮小 + `UserCollection` 新規 + `RecordFavoriteTrack` 新規（`__table_args__` で UNIQUE INDEX / partial INDEX を明示）
2. Alembic migration 手書き (DELETE → DROP COLUMNS → ADD INDEX → CREATE TABLE user_collections → CREATE TABLE record_favorite_tracks)
3. Repository 2 本に分割 (`RecordRepository` を catalog 専用に、`UserCollectionRepository` 新規、`RecordFavoriteTrackRepository` 新規 もしくは `UserCollectionRepository` に内包は実装フェーズで判断)
4. `RecordService` 書き直し (1 TX で catalog → user_collection、favorite_tracks の全置換ロジックを `set_favorite_tracks` メソッドとして同居)
5. Routers: `routers/records.py` は表面据え置きで内部経路だけ差し替え、`routers/user_follows.py` の `count_owned_by_artist_for_user` を新 repo 経由に、`routers/deps.py` の DI 配線を更新。favorite_tracks 用 endpoint の追加 or PUT body 拡張は実装フェーズで決定
6. seed.py / release_service.py の依存差し替え
7. Tests 一通り書き直し (上記 §3.5)
8. `make spec && make gen` で OpenAPI / orval 再生成、差分確認
9. ADR-006 の Status を `Proposed` → `Accepted` に更新
