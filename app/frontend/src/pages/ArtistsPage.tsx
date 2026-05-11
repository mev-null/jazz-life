import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  getConcerts,
  getFollowedArtists,
  getRecordCounts,
  getReleases,
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
import { concertMatchesArtist } from "../lib/matchArtist";
import { useReadState } from "../lib/useReadState";
import type { Artist, Concert, Release, VinylRecord } from "../types/api";

export function ArtistsPage() {
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
  // 行頭の「未読黒豆」表示用。release は backend (is_read)、concert は
  // localStorage (useReadState) を見る。FeedPage / ArtistDetailModal と
  // 同じ query key なのでキャッシュは共有される。
  const releasesQ = useQuery({
    queryKey: ["releases"],
    queryFn: () => getReleases(),
  });
  const concertsQ = useQuery({ queryKey: ["concerts"], queryFn: getConcerts });

  const [openArtist, setOpenArtist] = useState<Artist | null>(null);
  const [openRecord, setOpenRecord] = useState<VinylRecord | null>(null);
  const [openFeedItem, setOpenFeedItem] = useState<FeedItem | null>(null);
  const [formMode, setFormMode] = useState<FormMode | null>(null);

  const { isRead, markRead, markUnread } = useReadState();

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

  // artist_id -> 未読 release または未読 concert が 1 件でもあるか。
  // concert は単一 artist に紐付かない (タイトル文字列マッチ) ので、各 concert を
  // 全 artist と突き合わせて該当 artist の set に積む。
  const unreadArtistIds = useMemo(() => {
    const set = new Set<string>();
    for (const r of releasesQ.data?.items ?? []) {
      if (!r.is_read) set.add(r.artist_id);
    }
    const artistList = artistsQ.data?.items ?? [];
    for (const c of concertsQ.data?.items ?? []) {
      if (isRead(`concert:${c.id}`)) continue;
      for (const a of artistList) {
        if (concertMatchesArtist(c, a)) set.add(a.spotify_id);
      }
    }
    return set;
  }, [releasesQ.data, concertsQ.data, artistsQ.data, isRead]);

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

  function handleConcertClick(c: Concert, matchedArtist?: Artist) {
    markRead(`concert:${c.id}`);
    setOpenFeedItem({ kind: "concert", data: c, artist: matchedArtist });
  }

  function handleEditOpenRecord() {
    // HomePage と同じパターン: 詳細を閉じてから edit form を開く。
    if (!openRecord) return;
    setFormMode({ kind: "edit", record: openRecord });
    setOpenRecord(null);
  }

  /**
   * Activity の release を開いた状態で「買った/ほしい」を押した時のハンドラ。
   * FeedPage と同じ動作: FeedDetailModal を閉じてから RecordFormModal を
   * release のメタデータ pre-fill で開く。
   */
  function handleCollectFromRelease(r: Release, status: "owned" | "wanted") {
    setOpenFeedItem(null);
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
                    <span className="ml-auto pr-[3px] text-ink-mute tabular-nums">
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
        onEdit={handleEditOpenRecord}
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
        onCollectFromRelease={handleCollectFromRelease}
      />
    </section>
  );
}
