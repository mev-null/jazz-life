import type { VinylRecord } from "../../types/api";
import { ModalShell } from "../ModalShell";
import { AddRecordTile } from "./AddRecordTile";
import { JacketArt } from "./JacketCard";

type Props = {
  /** メインのセクションラベル ("Records" / "On the shelf" / "On the hunt" 等)。 */
  label: string;
  /** label の左に italic で出すアーティスト名等のプレフィクス。省略時は出ない。 */
  prefix?: string;
  records: VinylRecord[];
  onClose: () => void;
  onRecordClick: (record: VinylRecord) => void;
  onAddRecord: () => void;
};

/**
 * 「view all 拡大表示」モーダル。HomePage の Records プレビューと
 * ArtistDetailModal の On the shelf / On the hunt プレビューで共有する。
 *
 * 仕様:
 * - グリッドは 4 列固定 (sm+)。元のプレビュー (Home 4 列 / ArtistDetail 4 列) と揃える
 * - 末尾に AddRecordTile を置いて、プレビューでは消えた「+」追加導線を担う
 * - prefix が渡されたときだけ「{prefix} / {label}」のパンくず表示にする
 */
export function RecordsAllModal({
  label,
  prefix,
  records,
  onClose,
  onRecordClick,
  onAddRecord,
}: Props) {
  return (
    <ModalShell onClose={onClose}>
      <div className="max-h-[92vh] w-[min(92vw,1200px)] overflow-y-auto bg-paper p-8 text-left text-ink shadow-xl ring-1 ring-ink/10">
        <header className="flex items-baseline gap-3 border-b border-ink/15 pb-4 text-sm">
          {prefix && (
            <>
              <span className="text-ink-mute italic">{prefix}</span>
              <span className="text-ink">/</span>
            </>
          )}
          <span className="font-medium">{label}</span>
          <span className="text-ink-faint tabular-nums">{records.length}</span>
        </header>

        <div className="mt-6 grid grid-cols-3 gap-3 sm:grid-cols-4">
          {records.map((r) => (
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
          <AddRecordTile
            onClick={onAddRecord}
            prominent={records.length === 0}
          />
        </div>
      </div>
    </ModalShell>
  );
}
