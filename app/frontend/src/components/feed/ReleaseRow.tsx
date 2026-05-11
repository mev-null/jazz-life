import { formatShortDate } from "../../lib/dates";
import type { Artist, Release } from "../../types/api";
import { ReleaseJacket } from "./ReleaseJacket";

/**
 * Feed と ArtistDetailModal の Activity セクションで共有する Release 行。
 * 左 64px のジャケット + 右にタイトル / アーティスト / album_type / 日付。
 *
 * 「未読 dot」「past か (= 灰色化)」は呼び出し側で組み立てて渡す。
 * 未読判定は useReadState ベースで呼び出し側のローカル state に依存するため、
 * このコンポーネントはなるべく素の表示に徹する。
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
      className={`flex w-full cursor-pointer items-stretch gap-4 py-3 text-left text-sm transition-opacity hover:opacity-80 ${isPast ? "text-ink-mute" : ""}`}
    >
      <div className="relative aspect-square w-16 shrink-0 overflow-hidden ring-1 ring-ink/10">
        <ReleaseJacket release={release} />
        {!isRead && (
          <span className="absolute right-1 top-1 block h-1.5 w-1.5 rounded-full bg-ink" />
        )}
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
