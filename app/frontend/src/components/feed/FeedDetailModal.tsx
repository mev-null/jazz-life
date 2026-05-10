import { formatLongDate } from "../../lib/dates";
import { formatVenue } from "../../lib/formatVenue";
import type { Artist, Concert, Release } from "../../types/api";
import { ModalShell } from "../ModalShell";

export type FeedItem =
  | { kind: "release"; data: Release; artist?: Artist }
  | { kind: "concert"; data: Concert; artist?: Artist };

type Props = {
  item: FeedItem | null;
  isRead?: boolean;
  onToggleRead?: () => void;
  onClose: () => void;
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
}: {
  release: Release;
  artist?: Artist;
}) {
  const spotifyUrl = `https://open.spotify.com/album/${release.spotify_id}`;
  return (
    <>
      <header className="border-b border-ink/15 pb-4">
        <div className="text-2xl font-medium leading-tight">
          {release.title}
        </div>
        <div className="mt-1 text-base text-ink-mute">
          {artist?.name ?? "—"}
        </div>
      </header>

      <div className="space-y-2 py-5">
        <Field label="Released" value={formatLongDate(release.release_date)} />
        <Field label="Type" value={release.album_type} />
      </div>

      <footer className="border-t border-ink/15 pt-4">
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
}: Props) {
  if (!item) return null;

  return (
    <ModalShell onClose={onClose}>
      <div className="max-h-[85vh] w-[min(90vw,480px)] overflow-y-auto bg-paper p-8 text-left text-ink shadow-xl ring-1 ring-ink/10">
        {item.kind === "release" ? (
          <ReleaseDetail release={item.data} artist={item.artist} />
        ) : (
          <ConcertDetail concert={item.data} artist={item.artist} />
        )}
        {onToggleRead && (
          <div className="mt-4 flex justify-end">
            <button
              type="button"
              onClick={onToggleRead}
              className="text-xs italic text-ink-mute transition-colors hover:text-ink"
            >
              {isRead ? "mark as unread" : "mark as read"}
            </button>
          </div>
        )}
      </div>
    </ModalShell>
  );
}
