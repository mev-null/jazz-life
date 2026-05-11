import type { Artist, VinylRecord } from "../../types/api";
import { ModalShell } from "../ModalShell";
import { AddRecordTile } from "../records/AddRecordTile";
import { JacketArt } from "../records/JacketCard";

type Props = {
  artist: Artist;
  records: VinylRecord[];
  status: "owned" | "wanted";
  onClose: () => void;
  onRecordClick: (record: VinylRecord) => void;
  onAddRecord: (artist: Artist, status: "owned" | "wanted") => void;
};

/**
 * ArtistDetailModal の Records / Want list セクションが 4 件以上のとき開く
 * 「拡大表示」モーダル。detail modal の上にスタックして全件をグリッド表示し、
 * 末尾に AddRecordTile を置く。
 *
 * detail modal 側で件数によってグリッドの末尾「+」を出すかどうかが変わる
 * (≤3 件は detail に「+」を出す、≥4 件は隠す) のとは独立に、こちらは
 * 常に末尾に「+」タイルを出す。「ここは編集ビューだ」というメタファに揃える。
 */
export function ArtistRecordsAllModal({
  artist,
  records,
  status,
  onClose,
  onRecordClick,
  onAddRecord,
}: Props) {
  const label = status === "owned" ? "Records" : "Want list";
  return (
    <ModalShell onClose={onClose}>
      <div className="max-h-[92vh] w-[min(96vw,1200px)] overflow-y-auto bg-paper p-8 text-left text-ink shadow-xl ring-1 ring-ink/10">
        <header className="flex items-baseline gap-3 border-b border-ink/15 pb-4 text-sm">
          <span className="text-ink-mute italic">{artist.name}</span>
          <span className="text-ink">/</span>
          <span className="font-medium">{label}</span>
          <span className="text-ink-faint tabular-nums">{records.length}</span>
        </header>

        <div className="mt-6 grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6">
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
            onClick={() => onAddRecord(artist, status)}
            prominent={records.length === 0}
          />
        </div>
      </div>
    </ModalShell>
  );
}
