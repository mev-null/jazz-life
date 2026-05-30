import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getArtists,
  getFollowedArtists,
  getReleaseSyncStatus,
  getReleases,
  getWantedRecords,
  setReleaseRead,
  triggerReleaseSync,
} from "../api/client";
import {
  HuntListPanel,
  type HuntSort,
} from "../components/feed/HuntListPanel";
import { ReleaseRow } from "../components/feed/ReleaseRow";
import {
  ReleaseDetailModal,
  type ReleaseItem,
} from "../components/feed/ReleaseDetailModal";
import { TodayDivider } from "../components/feed/TodayDivider";
import { RecordDetailModal } from "../components/records/RecordDetailModal";
import {
  RecordFormModal,
  type FormMode,
} from "../components/records/RecordFormModal";
import { formatLongDate, formatShortDate, partitionByToday } from "../lib/dates";
import type { Release, VinylRecord } from "../types/api";

type Tab = "hunt" | "releases";

export function DiggingPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("hunt");
  const [huntSort, setHuntSort] = useState<HuntSort>("artist");

  const releases = useQuery({
    queryKey: ["releases"],
    queryFn: () => getReleases(),
  });
  // global registry (archived 含む)。release 行や Hunt list の artist 名表示で、
  // 現在 unfollow しているアーティストでも名前が消えないよう全件持つ。
  const artists = useQuery({ queryKey: ["artists"], queryFn: getArtists });
  const followedArtists = useQuery({
    queryKey: ["followed-artists"],
    queryFn: getFollowedArtists,
  });
  // Hunt list は backend で status=wanted 絞り込み + sort 済みのものを受け取る。
  // ["records"] 系の invalidate は prefix match でこの query にも波及する。
  const wanted = useQuery({
    queryKey: ["records", "wanted", huntSort],
    queryFn: () => getWantedRecords(huntSort),
  });
  const syncStatusQ = useQuery({
    queryKey: ["release-sync-status"],
    queryFn: getReleaseSyncStatus,
  });

  const syncMutation = useMutation({
    mutationFn: () => triggerReleaseSync(),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["releases"] });
      queryClient.invalidateQueries({ queryKey: ["release-sync-status"] });
    },
  });

  // release の既読化は backend (release.is_read / read_at) を真とする mutation。
  const setReleaseReadMutation = useMutation({
    mutationFn: ({ id, isRead }: { id: string; isRead: boolean }) =>
      setReleaseRead(id, isRead),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["releases"] });
    },
  });

  const [openRelease, setOpenRelease] = useState<ReleaseItem | null>(null);
  const [openRecord, setOpenRecord] = useState<VinylRecord | null>(null);
  const [formMode, setFormMode] = useState<FormMode | null>(null);

  const artistById = (id: string) =>
    artists.data?.items.find((a) => a.spotify_id === id);

  // 開いている release の最新版を releases.data から look up し、既読 toggle 後の
  // backend の is_read を modal に追従させる。
  const openReleaseLatest = openRelease
    ? releases.data?.items.find(
        (r) => r.spotify_id === openRelease.release.spotify_id,
      ) ?? openRelease.release
    : null;
  const openIsRead = Boolean(openReleaseLatest?.is_read);

  function toggleOpenRead() {
    if (!openRelease) return;
    setReleaseReadMutation.mutate({
      id: openRelease.release.spotify_id,
      isRead: !openIsRead,
    });
  }

  function handleReleaseRowClick(r: Release) {
    if (!r.is_read) {
      setReleaseReadMutation.mutate({ id: r.spotify_id, isRead: true });
    }
    setOpenRelease({ release: r, artist: artistById(r.artist_id) });
  }

  /**
   * ReleaseDetailModal の「On the hunt / On the shelf」から呼ぶ。release のメタを
   * RecordFormModal の defaults に流し込む。詳細を閉じてからフォームを開く。
   */
  function handleCollectFromRelease(r: Release, status: "owned" | "wanted") {
    setOpenRelease(null);
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

  function handleEditOpenRecord() {
    if (!openRecord) return;
    setFormMode({ kind: "edit", record: openRecord });
    setOpenRecord(null);
  }

  const todayLabel = formatLongDate(new Date().toISOString());

  const releaseParts = partitionByToday(
    releases.data?.items ?? [],
    (r) => r.release_date,
  );

  const syncStatusLine = syncMutation.isError ? (
    <span className="text-ink-mute">sync failed</span>
  ) : syncMutation.data?.first_error ? (
    <span className="text-ink-mute">
      partial: {syncMutation.data.albums_ingested} ingested ·{" "}
      {syncMutation.data.artists_total - syncMutation.data.artists_succeeded} failed
    </span>
  ) : syncStatusQ.data?.last_success_at ? (
    <span>last sync {formatShortDate(syncStatusQ.data.last_success_at)}</span>
  ) : (
    <span>not synced yet</span>
  );

  return (
    <section>
      <p className="text-right text-lg italic text-ink-mute">{todayLabel}</p>

      {/* タブバー */}
      <nav className="mt-8 flex items-baseline gap-6 text-base">
        <TabButton active={tab === "hunt"} onClick={() => setTab("hunt")}>
          On the hunt
        </TabButton>
        <TabButton active={tab === "releases"} onClick={() => setTab("releases")}>
          Releases
        </TabButton>
      </nav>

      <div className="mt-6">
        {tab === "hunt" ? (
          <HuntListPanel
            records={wanted.data?.items ?? []}
            artists={artists.data?.items ?? []}
            sort={huntSort}
            onSortChange={setHuntSort}
            onRecordClick={(r) => setOpenRecord(r)}
          />
        ) : (
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
            <div className="mt-1 text-xs italic text-ink-faint">{syncStatusLine}</div>
            <div className="mt-4">
              {releaseParts.upcoming.length > 0 && (
                <div className="divide-y divide-ink-faint/30">
                  {releaseParts.upcoming.map((r) => (
                    <ReleaseRow
                      key={r.spotify_id}
                      release={r}
                      artist={artistById(r.artist_id)}
                      isPast={false}
                      isRead={r.is_read}
                      onClick={() => handleReleaseRowClick(r)}
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
                      isRead={r.is_read}
                      onClick={() => handleReleaseRowClick(r)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <ReleaseDetailModal
        item={openRelease}
        isRead={openIsRead}
        onToggleRead={toggleOpenRead}
        onClose={() => setOpenRelease(null)}
        onCollect={handleCollectFromRelease}
      />

      <RecordDetailModal
        record={openRecord}
        artistName={
          openRecord ? artistById(openRecord.artist_id)?.name : undefined
        }
        onClose={() => setOpenRecord(null)}
        onEdit={handleEditOpenRecord}
      />

      <RecordFormModal
        mode={formMode}
        artists={artists.data?.items ?? []}
        followedArtists={followedArtists.data?.items ?? []}
        onClose={() => setFormMode(null)}
      />
    </section>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`cursor-pointer transition-colors ${
        active ? "font-medium text-ink" : "italic text-ink-mute hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}
