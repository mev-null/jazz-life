/**
 * venue_id (snake_case のスラグ) を表示用文字列に変換する。
 * 例: "blue_note_tokyo" → "blue note tokyo"
 *
 * Phase B 以降で venues テーブルが入ったら、ID から正式名を引く lookup に差し替える想定。
 */
export function formatVenue(venueId: string): string {
  return venueId.replace(/_/g, " ");
}
