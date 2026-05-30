// Home に showcase するピンの上限。モバイルの Home プレビュー枚数に合わせる
// (ADR-015)。backend の `_PIN_LIMIT` と一致させること。auto-pin の枠判定・
// 手動 pin の上限・「満杯」ヒント表示の全てでこの値を使う。
export const PIN_LIMIT = 6;
