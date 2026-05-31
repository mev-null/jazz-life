import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getArtists, getFollowedArtists, getVinylRecords } from "../api/client";
import { AddRecordTile } from "../components/records/AddRecordTile";
import { JacketCard } from "../components/records/JacketCard";
import { RecordDetailModal } from "../components/records/RecordDetailModal";
import {
  RecordFormModal,
  type FormMode,
} from "../components/records/RecordFormModal";
import { RecordsAllModal } from "../components/records/RecordsAllModal";
import { useBreakpoint } from "../hooks/useBreakpoint";
import { MOBILE_UI_ENABLED } from "../lib/featureFlags";
import type { VinylRecord } from "../types/api";

// PC / Mobile とも 6 件 showcase に統一 (PIN_LIMIT=6 と一致させ、満杯時は
// 追加タイルを出さない)。PC は 3 列 × 2 行、Mobile は 2 列 × 3 行。
const HOME_PREVIEW_LIMIT = 6;
const HOME_MOBILE_PREVIEW_LIMIT = 6;

export function HomePage() {
  const records = useQuery({
    queryKey: ["records"],
    queryFn: () => getVinylRecords(),
  });
  // `artists` は global registry (archived 含む)。既存 record の artist_id →
  // name 引きに使うので、unfollow 済みアーティストの過去 record でも名前が
  // 出るよう維持する。typeahead サジェスト用は followed-only で別キャッシュ。
  const artists = useQuery({ queryKey: ["artists"], queryFn: getArtists });
  const followedArtists = useQuery({
    queryKey: ["followed-artists"],
    queryFn: getFollowedArtists,
  });

  const { isMobile } = useBreakpoint();
  const mobile = MOBILE_UI_ENABLED && isMobile;
  const previewLimit = mobile ? HOME_MOBILE_PREVIEW_LIMIT : HOME_PREVIEW_LIMIT;

  // Mobile の Home は「棚をひと目で見せる」コンセプトで body スクロールを抑止する。
  // レイアウトは dvh 基準 (AppLayout) + 高さを埋めるグリッドで可視領域に収めるので、
  // スクロールせずに 6 枚すべてが収まる。
  useEffect(() => {
    if (!mobile) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mobile]);

  // Home は「ピンした owned だけ」を showcase する (ADR-014)。所有はしているが
  // 未ピンのレコードは view all (RecordsAllModal) でのみ参照する。wanted は Digging。
  const ownedRecords = records.data?.items.filter((r) => r.status === "owned") ?? [];
  // backend が pin_order 昇順で返すので、filter してもピン順は維持される。
  // ピン上限は 8 枚なので previewLimit (PC 8) には収まる。
  const pinnedRecords = ownedRecords.filter((r) => r.is_pinned);
  const hasRoomForAdd = pinnedRecords.length < previewLimit;

  const [openRecord, setOpenRecord] = useState<VinylRecord | null>(null);
  const [formMode, setFormMode] = useState<FormMode | null>(null);
  const [showAll, setShowAll] = useState(false);

  const artistNameById = (id: string) =>
    artists.data?.items.find((a) => a.spotify_id === id)?.name;

  function handleEditCurrent() {
    if (!openRecord) return;
    setFormMode({ kind: "edit", record: openRecord });
    setOpenRecord(null);
  }

  return (
    <section className={mobile ? "flex h-full flex-col" : ""}>
      <h1 className="flex items-baseline gap-3 text-base">
        <span className="font-medium">Records</span>
        <span className="text-ink-faint tabular-nums">
          {records.data ? ownedRecords.length : ""}
        </span>
        {ownedRecords.length > 0 && (
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className="ml-auto cursor-pointer text-sm italic text-ink-mute transition-colors hover:text-ink"
          >
            view all
          </button>
        )}
      </h1>

      <div
        className={mobile ? "mt-4 min-h-0 flex-1" : "my-6"}
        data-tour="home-records"
      >
        {records.isLoading && (
          <p className="text-sm text-ink-faint">loading…</p>
        )}
        {records.isError && (
          <p className="text-sm text-ink-mute">読み込みに失敗しました</p>
        )}
        {records.data &&
          (pinnedRecords.length > 0 ? (
            // ピン済みの showcase。room があれば末尾に追加タイルも出す。
            // mobile = 2 列 × 3 行で利用可能な高さ (dvh) を埋め、タイルは高さ基準の
            // 正方形にして 1 画面に収める。sm 以上 = 3 列 × 2 行 (幅を抑えた center)。
            <div
              className={
                mobile
                  ? "grid h-full grid-cols-2 grid-rows-3 place-items-center gap-3"
                  : "mx-auto grid max-w-3xl grid-cols-2 gap-4 sm:grid-cols-3"
              }
            >
              {pinnedRecords.map((r) => (
                <JacketCard
                  key={r.id}
                  record={r}
                  onClick={() => setOpenRecord(r)}
                  fillHeight={mobile}
                />
              ))}
              {hasRoomForAdd && (
                <AddRecordTile
                  onClick={() => setFormMode({ kind: "add" })}
                  fillHeight={mobile}
                />
              )}
            </div>
          ) : ownedRecords.length > 0 ? (
            // owned はあるが Home に固定されたものが無い状態。view all から
            // レコードを開いて ★ で固定するよう促す。
            <p className="mt-6 text-center text-sm italic text-ink-mute">
              Home に固定されたレコードがありません。
              <br />
              view all からレコードを開き ★ で固定してください。
            </p>
          ) : (
            // まだ 1 枚も owned が無い。最初の追加導線を目立たせる。
            <>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                <AddRecordTile
                  onClick={() => setFormMode({ kind: "add" })}
                  prominent
                />
              </div>
              <p className="mt-6 text-center text-sm italic text-ink-mute">
                まだレコードがありません。最初の 1 枚を追加してください。
              </p>
            </>
          ))}
      </div>

      {showAll && (
        <RecordsAllModal
          label="Records"
          records={ownedRecords}
          paginated
          statusFilter="owned"
          onClose={() => setShowAll(false)}
          onRecordClick={(r) => setOpenRecord(r)}
          onAddRecord={() => setFormMode({ kind: "add" })}
        />
      )}

      <RecordDetailModal
        record={openRecord}
        artistName={
          openRecord ? artistNameById(openRecord.artist_id) : undefined
        }
        onClose={() => setOpenRecord(null)}
        onEdit={handleEditCurrent}
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
