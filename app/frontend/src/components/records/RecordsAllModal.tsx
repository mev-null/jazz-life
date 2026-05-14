import { useMemo, useState } from "react";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  rectSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { getVinylRecords, reorderPins, updateVinylRecord } from "../../api/client";
import { useBreakpoint } from "../../hooks/useBreakpoint";
import type { ListResponse, VinylRecord } from "../../types/api";
import { ModalShell } from "../ModalShell";
import { AddRecordTile } from "./AddRecordTile";
import { JacketArt, PinBadge } from "./JacketCard";

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
   * true で各ジャケ右上に pin トグルを出し、pin 済み行同士の drag & drop で
   * 並び順を変えられる。Home プレビューを編集する手段。`paginated=true` の
   * ときだけ意味があり、内部 query キャッシュを楽観更新する。
   */
  pinningEnabled?: boolean;
};

export function RecordsAllModal({
  label,
  prefix,
  records,
  onClose,
  onRecordClick,
  onAddRecord,
  paginated = false,
  pinningEnabled = false,
}: Props) {
  return paginated ? (
    <PaginatedBody
      label={label}
      prefix={prefix}
      onClose={onClose}
      onRecordClick={onRecordClick}
      onAddRecord={onAddRecord}
      pinningEnabled={pinningEnabled}
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
  onClose: () => void;
  onRecordClick: (record: VinylRecord) => void;
  onAddRecord: () => void;
  pinningEnabled: boolean;
};

function PaginatedBody({
  label,
  prefix,
  onClose,
  onRecordClick,
  onAddRecord,
  pinningEnabled,
}: PaginatedBodyProps) {
  const { isMobile } = useBreakpoint();
  // モバイル 3×3 / PC 4×2。モバイルは雑誌表紙の 3×3 と Insta 共有を見据えて
  // 9 件固定 (将来テンプレと揃える)。PC は Home プレビュー枚数 (8) と揃えて
  // 4 列 × 2 行。1 ページぶんを「Home に出るとしたらこれ」の枠と読み替えやすい。
  const pageSize = isMobile ? 9 : 8;
  const [page, setPage] = useState(0);
  const [pinError, setPinError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["records", { limit: pageSize, offset: page * pageSize }],
    queryFn: () => getVinylRecords(pageSize, page * pageSize),
    placeholderData: keepPreviousData,
  });

  const items = query.data?.items ?? [];
  const total = query.data?.total ?? items.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const isLastPage = page >= pageCount - 1;

  // pin と非 pin を分けて、pin だけ SortableContext に登録する。pin は順序が
  // 全 pinned レコード (pin_order ASC) で決まり、ページネーションとは独立して
  // 1 ページ目の先頭側に固まって表示される (8 件以下 → 必ず先頭ページ内)。
  const pinnedItems = items.filter((r) => r.is_pinned);
  const nonPinnedItems = items.filter((r) => !r.is_pinned);

  const gridColumns = isMobile ? "grid-cols-3" : "grid-cols-4";

  return (
    <ModalShell onClose={onClose}>
      <div className="max-h-[92vh] w-[min(92vw,1200px)] overflow-y-auto bg-paper p-8 text-left text-ink shadow-xl ring-1 ring-ink/10">
        <Header label={label} prefix={prefix} count={total} />

        {pinError && <p className="mt-3 text-sm text-ink-mute">{pinError}</p>}

        <div className={`mt-6 grid gap-3 ${gridColumns}`}>
          <PinDragLayer
            pinnedItems={pinnedItems}
            onRecordClick={onRecordClick}
            pinningEnabled={pinningEnabled}
            onPinError={setPinError}
          />
          {nonPinnedItems.map((r) => (
            <RecordTile
              key={r.id}
              record={r}
              onClick={() => onRecordClick(r)}
              pinningEnabled={pinningEnabled}
              onPinError={setPinError}
            />
          ))}
          {isLastPage && (
            <AddRecordTile onClick={onAddRecord} prominent={total === 0} />
          )}
        </div>

        <Pager
          page={page}
          pageCount={pageCount}
          onPrev={() => {
            setPinError(null);
            setPage((p) => Math.max(0, p - 1));
          }}
          onNext={() => {
            setPinError(null);
            setPage((p) => Math.min(pageCount - 1, p + 1));
          }}
        />
      </div>
    </ModalShell>
  );
}

// ----------------------------------------------------------------------------

type PinDragLayerProps = {
  pinnedItems: VinylRecord[];
  onRecordClick: (record: VinylRecord) => void;
  pinningEnabled: boolean;
  onPinError: (message: string) => void;
};

/**
 * pinned レコード同士を drag & drop で並び替える領域。SortableContext は
 * pinned id 配列だけを管理する。非 pin 行は親側で別途描画されるので、ここの
 * children には pin 行だけ並べる。
 */
function PinDragLayer({
  pinnedItems,
  onRecordClick,
  pinningEnabled,
  onPinError,
}: PinDragLayerProps) {
  const queryClient = useQueryClient();

  // 5px 動かさないと drag 開始 → タイル内ボタンのクリック (ピントグル / 詳細)
  // が誤発火しない。Touch sensor は 200ms 長押しで起動 (スクロールと両立)。
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 200, tolerance: 5 },
    }),
  );

  const ids = useMemo(() => pinnedItems.map((r) => r.id), [pinnedItems]);

  const reorderMutation = useMutation({
    mutationFn: (orderedIds: string[]) => reorderPins(orderedIds),
    onMutate: async (orderedIds: string[]) => {
      await queryClient.cancelQueries({ queryKey: ["records"] });
      const snapshots = queryClient.getQueriesData<ListResponse<VinylRecord>>({
        queryKey: ["records"],
      });
      // 楽観更新: 各 records cache の items 内で pinned 行を orderedIds 順に
      // 並べ替え、新しい pin_order を 1..N で振り直す。非 pin 行は不動。
      for (const [key, data] of snapshots) {
        if (!data) continue;
        const pinned = data.items.filter((r) => r.is_pinned);
        const nonPinned = data.items.filter((r) => !r.is_pinned);
        const reorderedPinned: VinylRecord[] = orderedIds.flatMap((id, idx) => {
          const found = pinned.find((r) => r.id === id);
          return found ? [{ ...found, pin_order: idx + 1 }] : [];
        });
        queryClient.setQueryData<ListResponse<VinylRecord>>(key, {
          ...data,
          items: [...reorderedPinned, ...nonPinned],
        });
      }
      return { snapshots };
    },
    onError: (_err, _vars, ctx) => {
      for (const [key, data] of ctx?.snapshots ?? []) {
        queryClient.setQueryData(key, data);
      }
      onPinError("並び順の保存に失敗しました。");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["records"] });
    },
  });

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = ids.indexOf(String(active.id));
    const newIndex = ids.indexOf(String(over.id));
    if (oldIndex < 0 || newIndex < 0) return;
    const next = arrayMove(ids, oldIndex, newIndex);
    reorderMutation.mutate(next);
  }

  if (pinnedItems.length === 0) return null;

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <SortableContext items={ids} strategy={rectSortingStrategy}>
        {pinnedItems.map((r) => (
          <SortablePinTile
            key={r.id}
            record={r}
            onClick={() => onRecordClick(r)}
            pinningEnabled={pinningEnabled}
            onPinError={onPinError}
          />
        ))}
      </SortableContext>
    </DndContext>
  );
}

// ----------------------------------------------------------------------------

type SortablePinTileProps = {
  record: VinylRecord;
  onClick: () => void;
  pinningEnabled: boolean;
  onPinError: (message: string) => void;
};

function SortablePinTile({
  record,
  onClick,
  pinningEnabled,
  onPinError,
}: SortablePinTileProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: record.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    // drag 中のタイルだけ前面に出して下のタイルにテキスト等が透けるのを防ぐ
    zIndex: isDragging ? 10 : "auto",
    opacity: isDragging ? 0.85 : 1,
  } as const;

  return (
    <div ref={setNodeRef} style={style} className="relative touch-none">
      <button
        type="button"
        onClick={onClick}
        aria-label={record.title}
        // listeners + attributes は タイル全体に当てて、どこをつかんでも drag
        // 可能にする。activationConstraint=5px のおかげで click は通る。
        {...listeners}
        {...attributes}
        className="block aspect-square w-full cursor-grab appearance-none bg-transparent p-0 transition-opacity hover:opacity-90 active:cursor-grabbing"
      >
        <JacketArt record={record} />
      </button>
      {pinningEnabled ? (
        <PinToggleButton record={record} onPinError={onPinError} pinned />
      ) : (
        <PinBadge />
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------

type RecordTileProps = {
  record: VinylRecord;
  onClick: () => void;
  pinningEnabled?: boolean;
  onPinError?: (message: string) => void;
};

function RecordTile({
  record,
  onClick,
  pinningEnabled = false,
  onPinError,
}: RecordTileProps) {
  return (
    <div className="relative">
      <button
        type="button"
        onClick={onClick}
        aria-label={record.title}
        className="block aspect-square w-full cursor-pointer appearance-none bg-transparent p-0 transition-opacity hover:opacity-90"
      >
        <JacketArt record={record} />
      </button>
      {pinningEnabled && onPinError && (
        <PinToggleButton
          record={record}
          onPinError={onPinError}
          pinned={record.is_pinned}
        />
      )}
    </div>
  );
}

// ----------------------------------------------------------------------------

type PinToggleButtonProps = {
  record: VinylRecord;
  onPinError: (message: string) => void;
  /** 表示状態。`record.is_pinned` を渡すが、drag 中など override したい時用 */
  pinned: boolean;
};

function PinToggleButton({ record, onPinError, pinned }: PinToggleButtonProps) {
  const queryClient = useQueryClient();

  const togglePin = useMutation({
    mutationFn: () =>
      updateVinylRecord(record.id, { is_pinned: !record.is_pinned }),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ["records"] });
      const snapshots = queryClient.getQueriesData<ListResponse<VinylRecord>>({
        queryKey: ["records"],
      });
      for (const [key, data] of snapshots) {
        if (!data) continue;
        queryClient.setQueryData<ListResponse<VinylRecord>>(key, {
          ...data,
          items: data.items.map((r) =>
            r.id === record.id ? { ...r, is_pinned: !r.is_pinned } : r,
          ),
        });
      }
      return { snapshots };
    },
    onError: (err, _vars, ctx) => {
      for (const [key, data] of ctx?.snapshots ?? []) {
        queryClient.setQueryData(key, data);
      }
      const msg =
        err instanceof Error && /pin limit/i.test(err.message)
          ? "ピンは最大 8 枚までです。"
          : "ピンの更新に失敗しました。";
      onPinError(msg);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["records"] });
    },
  });

  return (
    <button
      type="button"
      onClick={(e) => {
        // SortablePinTile では drag listener が同じ階層にいるので、トグルが
        // drag に消されないよう pointerDown 段階で握りつぶす。
        e.stopPropagation();
        togglePin.mutate();
      }}
      onPointerDown={(e) => e.stopPropagation()}
      disabled={togglePin.isPending}
      aria-label={pinned ? "Unpin" : "Pin"}
      aria-pressed={pinned}
      className={`absolute right-1.5 top-1.5 flex size-6 cursor-pointer items-center justify-center rounded-full text-[11px] leading-none shadow transition-colors ${
        pinned
          ? "bg-ink text-paper"
          : "bg-paper/85 text-ink/70 hover:bg-paper hover:text-ink"
      } disabled:cursor-wait disabled:opacity-60`}
    >
      ★
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
