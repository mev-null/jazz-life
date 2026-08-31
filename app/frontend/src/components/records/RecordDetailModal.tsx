import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getVinylRecords, updateVinylRecord } from "../../api/client";
import { formatReleaseDate } from "../../lib/dates";
import { PIN_LIMIT } from "../../lib/pins";
import type { ListResponse, VinylRecord } from "../../types/api";
import { useShelfWelcome } from "../../hooks/useShelfWelcome";
import { ModalShell } from "../ModalShell";
import { useToast } from "../ToastProvider";
import { JacketArt } from "./JacketCard";

function PencilIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
      <path d="m15 5 4 4" />
    </svg>
  );
}

function BackFace({
  record,
  artistName,
  footerAction,
  pinToggle,
}: {
  record: VinylRecord;
  artistName?: string;
  // wanted record の「買った」ボタンを footer 内に流す用のスロット。
  // absolute 配置だと footer の border-t と重なるのでここに渡す。
  footerAction?: ReactNode;
  // ピントグル (★) を流すスロット。ジャケ写真には重ねず、ヘッダー下の
  // メタ情報セクション右上に absolute で出す。
  pinToggle?: ReactNode;
}) {
  return (
    <div className="flex h-full flex-col bg-paper p-8 text-left text-ink shadow-xl ring-1 ring-ink/10">
      <header className="flex items-start gap-4 border-b border-ink/15 pb-4">
        <div className="min-w-0 flex-1">
          <div className="text-2xl font-medium leading-tight">
            {record.title}
          </div>
          <div className="mt-1 text-base text-ink-mute">
            {artistName ?? "—"}
          </div>
        </div>
        <div className="aspect-square w-20 shrink-0 overflow-hidden">
          <JacketArt record={record} />
        </div>
      </header>

      <div className="relative flex-1 space-y-3 py-5 pr-8 text-[15px] leading-relaxed">
        {pinToggle && (
          <div className="absolute right-0 top-3">{pinToggle}</div>
        )}
        {(() => {
          const released = formatReleaseDate(record.original_release_date);
          const pressing = record.pressing_info ?? "";
          if (!released && !pressing) return null;
          return (
            <div className="text-ink-mute">
              {released}
              {released && pressing && " · "}
              {pressing}
            </div>
          );
        })()}
        {record.memo && (
          <p className="italic leading-relaxed text-ink-mute">
            “{record.memo}”
          </p>
        )}
        {record.favorite_tracks.length > 0 && (
          <div>
            <div className="italic text-ink-mute">Favorites</div>
            <div className="whitespace-pre-line leading-relaxed text-ink">
              {record.favorite_tracks.map((t) => t.track_name).join("\n")}
            </div>
          </div>
        )}
      </div>

      <footer className="flex items-end justify-between gap-4 border-t border-ink/15 pt-4 text-sm leading-relaxed text-ink-mute">
        <div className="min-w-0 flex-1">
          {/* wanted (On the hunt) はまだ買っていない状態なので、購入場所 /
              購入日は伏せる。owned のみ表示する。 */}
          {record.status !== "wanted" && record.purchase_store && (
            <div>{record.purchase_store}</div>
          )}
          {record.status !== "wanted" && record.purchase_date && (
            <div>{record.purchase_date}</div>
          )}
        </div>
        {footerAction}
      </footer>
    </div>
  );
}

type PinToggleButtonProps = {
  record: VinylRecord;
};

/**
 * 詳細モーダル内のピントグル。`["records"]` 全クエリを楽観更新し、Home プレビュー
 * にも即座に反映する。上限 (PIN_LIMIT) 到達時は未 pin の ★ を「非活性」見た目に
 * し、タップでトースト通知して mutate しない (ADR-015)。
 */
function PinToggleButton({ record }: PinToggleButtonProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  // 親から渡る `record` はモーダルを開いた時点のスナップショットなので、
  // is_pinned はライブの `["records"]` キャッシュから引き直す。これにより
  // 楽観更新 (onMutate) 後に ★ の表示とトグル対象が即座に追従する
  // (スナップショット参照だと開いたまま操作しても反映されない)。
  const { data } = useQuery({
    queryKey: ["records"],
    queryFn: () => getVinylRecords(),
  });
  const live = data?.items.find((r) => r.id === record.id);
  const pinned = live?.is_pinned ?? record.is_pinned;
  // 未 pin かつ枠が満杯なら「これ以上 pin できない」状態。
  const pinnedCount = data?.items.filter((r) => r.is_pinned).length ?? 0;
  const atLimit = !pinned && pinnedCount >= PIN_LIMIT;

  const togglePin = useMutation({
    mutationFn: () => updateVinylRecord(record.id, { is_pinned: !pinned }),
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
          ? `You can pin up to ${PIN_LIMIT} records.`
          : "Could not update the pin.";
      showToast(msg);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["records"] });
    },
  });

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        if (togglePin.isPending) return;
        // 上限到達時は mutate せず、理由をトーストで知らせる。HTML disabled に
        // すると onClick が発火せずモバイルで理由を出せないため、見た目だけ
        // 非活性にして onClick は生かす。
        if (atLimit) {
          showToast(`You can pin up to ${PIN_LIMIT} records.`);
          return;
        }
        togglePin.mutate();
      }}
      aria-label={pinned ? "Unpin" : "Pin"}
      aria-pressed={pinned}
      aria-disabled={atLimit}
      title={atLimit ? `You can pin up to ${PIN_LIMIT} records` : undefined}
      className={`flex size-6 cursor-pointer items-center justify-center rounded-full text-[11px] leading-none shadow transition-colors ${
        pinned
          ? "bg-ink text-paper"
          : "bg-paper/85 text-ink/70 ring-1 ring-ink/15 hover:bg-paper hover:text-ink"
      } ${atLimit ? "cursor-not-allowed opacity-40 hover:bg-paper/85 hover:text-ink/70" : ""} ${
        togglePin.isPending ? "cursor-wait opacity-60" : ""
      }`}
    >
      ★
    </button>
  );
}

type Props = {
  record: VinylRecord | null;
  artistName?: string;
  onClose: () => void;
  onEdit?: () => void;
};

export function RecordDetailModal({
  record,
  artistName,
  onClose,
  onEdit,
}: Props) {
  const queryClient = useQueryClient();
  const celebrateShelf = useShelfWelcome();
  // wanted → owned 昇格用 mutation。Want list (ArtistDetailModal の拡大表示)
  // で詳細を開いた時にだけボタンが見える前提。Home は owned のみ表示なので
  // status === "wanted" の判定で自然に出ない。
  const markOwned = useMutation({
    mutationFn: (id: string) => updateVinylRecord(id, { status: "owned" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["records"] });
      void celebrateShelf(); // 棚入れの祝福 (ADR-017)
      onClose();
    },
  });
  if (!record) return null;

  const markOwnedButton =
    record.status === "wanted" ? (
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          markOwned.mutate(record.id);
        }}
        disabled={markOwned.isPending}
        aria-label="To the shelf"
        className="shrink-0 cursor-pointer bg-ink/10 px-3 py-1.5 text-sm text-ink transition-colors hover:bg-ink/20 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {markOwned.isPending ? "Moving…" : "To the shelf"}
      </button>
    ) : undefined;

  // ピンは Home (owned) のコレクション概念。wanted には出さない (編集鉛筆と同条件)。
  const pinToggle =
    record.status !== "wanted" ? <PinToggleButton record={record} /> : undefined;

  return (
    <ModalShell onClose={onClose}>
      <div className="relative aspect-square w-[min(72vh,90vw,440px)]">
        <BackFace
          record={record}
          artistName={artistName}
          footerAction={markOwnedButton}
          pinToggle={pinToggle}
        />
        {onEdit && record.status !== "wanted" && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onEdit();
            }}
            aria-label="Edit"
            className="absolute bottom-4 right-4 cursor-pointer p-1 text-ink-mute transition-colors hover:text-ink"
          >
            <PencilIcon />
          </button>
        )}
      </div>
    </ModalShell>
  );
}
