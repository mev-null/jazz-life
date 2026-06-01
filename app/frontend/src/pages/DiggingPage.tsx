import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getArtists,
  getFollowedArtists,
  getReleaseSyncStatus,
  getReleases,
  getWantedRecords,
  setReleaseRead,
  triggerReleaseSync,
  upsertArtist,
} from "../api/client";
import {
  HuntListPanel,
  type HuntSort,
} from "../components/feed/HuntListPanel";
import { ListenPanel } from "../components/feed/ListenPanel";
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
import type { RecognitionResult, Release, VinylRecord } from "../types/api";

type Tab = "hunt" | "listen" | "releases";

const TABS: Tab[] = ["hunt", "listen", "releases"];

export function DiggingPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  // タブは URL (/digging/:tab) を真実の出所にする。無印 /digging や未知の値は
  // hunt に正規化する。setTab 相当は navigate でパスを切り替える。
  const { tab: tabParam } = useParams<{ tab: string }>();
  const tab: Tab = TABS.includes(tabParam as Tab) ? (tabParam as Tab) : "hunt";
  const setTab = (t: Tab) => navigate(`/digging/${t}`);
  const [huntSort, setHuntSort] = useState<HuntSort>("artist");

  // タブ別 lazy fetch。開いているタブに必要な query だけ走らせて API を節約する。
  // 一度取得した分は TanStack Query のキャッシュに残るので、タブを往復しても
  // staleTime 内なら再フェッチは走らない。
  const releases = useQuery({
    queryKey: ["releases"],
    queryFn: () => getReleases(),
    enabled: tab === "releases",
  });
  // global registry (archived 含む)。release 行 / Hunt list の artist 名表示、
  // 認識フォールバックの在籍判定、フォームの typeahead で全タブから必要なので常時。
  const artists = useQuery({ queryKey: ["artists"], queryFn: getArtists });
  // RecordFormModal の typeahead 候補。フォームは全タブから開きうる (hunt → 詳細 →
  // edit / listen → 認識追加 / releases → collect) ので常時取得しておく。
  const followedArtists = useQuery({
    queryKey: ["followed-artists"],
    queryFn: getFollowedArtists,
  });
  // Hunt list は backend で status=wanted 絞り込み + sort 済みのものを受け取る。
  // ["records"] 系の invalidate は prefix match でこの query にも波及する。
  const wanted = useQuery({
    queryKey: ["records", "wanted", huntSort],
    queryFn: () => getWantedRecords(huntSort),
    enabled: tab === "hunt",
  });
  const syncStatusQ = useQuery({
    queryKey: ["release-sync-status"],
    queryFn: getReleaseSyncStatus,
    enabled: tab === "releases",
    // sync はバックグラウンド実行なので、実行中 (is_running) はジョブ完了を
    // 検知するため 2 秒間隔で polling する。完了すると false になり polling 停止。
    refetchInterval: (query) =>
      query.state.data?.is_running ? 2000 : false,
  });

  const syncMutation = useMutation({
    mutationFn: () => triggerReleaseSync(),
    onSettled: () => {
      // POST は 202 即返し。完了は sync-status の polling で検知するので、ここでは
      // status を取り直して polling (refetchInterval) を起動するだけ。
      queryClient.invalidateQueries({ queryKey: ["release-sync-status"] });
    },
  });

  // sync 実行中か (POST 飛行中 or バックグラウンドジョブ稼働中)。
  const isSyncing =
    syncMutation.isPending || Boolean(syncStatusQ.data?.is_running);

  // sync が完了 (is_running: true -> false) した瞬間に releases 一覧を取り直す。
  const wasSyncingRef = useRef(false);
  useEffect(() => {
    const running = Boolean(syncStatusQ.data?.is_running);
    if (wasSyncingRef.current && !running) {
      queryClient.invalidateQueries({ queryKey: ["releases"] });
    }
    wasSyncingRef.current = running;
  }, [syncStatusQ.data?.is_running, queryClient]);

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

  /**
   * Listen タブの音声認識結果を「On the hunt に追加」する (ADR-016)。
   *
   * 1. 認識した Spotify アーティストが artists レジストリ未在籍なら upsertArtist で
   *    先に DB へ追加する (backend の artist_id 必須を満たすフォールバック)。
   * 2. RecordFormModal を status=wanted で開き、認識メタを prefill する。
   *    spotify_album_id が無ければ autoSearchSpotify で title 検索を自動発火させ、
   *    ユーザがアルバムを選んで artist_id / album を確定できるようにする。
   */
  async function handleRecognizedAdd(r: RecognitionResult) {
    let artistId: string | undefined;
    if (r.spotify_artist_id) {
      artistId = r.spotify_artist_id;
      const known = artists.data?.items.some(
        (a) => a.spotify_id === r.spotify_artist_id,
      );
      if (!known) {
        try {
          await upsertArtist({
            spotify_id: r.spotify_artist_id,
            name: r.artist_name ?? r.spotify_artist_id,
            image_url: r.artist_image_url ?? null,
            source: "spotify_dynamic",
          });
          queryClient.invalidateQueries({ queryKey: ["artists"] });
        } catch {
          // upsert 失敗時は artistId を諦めてフォーム内 Spotify 検索に委ねる。
          artistId = undefined;
        }
      }
    }
    setFormMode({
      kind: "add",
      defaults: {
        status: "wanted",
        artistId,
        // artists レジストリ未反映でも名前欄が空にならないよう認識名を渡す。
        artistName: r.artist_name ?? undefined,
        title: r.album ?? r.title ?? "",
        imageUrl: r.image_url,
        spotifyAlbumId: r.spotify_album_id,
        originalReleaseDate: r.original_release_date,
        favoriteTrackNames: r.title ? [r.title] : [],
        // Spotify album が未解決なら title 検索を自動発火してアルバム候補を提示。
        autoSearchSpotify: !r.spotify_album_id,
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

  const lastRun = syncStatusQ.data?.last_run ?? null;
  const lastRunFailed = lastRun
    ? lastRun.artists_total - lastRun.artists_succeeded
    : 0;
  const isRateLimited = lastRun?.first_error
    ? /rate limit/i.test(lastRun.first_error)
    : false;

  const syncStatusLine = isSyncing ? (
    <span className="text-ink-mute">syncing…</span>
  ) : syncMutation.isError ? (
    <span className="text-ink-mute">sync failed</span>
  ) : isRateLimited ? (
    // partial 同期 (rate limit で打ち切り)。残りは再 sync で取り込まれる。
    <span className="text-ink-mute">
      Spotify rate limit — {lastRunFailed} deferred, try again shortly
    </span>
  ) : lastRun && lastRunFailed > 0 ? (
    <span className="text-ink-mute">
      partial: {lastRun.albums_ingested} ingested · {lastRunFailed} failed
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
        <TabButton
          active={tab === "hunt"}
          onClick={() => setTab("hunt")}
          dataTour="subtab-hunt"
        >
          On the hunt
        </TabButton>
        <TabButton
          active={tab === "listen"}
          onClick={() => setTab("listen")}
          dataTour="subtab-listen"
        >
          Listen
        </TabButton>
        <TabButton
          active={tab === "releases"}
          onClick={() => setTab("releases")}
          dataTour="subtab-releases"
        >
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
        ) : tab === "listen" ? (
          <ListenPanel onAdd={handleRecognizedAdd} />
        ) : (
          <div data-tour="releases-feed">
            <h1 className="flex items-baseline gap-3 text-base">
              <span className="font-medium">Records</span>
              {releases.data && (
                <span className="text-ink-faint tabular-nums">
                  {releaseParts.upcoming.length} upcoming ·{" "}
                  {releaseParts.past.length} past
                </span>
              )}
              <button
                type="button"
                onClick={() => syncMutation.mutate()}
                disabled={isSyncing}
                className="ml-auto inline-flex items-center gap-1.5 cursor-pointer text-xs italic text-ink-mute transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSyncing && (
                  <span
                    aria-hidden
                    className="inline-block h-3 w-3 animate-spin rounded-full border border-ink-faint border-t-transparent"
                  />
                )}
                {isSyncing ? "syncing…" : "sync now"}
              </button>
            </h1>
            <div className="mt-1 text-xs italic text-ink-faint">{syncStatusLine}</div>
            <div className="mt-4">
              {isSyncing && (
                <div
                  data-tour="releases-syncing"
                  className="mb-3 flex items-center gap-2 text-xs italic text-ink-faint"
                >
                  <span
                    aria-hidden
                    className="inline-block h-3 w-3 animate-spin rounded-full border border-ink-faint border-t-transparent"
                  />
                  Spotify から新譜を取得中…
                </div>
              )}
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
  dataTour,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  dataTour?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-tour={dataTour}
      className={`cursor-pointer transition-colors ${
        active ? "font-medium text-ink" : "italic text-ink-mute hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}
