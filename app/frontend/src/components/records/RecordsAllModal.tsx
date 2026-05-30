import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { getVinylRecords } from "../../api/client";
import { useBreakpoint } from "../../hooks/useBreakpoint";
import type { VinylRecord } from "../../types/api";
import { ModalShell } from "../ModalShell";
import { AddRecordTile } from "./AddRecordTile";
import { JacketArt } from "./JacketCard";

type Props = {
  /** メインのセクションラベル ("Records" / "On the shelf" / "On the hunt" 等)。 */
  label: string;
  /** label の左に italic で出すアーティスト名等のプレフィクス。省略時は出ない。 */
  prefix?: string;
  /** `paginated=false` 時に表示するレコード一覧。ArtistDetailModal 経由はこちら。 */
  records: VinylRecord[];
  onClose: () => void;
  onRecordClick: (record: VinylRecord) => void;
  onAddRecord: () => void;
  /**
   * true で HomePage 経由のサーバ側ページネーション (PC 8/page, モバイル 9/page) +
   * 矢印 UI を有効化する。false (デフォルト) は ArtistDetailModal 互換の全件描画。
   */
  paginated?: boolean;
  /**
   * paginated query の status 絞り込み。Home の view all は "owned" 固定で、
   * wanted を混在させない (count / ページ数も owned のみで算出)。
   */
  statusFilter?: VinylRecord["status"];
};

export function RecordsAllModal({
  label,
  prefix,
  records,
  onClose,
  onRecordClick,
  onAddRecord,
  paginated = false,
  statusFilter,
}: Props) {
  return paginated ? (
    <PaginatedBody
      label={label}
      prefix={prefix}
      statusFilter={statusFilter}
      onClose={onClose}
      onRecordClick={onRecordClick}
      onAddRecord={onAddRecord}
    />
  ) : (
    <StaticBody
      label={label}
      prefix={prefix}
      records={records}
      onClose={onClose}
      onRecordClick={onRecordClick}
      onAddRecord={onAddRecord}
    />
  );
}

// ----------------------------------------------------------------------------

type StaticBodyProps = {
  label: string;
  prefix?: string;
  records: VinylRecord[];
  onClose: () => void;
  onRecordClick: (record: VinylRecord) => void;
  onAddRecord: () => void;
};

function StaticBody({
  label,
  prefix,
  records,
  onClose,
  onRecordClick,
  onAddRecord,
}: StaticBodyProps) {
  return (
    <ModalShell onClose={onClose}>
      <div className="max-h-[92vh] w-[min(92vw,1200px)] overflow-y-auto bg-paper p-8 text-left text-ink shadow-xl ring-1 ring-ink/10">
        <Header label={label} prefix={prefix} count={records.length} />
        <div className="mt-6 grid grid-cols-3 gap-3 sm:grid-cols-4">
          {records.map((r) => (
            <RecordTile key={r.id} record={r} onClick={() => onRecordClick(r)} />
          ))}
          <AddRecordTile onClick={onAddRecord} prominent={records.length === 0} />
        </div>
      </div>
    </ModalShell>
  );
}

// ----------------------------------------------------------------------------

type PaginatedBodyProps = {
  label: string;
  prefix?: string;
  statusFilter?: VinylRecord["status"];
  onClose: () => void;
  onRecordClick: (record: VinylRecord) => void;
  onAddRecord: () => void;
};

function PaginatedBody({
  label,
  prefix,
  statusFilter,
  onClose,
  onRecordClick,
  onAddRecord,
}: PaginatedBodyProps) {
  const { isMobile } = useBreakpoint();
  // モバイル 3×3 / PC 4×2。モバイルは雑誌表紙の 3×3 と Insta 共有を見据えて
  // 9 件固定 (将来テンプレと揃える)。PC は Home プレビュー枚数 (8) と揃えて
  // 4 列 × 2 行。1 ページぶんを「Home に出るとしたらこれ」の枠と読み替えやすい。
  const pageSize = isMobile ? 9 : 8;
  const [page, setPage] = useState(0);

  const query = useQuery({
    queryKey: [
      "records",
      { limit: pageSize, offset: page * pageSize, status: statusFilter },
    ],
    queryFn: () => getVinylRecords(pageSize, page * pageSize, statusFilter),
    placeholderData: keepPreviousData,
  });

  const items = query.data?.items ?? [];
  const total = query.data?.total ?? items.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const isLastPage = page >= pageCount - 1;

  const gridColumns = isMobile ? "grid-cols-3" : "grid-cols-4";

  // pin / display 順は API 側 (pin_order ASC → display_order) で決まり、ここは
  // 並び替えをしない純粋な閲覧グリッド。ピンの ON/OFF は詳細モーダル側に集約。
  return (
    <ModalShell onClose={onClose}>
      <div className="max-h-[92vh] w-[min(92vw,1200px)] overflow-y-auto bg-paper p-8 text-left text-ink shadow-xl ring-1 ring-ink/10">
        <Header label={label} prefix={prefix} count={total} />

        <div className={`mt-6 grid gap-3 ${gridColumns}`}>
          {items.map((r) => (
            <RecordTile key={r.id} record={r} onClick={() => onRecordClick(r)} />
          ))}
          {isLastPage && (
            <AddRecordTile onClick={onAddRecord} prominent={total === 0} />
          )}
        </div>

        <Pager
          page={page}
          pageCount={pageCount}
          onPrev={() => setPage((p) => Math.max(0, p - 1))}
          onNext={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
        />
      </div>
    </ModalShell>
  );
}

// ----------------------------------------------------------------------------

type RecordTileProps = {
  record: VinylRecord;
  onClick: () => void;
};

function RecordTile({ record, onClick }: RecordTileProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={record.title}
      className="block aspect-square w-full cursor-pointer appearance-none bg-transparent p-0 transition-opacity hover:opacity-90"
    >
      <JacketArt record={record} />
    </button>
  );
}

// ----------------------------------------------------------------------------

function Header({
  label,
  prefix,
  count,
}: {
  label: string;
  prefix?: string;
  count: number;
}) {
  return (
    <header className="flex items-baseline gap-3 border-b border-ink/15 pb-4 text-sm">
      {prefix && (
        <>
          <span className="italic text-ink-mute">{prefix}</span>
          <span className="text-ink">/</span>
        </>
      )}
      <span className="font-medium">{label}</span>
      <span className="tabular-nums text-ink-faint">{count}</span>
    </header>
  );
}

function Pager({
  page,
  pageCount,
  onPrev,
  onNext,
}: {
  page: number;
  pageCount: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  if (pageCount <= 1) return null;
  const canPrev = page > 0;
  const canNext = page < pageCount - 1;
  return (
    <div className="mt-6 flex items-center justify-center gap-6 text-sm text-ink-mute">
      <button
        type="button"
        onClick={onPrev}
        disabled={!canPrev}
        aria-label="Previous page"
        className="cursor-pointer appearance-none bg-transparent p-2 transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:text-ink-mute"
      >
        ←
      </button>
      <span className="tabular-nums">
        {page + 1} / {pageCount}
      </span>
      <button
        type="button"
        onClick={onNext}
        disabled={!canNext}
        aria-label="Next page"
        className="cursor-pointer appearance-none bg-transparent p-2 transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:text-ink-mute"
      >
        →
      </button>
    </div>
  );
}
