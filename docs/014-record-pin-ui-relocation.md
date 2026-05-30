# ADR-014: records のピン UI を詳細モーダルへ移設 / view all の並び替えを撤去

**Status**: Accepted | **Date**: 2026-05-30
**Related**: [ADR-013](./013-digging-tab-and-concert-removal.md) §2.2（records の既定ソート `is_pinned DESC, pin_order ASC NULLS LAST, display_order ASC`）, [ADR-000](./000-pre-adr.md) §B-7（vinyl_records 並び替えエンドポイント）, [ADR-990](./990-ui-philosophy.md)（Home = 所有のショーケース）

---

## 1. Context

Home の「view all」モーダル（`RecordsAllModal`、PC 8/page・モバイル 9/page のページネーション一覧）で、ピン UI が 2 つの形でジャケット・グリッドに重なっていた。

1. **各ジャケ右上の ★ トグル / バッジ**。owned レコードの表紙の上に ★ を常時オーバーレイしており、「所有の棚をひと目で見せる」ショーケース（[ADR-990](./990-ui-philosophy.md)）の視覚を損ねていた。
2. **ピン済みレコードのドラッグ&ドロップ並び替え**（`PinDragLayer` / dnd-kit）。Home プレビュー順（最初の 8 枚の並び）を編集する手段だったが、view all の中だけに存在する重い操作で、ジャケットを掴むと drag/click が競合しやすかった。

ピンの本質は「**Home に showcase する owned を選ぶ**」ことであり、これは個々のレコードに対する属性操作。一覧グリッドの上に常時 UI を散らすより、レコードを開いた詳細の文脈で切り替えるほうが情報設計として素直。なお Home プレビュー本体（`JacketCard`）には元々 ★ を出していない（★ 単独では解釈できないため）。

---

## 2. Decision

### 2.1 view all（`RecordsAllModal`）を純粋な閲覧グリッドに戻す

- 各ジャケの **★ トグル（`PinToggleButton`）と表示専用バッジ（`PinBadge`）を撤去**。グリッドはジャケットだけのクリーンな見た目になる。
- **ピン並び替え（drag&drop）を完全撤去**する（`PinDragLayer` / `SortablePinTile` / dnd-kit 依存 / `reorderPins` 呼び出し）。`pinningEnabled` prop も廃止。
- 表示順は backend が返す既定ソート（[ADR-013](./013-digging-tab-and-concert-removal.md) §2.2 の `is_pinned DESC, pin_order ASC NULLS LAST, display_order ASC`）をそのまま尊重する。ピン済みが先頭に固まる挙動は維持されるが、フロントで再ソート・再並べ替えはしない。
- `ArtistDetailModal` 経由の全件表示（`paginated=false` の `StaticBody`）は元々ピン無しのため影響なし。

### 2.2 ピンの ON/OFF トグルを `RecordDetailModal` に集約

- アルバムを 1 回クリックで開く詳細モーダルに ★ トグルを置く。owned のみ表示（`status !== "wanted"`、編集鉛筆と同条件。Home は owned のみ・wanted にピン概念は無い）。
- **配置はジャケット写真に重ねない**。タイトル+写真ヘッダーの下の横線（`border-b`）の下にある**メタ情報セクション（リリース日/プレス情報・memo・Favorites）の右上**に出す。`BackFace` に `footerAction` と同様の `pinToggle` スロットを追加して流し込む。
- トグルは `["records"]` 全クエリを楽観更新するため、ピン/解除は Home に即時反映される。
- ピン上限 **8 枚**は維持（超過は backend 409）。エラーは「ピンは最大 8 枚までです。」をモーダル内メタ右上に表示。

### 2.3 Home はピン済み owned のみを表示する

- `HomePage` のグリッドは **`is_pinned` の owned だけ**を出す（最大 8 枚。backend の `pin_order` 昇順をそのまま使う）。所有はしているが未ピンのレコードは **view all（`RecordsAllModal`）でのみ**参照する。
- これにより Home は「自分で選んだ棚」になり、ピンが Home への載せる/載せないの明示スイッチになる。[ADR-990](./990-ui-philosophy.md) の「Home = 所有のショーケース」を「ピンで厳選したショーケース」に具体化する。
- 状態別の表示:
  - ピン済みあり: ピンの grid（room があれば末尾に追加タイル）。
  - owned はあるがピン 0: 「Home に固定されたレコードがありません。view all から ★ で固定」を促す。view all は owned があれば常時出す。
  - owned 0: 追加導線（prominent な AddRecordTile）。
- ヘッダの件数は所有総数（`ownedRecords.length`）を出す（コレクション規模の指標。実体は view all で全件参照できる）。

---

## 3. Consequences

- **frontend のみの変更**。`GET /api/records` のレスポンス shape・既定ソートは不変で、`openapi.json` / orval 再生成は不要。変更は `RecordsAllModal.tsx` / `JacketCard.tsx` / `RecordDetailModal.tsx` + `HomePage.tsx`（§2.3 の pinned-only 化 + `pinningEnabled` prop 除去）。
- **ピン並び替えエンドポイント（`PUT /api/records/pins/order`）と client の `reorderPins` ラッパーは UI から未使用（dormant）になる**。[ADR-013](./013-digging-tab-and-concert-removal.md) §2.3 の concert モデル温存と同じ方針で、backend と `pin_order` カラムは温存し migration は切らない。並び替え UI を将来別の形で再導入する余地を残す。
- 新規ピンは backend の `pin_order` 採番順に Home へ並ぶ。**ユーザーによる手動の並べ替え手段は当面なし**（必要になれば詳細モーダル or 専用 UI として別途設計）。
- `JacketCard` の `PinBadge` は撤去（dead code 化のため）。`JacketArt` は据え置き。
