# ADR-017: 棚入れ (owned 化) の迎え入れトースト

> **Summary (English).** When a record becomes owned ("To the shelf": a new owned record or a wanted → owned transition), show a quiet toast at the top of the screen — "Welcome to the collection — your Nth record." — using the existing toast provider and no new libraries. The count is fetched fresh via `GET /api/records?status=owned&limit=1` (`total`) and omitted if unknown, never wrong. Celebrations appear at the top, warnings at the bottom; no automatic navigation. Frontend-only, mock parity kept.
>
> *The body of this document is in Japanese. See [docs/README.md](./README.md) for the index of all design documents.*

**Status**: Accepted | **Date**: 2026-05-30
**Related**: [ADR-015](./015-pin-auto-and-limit.md) §2.2（owned になった瞬間 = 新規 owned 作成 / wanted→owned 遷移。本祝福の発火点と同一面）, UI 設計原則（Home = 所有のショーケース / paper・ink のミニマル世界観。ADR-990、未公開）, [ADR-002](./002-phase-b-decisions.md) §2.8（mock パリティ）

---

## 1. Context

レコードが `owned` になる瞬間（"To the shelf"）は、現状「mutation 成功 → `["records"]` invalidate → モーダル即閉じ」だけで、status フラグの反転以上の意味を持っていなかった。

しかし **レコードを実際に所有するという体験は、ユーザーにとって大きな意味を持つ**。コレクションに一枚を迎え入れる行為は、本アプリの中心体験（Home = 所有のショーケース、UI 設計原則）そのものであり、その瞬間が無反応で過ぎるのは軽すぎる。

検討の過程で「ジャケットに収集印を押す」スタンプ演出も候補に挙がったが、「押す」という能動的な所作は *所有が静かに確定する* 感覚と合わず不採用とした。派手な祝福ではなく、**静かな迎え入れ**を、既存資産の範囲で最小実装する方針とする。

## 2. Decision

### 2.1 owned 化の瞬間に「迎え入れ」トーストを出す

- 既存のトースト基盤（`ToastProvider` / `useToast`, [ADR-015](./015-pin-auto-and-limit.md) で導入）をそのまま流用し、新規 Provider やオーバーレイ・アニメーションライブラリは追加しない（paper/ink・CSS のみの世界観を維持）。
- 発火点は [ADR-015](./015-pin-auto-and-limit.md) §2.2 の auto-pin と **同一面**:
  - **新規作成**で `status=owned`（`status` 未指定＝backend 既定 owned を含む）
  - **wanted→owned 遷移**（詳細モーダルの "To the shelf"）
- どの動線（手動追加 / Release "On the shelf" / 音声認識追加 / wanted 昇格）から来ても **所有は所有として同じ重み**で祝う。これらはすべて `RecordFormModal` の add 分岐か `RecordDetailModal` の `markOwned` に集約されるため、ロジックは小フック `useShelfWelcome()` 1 箇所に集約する。
- **owned の通常編集 / wanted 追加では発火しない**（auto-pin と同じく、所有の確定という事実にのみ反応する）。

### 2.2 コピーは所持枚数を添える

- 既定: `Welcome to the collection — your {N}th record.`（`N` = owned 総数）
- 所持枚数は `["records"]` の invalidate が非同期で確定するのを待たず、`getVinylRecords(1, 0, "owned")` の `total` を `staleTime: 0` で fresh fetch して権威的に取得する（キャッシュ同期読みだと追加前の値になるため）。`total` は `count_for_user` 由来で、Home が `items.filter(status==="owned")` で出す数と一致する。
- 取得に失敗 / `total` 不明な場合は **枚数を伏せて** `Welcome to the collection.` を出す。誤った件数（`your 0th record` 等）は絶対に出さない。

### 2.3 祝事は上・警告は下

- 迎え入れトーストは **画面上部** に出す。ピン上限警告などの既存トーストは従来どおり **下部** のまま。「祝事は上・警告は下」で意味を視覚的に分ける。
- `showToast(message, options?: { position?: "top" | "bottom" })` に拡張（既定 `bottom`）。既存呼び出しは引数なしのまま無変更。上部用に `toast-in-top`（上から降りる）アニメを `index.css` に追加。

### 2.4 自動遷移はしない

- 祝福後に Home へ自動でナビゲートはしない。ユーザーを今いる場所（Hunt list / Release 詳細など）に留め、操作を奪わない。

## 3. Consequences

- **backend 変更なし**。owned 総数は既存 `GET /api/records?status=owned&limit=1` の `total` で賄え、`openapi.json` / orval 再生成は不要。
- frontend のみの変更。mock でも `getVinylRecords(status)` が `total` を返すため mock パリティ（[ADR-002](./002-phase-b-decisions.md) §2.8）を維持。
- トーストは単一インスタンス方式のまま。連続追加（digging セッション等）では最新の一枚の迎え入れが表示され、積まれない。
- アクセシビリティは既存トーストの `aria-live="polite"` をそのまま利用。
- 変更ファイル: `src/hooks/useShelfWelcome.ts`（新規）, `src/components/ToastProvider.tsx`（position 拡張）, `src/index.css`（`toast-in-top`）, `src/components/records/RecordDetailModal.tsx` / `RecordFormModal.tsx`（発火点）。
