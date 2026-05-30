import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getArtist,
  getReleases,
  getVinylRecords,
  unfollowArtist,
} from "../../api/client";
import { partitionByToday } from "../../lib/dates";
import { useBreakpoint } from "../../hooks/useBreakpoint";
import { MOBILE_UI_ENABLED } from "../../lib/featureFlags";
import type { Artist, Release, VinylRecord } from "../../types/api";
import { InlineConfirm } from "../InlineConfirm";
import { ModalShell } from "../ModalShell";
import { ReleaseRow } from "../feed/ReleaseRow";
import { TodayDivider } from "../feed/TodayDivider";
import { AddRecordTile } from "../records/AddRecordTile";
import { JacketArt } from "../records/JacketCard";
import { RecordsAllModal } from "../records/RecordsAllModal";
import { ArtistAvatar } from "./ArtistAvatar";

// detail modal のセクションが「拡大表示」(別 modal で全件) に切り替わる件数閾値。
// PC は 4 列 grid で 2 行分 = 8 件。Mobile は 2 列 grid だが詳細モーダル自体が
// 縦長で 3 セクション (owned/wanted/activity) を同時に出すので、各セクションは
// プレビュー 2 件に抑えて "view all" 経由で全件閲覧へ。
const SECTION_PREVIEW_LIMIT = 8;
const SECTION_MOBILE_PREVIEW_LIMIT = 2;

function RecordsSection({
  label,
  records,
  previewLimit,
  onRecordClick,
  onAddRecord,
  onViewAll,
}: {
  label: string;
  records: VinylRecord[];
  previewLimit: number;
  onRecordClick: (record: VinylRecord) => void;
  onAddRecord: () => void;
  onViewAll: () => void;
}) {
  // ≤ previewLimit - 1 件: detail 内グリッドに「+」も並べる (現状維持)
  // ≥ previewLimit 件: 先頭 N 件だけプレビューし、"view all" 経由で
  // 拡大表示モーダルに誘導する。グリッド内の「+」は出さない。
  const exceedsPreview = records.length >= previewLimit;
  const visible = exceedsPreview ? records.slice(0, previewLimit) : records;
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
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
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
  // セクションのグリッド末尾に出る「＋」タイル（hover 表示）からの追加導線。
  // 呼び出し側で RecordFormModal を defaults 付きで開く責務を持つ。
  onAddRecord: (artist: Artist, status: "owned" | "wanted") => void;
};

export function ArtistDetailModal({
  artist,
  onClose,
  onRecordClick,
  onReleaseClick,
  onAddRecord,
}: Props) {
  const { isMobile } = useBreakpoint();
  const previewLimit =
    MOBILE_UI_ENABLED && isMobile
      ? SECTION_MOBILE_PREVIEW_LIMIT
      : SECTION_PREVIEW_LIMIT;

  // どちらのセクションを「拡大表示」しているか。null = 拡大表示は閉じている。
  // detail modal が閉じる (artist=null) / 別アーティストに切り替わる時にリセットして、
  // 「Artist A の Records を拡大表示したまま Artist B を開く」ような状態の引きずりを防ぐ。
  const [expandedSection, setExpandedSection] = useState<
    "owned" | "wanted" | null
  >(null);
  useEffect(() => {
    setExpandedSection(null);
  }, [artist?.spotify_id]);
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
  // - releasesQ: activity timeline の元 (mock のまま frontend filter)
  const artistId = artist?.spotify_id ?? null;
  const artistQ = useQuery({
    queryKey: ["artist", artistId],
    queryFn: () => getArtist(artistId as string),
    enabled: artistId !== null,
  });
  const recordsQ = useQuery({
    queryKey: ["records"],
    queryFn: () => getVinylRecords(),
    enabled: artistId !== null,
  });
  const releasesQ = useQuery({
    queryKey: ["releases"],
    queryFn: () => getReleases(),
    enabled: artistId !== null,
  });

  if (!artist) return null;

  // backend からの hydrated artist があればそちらを優先 (image_url が埋まる)、
  // 未到着時は親から渡された prop を fallback として使う。
  const displayArtist = artistQ.data ?? artist;

  // ADR-003: own → want → activity の 3 セクション構造。
  // Activity は ADR-013 で concert を撤去し releases のみになった。
  const records = recordsQ.data?.items ?? [];
  const releases = releasesQ.data?.items ?? [];
  const artistRecords = records.filter((r) => r.artist_id === artist.spotify_id);
  const ownedRecords = artistRecords.filter((r) => r.status === "owned");
  const wantedRecords = artistRecords.filter((r) => r.status === "wanted");

  const artistReleases = releases.filter((r) => r.artist_id === artist.spotify_id);
  const tp = partitionByToday(artistReleases, (r) => r.release_date);

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

        {/* Owned records */}
        <RecordsSection
          label="On the shelf"
          records={ownedRecords}
          previewLimit={previewLimit}
          onRecordClick={onRecordClick}
          onAddRecord={() => onAddRecord(artist, "owned")}
          onViewAll={() => setExpandedSection("owned")}
        />

        {/* Wanted records — Home からは見えず、ここでだけ参照する */}
        <RecordsSection
          label="On the hunt"
          records={wantedRecords}
          previewLimit={previewLimit}
          onRecordClick={onRecordClick}
          onAddRecord={() => onAddRecord(artist, "wanted")}
          onViewAll={() => setExpandedSection("wanted")}
        />

        {/* Activity (releases timeline。concert は ADR-013 で撤去) */}
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
                {tp.upcoming.map((r) => (
                  <ReleaseRow
                    key={r.spotify_id}
                    release={r}
                    artist={artist}
                    isPast={false}
                    isRead={r.is_read}
                    onClick={() => onReleaseClick(r)}
                  />
                ))}
              </div>
            )}
            {(tp.upcoming.length > 0 || tp.past.length > 0) && (
              <TodayDivider />
            )}
            {tp.past.length > 0 && (
              <div className="divide-y divide-ink-faint/30">
                {tp.past.map((r) => (
                  <ReleaseRow
                    key={r.spotify_id}
                    release={r}
                    artist={artist}
                    isPast={true}
                    isRead={r.is_read}
                    onClick={() => onReleaseClick(r)}
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
        <RecordsAllModal
          prefix={displayArtist.name}
          label={expandedSection === "owned" ? "On the shelf" : "On the hunt"}
          records={expandedSection === "owned" ? ownedRecords : wantedRecords}
          onClose={() => setExpandedSection(null)}
          onRecordClick={onRecordClick}
          onAddRecord={() => onAddRecord(artist, expandedSection)}
        />
      )}
    </ModalShell>
  );
}
