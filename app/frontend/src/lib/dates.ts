// 日付関連のフォーマット・パーティション処理を集約する。
// 旧 lib/formatReleaseDate.ts はここに統合した。

const MONTH_NAMES = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/** 当日の日付 (YYYY-MM-DD)。モジュール load 時に確定。 */
export const TODAY_STR = new Date().toISOString().slice(0, 10);

/**
 * 部分日付 ("YYYY" or "YYYY-MM") を表示用文字列に変換する。
 * 例: "1962-01" → "Jan 1962", "1962" → "1962", null/不正値 → "".
 */
export function formatReleaseDate(value: string | null): string {
  if (!value) return "";
  const [yearStr, monthStr] = value.split("-");
  const year = yearStr?.trim();
  if (!year || !/^\d{4}$/.test(year)) return "";
  if (!monthStr) return year;
  const month = parseInt(monthStr, 10);
  if (isNaN(month) || month < 1 || month > 12) return year;
  return `${MONTH_NAMES[month - 1]} ${year}`;
}

/** ISO 日付 (YYYY-MM-DD) を "Jun 12" 形式に整形する。 */
export function formatShortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

/** ISO 日付を "Friday, May 10, 2026" 形式に整形する。 */
export function formatLongDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * 日付文字列を持つアイテム配列を、当日基準で upcoming / past に分割する。
 * - upcoming: 当日以降、昇順（直近が先頭）
 * - past:    当日より前、降順（最近が先頭）
 */
export function partitionByToday<T>(
  items: T[],
  dateOf: (item: T) => string,
): { upcoming: T[]; past: T[] } {
  const upcoming: T[] = [];
  const past: T[] = [];
  for (const item of items) {
    if (dateOf(item) >= TODAY_STR) upcoming.push(item);
    else past.push(item);
  }
  upcoming.sort((a, b) => dateOf(a).localeCompare(dateOf(b)));
  past.sort((a, b) => dateOf(b).localeCompare(dateOf(a)));
  return { upcoming, past };
}
