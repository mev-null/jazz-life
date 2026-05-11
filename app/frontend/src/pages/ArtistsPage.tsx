import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  getArtists,
  getConcerts,
  getReleases,
  getVinylRecords,
} from "../api/client";
import { ArtistDetailModal } from "../components/artists/ArtistDetailModal";
import {
  FeedDetailModal,
  type FeedItem,
} from "../components/feed/FeedDetailModal";
import { RecordDetailModal } from "../components/records/RecordDetailModal";
import {
  RecordFormModal,
  type FormMode,
} from "../components/records/RecordFormModal";
import { findArtistInConcert } from "../lib/matchArtist";
import { useReadState } from "../lib/useReadState";
import type { Artist, Concert, Release, VinylRecord } from "../types/api";

export function ArtistsPage() {
  const artistsQ = useQuery({ queryKey: ["artists"], queryFn: getArtists });
  const recordsQ = useQuery({
    queryKey: ["records"],
    queryFn: getVinylRecords,
  });
  const releasesQ = useQuery({ queryKey: ["releases"], queryFn: getReleases });
  const concertsQ = useQuery({ queryKey: ["concerts"], queryFn: getConcerts });

  const [openArtist, setOpenArtist] = useState<Artist | null>(null);
  const [openRecord, setOpenRecord] = useState<VinylRecord | null>(null);
  const [openFeedItem, setOpenFeedItem] = useState<FeedItem | null>(null);
  const [formMode, setFormMode] = useState<FormMode | null>(null);

  const { isRead, markRead, markUnread } = useReadState();

  const artistById = (id: string) =>
    artistsQ.data?.items.find((a) => a.spotify_id === id);

  const recordsCountByArtist = (artistId: string) =>
    recordsQ.data?.items.filter((r) => r.artist_id === artistId).length ?? 0;

  // FeedDetailModal toggle state
  const openFeedKey = openFeedItem
    ? openFeedItem.kind === "release"
      ? `release:${openFeedItem.data.spotify_id}`
      : `concert:${openFeedItem.data.id}`
    : null;
  const openFeedIsRead = openFeedKey ? isRead(openFeedKey) : false;
  function toggleOpenFeedRead() {
    if (!openFeedKey) return;
    if (openFeedIsRead) markUnread(openFeedKey);
    else markRead(openFeedKey);
  }

  function handleReleaseClick(r: Release) {
    markRead(`release:${r.spotify_id}`);
    setOpenFeedItem({
      kind: "release",
      data: r,
      artist: artistById(r.artist_id),
    });
  }

  function handleConcertClick(c: Concert) {
    markRead(`concert:${c.id}`);
    const matched = findArtistInConcert(c, artistsQ.data?.items ?? []);
    setOpenFeedItem({ kind: "concert", data: c, artist: matched });
  }

  return (
    <section>
      <h1 className="flex items-baseline gap-3 text-base">
        <span className="font-medium">Artists</span>
        <span className="text-ink-faint tabular-nums">
          {artistsQ.data ? artistsQ.data.items.length : ""}
        </span>
      </h1>

      <div className="mt-6">
        {artistsQ.isLoading && (
          <p className="text-sm text-ink-faint">loading…</p>
        )}
        {artistsQ.isError && (
          <p className="text-sm text-ink-mute">読み込みに失敗しました</p>
        )}
        {artistsQ.data && (
          <ul className="divide-y divide-ink-faint/30">
            {artistsQ.data.items.map((a, i) => {
              const count = recordsCountByArtist(a.spotify_id);
              return (
                <li key={a.spotify_id}>
                  <button
                    type="button"
                    onClick={() => setOpenArtist(a)}
                    className="flex w-full cursor-pointer items-baseline gap-3 py-3 text-left text-sm transition-opacity hover:opacity-70"
                  >
                    <span className="w-6 shrink-0 text-ink-faint tabular-nums">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="flex-1 font-medium">{a.name}</span>
                    <span className="text-ink-mute tabular-nums">
                      {count} {count === 1 ? "record" : "records"}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <ArtistDetailModal
        artist={openArtist}
        records={recordsQ.data?.items ?? []}
        releases={releasesQ.data?.items ?? []}
        concerts={concertsQ.data?.items ?? []}
        onClose={() => setOpenArtist(null)}
        onRecordClick={(r) => setOpenRecord(r)}
        onReleaseClick={handleReleaseClick}
        onConcertClick={handleConcertClick}
        onAddRecord={(a, status) =>
          setFormMode({
            kind: "add",
            defaults: { artistId: a.spotify_id, status },
          })
        }
      />

      <RecordDetailModal
        record={openRecord}
        artistName={
          openRecord ? artistById(openRecord.artist_id)?.name : undefined
        }
        onClose={() => setOpenRecord(null)}
      />

      <RecordFormModal
        mode={formMode}
        artists={artistsQ.data?.items ?? []}
        onClose={() => setFormMode(null)}
      />

      <FeedDetailModal
        item={openFeedItem}
        isRead={openFeedIsRead}
        onToggleRead={toggleOpenFeedRead}
        onClose={() => setOpenFeedItem(null)}
      />
    </section>
  );
}
