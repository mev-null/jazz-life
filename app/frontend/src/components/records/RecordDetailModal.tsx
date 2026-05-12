import type { ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { updateVinylRecord } from "../../api/client";
import { formatReleaseDate } from "../../lib/dates";
import type { VinylRecord } from "../../types/api";
import { ModalShell } from "../ModalShell";
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
}: {
  record: VinylRecord;
  artistName?: string;
  // wanted record の「買った」ボタンを footer 内に流す用のスロット。
  // absolute 配置だと footer の border-t と重なるのでここに渡す。
  footerAction?: ReactNode;
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

      <div className="flex-1 space-y-3 py-5 text-[15px] leading-relaxed">
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
        {record.favorite_tracks && (
          <div>
            <div className="italic text-ink-mute">Favorites</div>
            <div className="leading-relaxed text-ink">
              {record.favorite_tracks}
            </div>
          </div>
        )}
      </div>

      <footer className="flex items-end justify-between gap-4 border-t border-ink/15 pt-4 text-sm leading-relaxed text-ink-mute">
        <div className="min-w-0 flex-1">
          {record.purchase_store && <div>{record.purchase_store}</div>}
          {record.purchase_date && <div>{record.purchase_date}</div>}
        </div>
        {footerAction}
      </footer>
    </div>
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
  // wanted → owned 昇格用 mutation。Want list (ArtistDetailModal の拡大表示)
  // で詳細を開いた時にだけボタンが見える前提。Home は owned のみ表示なので
  // status === "wanted" の判定で自然に出ない。
  const markOwned = useMutation({
    mutationFn: (id: string) => updateVinylRecord(id, { status: "owned" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["records"] });
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
        aria-label="On the shelf"
        className="shrink-0 cursor-pointer bg-ink/10 px-3 py-1.5 text-sm text-ink transition-colors hover:bg-ink/20 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {markOwned.isPending ? "Moving…" : "On the shelf"}
      </button>
    ) : undefined;

  return (
    <ModalShell onClose={onClose}>
      <div className="relative aspect-square w-[min(72vh,520px)]">
        <BackFace
          record={record}
          artistName={artistName}
          footerAction={markOwnedButton}
        />
        {onEdit && (
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
