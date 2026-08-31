# ADR-013: Feed を Digging に再編（Hunt list 集約 + records の status/sort）/ Concert UI 撤去

> **Summary (English).** Renames the Feed tab to **Digging** with two sub-tabs: **On the hunt** (a cross-artist list of wanted records, sorted A–Z by artist with an index rail, or by date added) and **Releases**. `GET /api/records` gains `status` (`owned` | `wanted`) and `sort` (`artist` | `added`) query parameters; filtering and sorting are backend responsibilities, grouping is presentation. Concert UI is removed entirely from the frontend (backend models are kept, no migration); release read state stays. Supersedes ADR-000's "Feed = releases + concerts" and its 3-tab layout. Motivated by real-world use: wanting a shopping list ordered the way record shops shelve their bins.
>
> *The body of this document is in Japanese. See [docs/README.md](./README.md) for the index of all design documents.*

**Status**: Accepted | **Date**: 2026-05-30
**Related**: [ADR-000](./000-pre-adr.md) §F-F1/F-F2（Feed = 新譜・公演の 2 タブ）, [ADR-003](./003-artist-management.md) §2.1（owned/wanted の意味づけ）, [ADR-006](./006-records-user-scope-schema.md)（records catalog/ownership 2 層分離、response shape 維持）, [ADR-007](./007-releases-user-scope.md) §「concerts の既読 backend 化（Phase B-4）」

---

## 1. Context

実利用の観察から 2 点の不満が顕在化した。

1. **欲しいレコードの横断一覧が無い**。「欲しい」レコード（`user_collections.status = 'wanted'`、UI 名 "On the hunt"）は [ADR-003](./003-artist-management.md) の設計上 `ArtistDetailModal` を開いたときに **アーティスト単位でしか** 見られない。店はアーティスト名で棚分けされているため、「今日この店で探すもの」をアーティスト名アルファベット順で一覧できる買い物リストが欲しい。
2. **Concert の優先度が実際には低い**。[ADR-000](./000-pre-adr.md) は Feed を「新譜タブ + 公演タブ」と規定したが、公演は backend に endpoint が無くフロントのモック駆動のまま運用されており（[ADR-007](./007-releases-user-scope.md) でも concerts の backend 化は Phase B-4 へ先送り）、現状の体験価値が薄い。

情報設計として、コレクションは「**所有 / 未所有**」でまず割れ、未所有側は性質で 2 つに分かれる:

```
Home（所有）          Digging（未所有 = レーダー）           Artists（ソース管理）
所有レコードの棚        [ On the hunt | Releases ]           フォロー管理
                        ・On the hunt = 能動的な狙い (A→Z)
                        ・Releases    = 受動的な新譜流入
```

「新譜で見つける → 欲しいに入れる → 買って所有する」という取得パイプライン（Discover → Want → Own）のうち、Want と Discover は「まだ持っていないが視界に入っているもの」として同じ場所にまとまるのが自然。Own は Home に純粋に残す。

---

## 2. Decision

### 2.1 中央ナビ `Feed` を `Digging` に改名し 2 タブ化

- route `/feed` → `/digging`（`/feed` は後方互換リダイレクト）。`FeedPage` → `DiggingPage`。
- タブは **On the hunt（初期表示） / Releases** の 2 つ。PC・モバイル共通でタブ切替に統一し、従来の PC 2 カラム（Releases | Concerts）/ モバイル統合タイムラインは廃止。
- 名称は記録収集の語彙（crate digging）から `Digging`。wanted の UI 名は既存の "On the hunt" に統一（"Wishlist" は使わない）。
- [ADR-000](./000-pre-adr.md) §F-F1/F-F2 の「Feed = 新譜タブ + 公演タブ」「3 タブ Home/Feed/Artists」を本 ADR で **supersede** する。

### 2.2 On the hunt（Hunt list）= wanted の横断一覧。並び替え/絞り込みは backend 責務

- `GET /api/records` に 2 つの query param を追加する（[ADR-006](./006-records-user-scope-schema.md) の response shape は不変）:
  - `status`: `owned` | `wanted`。指定時に `user_collections.status` で絞り込む。
  - `sort`: `artist`（`artists` を join して name 昇順 → `vinyl_records.title` 昇順）/ `added`（`user_collections.created_at` 降順）。**未指定時は従来の `is_pinned DESC, pin_order ASC NULLS LAST, display_order ASC`**（Home マトリクスの挙動を維持）。
- フロントは backend が返した順序を尊重し、`artist` モードでは **連続する同一アーティストをグループ見出しにまとめる**プレゼンテーションのみ担う（再ソートしない）。`added` モードはフラットリスト。
- `artist` モードでは右端に **A–Z インデックスレール**（旧 iOS Contacts 風）を出し、頭文字グループへスクロールジャンプできる。
- 行ビジュアルは Releases の `ReleaseRow` に揃える（左ガター + 64px ジャケット + title / artist / pressing_info + 右に日付）。右の日付は **"on the hunt" 登録日 = `user_collections.created_at`**。未読概念は持たない。
- 採用理由: 絞り込み/並び替えはクエリの自然な責務であり、Home の owned 一覧が既に backend ソート（pin/display order）である一貫性に合わせる。グループ化（見出し・レール）は純粋な表示都合なので frontend に残す。

### 2.3 Concert を UI から全撤去（backend モデルは温存）

- frontend から concert 関連を削除する: Digging の Concerts 表示、`ArtistDetailModal` の Activity（releases のみに）、Artists 一覧の concert 未読ドット、`ReleaseDetailModal`（旧 `FeedDetailModal`）の concert 分岐、client の `getConcerts`、`concerts.json` モック、`Venue`/`Concert`/`ConcertArtist` 型、`matchArtist`/`formatVenue`/`useReadState`（concert 既読専用だったため）。
- **backend の concert モデル（`venues` / `concerts` / `concert_artists` / `user_concert_attendances`）は温存**し migration は切らない。endpoint は元々無いため API 表面に影響なし。
- Releases の未読機能（[ADR-007](./007-releases-user-scope.md) の `release_read_states` / `is_read`）は **維持**する。
- [ADR-007](./007-releases-user-scope.md) の「concerts の既読 backend 化（Phase B-4）」は当面凍結。場所まわりの設計メモ（未公開）の Feed 参照は Digging（On the hunt / Releases）前提で読み替える。

---

## 3. Consequences

- backend（records の status/sort）+ frontend を **機能完結 1 PR** で出す（開発ガイド [docs/DEVELOPMENT.md](./DEVELOPMENT.md) の「backend と frontend を混ぜない」例外条項、PR description で明示）。`openapi.json` 再生成 + orval 再生成物も同梱。
- Home は変更なし（owned のショーケースとして純粋に保つ）。`status`/`sort` は省略可・後方互換なので既存呼び出し（Home / ArtistDetailModal の records 取得）は不変。
- Concert は将来 [ADR-007](./007-releases-user-scope.md) の方針（catalog を backend に降ろし read_states を別 ADR で起こす）に沿って再導入可能。モデルを温存しているためスキーマの手戻りは発生しない。
- Hunt list の frontend 取得は専用 query key `["records", "wanted", sort]` を使うが、`["records"]` への invalidate が prefix match で波及するため、既存の record mutation でリフレッシュされる。
