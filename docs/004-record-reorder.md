# ADR-004: レコードコレクションの DnD 並び替え

**Status**: Proposed | **Date**: 2026-05-13
**Related**: [ADR-000](./000-pre-adr.md) §7 F-H4, [ADR-002](./002-phase-b-decisions.md) §2.5（`pg_advisory_xact_lock` 採用）

---

## 1. Context

ADR-000 §7 F-H4「デフォルト順のドラッグ&ドロップ並び替え（dnd-kit、`PATCH /api/records/reorder` で `display_order` 保存）」が backend / frontend いずれも未着手で残っている。README §開発フェーズ表でも Phase B-3 残タスクとして明記。

現状:

- `@dnd-kit/core` / `@dnd-kit/sortable` は [app/frontend/package.json](../app/frontend/package.json) に依存追加済みだが、コード中の import はゼロ。
- backend には reorder router / service なし。ただし [record_repository.py](../app/backend/app/core/repositories/record_repository.py) に `lock_for_display_order()`（`pg_advisory_xact_lock(0x1A22_DE51_0001)`）と `max_display_order()` が `create` 経路用に整備済み。
- mock の `vinyl_records.json` には `display_order` 1〜11 が既に入っている。
- HomePage は records ≤ 8 件で直接タイル表示、9 件以上で `RecordsAllModal`（"view all"）。

このまま実装に入るのではなく、ADR にスコープと設計判断を固定してから着手する。

---

## 2. Decision

### 2.1 スコープを「default 並び替え 1 機能」に絞る

- ドラッグ&ドロップで `display_order` を更新する経路のみ。
- ADR-000 §7 の「並び替えモード 4 種切替 UI（default / 購入日 / リリース順 / アーティストごと）」は別タスクへ分離。
- DnD を有効にするのは **HomePage の直接タイル表示（records ≤ 8 件）のみ**。`RecordsAllModal`（view all、9 件以上の経路）は表示専用のまま、DnD 無効。

理由: 4 モード切替を一括で入れると UI 側の状態管理が増え、レビュー単位が肥大化する。最小ユニットで「並びが永続化される」体験だけ先に閉じる。

### 2.2 API は全件 ids 配列で全置換

- `PATCH /api/records/reorder` の body は `{ ids: list[UUID] }`。
- DB の全件総数と配列長が一致しなければ 422。集合が一致しなくても 422。配列内重複も 422（pydantic `field_validator`）。
- response は `200 + ListResponse[VinylRecordRead]`。204 ではなく確定値を返すことで、frontend の楽観 cache を確定値で上書きできる。

理由: partial apply は「削除済み id が残っているリクエスト」を許容してしまい、状態が崩れる。422 で frontend 側に再 fetch + revert させるほうが決定論的でテストしやすい。

### 2.3 advisory lock を reorder 側でも取る

- service の `reorder()` 先頭で `repo.lock_for_display_order()` を呼ぶ。`create` と同じキー（`0x1A22_DE51_0001`）。

理由: `create` は `pg_advisory_xact_lock` 下で `MAX + 1` 採番している。reorder が「件数チェック → UPDATE」の間に `create` が走ると、reorder のチェック時点では n 件だったのが UPDATE 直前で n+1 件になり、新規行を上書きしないまま整合が崩れる。同一キーを取れば両者が相互直列化される。

### 2.4 `display_order` の UNIQUE 制約は導入しない

- 現状の `VinylRecord.display_order: int = Field(index=True)`（unique なし）を維持。
- bulk update は **単純な 1-pass の個別 UPDATE ループ**で実装する。中間状態の重複は DB 上許容される。

理由: UNIQUE を入れると bulk update を 2-pass（一旦負数オフセットに退避→正値へ）にするか DEFERRABLE 制約が必要になり、コストに見合わない。

### 2.5 wanted record は末尾固定で送る

- backend は DB 全件の ids を期待するが、UI でドラッグできるのは Home に出る owned record のみ。
- HomePage 側で `status='wanted'` の record を元の display_order 順のまま末尾に詰めて API に渡す pragma で回避する。

理由: 現状 wanted を生成する API（`from-release`）が未実装で実害はゼロ。将来 wanted 生成が入った時点で、API シグネチャを `{ status: "owned", ids: [...] }` のような status filter 付きに進化させるか再検討する（TBD、§5）。

### 2.6 楽観更新は snapshot revert 方式

- `useMutation.onMutate` で `queryClient.getQueryData(["records"])` を context に退避 → `setQueryData` で `arrayMove` 結果を反映。
- `onError` で context.snapshot を `setQueryData` で復元。
- `onSettled` で `invalidateQueries({ queryKey: ["records"] })`。

理由: 既存 mutation は楽観更新を一切していないが、DnD はレスポンス待ちで並びが戻ると体感が悪い。reorder のみ例外的に楽観更新する。

### 2.7 フリップとドラッグの排他

- PointerSensor の `activationConstraint: { distance: 8 }` を設定。
- 8px 未満のジェスチャはクリックとして子の `<button onClick>`（フリップ）に流れる。
- 8px 以上のドラッグは dnd-kit が onClick を抑制する。

---

## 3. Specification

### 3.1 API

| Method | Path | Body | Response |
|---|---|---|---|
| PATCH | `/api/records/reorder` | `{ ids: list[UUID] }`（`min_length=1`、重複不可） | `200` + `ListResponse[VinylRecordRead]`（並び替え後の全件、`display_order` 1..N） |

エラー:

| 条件 | HTTP | 検出層 |
|---|---|---|
| 認証なし | 401 | `Depends(get_current_user)` |
| `ids` が空 / 型違い | 422 | pydantic |
| 配列内重複 | 422 | pydantic `field_validator` |
| ids 長 ≠ DB 総件数 | 422 | service（`ReorderMismatchError`） |
| 配列長一致だが集合不一致（未知 id / 不足 id） | 422 | service（`ReorderMismatchError`） |

### 3.2 データモデル

`VinylRecord.display_order` は現状通り `int = Field(index=True)`（nullable=False、unique なし）。スキーマ変更なし、migration 追加なし。

### 3.3 主要コードパターン

**service.reorder（[record_service.py](../app/backend/app/services/record_service.py) に追加）**:

```python
def reorder(self, ids: list[UUID]) -> list[VinylRecord]:
    self.repo.lock_for_display_order()
    total = self.repo.count_all()
    if len(ids) != total:
        raise ReorderMismatchError(f"ids length {len(ids)} != total {total}")
    db_ids = self.repo.list_ids_all()
    req_ids = set(ids)
    unknown = req_ids - db_ids
    missing = db_ids - req_ids
    if unknown or missing:
        raise ReorderMismatchError(
            f"unknown={sorted(map(str, unknown))} missing={sorted(map(str, missing))}"
        )
    id_to_order = {id_: i + 1 for i, id_ in enumerate(ids)}
    self.repo.bulk_reassign_display_order(id_to_order)
    return self.repo.list_all()
```

**repository への追加（[record_repository.py](../app/backend/app/core/repositories/record_repository.py)）**:

- `count_all() -> int`
- `list_ids_all() -> set[UUID]`
- `bulk_reassign_display_order(id_to_order: dict[UUID, int]) -> None`（個別 UPDATE ループ、`updated_at` も同時更新）

**router（[records.py](../app/backend/app/routers/records.py) に追加）**:

```python
@router.patch("/reorder", response_model=ListResponse[VinylRecordRead])
def reorder_records(
    body: RecordReorderRequest,
    service: RecordService = Depends(get_record_service),
    _: User = Depends(get_current_user),
) -> ListResponse[VinylRecordRead]:
    with http_errors():
        rows = service.reorder(body.ids)
        return ListResponse(items=[VinylRecordRead.model_validate(r) for r in rows])
```

`PUT /{id}` より上に置く（人間可読性のため。method が違うので衝突自体はしない）。

**例外マップ（[\_handlers.py](../app/backend/app/routers/_handlers.py)）**:

`http_errors()` の except 節に `ReorderMismatchError → 422` を追加。

### 3.4 frontend の動線

**新規**: [SortableJacketCard.tsx](../app/frontend/src/components/records/SortableJacketCard.tsx)

- `useSortable({ id: record.id })` を呼び、`<div ref={setNodeRef} {...attributes} {...listeners} style={...}>` で既存 [JacketCard](../app/frontend/src/components/records/JacketCard.tsx) をラップする構造。
- JacketCard 自体は変更しない（RecordsAllModal や ArtistDetailModal でも表示専用のまま使うため）。

**変更**: [HomePage.tsx](../app/frontend/src/pages/HomePage.tsx)

- `DndContext` + `SortableContext`（`rectSortingStrategy`）+ `PointerSensor`（`distance: 8`）。
- `dndEnabled = !exceedsPreview && ownedRecords.length > 1` のときだけ Sortable をレンダリング。
- `onDragEnd` で `arrayMove(ownedRecords)` → wanted は元順序のまま末尾固定 → 全件 ids を `reorderMutation.mutate(ids)`。

**変更**: [client.ts](../app/frontend/src/api/client.ts)

- `reorderVinylRecords(ids: string[]): Promise<ListResponse<VinylRecord>>` を追加。
- mock 経路: `mockRecordsStore` を ids 順に並び替え、`display_order` を 1..N、`updated_at` を ISO 文字列で更新。長さ不一致 / 未知 id は `throw` で 422 相当の挙動を模す。
- 実 API 経路: orval 生成の `reorderRecordsApiRecordsReorderPatch({ ids })` を呼ぶ。

---

## 4. Implementation Plan

### 4.1 PR 分割

[CLAUDE.md](../CLAUDE.md) の「backend と frontend を同一 PR で混ぜない」原則に従い、2 PR 推奨。

| PR | 内容 |
|---|---|
| PR-A (backend) | schema / exception / repository / service / router 追加 + integration & unit test 追加 + `app/backend/openapi.json` 更新 |
| PR-B (frontend) | PR-A merge 後に rebase → `npm run gen` → `client.ts` / `SortableJacketCard` / `HomePage.tsx` 実装 |

スコープが小さいので 1 PR 機能完結も許容範囲。1 PR にする場合は PR description で明示。

### 4.2 backend テスト一覧

**integration ([test_records.py](../app/backend/tests/integration/test_records.py))**:

- `test_reorder_happy_path_returns_new_order`
- `test_reorder_persists_across_get`
- `test_reorder_length_mismatch_returns_422`
- `test_reorder_duplicate_ids_returns_422`
- `test_reorder_unknown_id_returns_422`
- `test_reorder_requires_auth`
- `test_reorder_does_not_touch_other_fields`

**unit ([test_record_service.py](../app/backend/tests/unit/test_record_service.py))**:

- `test_reorder_reassigns_display_order_1_to_n`
- `test_reorder_length_mismatch_raises`
- `test_reorder_unknown_id_raises`
- `test_reorder_acquires_advisory_lock_before_count`（`MagicMock(wraps=...)` で呼び出し順序検証）

### 4.3 OpenAPI spec 更新手順

1. backend 実装後、`cd app && make spec` で `app/backend/openapi.json` を再生成してコミット。
2. frontend 側で `cd app/frontend && npm run gen` で `src/api/generated/records/` 配下を再生成してコミット。
3. CI の `openapi-spec-check` ジョブが byte 一致を確認する。

### 4.4 動作確認（手動 golden path）

1. `cd app && make up` でスタック起動。
2. Spotify ログイン。
3. records を 3〜8 件作成（`display_order` が +1 ずつ採番されること）。
4. HomePage で 1 枚目を 3 枚目の位置にドラッグ → 即座に並びが切り替わる（楽観更新）。
5. DevTools Network で `PATCH /api/records/reorder` が 200 + `ListResponse` を返すこと。
6. リロード後も順序が保持される。
7. 短押し（< 8px）で `RecordDetailModal` が開く（フリップとドラッグの排他）。
8. 9 件目を追加 → `exceedsPreview` に切り替わり view all 表示。`RecordsAllModal` を開いてもドラッグ不可。

---

## 5. Out of scope / TBD

- 4 並び替えモード切替 UI（default / 購入日 / リリース順 / アーティストごと）は別 ADR / 別タスク。
- `RecordsAllModal` 内での DnD は今回見送り。4 モード切替と合わせて検討。
- `display_order` UNIQUE 制約導入は不要と判断。導入する場合は `bulk_reassign_display_order` を 2-pass（負数オフセット）に変更。
- 将来 `from-release` API で wanted record が生成されるようになったら、reorder API のスコープを `{ status: "owned", ids: [...] }` に進化させるか再検討。今は wanted を末尾に詰める pragma で回避。

---

## 6. Consequences

### Positive

- ADR-000 §7 F-H4 の長期残課題が閉じる。
- backend 側は既存の advisory lock 機構に乗るだけで実装でき、create 経路との整合が保たれる。
- 楽観更新パターンが reorder 経由でプロジェクト初導入され、後続の mutation でも転用できる。

### Negative / 留意事項

- wanted record の末尾固定 pragma は将来 `from-release` API 導入時に再設計が必要（§5）。
- 楽観更新 + 422 revert の経路がテストしにくい（手動確認に依存する部分が残る）。
- `display_order` 非 UNIQUE のままなので、将来「同 display_order 行が複数」になるバグが入っても DB 制約では捕まらない。テストでカバーする。
