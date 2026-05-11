import type { ReactNode } from "react";

import {
  formatShortDate,
  partitionByToday,
} from "../../lib/dates";
import { formatVenue } from "../../lib/formatVenue";
import { concertMatchesArtist } from "../../lib/matchArtist";
import { avatarTintByString } from "../../lib/palette";
import type {
  Artist,
  Concert,
  Release,
  VinylRecord,
} from "../../types/api";
import { ModalShell } from "../ModalShell";
import { TodayDivider } from "../feed/TodayDivider";
import { JacketArt } from "../records/JacketCard";

function initials(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length === 0) return "—";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

function ArtistAvatar({ artist }: { artist: Artist }) {
  if (artist.image_url) {
    return (
      <img
        src={artist.image_url}
        alt=""
        className="aspect-square w-20 shrink-0 rounded-full object-cover"
      />
    );
  }
  const bg = avatarTintByString(artist.spotify_id);
  const isWarm = bg === "#b08a3a";
  return (
    <div
      className="flex aspect-square w-20 shrink-0 items-center justify-center rounded-full"
      style={{
        backgroundColor: bg,
        color: isWarm ? "#1a1714" : "#f4efe3",
      }}
    >
      <span className="text-base font-medium tracking-wide">
        {initials(artist.name)}
      </span>
    </div>
  );
}

type TimelineItem =
  | { kind: "release"; data: Release; date: string }
  | { kind: "concert"; data: Concert; date: string };

function timelineSub(item: TimelineItem): ReactNode {
  if (item.kind === "release") return null;
  return formatVenue(item.data.venue_id);
}

function timelineTag(item: TimelineItem): string {
  return item.kind === "release" ? "release" : "concert";
}

function timelineKey(item: TimelineItem): string {
  return item.kind === "release"
    ? `release:${item.data.spotify_id}`
    : `concert:${item.data.id}`;
}

function TimelineRow({
  index,
  title,
  sub,
  date,
  tag,
  isPast,
  onClick,
}: {
  index: number;
  title: string;
  sub: ReactNode;
  date: string;
  tag: string;
  isPast: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full cursor-pointer items-start gap-3 py-3 text-left text-sm transition-opacity hover:opacity-70 ${isPast ? "text-ink-mute" : ""}`}
    >
      <span className="w-6 shrink-0 text-ink-faint tabular-nums">
        {String(index).padStart(2, "0")}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">{title}</div>
        {sub && <div className="mt-0.5 truncate text-ink-mute">{sub}</div>}
      </div>
      <div className="shrink-0 text-right">
        <div className="text-ink-mute tabular-nums">
          {formatShortDate(date)}
        </div>
        <div className="mt-0.5 text-xs italic text-ink-faint">{tag}</div>
      </div>
    </button>
  );
}

type Props = {
  artist: Artist | null;
  records: VinylRecord[];
  releases: Release[];
  concerts: Concert[];
  onClose: () => void;
  onRecordClick: (record: VinylRecord) => void;
  onReleaseClick: (release: Release) => void;
  onConcertClick: (concert: Concert) => void;
};

export function ArtistDetailModal({
  artist,
  records,
  releases,
  concerts,
  onClose,
  onRecordClick,
  onReleaseClick,
  onConcertClick,
}: Props) {
  if (!artist) return null;

  // ADR-003: own → want → activity の 3 セクション構造。
  const artistRecords = records.filter((r) => r.artist_id === artist.spotify_id);
  const ownedRecords = artistRecords.filter((r) => r.status === "owned");
  const wantedRecords = artistRecords.filter((r) => r.status === "wanted");

  const timeline: TimelineItem[] = [
    ...releases
      .filter((r) => r.artist_id === artist.spotify_id)
      .map((r) => ({
        kind: "release" as const,
        data: r,
        date: r.release_date,
      })),
    ...concerts
      .filter((c) => concertMatchesArtist(c, artist))
      .map((c) => ({ kind: "concert" as const, data: c, date: c.date })),
  ];

  const tp = partitionByToday(timeline, (t) => t.date);

  function handleClick(item: TimelineItem) {
    if (item.kind === "release") onReleaseClick(item.data);
    else onConcertClick(item.data);
  }

  return (
    <ModalShell onClose={onClose}>
      <div className="max-h-[90vh] w-[min(92vw,720px)] overflow-y-auto bg-paper p-8 text-left text-ink shadow-xl ring-1 ring-ink/10">
        <header className="flex items-start gap-4 border-b border-ink/15 pb-4">
          <div className="min-w-0 flex-1">
            <div className="text-2xl font-medium leading-tight">
              {artist.name}
            </div>
            <div className="mt-1 text-sm italic text-ink-mute">
              {artist.source}
            </div>
          </div>
          <ArtistAvatar artist={artist} />
        </header>

        {/* Records (owned) */}
        <section className="mt-8">
          <h3 className="flex items-baseline gap-3 text-base">
            <span className="font-medium">Records</span>
            <span className="text-ink-faint tabular-nums">
              {ownedRecords.length}
            </span>
          </h3>
          {ownedRecords.length > 0 ? (
            <div className="mt-4 grid grid-cols-3 gap-3 sm:grid-cols-4">
              {ownedRecords.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => onRecordClick(r)}
                  aria-label={r.title}
                  className="block aspect-square w-full cursor-pointer appearance-none bg-transparent p-0 transition-opacity hover:opacity-90"
                >
                  <JacketArt record={r} />
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-sm italic text-ink-faint">none owned</p>
          )}
        </section>

        {/* Want list (wanted) — Home からは見えず、ここでだけ参照する */}
        <section className="mt-10">
          <h3 className="flex items-baseline gap-3 text-base">
            <span className="font-medium">Want list</span>
            <span className="text-ink-faint tabular-nums">
              {wantedRecords.length}
            </span>
          </h3>
          {wantedRecords.length > 0 ? (
            <div className="mt-4 grid grid-cols-3 gap-3 sm:grid-cols-4">
              {wantedRecords.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => onRecordClick(r)}
                  aria-label={r.title}
                  className="block aspect-square w-full cursor-pointer appearance-none bg-transparent p-0 transition-opacity hover:opacity-90"
                >
                  <JacketArt record={r} />
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-sm italic text-ink-faint">none wanted</p>
          )}
        </section>

        {/* Activity (releases + concerts unified timeline) */}
        <section className="mt-10">
          <h3 className="flex items-baseline gap-3 text-base">
            <span className="font-medium">Activity</span>
            <span className="text-ink-faint tabular-nums">
              {tp.upcoming.length} upcoming · {tp.past.length} past
            </span>
          </h3>
          <div className="mt-4">
            {tp.upcoming.length > 0 && (
              <div className="divide-y divide-ink-faint/30">
                {tp.upcoming.map((item, i) => (
                  <TimelineRow
                    key={timelineKey(item)}
                    index={i + 1}
                    title={item.data.title}
                    sub={timelineSub(item)}
                    date={item.date}
                    tag={timelineTag(item)}
                    isPast={false}
                    onClick={() => handleClick(item)}
                  />
                ))}
              </div>
            )}
            {(tp.upcoming.length > 0 || tp.past.length > 0) && (
              <TodayDivider />
            )}
            {tp.past.length > 0 && (
              <div className="divide-y divide-ink-faint/30">
                {tp.past.map((item, i) => (
                  <TimelineRow
                    key={timelineKey(item)}
                    index={tp.upcoming.length + i + 1}
                    title={item.data.title}
                    sub={timelineSub(item)}
                    date={item.date}
                    tag={timelineTag(item)}
                    isPast={true}
                    onClick={() => handleClick(item)}
                  />
                ))}
              </div>
            )}
            {tp.upcoming.length === 0 && tp.past.length === 0 && (
              <p className="text-sm italic text-ink-faint">none</p>
            )}
          </div>
        </section>
      </div>
    </ModalShell>
  );
}
