import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getArtist,
  getConcerts,
  getReleases,
  getVinylRecords,
  unfollowArtist,
} from "../../api/client";
import {
  formatShortDate,
  partitionByToday,
} from "../../lib/dates";
import { formatVenue } from "../../lib/formatVenue";
import { concertMatchesArtist } from "../../lib/matchArtist";
import type {
  Artist,
  Concert,
  Release,
  VinylRecord,
} from "../../types/api";
import { useReadState } from "../../lib/useReadState";
import { InlineConfirm } from "../InlineConfirm";
import { ModalShell } from "../ModalShell";
import { ReleaseRow } from "../feed/ReleaseRow";
import { TodayDivider } from "../feed/TodayDivider";
import { AddRecordTile } from "../records/AddRecordTile";
import { JacketArt } from "../records/JacketCard";
import { ArtistAvatar } from "./ArtistAvatar";
import { ArtistRecordsAllModal } from "./ArtistRecordsAllModal";

// detail modal のセクションが「拡大表示」(別 modal で全件) に切り替わる件数閾値。
// 4 = sm+ の grid 1 行に収まる枚数。これ以上は detail 内グリッドに「+」を出さず、
// 4 件だけプレビューして "view all" 経由で拡大表示へ誘導する。
const SECTION_PREVIEW_LIMIT = 4;

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

function ActivityRow({
  item,
  index,
  isPast,
  artist,
  isRead,
  onClick,
}: {
  item: TimelineItem;
  index: number;
  isPast: boolean;
  artist: Artist;
  isRead: (key: string) => boolean;
  onClick: () => void;
}) {
  // release は Feed と共通の jacket-style 行で表示する。concert は既存の
  // テキスト index 行 (TimelineRow) を使い続ける。混在で行高が違うが、
  // 「ジャケットあり = リリース、無し = 公演」 と直感的に区別できる方を優先。
  if (item.kind === "release") {
    return (
      <ReleaseRow
        release={item.data}
        artist={artist}
        isPast={isPast}
        isRead={isRead(`release:${item.data.spotify_id}`)}
        onClick={onClick}
      />
    );
  }
  return (
    <TimelineRow
      index={index}
      title={item.data.title}
      sub={timelineSub(item)}
      date={item.date}
      tag={timelineTag(item)}
      isPast={isPast}
      onClick={onClick}
    />
  );
}

function RecordsSection({
  label,
  records,
  onRecordClick,
  onAddRecord,
  onViewAll,
}: {
  label: string;
  records: VinylRecord[];
  onRecordClick: (record: VinylRecord) => void;
  onAddRecord: () => void;
  onViewAll: () => void;
}) {
  // ≤ SECTION_PREVIEW_LIMIT - 1 件: detail 内グリッドに「+」も並べる (現状維持)
  // ≥ SECTION_PREVIEW_LIMIT 件: 先頭 N 件だけプレビューし、"view all" 経由で
  // 拡大表示モーダルに誘導する。グリッド内の「+」は出さない。
  const exceedsPreview = records.length >= SECTION_PREVIEW_LIMIT;
  const visible = exceedsPreview
    ? records.slice(0, SECTION_PREVIEW_LIMIT)
    : records;
  return (
    <section className="mt-8">
      <h3 className="flex items-baseline gap-3 text-base">
        <span className="font-medium">{label}</span>
        <span className="text-ink-faint tabular-nums">{records.length}</span>
        {exceedsPreview && (
          <button
            type="button"
            onClick={onViewAll}
            className="ml-auto cursor-pointer text-xs italic text-ink-mute transition-colors hover:text-ink"
          >
            view all
          </button>
        )}
      </h3>
      <div className="mt-4 grid grid-cols-3 gap-3 sm:grid-cols-4">
        {visible.map((r) => (
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
        {!exceedsPreview && (
          <AddRecordTile onClick={onAddRecord} prominent={records.length === 0} />
        )}
      </div>
    </section>
  );
}

type Props = {
  artist: Artist | null;
  onClose: () => void;
  onRecordClick: (record: VinylRecord) => void;
  onReleaseClick: (release: Release) => void;
  // matchedArtist は ArtistDetailModal 文脈では自明 (props の artist と一致) だが、
  // FeedPage と signature を揃えるため明示的に渡す。
  onConcertClick: (concert: Concert, matchedArtist?: Artist) => void;
  // セクションのグリッド末尾に出る「＋」タイル（hover 表示）からの追加導線。
  // 呼び出し側で RecordFormModal を defaults 付きで開く責務を持つ。
  onAddRecord: (artist: Artist, status: "owned" | "wanted") => void;
};

export function ArtistDetailModal({
  artist,
  onClose,
  onRecordClick,
  onReleaseClick,
  onConcertClick,
  onAddRecord,
}: Props) {
  // どちらのセクションを「拡大表示」しているか。null = 拡大表示は閉じている。
  // detail modal が閉じる (artist=null) / 別アーティストに切り替わる時にリセットして、
  // 「Artist A の Records を拡大表示したまま Artist B を開く」ような状態の引きずりを防ぐ。
  const [expandedSection, setExpandedSection] = useState<
    "owned" | "wanted" | null
  >(null);
  useEffect(() => {
    setExpandedSection(null);
  }, [artist?.spotify_id]);
  // Activity に release を出すとき、Feed と同じ既読状態 (localStorage 共有) を尊重する。
  const { isRead } = useReadState();
  const queryClient = useQueryClient();
  const unfollow = useMutation({
    mutationFn: unfollowArtist,
    onSuccess: () => {
      // ArtistsPage 一覧 (followed-artists) と件数表示を更新。global artists
      // registry (HomePage 等が使う) は変わらないので invalidate しない。
      queryClient.invalidateQueries({ queryKey: ["followed-artists"] });
      queryClient.invalidateQueries({ queryKey: ["record-counts"] });
      onClose();
    },
  });
  // 個別アーティストクリック時に発火する lazy fetch 群。modal が閉じている間は
  // enabled=false で発火しない。
  // - artistQ: backend が image_url を Spotify から hydrate して返す
  // - recordsQ: own/want セクションの絞り込み元 (artist_id でフィルタ)
  // - releasesQ / concertsQ: activity timeline の元 (mock のまま frontend filter)
  const artistId = artist?.spotify_id ?? null;
  const artistQ = useQuery({
    queryKey: ["artist", artistId],
    queryFn: () => getArtist(artistId as string),
    enabled: artistId !== null,
  });
  const recordsQ = useQuery({
    queryKey: ["records"],
    queryFn: getVinylRecords,
    enabled: artistId !== null,
  });
  const releasesQ = useQuery({
    queryKey: ["releases"],
    queryFn: () => getReleases(),
    enabled: artistId !== null,
  });
  const concertsQ = useQuery({
    queryKey: ["concerts"],
    queryFn: getConcerts,
    enabled: artistId !== null,
  });

  if (!artist) return null;

  // backend からの hydrated artist があればそちらを優先 (image_url が埋まる)、
  // 未到着時は親から渡された prop を fallback として使う。
  const displayArtist = artistQ.data ?? artist;

  // ADR-003: own → want → activity の 3 セクション構造。
  const records = recordsQ.data?.items ?? [];
  const releases = releasesQ.data?.items ?? [];
  const concerts = concertsQ.data?.items ?? [];
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
    else onConcertClick(item.data, artist ?? undefined);
  }

  return (
    <ModalShell onClose={onClose}>
      <div className="max-h-[90vh] w-[min(92vw,720px)] overflow-y-auto bg-paper p-8 text-left text-ink shadow-xl ring-1 ring-ink/10">
        <header className="flex items-center gap-4 border-b border-ink/15 pb-4">
          <div className="min-w-0 flex-1">
            <div className="text-2xl font-medium leading-tight">
              {displayArtist.name}
            </div>
          </div>
          <ArtistAvatar artist={displayArtist} />
        </header>

        {/* Records (owned) */}
        <RecordsSection
          label="Records"
          records={ownedRecords}
          onRecordClick={onRecordClick}
          onAddRecord={() => onAddRecord(artist, "owned")}
          onViewAll={() => setExpandedSection("owned")}
        />

        {/* Want list (wanted) — Home からは見えず、ここでだけ参照する */}
        <RecordsSection
          label="Want list"
          records={wantedRecords}
          onRecordClick={onRecordClick}
          onAddRecord={() => onAddRecord(artist, "wanted")}
          onViewAll={() => setExpandedSection("wanted")}
        />

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
                  <ActivityRow
                    key={timelineKey(item)}
                    item={item}
                    index={i + 1}
                    isPast={false}
                    artist={artist}
                    isRead={isRead}
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
                  <ActivityRow
                    key={timelineKey(item)}
                    item={item}
                    index={tp.upcoming.length + i + 1}
                    isPast={true}
                    artist={artist}
                    isRead={isRead}
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

        {/* Remove (unfollow) — modal 最下部。記録がある間は disable。
            共通の InlineConfirm で「trigger → prompt+Cancel+Confirm」を表現。
        */}
        <section className="mt-12 border-t border-ink/15 pt-4 text-sm">
          <InlineConfirm
            // 別アーティストに切り替えた時に confirm 状態が引き継がれないよう
            // spotify_id で remount させる。
            key={artist.spotify_id}
            className="flex items-center justify-end gap-3"
            triggerLabel="Remove from follow"
            prompt={`Stop following ${displayArtist.name}?`}
            pendingLabel="Removing…"
            isPending={unfollow.isPending}
            disabled={artistRecords.length > 0}
            disabledHint="good music..."
            onConfirm={() => unfollow.mutate(artist.spotify_id)}
          />
        </section>
      </div>
      {expandedSection !== null && (
        <ArtistRecordsAllModal
          artist={displayArtist}
          records={expandedSection === "owned" ? ownedRecords : wantedRecords}
          status={expandedSection}
          onClose={() => setExpandedSection(null)}
          onRecordClick={onRecordClick}
          onAddRecord={onAddRecord}
        />
      )}
    </ModalShell>
  );
}
