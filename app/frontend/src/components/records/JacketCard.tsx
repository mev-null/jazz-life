import { sleeveTintByKey } from "../../lib/palette";
import type { VinylRecord } from "../../types/api";

export function SleeveFallback({ record }: { record: VinylRecord }) {
  return (
    <div
      className="h-full w-full"
      style={{ backgroundColor: sleeveTintByKey(record.id) }}
    />
  );
}

export function JacketArt({ record }: { record: VinylRecord }) {
  if (record.image_url) {
    return (
      <img
        src={record.image_url}
        alt=""
        className="h-full w-full object-cover"
      />
    );
  }
  return <SleeveFallback record={record} />;
}

type JacketCardProps = {
  record: VinylRecord;
  onClick: () => void;
  // true で「高さ基準の正方形」にする (利用可能な高さに収める mobile showcase 用)。
  // 既定は従来どおり横幅基準 (w-full)。
  fillHeight?: boolean;
};

export function JacketCard({ record, onClick, fillHeight = false }: JacketCardProps) {
  // HomePage プレビューはピン状態を表示しない (★ だけ出ても解釈できないため、
  // ピンの ON/OFF は詳細モーダル RecordDetailModal に集約)。ここは純粋に
  // 「ジャケ + クリック」だけを担う。
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={record.title}
      className={`block aspect-square cursor-pointer appearance-none bg-transparent p-0 transition-opacity hover:opacity-90 ${
        fillHeight ? "h-full" : "w-full"
      }`}
    >
      <JacketArt record={record} />
    </button>
  );
}
