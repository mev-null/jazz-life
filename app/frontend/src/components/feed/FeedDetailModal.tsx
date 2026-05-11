import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getVinylRecords, updateVinylRecord } from "../../api/client";
import { formatLongDate } from "../../lib/dates";
import { formatVenue } from "../../lib/formatVenue";
import type { Artist, Concert, Release } from "../../types/api";
import { ModalShell } from "../ModalShell";
import { ReleaseJacket } from "./ReleaseJacket";

export type FeedItem =
  | { kind: "release"; data: Release; artist?: Artist }
  | { kind: "concert"; data: Concert; artist?: Artist };

type Props = {
  item: FeedItem | null;
  isRead?: boolean;
  onToggleRead?: () => void;
  onClose: () => void;
  // Release 詳細時に表示する「買った/ほしい」ボタンの押下ハンドラ。
  // FeedPage 側で modal を閉じてから RecordFormModal を defaults 付きで開く責務を持つ。
  // 省略可 (Concert detail でも同 modal を使うため)。
  onCollectFromRelease?: (release: Release, status: "owned" | "wanted") => void;
};

function safeHostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function Field({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex gap-6 text-[15px] leading-relaxed">
      <span className="w-24 shrink-0 italic text-ink-mute">{label}</span>
      <span className="min-w-0 flex-1 text-ink">{value}</span>
    </div>
  );
}

function ExternalLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-ink underline decoration-ink-faint underline-offset-4 transition-colors hover:decoration-ink"
    >
      {label}
      <span aria-hidden="true">↗</span>
    </a>
  );
}

function ReleaseDetail({
  release,
  artist,
  onClose,
  onCollect,
}: {
  release: Release;
  artist?: Artist;
  onClose: () => void;
  onCollect?: (status: "owned" | "wanted") => void;
}) {
  // 同じ album (spotify_album_id) の record が既にコレクションにある場合の挙動:
  // - status=owned : 既に持ってるので両ボタン非表示
  // - status=wanted: 物理的にまだ持ってないので「買った」だけ出して upgrade に使う
  // - 無し         : 両ボタン (parent onCollect で新規追加)
  const queryClient = useQueryClient();
  const recordsQ = useQuery({ queryKey: ["records"], queryFn: getVinylRecords });
  const existing = (recordsQ.data?.items ?? []).find(
    (r) => r.spotify_album_id === release.spotify_id,
  );
  const promoteToOwned = useMutation({
    mutationFn: (id: string) => updateVinylRecord(id, { status: "owned" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["records"] });
      onClose();
    },
  });
  const showAddButtons = onCollect && existing === undefined;
  const showPromoteButton = existing?.status === "wanted";
  const spotifyUrl = `https://open.spotify.com/album/${release.spotify_id}`;
  return (
    <>
      <header className="flex items-start gap-4 border-b border-ink/15 pb-4">
        <div className="min-w-0 flex-1">
          <div className="text-2xl font-medium leading-tight">
            {release.title}
          </div>
          <div className="mt-1 text-base text-ink-mute">
            {artist?.name ?? "—"}
          </div>
        </div>
        <div className="aspect-square w-20 shrink-0 overflow-hidden ring-1 ring-ink/10">
          <ReleaseJacket release={release} />
        </div>
      </header>

      <div className="space-y-2 py-5">
        <Field label="Released" value={formatLongDate(release.release_date)} />
        <Field label="Type" value={release.album_type} />
      </div>

      {showAddButtons && (
        <div className="flex gap-3 border-t border-ink/15 pt-4">
          <button
            type="button"
            onClick={() => onCollect("wanted")}
            className="flex-1 cursor-pointer border border-ink/20 px-4 py-2 text-sm text-ink transition-colors hover:bg-ink/5"
          >
            On the hunt
          </button>
          <button
            type="button"
            onClick={() => onCollect("owned")}
            className="flex-1 cursor-pointer bg-ink/10 px-4 py-2 text-sm text-ink transition-colors hover:bg-ink/20"
          >
            On the shelf
          </button>
        </div>
      )}
      {showPromoteButton && existing && (
        // 既に「ほしい」登録済 → 物理購入後の upgrade 専用ボタン。
        // 新規 record を作らず、既存の wanted を status=owned に flip する。
        <div className="flex border-t border-ink/15 pt-4">
          <button
            type="button"
            onClick={() => promoteToOwned.mutate(existing.id)}
            disabled={promoteToOwned.isPending}
            className="flex-1 cursor-pointer bg-ink/10 px-4 py-2 text-sm text-ink transition-colors hover:bg-ink/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {promoteToOwned.isPending ? "Moving…" : "On the shelf"}
          </button>
        </div>
      )}

      <footer
        className={`${showAddButtons || showPromoteButton ? "mt-4" : ""} border-t border-ink/15 pt-4`}
      >
        <div className="mb-1 italic text-sm text-ink-mute">Source</div>
        <ExternalLink href={spotifyUrl} label="Spotify" />
      </footer>
    </>
  );
}

function ConcertDetail({
  concert,
  artist,
}: {
  concert: Concert;
  artist?: Artist;
}) {
  const venue = formatVenue(concert.venue_id);
  return (
    <>
      <header className="border-b border-ink/15 pb-4">
        <div className="text-2xl font-medium leading-tight">
          {concert.title}
        </div>
        <div className="mt-1 text-base text-ink-mute capitalize">
          {venue}
          {artist && (
            <span className="text-ink-faint normal-case"> · {artist.name}</span>
          )}
        </div>
      </header>

      <div className="space-y-2 py-5">
        <Field label="Date" value={formatLongDate(concert.date)} />
        {concert.stage_times && (
          <Field label="Stages" value={concert.stage_times} />
        )}
        {concert.status !== "scheduled" && (
          <Field
            label="Status"
            value={<span className="text-ink">{concert.status}</span>}
          />
        )}
      </div>

      <footer className="border-t border-ink/15 pt-4">
        <div className="mb-1 italic text-sm text-ink-mute">Source</div>
        {concert.url ? (
          <ExternalLink
            href={concert.url}
            label={safeHostname(concert.url)}
          />
        ) : (
          <span className="text-sm text-ink-faint">unknown</span>
        )}
      </footer>
    </>
  );
}

export function FeedDetailModal({
  item,
  isRead,
  onToggleRead,
  onClose,
  onCollectFromRelease,
}: Props) {
  if (!item) return null;

  return (
    <ModalShell onClose={onClose}>
      <div className="max-h-[85vh] w-[min(90vw,480px)] overflow-y-auto bg-paper p-8 text-left text-ink shadow-xl ring-1 ring-ink/10">
        {item.kind === "release" ? (
          <ReleaseDetail
            release={item.data}
            artist={item.artist}
            onClose={onClose}
            onCollect={
              onCollectFromRelease
                ? (status) => onCollectFromRelease(item.data, status)
                : undefined
            }
          />
        ) : (
          <ConcertDetail concert={item.data} artist={item.artist} />
        )}
        {onToggleRead && (
          <div className="mt-4 flex justify-end">
            <button
              type="button"
              onClick={onToggleRead}
              className={`text-sm italic transition-colors hover:text-ink ${isRead ? "text-ink" : "text-ink-mute"}`}
            >
              {isRead ? "mark as unread" : "mark as read"}
            </button>
          </div>
        )}
      </div>
    </ModalShell>
  );
}
