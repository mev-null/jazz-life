import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getArtists,
  getConcerts,
  getReleaseSyncStatus,
  getReleases,
  triggerReleaseSync,
} from "../api/client";
import {
  FeedDetailModal,
  type FeedItem,
} from "../components/feed/FeedDetailModal";
import { ReleaseRow } from "../components/feed/ReleaseRow";
import { TodayDivider } from "../components/feed/TodayDivider";
import {
  RecordFormModal,
  type FormMode,
} from "../components/records/RecordFormModal";
import {
  formatLongDate,
  formatShortDate,
  partitionByToday,
} from "../lib/dates";
import { formatVenue } from "../lib/formatVenue";
import { findArtistInConcert } from "../lib/matchArtist";
import { useReadState } from "../lib/useReadState";
import type { Artist, Concert, Release } from "../types/api";

function ConcertRow({
  concert,
  artists,
  index,
  isPast,
  isRead,
  onClick,
}: {
  concert: Concert;
  artists: Artist[];
  index: number;
  isPast: boolean;
  isRead: boolean;
  onClick: () => void;
}) {
  const matchedArtist = findArtistInConcert(concert, artists);
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full cursor-pointer items-start gap-3 py-3 text-left text-sm transition-opacity hover:opacity-70 ${isPast ? "text-ink-mute" : ""}`}
    >
      <span className="flex w-2 shrink-0 justify-center pt-2">
        {!isRead && (
          <span className="block h-1.5 w-1.5 rounded-full bg-ink" />
        )}
      </span>
      <span className="w-6 shrink-0 text-ink-faint tabular-nums">
        {String(index).padStart(2, "0")}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">
          {concert.title}
          {concert.status !== "scheduled" && (
            <span className="ml-2 text-ink-mute">[{concert.status}]</span>
          )}
        </div>
        <div className="mt-0.5 truncate text-ink-mute">
          {formatVenue(concert.venue_id)}
          {matchedArtist && (
            <span className="text-ink-faint"> · {matchedArtist.name}</span>
          )}
        </div>
      </div>
      <span className="shrink-0 text-ink-mute tabular-nums">
        {formatShortDate(concert.date)}
      </span>
    </button>
  );
}

export function FeedPage() {
  const queryClient = useQueryClient();
  const releases = useQuery({
    queryKey: ["releases"],
    queryFn: () => getReleases(),
  });
  const concerts = useQuery({ queryKey: ["concerts"], queryFn: getConcerts });
  const artists = useQuery({ queryKey: ["artists"], queryFn: getArtists });
  const syncStatusQ = useQuery({
    queryKey: ["release-sync-status"],
    queryFn: getReleaseSyncStatus,
  });

  // 「Sync now」ボタン用 mutation。
  // - isPending で button を disable してダブルクリック多重実行を防ぐ
  // - 成功 / 失敗どちらでも sync-status と releases を再 fetch する
  const syncMutation = useMutation({
    mutationFn: () => triggerReleaseSync(),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["releases"] });
      queryClient.invalidateQueries({ queryKey: ["release-sync-status"] });
    },
  });

  const [openItem, setOpenItem] = useState<FeedItem | null>(null);
  const [formMode, setFormMode] = useState<FormMode | null>(null);
  const { isRead, markRead, markUnread } = useReadState();

  const openKey = openItem
    ? openItem.kind === "release"
      ? `release:${openItem.data.spotify_id}`
      : `concert:${openItem.data.id}`
    : null;
  const openIsRead = openKey ? isRead(openKey) : false;

  function toggleOpenRead() {
    if (!openKey) return;
    if (openIsRead) markUnread(openKey);
    else markRead(openKey);
  }

  const artistById = (id: string) =>
    artists.data?.items.find((a) => a.spotify_id === id);

  const matchArtistFromConcert = (concert: Concert) =>
    findArtistInConcert(concert, artists.data?.items ?? []);

  function openRelease(r: Release) {
    markRead(`release:${r.spotify_id}`);
    setOpenItem({
      kind: "release",
      data: r,
      artist: artistById(r.artist_id),
    });
  }

  function openConcert(c: Concert) {
    markRead(`concert:${c.id}`);
    setOpenItem({
      kind: "concert",
      data: c,
      artist: matchArtistFromConcert(c),
    });
  }

  /**
   * FeedDetailModal の「買った/ほしい」ボタンから呼ぶ。Release のメタデータ
   * (title / image_url / spotify_album_id / release_date / artist_id) を
   * RecordFormModal の defaults に流し込んで開く。詳細モーダルは先に閉じて
   * フォームを最前面にする。
   */
  function handleCollectFromRelease(r: Release, status: "owned" | "wanted") {
    setOpenItem(null);
    setFormMode({
      kind: "add",
      defaults: {
        artistId: r.artist_id,
        status,
        title: r.title,
        imageUrl: r.image_url,
        spotifyAlbumId: r.spotify_id,
        originalReleaseDate: r.release_date,
      },
    });
  }

  const todayLabel = formatLongDate(new Date().toISOString());

  const releaseParts = partitionByToday(
    releases.data?.items ?? [],
    (r) => r.release_date,
  );
  const concertParts = partitionByToday(
    concerts.data?.items ?? [],
    (c) => c.date,
  );

  return (
    <section>
      <p className="text-right text-lg italic text-ink-mute">{todayLabel}</p>

      <div className="mt-10 grid grid-cols-1 gap-x-30 gap-y-16 md:grid-cols-2">
        {/* Releases */}
        <div>
          <h1 className="flex items-baseline gap-3 text-base">
            <span className="font-medium">Releases</span>
            {releases.data && (
              <span className="text-ink-faint tabular-nums">
                {releaseParts.upcoming.length} upcoming ·{" "}
                {releaseParts.past.length} past
              </span>
            )}
            <button
              type="button"
              onClick={() => syncMutation.mutate()}
              disabled={syncMutation.isPending}
              className="ml-auto cursor-pointer text-xs italic text-ink-mute transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
            >
              {syncMutation.isPending ? "syncing…" : "sync now"}
            </button>
          </h1>
          <div className="mt-1 text-xs italic text-ink-faint">
            {syncMutation.isError ? (
              <span className="text-ink-mute">sync failed</span>
            ) : syncMutation.data?.first_error ? (
              <span className="text-ink-mute">
                partial: {syncMutation.data.albums_ingested} ingested ·{" "}
                {syncMutation.data.artists_total - syncMutation.data.artists_succeeded}{" "}
                failed
              </span>
            ) : syncStatusQ.data?.last_success_at ? (
              <span>
                last sync {formatShortDate(syncStatusQ.data.last_success_at)}
              </span>
            ) : (
              <span>not synced yet</span>
            )}
          </div>
          <div className="mt-4">
            {releaseParts.upcoming.length > 0 && (
              <div className="divide-y divide-ink-faint/30">
                {releaseParts.upcoming.map((r) => (
                  <ReleaseRow
                    key={r.spotify_id}
                    release={r}
                    artist={artistById(r.artist_id)}
                    isPast={false}
                    isRead={isRead(`release:${r.spotify_id}`)}
                    onClick={() => openRelease(r)}
                  />
                ))}
              </div>
            )}
            <TodayDivider />
            {releaseParts.past.length > 0 && (
              <div className="divide-y divide-ink-faint/30">
                {releaseParts.past.map((r) => (
                  <ReleaseRow
                    key={r.spotify_id}
                    release={r}
                    artist={artistById(r.artist_id)}
                    isPast={true}
                    isRead={isRead(`release:${r.spotify_id}`)}
                    onClick={() => openRelease(r)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Concerts */}
        <div>
          <h1 className="flex items-baseline gap-3 text-base">
            <span className="font-medium">Concerts</span>
            {concerts.data && (
              <span className="text-ink-faint tabular-nums">
                {concertParts.upcoming.length} upcoming ·{" "}
                {concertParts.past.length} past
              </span>
            )}
          </h1>
          <div className="mt-4">
            {concertParts.upcoming.length > 0 && (
              <div className="divide-y divide-ink-faint/30">
                {concertParts.upcoming.map((c, i) => (
                  <ConcertRow
                    key={c.id}
                    concert={c}
                    artists={artists.data?.items ?? []}
                    index={i + 1}
                    isPast={false}
                    isRead={isRead(`concert:${c.id}`)}
                    onClick={() => openConcert(c)}
                  />
                ))}
              </div>
            )}
            <TodayDivider />
            {concertParts.past.length > 0 && (
              <div className="divide-y divide-ink-faint/30">
                {concertParts.past.map((c, i) => (
                  <ConcertRow
                    key={c.id}
                    concert={c}
                    artists={artists.data?.items ?? []}
                    index={concertParts.upcoming.length + i + 1}
                    isPast={true}
                    isRead={isRead(`concert:${c.id}`)}
                    onClick={() => openConcert(c)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <FeedDetailModal
        item={openItem}
        isRead={openIsRead}
        onToggleRead={toggleOpenRead}
        onClose={() => setOpenItem(null)}
        onCollectFromRelease={handleCollectFromRelease}
      />

      <RecordFormModal
        mode={formMode}
        artists={artists.data?.items ?? []}
        onClose={() => setFormMode(null)}
      />
    </section>
  );
}
