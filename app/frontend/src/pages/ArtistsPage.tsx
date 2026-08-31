import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getFollowedArtists,
  getRecordCounts,
  getReleases,
  setReleaseRead,
} from "../api/client";
import { AddArtistModal } from "../components/artists/AddArtistModal";
import { ArtistDetailModal } from "../components/artists/ArtistDetailModal";
import {
  ReleaseDetailModal,
  type ReleaseItem,
} from "../components/feed/ReleaseDetailModal";
import { RecordDetailModal } from "../components/records/RecordDetailModal";
import {
  RecordFormModal,
  type FormMode,
} from "../components/records/RecordFormModal";
import { useBreakpoint } from "../hooks/useBreakpoint";
import { MOBILE_UI_ENABLED } from "../lib/featureFlags";
import { useAuth } from "../lib/useAuth";
import type { Artist, Release, VinylRecord } from "../types/api";

export function ArtistsPage() {
  const { isMobile } = useBreakpoint();
  const { logout } = useAuth();
  // ArtistsPage の一覧は「現ユーザが follow 中 (archived=false) の artists」だけ。
  // record→artist 名前引きで使う global artist registry とはキャッシュキーを
  // 分けてある (HomePage 等は依然 ["artists"] を共有)。unfollow で archived 化
  // した artist はここから消える。
  const artistsQ = useQuery({
    queryKey: ["followed-artists"],
    queryFn: getFollowedArtists,
  });
  // 件数は専用エンドポイント /api/artists/record-counts で受け取る。
  // records 本体は ArtistDetailModal を開いた時にだけ fetch する設計のため、
  // 一覧では集計値だけを軽量に取得する。
  const recordCountsQ = useQuery({
    queryKey: ["record-counts"],
    queryFn: getRecordCounts,
  });
  // 行頭の「未読黒豆」表示用。release は backend (is_read) を見る。
  // DiggingPage / ArtistDetailModal と同じ query key なのでキャッシュは共有される。
  const releasesQ = useQuery({
    queryKey: ["releases"],
    queryFn: () => getReleases(),
  });

  const queryClient = useQueryClient();
  const setReleaseReadMutation = useMutation({
    mutationFn: ({ id, isRead }: { id: string; isRead: boolean }) =>
      setReleaseRead(id, isRead),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["releases"] });
    },
  });

  const [openArtist, setOpenArtist] = useState<Artist | null>(null);
  const [openRecord, setOpenRecord] = useState<VinylRecord | null>(null);
  const [openRelease, setOpenRelease] = useState<ReleaseItem | null>(null);
  const [formMode, setFormMode] = useState<FormMode | null>(null);
  const [addArtistOpen, setAddArtistOpen] = useState(false);

  const artistById = (id: string) =>
    artistsQ.data?.items.find((a) => a.spotify_id === id);

  // ListResponse 形式から spotify_id -> count の lookup に変換 (一覧 render のたびに走る)。
  const countsByArtistId = useMemo(() => {
    const map = new Map<string, number>();
    for (const c of recordCountsQ.data?.items ?? []) {
      map.set(c.artist_id, c.count);
    }
    return map;
  }, [recordCountsQ.data]);

  // artist_id -> 未読 release が 1 件でもあるか (backend の is_read を真とする)。
  const unreadArtistIds = useMemo(() => {
    const set = new Set<string>();
    for (const r of releasesQ.data?.items ?? []) {
      if (!r.is_read) set.add(r.artist_id);
    }
    return set;
  }, [releasesQ.data]);

  // ReleaseDetailModal の既読 toggle 用。開いている release の最新 is_read を
  // releases query から look up する。
  const openReleaseLatest = openRelease
    ? releasesQ.data?.items.find(
        (r) => r.spotify_id === openRelease.release.spotify_id,
      ) ?? openRelease.release
    : null;
  const openReleaseIsRead = Boolean(openReleaseLatest?.is_read);
  function toggleOpenReleaseRead() {
    if (!openRelease) return;
    setReleaseReadMutation.mutate({
      id: openRelease.release.spotify_id,
      isRead: !openReleaseIsRead,
    });
  }

  function handleReleaseClick(r: Release) {
    if (!r.is_read) {
      setReleaseReadMutation.mutate({ id: r.spotify_id, isRead: true });
    }
    setOpenRelease({ release: r, artist: artistById(r.artist_id) });
  }

  function handleEditOpenRecord() {
    // HomePage と同じパターン: 詳細を閉じてから edit form を開く。
    if (!openRecord) return;
    setFormMode({ kind: "edit", record: openRecord });
    setOpenRecord(null);
  }

  /**
   * Activity の release を開いた状態で「On the hunt / On the shelf」を押した時の
   * ハンドラ。DiggingPage と同じ動作: 詳細を閉じてから RecordFormModal を
   * release のメタデータ pre-fill で開く。
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

  return (
    <section>
      <h1 className="flex items-baseline gap-3 text-base" data-tour="artists">
        <span className="font-medium">Artists</span>
        <span className="text-ink-faint tabular-nums">
          {artistsQ.data ? artistsQ.data.items.length : ""}
        </span>
        <button
          type="button"
          onClick={() => setAddArtistOpen(true)}
          className="ml-auto cursor-pointer text-xs italic text-ink-mute transition-colors hover:text-ink"
        >
          + add
        </button>
      </h1>

      <div className="mt-6">
        {artistsQ.isLoading && (
          <p className="text-sm text-ink-faint">loading…</p>
        )}
        {artistsQ.isError && (
          <p className="text-sm text-ink-mute">Failed to load</p>
        )}
        {artistsQ.data && (
          <ul className="divide-y divide-ink-faint/30">
            {artistsQ.data.items.map((a) => {
              const count = countsByArtistId.get(a.spotify_id) ?? 0;
              const hasUnread = unreadArtistIds.has(a.spotify_id);
              return (
                <li key={a.spotify_id}>
                  <button
                    type="button"
                    onClick={() => setOpenArtist(a)}
                    className="flex w-full cursor-pointer items-center gap-2 py-3 text-left text-sm transition-opacity hover:opacity-70"
                  >
                    <span className="flex w-2 shrink-0 items-center justify-center">
                      {hasUnread && (
                        <span className="block h-1 w-1 rounded-full bg-ink/70" />
                      )}
                    </span>
                    <span className="font-medium">{a.name}</span>
                    {count === 0 ? (
                      <span className="ml-auto pr-[3px] italic text-ink-faint">
                        no records yet
                      </span>
                    ) : (
                      <span className="ml-auto pr-[3px] text-ink-mute tabular-nums">
                        {count} {count === 1 ? "record" : "records"}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {MOBILE_UI_ENABLED && isMobile && (
        <div className="mt-10 border-t border-rule pt-6 text-center">
          <button
            type="button"
            onClick={() => logout()}
            className="text-xs italic tracking-wider text-ink-faint transition-colors hover:text-ink"
          >
            logout
          </button>
        </div>
      )}

      <ArtistDetailModal
        artist={openArtist}
        onClose={() => setOpenArtist(null)}
        onRecordClick={(r) => setOpenRecord(r)}
        onReleaseClick={handleReleaseClick}
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
        onEdit={handleEditOpenRecord}
      />

      <RecordFormModal
        mode={formMode}
        artists={artistsQ.data?.items ?? []}
        followedArtists={artistsQ.data?.items ?? []}
        onClose={() => setFormMode(null)}
      />

      <ReleaseDetailModal
        item={openRelease}
        isRead={openReleaseIsRead}
        onToggleRead={toggleOpenReleaseRead}
        onClose={() => setOpenRelease(null)}
        onCollect={handleCollectFromRelease}
      />

      <AddArtistModal
        open={addArtistOpen}
        onClose={() => setAddArtistOpen(false)}
      />
    </section>
  );
}
