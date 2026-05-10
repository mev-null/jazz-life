# 001. Phase A における設計変更の集約

**Status**: Accepted（Phase A 完了時点でのスナップショット）
**Date**: 2026-05-10
**Relates to**: [000-pre-adr.md](./000-pre-adr.md) §4（型契約）, §12（データモデル）, §17（API）, §19（将来拡張）

---

## 1. Context

Phase A のフロントエンドモック実装を進める過程で、UI 仕様の確定に伴いデータモデルおよび API 契約に複数の変更が発生した。これらは個別の意思決定として行われたため、各所に散在する。Phase B（バックエンド実装）の着手前に一箇所へ集約することを本ドキュメントの目的とする。

集約しない場合、以下の問題が想定される。

- Phase B で Pydantic / SQLModel を定義する際、各変更の意図および確定形を都度参照する必要が生じる。
- フロントエンドが期待する API 形式と、バックエンド実装の差異が顕在化するリスクがある。
- 既往の決定事項について再度検討が必要となり、開発速度が低下する。

---

## 2. Decision

### 2.1 VinylRecord スキーマ改訂

[000-pre-adr.md](./000-pre-adr.md) §12 の `vinyl_records` テーブル定義を以下のとおり更新する。

| 変更点 | Before | After | 理由 |
|---|---|---|---|
| 発売年月 | `original_release_year: int \| null` | `original_release_date: string \| null` | 「YYYY-MM」相当の精度で保持する必要が生じた。完全な日付までは要求されないため、部分日付として string で扱う |
| お気に入り曲 | （なし） | `favorite_tracks: string \| null` | 自由記述形式で、レコード裏面に「好きな曲」を残せるようにするため |

`original_release_date` のフォーマットは **"YYYY"** または **"YYYY-MM"** の 2 形式に限定する。バックエンドで正規表現 `^\d{4}(-\d{2})?$` によるバリデーションを行う。

#### 表示対象から除外したが保持するフィールド

| フィールド | UI 上の扱い | データの扱い |
|---|---|---|
| `rating: int?` (1-5) | 表示・入力ともになし | データ型および mock には保持。将来再導入の余地を残す |
| `purchase_price: int?` | 同上 | 同上 |

これらはフロントエンドのフォーム項目から除外しているが、Phase B でも DB スキーマには含める。API レスポンスでは optional / null 既定とする。

#### Phase B における実装イメージ

```python
class VinylRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    artist_id: str = Field(foreign_key="artist.spotify_id")
    spotify_album_id: str | None = None
    title: str
    image_url: str | None = None
    original_release_date: str | None = None  # "YYYY" or "YYYY-MM"
    pressing_info: str | None = None
    purchase_date: date | None = None
    purchase_store: str | None = None
    purchase_price: int | None = None
    rating: int | None = None
    memo: str | None = None
    favorite_tracks: str | None = None
    display_order: int
    created_at: datetime
    updated_at: datetime
```

### 2.2 既読／未読状態の永続化

Feed（releases / concerts）に既読／未読の状態管理を追加する。

- **mock 実装**: localStorage の `jazz-life:read` キーに、`${kind}:${id}` 形式のキーを Set として保存する（[src/lib/useReadState.ts](../app/frontend/src/lib/useReadState.ts) 参照）。
- **キー規約**: `release:{spotify_id}` および `concert:{concert.id}`。
- **挙動**: 行クリックで自動的に既読化し、詳細モーダル内に「mark as unread」操作を提供する。

#### Phase B における DB 設計

単一ユーザ前提を維持する場合は、各テーブルへ `read_at` カラムを追加する方式が軽量である。

```sql
ALTER TABLE releases ADD COLUMN read_at TIMESTAMP NULL;
ALTER TABLE concerts ADD COLUMN read_at TIMESTAMP NULL;
```

将来マルチユーザ化する場合は、別テーブルとして分離する設計に移行する。

```sql
CREATE TABLE feed_read_state (
  user_id INTEGER NOT NULL,
  kind TEXT NOT NULL,           -- 'release' | 'concert'
  item_id TEXT NOT NULL,
  read_at TIMESTAMP NOT NULL,
  PRIMARY KEY (user_id, kind, item_id)
);
```

#### API 形式

以下のいずれかを採用する。実装方針に応じて選択する。

- リソース指向:
  ```
  PUT    /api/feed/{kind}/{id}/read   → read_at = now()
  DELETE /api/feed/{kind}/{id}/read   → read_at = null
  ```
- フラット形式:
  ```
  PUT    /api/feed/read    body: { kind, id, read: bool }
  ```

フロントエンド側は `useReadState` の内部実装を差し替えるのみで、呼び出し側の変更は不要となる。

### 2.3 書き込み API の確定

レコードの追加・更新およびジャケット画像のアップロードを、以下の 2 エンドポイントで扱う。

| 用途 | メソッド | パス | リクエスト | レスポンス |
|---|---|---|---|---|
| レコードの upsert | `PUT` | `/api/records/{id}` | `application/json`, body は VinylRecord 全体 | `VinylRecord` |
| ジャケット画像の差し替え | `PUT` | `/api/records/{id}/jacket` | `multipart/form-data`, field name `file` | `{ image_url: string }` |

`PUT` を upsert として扱う。`id` が既存の場合は更新、新規の場合は作成する。`id` の採番はクライアント側（mock では `Date.now()`）またはサーバ側のいずれでも可とする。

#### フロントエンド呼び出し側

[src/api/client.ts](../app/frontend/src/api/client.ts) に以下の関数を実装済みである。

- `upsertVinylRecord(record): Promise<VinylRecord>`
- `uploadJacket(recordId, file): Promise<{ image_url: string }>`

環境変数 `USE_MOCK` により mock / 実 API を分岐する。Phase B では fetch 実装側が有効化される。

### 2.4 ジャケット画像のストレージ仕様

[000-pre-adr.md](./000-pre-adr.md) §19.1 で「MVP はローカルFS」と決定済みである。本 ADR で具体的なパス規約および処理仕様を確定する。

- **保存先**: `app/data/jackets/{record_id}-{hash}.{ext}`
  - `hash`: ファイル内容の SHA1 先頭 8 文字。同一レコードへの再アップロードでも旧ファイルを上書きせず、未参照ファイルは別途バッチで削除する。
  - `ext`: `jpg` / `jpeg` / `png` / `webp` のいずれかに限定する（バリデーションで他は拒否）。
- **保存処理**:
  - Pillow を用い、受信画像を最大 1000x1000 にリサイズする（アスペクト比は維持）。
  - JPEG として再エンコードする（quality=85）。
- **配信**: FastAPI の `StaticFiles` により `/jackets/*` でホストする。
- **`image_url` の値**:
  - 自前アップロード時: `/jackets/{record_id}-{hash}.jpg`（先頭 `/` の相対パス）。
  - Spotify 同期時: `https://i.scdn.co/image/...`（完全 URL）。
  - フロントエンドは URL の形式によらず `<img src={image_url}>` で表示可能となる。

#### Phase B チェックリスト

- [ ] `app/data/jackets/` ディレクトリの作成（コンテナ起動時の自動生成）
- [ ] FastAPI への `app.mount("/jackets", StaticFiles(directory="data/jackets"))` 追加
- [ ] `PUT /api/records/{id}/jacket` の実装（multipart 受信、Pillow リサイズ、保存、URL 返却）
- [ ] レコード削除時の物理ファイル削除（cascade）の実装

### 2.5 アーティスト画像

`artists.image_url: string \| null` に、Spotify Get Artist API レスポンスの `images[0].url`（最大解像度）を保存する。

- mock では全アーティスト `null` とする。
- フォールバック UI として、頭文字とテーマカラーを用いた円形プレースホルダを実装済み（[src/components/artists/ArtistDetailModal.tsx](../app/frontend/src/components/artists/ArtistDetailModal.tsx) の `ArtistAvatar`）。
- Phase B で同期が稼働した時点で自動的に写真表示へ切り替わり、フロントエンド側の変更は不要となる。

---

## 3. Out of scope

以下の項目は本 ADR では扱わず、別ドキュメントに委ねる。

- **AI 補完** (`POST /api/records/lookup`): [000-pre-adr.md](./000-pre-adr.md) §19.2 を参照。
- **プレス違い管理** (MusicBrainz / Discogs): [000-pre-adr.md](./000-pre-adr.md) §19.3（Phase 2 候補）を参照。
- **マルチユーザ認証**: 当面単一ユーザ前提を維持する。
- **マイグレーション運用**: Alembic 経由とする既定方針（[000-pre-adr.md](./000-pre-adr.md) §11）に従う。

---

## 4. Consequences

### Positive

- Phase B 着手時に、フロントエンドが期待する型・エンドポイント・規約を本ドキュメントから直接参照可能となる。
- `client.ts` における mock / 実 API の切替パターンが確立しているため、`USE_MOCK=false` への切替は backend 立ち上げ時に最小変更で完了する。
- `useReadState` のようなフロントエンド抽象は内部実装の差し替えのみで完結し、呼び出し側に変更は不要となる。

### Negative / 留意事項

- `original_release_date` を string で保持するため、バックエンド側でのフォーマットバリデーションが必須となる。
- 既読状態のスキーマは単一ユーザ前提に最適化している。マルチユーザ化が決定された時点で §2.2 の代替設計（`feed_read_state` テーブル）への移行が必要となる。
- ジャケット画像の物理ファイルは DB と独立して管理されるため、レコード削除時の cascade 削除を実装に含める必要がある。
- mock の `image_url` に blob URL を設定した場合、ページリロードで参照が切れる。Phase B で実 API に切り替わることで解消する。

---

## 5. Phase B 実装チェックリスト

本 ADR から派生する Phase B の実装項目を以下にまとめる。

- [ ] `VinylRecord` SQLModel への `original_release_date` および `favorite_tracks` 追加
- [ ] Pydantic スキーマでの `original_release_date` フォーマットバリデーション
- [ ] `PUT /api/records/{id}` upsert エンドポイントの実装
- [ ] `PUT /api/records/{id}/jacket` multipart エンドポイントの実装（Pillow リサイズを含む）
- [ ] `StaticFiles` による `/jackets/*` の配信設定
- [ ] `releases` および `concerts` への `read_at` 追加と既読 API（PUT/DELETE）の実装
- [ ] `artists.image_url` の Spotify 同期処理
- [ ] `make gen` による `api.generated.ts` の再生成、および手書き型 `types/api.ts` の破棄
