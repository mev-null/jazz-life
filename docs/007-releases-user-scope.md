# ADR-007: releases を catalog + release_read_states に分離 + 配信スコープを follow でフィルタ

**Status**: Proposed | **Date**: 2026-05-13
**Related**: [ADR-001](./001-phase-a-revisions.md) §2.2（元案の feed_read_state）, [ADR-003](./003-artist-management.md) §1.2 原則 1 / 7（主従の反転、物質性の度合いがメモの粒度を決める）, [ADR-005](./005-railway-deploy-prep.md) §2.10（運用ガード）, [ADR-006](./006-records-user-scope-schema.md)（catalog/ownership 2 層分離パターン）

---

## 1. Context

[ADR-005](./005-railway-deploy-prep.md) のデプロイ準備で発覚した「マルチユーザー設計上の単一ユーザー前提」のうち、`vinyl_records` 系は [ADR-006](./006-records-user-scope-schema.md) で解決済み。`releases` 周辺には **2 つの単一ユーザー前提** が残っており、本 ADR で同時に解決する:

1. **既読状態の共有**: `releases.is_read` / `releases.read_at` を直接列で保持しているため、複数 user で既読が共有される。`routers/releases.py` のコメント自身が「単一ユーザだが将来 multi-user 化で current user が要るため最初から固定」と明示。
2. **配信スコープの未分離**: `ReleaseService.list_window` は全 user 共通の releases から期間窓だけでフィルタしている。マルチユーザーでは「current user が follow 中の artist の release **だけ**を返す」必要があるが、現状はそうなっていない。

これら 2 つを併せて解決しないと ADR-005 §2.10 の Spotify Dashboard 招待ガード（複数 user を Dashboard に登録しない運用）が外せない。

---

## 2. Decision

### 2.1 release を catalog と read_state に 2 層分離

```
artists (既存)
   ↑
   │ artist_id
   │
releases (catalog: album メタ情報、Spotify から日次同期)
  - 全 user 間で共有 (1 album = 1 row、Spotify ID で dedup)
   ↑
   │ release_spotify_id
   │
release_read_states (ownership: per-user の既読関係)
  - 行があれば既読、無ければ未読
```

ADR-006 の `vinyl_records` → `user_collections` と同じパターン。

### 2.2 PK と FK

`release_read_states` は `(user_id, release_spotify_id)` 複合 PK、両 FK は `ON DELETE CASCADE`:

- `user_id` → `users.id` ON DELETE CASCADE: user 削除で既読状態も消える
- `release_spotify_id` → `releases.spotify_id` ON DELETE CASCADE: release 削除（catalog cleanup 時）で既読も消える

### 2.3 API 表面は維持

- `GET /api/releases` / `PATCH /api/releases/{spotify_id}/read` の URL とレスポンス shape は **変えない**
- `ReleaseRead.is_read` / `ReleaseRead.read_at` は維持し、Service 層で `release_read_states` を JOIN した結果から計算して埋める
- frontend は orval 再生成で response 型は同一なので 0 変更（ただし mock JSON の整合化のみ必要）

### 2.4 配信スコープを user_follows でフィルタ

`GET /api/releases` は **current user が follow 中（archived_flag=false）の artist の release だけ** を返す:

```sql
SELECT releases.*
FROM releases
JOIN user_follows ON user_follows.artist_id = releases.artist_id
WHERE user_follows.user_id = :user_id
  AND user_follows.archived_flag = false
  AND releases.release_date BETWEEN :from AND :to
ORDER BY releases.release_date DESC
```

`user_follows.archived_flag=false` の参照は [ADR-003](./003-artist-management.md) の `UserFollowRepository.list_artist_ids` と同じ仕様。unfollow した artist の release は自然に Feed から消える。

### 2.5 sync 経路の `is_read` preserve ロジックは不要に

旧 `ReleaseRepository.upsert_many` は `ON CONFLICT DO UPDATE` の SET 句から `is_read` / `read_at` を **意図的に除外** することで sync 再実行時に既読状態を上書きしないよう守っていた。本 ADR 後 `is_read` / `read_at` は別テーブルに移るため、catalog の `upsert_many` は単に metadata だけ更新すれば自動的に既読状態が preserve される（独立テーブルなので触れない）。

### 2.6 feed_read_state 統合案を採用しない理由

[ADR-001](./001-phase-a-revisions.md) §2.2 で示唆されていた `feed_read_state(user_id, kind, item_id, read_at)` 統合テーブル案は採用しない:

- `kind` 値ごとに参照先テーブルが変わるため `item_id` 列に FK を張れず、参照整合性が弱い
- ADR-006 の `vinyl_records` / `user_collections` と同じ 2 層分離パターンに揃えることでコードベースの一貫性が出る
- vision.md §補足「**MVP では過剰な一般化はしない。具体的なものを作りながら抽象を見出す**」と整合
- `concerts` の既読は backend 未実装（localStorage で扱う）なので、将来 concerts catalog が backend に降りる時点で `concert_read_states` を別 ADR で別途起こす方が局所的

---

## 3. Specification

### 3.1 `releases` (catalog) の列

| 列 | 型 | 備考 |
|---|---|---|
| spotify_id | text(64) | PK |
| artist_id | text(64) | FK → artists.spotify_id, ON DELETE CASCADE, INDEX |
| title | text(300) |  |
| album_type | text(20) |  |
| release_date | date | INDEX |
| image_url | text(500) NULL |  |

現状の `releases` から **is_read / read_at** を抜く（および対応する INDEX も DROP）。

### 3.2 `release_read_states` (新規) の列

| 列 | 型 | 備考 |
|---|---|---|
| user_id | UUID | FK → users.id ON DELETE CASCADE, PK, INDEX |
| release_spotify_id | text(64) | FK → releases.spotify_id ON DELETE CASCADE, PK |
| read_at | timestamptz NOT NULL | 既読時刻。行の存在 = 既読 |

### 3.3 Migration プラン

Pre-deploy 前提で**既存 dev データは捨てる** (ADR-006 と同じ方針)。手書き migration を 1 本切る:

1. `DELETE FROM releases`（既存 is_read 込みのデータは破棄）
2. `releases` から `ix_releases_is_read` インデックス DROP、`is_read` / `read_at` 列を DROP
3. `release_read_states` テーブルを CREATE（複合 PK + 2 FK + user_id INDEX）

`release_read_states` には partial INDEX は不要（read_at は NOT NULL なので NULL 判定なし）。

### 3.4 API レイヤの実装方針

- **`ReleaseRepository.list_window_for_user(user_id, from_date, to_date)`**: 旧 `list_window` を置換。`Release JOIN UserFollow ON Release.artist_id = UserFollow.artist_id` + `WHERE UserFollow.user_id = ? AND UserFollow.archived_flag = false` + 期間窓フィルタ + `ORDER BY release_date DESC`
- **`ReleaseRepository.set_read_status` を削除**: 責務を `ReleaseReadStateRepository` に移譲
- **`ReleaseRepository.upsert_many`**: SET 句から `is_read` / `read_at` を除外していた条文を削除し、metadata のみ upsert
- **`ReleaseReadStateRepository.mark_read(user_id, spotify_id)`**: `pg_insert().on_conflict_do_update(set_={read_at: now()})` で upsert
- **`ReleaseReadStateRepository.mark_unread(user_id, spotify_id)`**: 行を DELETE
- **`ReleaseReadStateRepository.list_read_at_map_for_user(user_id, ids)`**: list_window 用に user の既読 read_at を `{spotify_id: datetime}` で一括取得（N+1 回避）
- **`ReleaseService.list_window(user_id, from, to)`**: repo の `list_window_for_user` + read_state map を JOIN して `ReleaseRead` を組み立て
- **`ReleaseService.set_read_status(spotify_id, is_read, user_id)`**: release 存在確認 → mark_read / mark_unread → `ReleaseRead` を返す

### 3.5 影響するテスト

**書き換え**:

- `tests/unit/test_release_service.py`: `test_sync_for_user_upsert_preserves_is_read` を削除し、代わりに `test_sync_does_not_touch_read_states` を追加（独立テーブルなので sync 再実行で既読が消えない事実を test で固定）
- `tests/integration/test_releases.py`: `test_set_read_*` を user_id ベースに、`test_get_releases_returns_within_window_and_sorts_desc` / `test_get_releases_accepts_custom_window` の seed に `UserFollow` 行を追加

**新規**:

- `test_set_read_isolated_between_users`（cross-user 隔離）
- `test_list_releases_returns_is_read_per_user`（同じ release を 2 user で見ると is_read が user 別）
- `test_list_releases_only_followed_artists`（user が follow している artist の release だけ返る）
- `test_list_releases_excludes_archived_follows`（archived な follow の artist の release は返らない）
- `test_list_releases_isolated_between_users`（user A の follow に無い artist の release は A に見えない）

---

## 4. Out of scope

- **concerts の既読 backend 化**: 現状 localStorage、Phase B-4 で concerts catalog が backend に降りる時点で別 ADR で `concert_read_states` を起こす
- **未読件数集計エンドポイント**: ArtistsPage の未読 dot 表示は現状 frontend 側で集計しているので backend に move する場合は別 ADR
- **複数デバイス同期 / リアルタイム更新**: PATCH で逐次 upsert する寛容戦略のみ。WebSocket / SSE は不要
- **release のクリーンアップ**: archived な follow しか紐付かない release を catalog から物理削除する経路は本 ADR では扱わない

---

## 5. Consequences

### Positive

- 既読が user 単位でスコープされ、Dashboard に複数 user を登録しても安全に動く（ADR-005 §2.10 の運用ガードを外す道が開ける）
- 配信スコープ（follow フィルタ）も同時に解決され、user A は user B の興味アーティストの release を見ない
- `ReleaseRepository.upsert_many` の「SET 句から特定列を除外する」preserve ロジックが不要になり、catalog / read_state の責務が明確化
- ADR-006 と同じ 2 層分離パターンが releases にも適用されることでコードベースの一貫性が出る
- Frontend は response shape 維持により 0 変更（orval 再生成で差分は ReleaseRead 周辺で出ない）

### Negative / 留意

- `ReleaseRead` を ORM から `model_validate()` で直に返せなくなり、Service が `_to_read` で手組みする必要がある（ADR-006 と同じパターン）
- 手書き migration が必要（pre-deploy 前提で `DELETE FROM releases` を含む）
- 既存 frontend mock `releases.json` が `is_read` / `read_at` を持っていなかったため、本 ADR を機に整合化する

### Migration リスク

- ADR-006 と同じく pre-deploy 段階でしか「既存データ DELETE」で済む手法を取れない。**本番投入後は本 ADR の migration は使えない**ので、デプロイ前にマージするか、デプロイ後なら別の段階移行プランが必要

---

## 6. Implementation 計画

別 PR で以下の順に実装する:

1. SQLModel: `Release` から `is_read` / `read_at` 削除、`ReleaseReadState` 新規、`models/__init__.py` 更新
2. Alembic migration 手書き（`DELETE FROM releases` → DROP INDEX/COLUMNS → CREATE TABLE `release_read_states`）
3. Repository: `ReleaseReadStateRepository` 新規、`ReleaseRepository.set_read_status` を削除、`list_window` → `list_window_for_user`、`upsert_many` の SET 句整理
4. `ReleaseService` 書き直し（`list_window` / `set_read_status` / `_to_read`）
5. Routers: `routers/releases.py` で `current_user.id` を渡す、`routers/deps.py` に `get_release_read_state_repository` 追加
6. Tests 一通り書き直し（§3.5）
7. `make spec && make gen` で OpenAPI / orval 再生成
8. frontend `api/mocks/releases.json` を `is_read` / `read_at` 入りに整合化
9. `make check` + frontend typecheck pass
10. ADR-007 の Status を `Proposed` → `Accepted` に更新
