import { formatShortDate } from "../../lib/dates";
import type { Artist, Release } from "../../types/api";
import { ReleaseJacket } from "./ReleaseJacket";

/**
 * Feed と ArtistDetailModal の Activity セクションで共有する Release 行。
 * 左 64px のジャケット + 右にタイトル / アーティスト / album_type / 日付。
 *
 * 視覚仕様:
 * - 未読 dot は行頭 (ジャケットの左中央脇) に置く。ジャケット右上に重ねると
 *   ジャケ自体が小さい時に画と被って読みにくい
 * - 既読は album 全体を半透明化して未読を相対的に強調する
 * - `isPast` は別軸 (灰色文字) で扱う
 */
export function ReleaseRow({
  release,
  artist,
  isPast,
  isRead,
  onClick,
}: {
  release: Release;
  artist?: Artist;
  isPast: boolean;
  isRead: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full cursor-pointer items-stretch gap-3 py-3 text-left text-sm transition-opacity hover:opacity-80 ${isPast ? "text-ink-mute" : ""} ${isRead ? "opacity-55" : ""}`}
    >
      <span className="flex w-2 shrink-0 items-center justify-center">
        {!isRead && <span className="block h-2 w-2 rounded-full bg-ink/70" />}
      </span>
      <div className="relative aspect-square w-16 shrink-0 overflow-hidden ring-1 ring-ink/10">
        <ReleaseJacket release={release} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col justify-center">
        <div className="truncate font-medium">{release.title}</div>
        <div className="mt-0.5 truncate text-ink-mute">{artist?.name ?? "—"}</div>
        <div className="mt-0.5 truncate text-xs italic text-ink-faint">
          {release.album_type}
        </div>
      </div>
      <span className="shrink-0 self-center text-ink-mute tabular-nums">
        {formatShortDate(release.release_date)}
      </span>
    </button>
  );
}
