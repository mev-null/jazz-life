import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getArtists, getVinylRecords } from "../api/client";
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

// PC 側は ArtistDetailModal の RecordsSection と同じ 8 件 (4 列 × 2 行)。
// Mobile は 2 列 × 3 行で 6 件に減らし、view all 経由で全件閲覧へ。
const HOME_PREVIEW_LIMIT = 8;
const HOME_MOBILE_PREVIEW_LIMIT = 6;

export function HomePage() {
  const records = useQuery({
    queryKey: ["records"],
    queryFn: getVinylRecords,
  });
  const artists = useQuery({ queryKey: ["artists"], queryFn: getArtists });

  const { isMobile } = useBreakpoint();
  const mobile = MOBILE_UI_ENABLED && isMobile;
  const previewLimit = mobile ? HOME_MOBILE_PREVIEW_LIMIT : HOME_PREVIEW_LIMIT;

  // Mobile の Home は「棚をひと目で見せる」コンセプトに合わせて body スクロールを抑止。
  // 6 件 + ヘッダ + 余白で iPhone 14 (390x844) 程度の縦に収まる前提。
  // 他ページや PC では効かないよう unmount / breakpoint 変化で必ず元に戻す。
  useEffect(() => {
    if (!mobile) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mobile]);

  // Home は所有レコードのコレクション。wanted は ArtistDetailModal の want list でだけ表示。
  const ownedRecords = records.data?.items.filter((r) => r.status === "owned") ?? [];
  const exceedsPreview = ownedRecords.length >= previewLimit;
  const visibleRecords = exceedsPreview
    ? ownedRecords.slice(0, previewLimit)
    : ownedRecords;

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
    <section>
      <h1 className="flex items-baseline gap-3 text-base">
        <span className="font-medium">Records</span>
        <span className="text-ink-faint tabular-nums">
          {records.data ? ownedRecords.length : ""}
        </span>
        {exceedsPreview && (
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className="ml-auto cursor-pointer text-sm italic text-ink-mute transition-colors hover:text-ink"
          >
            view all
          </button>
        )}
      </h1>

      <div className="my-6">
        {records.isLoading && (
          <p className="text-sm text-ink-faint">loading…</p>
        )}
        {records.isError && (
          <p className="text-sm text-ink-mute">読み込みに失敗しました</p>
        )}
        {records.data && (
          <>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {visibleRecords.map((r) => (
                <JacketCard
                  key={r.id}
                  record={r}
                  onClick={() => setOpenRecord(r)}
                />
              ))}
              {!exceedsPreview && (
                <AddRecordTile
                  onClick={() => setFormMode({ kind: "add" })}
                  prominent={ownedRecords.length === 0}
                />
              )}
            </div>
            {ownedRecords.length === 0 && (
              <p className="mt-6 text-center text-sm italic text-ink-mute">
                まだレコードがありません。最初の 1 枚を追加してください。
              </p>
            )}
          </>
        )}
      </div>

      {showAll && (
        <RecordsAllModal
          label="Records"
          records={ownedRecords}
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
        onClose={() => setFormMode(null)}
      />
    </section>
  );
}
