# ADR-015: ピンの auto-pin 化 / 上限 6 / view all owned-only

> **Summary (English).** Lowers the pin limit from 8 to 6 (matching the mobile Home preview) in both backend and mock; auto-pins a record the moment it becomes owned (creation with `status=owned`, or a wanted → owned transition) if a slot is free — never on ordinary edits and never for wanted records; and makes "view all" owned-only via a status filter so counts and pagination exclude wanted records. When the shelf is full, the add form shows an inline hint that the new record will not appear on Home. The backend is the source of truth; no API shape change.
>
> *The body of this document is in Japanese. See [docs/README.md](./README.md) for the index of all design documents.*

**Status**: Accepted | **Date**: 2026-05-30
**Related**: [ADR-014](./014-record-pin-ui-relocation.md)（ピン UI を詳細モーダルへ移設・Home = ピン済み owned ショーケース）, [ADR-013](./013-digging-tab-and-concert-removal.md) §2.2（records 既定ソート `is_pinned DESC, pin_order ASC NULLS LAST, display_order ASC`）, UI 設計原則（Home = 所有のショーケース。ADR-990、未公開）
**Supersedes**: [ADR-014](./014-record-pin-ui-relocation.md) §2.2 のピン上限 8 → **6**

---

## 1. Context

[ADR-014](./014-record-pin-ui-relocation.md) でピンは「Home に showcase する owned を選ぶ明示スイッチ」になり、Home はピン済み owned のみを表示する設計になった。運用してみて 2 点の課題が出た。

1. **手動ピンの手間**: レコードを登録するたびに詳細モーダルを開いて ★ を押さないと Home に出ない。モバイルでは特に煩雑で、「棚に追加したのに Home に出ない」状態が初期体験を損ねていた。
2. **view all に wanted が混入**: Home の view all（`RecordsAllModal` の `PaginatedBody`）が `status` 絞り込みなしで `GET /api/records` を叩いており、wanted レコードまで表示し件数・ページ数も全件で算出していた。Home / view all は所有のショーケース（owned のみ）であるべき（UI 設計原則）。

加えて、ピン枠は「ひと目で見せる棚」であり、モバイルの Home プレビュー枚数（6）に上限を合わせるのが自然と判断した。

---

## 2. Decision

### 2.1 ピン上限を 6 に統一

- `_PIN_LIMIT`（backend `record_service`）/ `MOCK_PIN_LIMIT`（frontend mock）を **8 → 6** に変更し、back / front で統一する。
- モバイルの Home プレビュー枚数（`HOME_MOBILE_PREVIEW_LIMIT = 6`）と一致させ、「棚 = ピンした 6 枚」を明確にする。PC の `HOME_PREVIEW_LIMIT`(8) は据え置き（枠だけ広いが実ピンは 6 まで）。

### 2.2 auto-pin（owned になった瞬間のみ）

- レコードが **owned になった瞬間**、ピン枠に空き（pin 済み < 6）があれば**自動でピン**する。発火点は 2 つ:
  - **新規作成**で `status=owned`
  - **wanted→owned 遷移**（`update_partial`）
- owned レコードの**通常編集では発火しない**（ユーザが明示的に unpin したものを、無関係な編集で復活させない）。同一リクエストで `is_pinned` を明示指定している場合もユーザ意図を優先し auto-pin しない。
- 採番は手動ピンと同じ `pin_order = max+1`（末尾）。`pinned_at` も now() をセット。
- **delete 時の棚補充はしない**。空いた枠は次に owned 化したレコードが埋める。
- wanted レコードは auto-pin の対象外（Home は owned のみのため）。
- 実装は `RecordService._auto_pin_if_room(collection, user_id)` に集約し、`create()`（add の前）と `update_partial()`（wanted→owned 判定の後）から呼ぶ。手動ピンの上限 enforce（False→True 遷移で 6 超過なら 409）は従来どおり維持。

### 2.3 view all を owned のみに

- `getVinylRecords(limit?, offset?, status?)` に `status` 引数を追加。`RecordsAllModal` に `statusFilter` prop を足し、Home からは `statusFilter="owned"` を渡す。items も `total`（ページ数）も owned のみで算出する。
- 並び順は backend 既定ソート（[ADR-013](./013-digging-tab-and-concert-removal.md) §2.2）のまま。`status=owned` 絞り込みでも `sort` は None なのでピン優先順は維持される。

### 2.4 上限到達の通知 UI

- 6 件ピン済みの状態で**新規 owned レコードを追加**しようとすると auto-pin されない（Home に出ない）。これを暗黙にせず、`RecordFormModal` の add モードで「ピン枠が満杯（6）なので Home には出ない／view all から入れ替える」旨の**インラインヒント**を保存前に表示する。

---

## 3. Consequences

- **backend が source of truth**。`GET /api/records` のレスポンス shape は不変（`status` クエリは既存）で、`openapi.json` / orval 再生成は不要。
- frontend は mock パリティを維持（`client.ts` の mock create/update にも auto-pin を反映）。
- auto-pin により、テストで「未ピン状態から手動ピンする」挙動を検証する場合は、owned だと作成時に auto-pin されてしまうため `status="wanted"` で作って初期状態を未ピンに固定する（`test_record_service.py` / `test_records.py` の pin 系テストはこの方針で更新済み）。
- ピンの本質（[ADR-014](./014-record-pin-ui-relocation.md)）は不変: ユーザは依然として詳細モーダルの ★ で手動 unpin / 別レコードへの差し替えができる。auto-pin は「枠が空いている間の初期表示を省力化する」だけで、満杯後は手動キュレーションに委ねる。
- ピン並び替えエンドポイント（`PUT /api/records/pins/order`）は引き続き dormant（[ADR-014](./014-record-pin-ui-relocation.md) §3）。
