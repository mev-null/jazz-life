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

/**
 * 右上に配置する pin インジケータ。`record.is_pinned` 時に Home プレビューや
 * 一覧で「これは pin 済み」を示す。
 *
 * RecordsAllModal の pin **トグル** とは別の責務 (こちらは表示のみ、トグルは
 * モーダル側の button)。両者で同じ位置に出して認知を揃える。
 */
export function PinBadge() {
  return (
    <span
      aria-label="pinned"
      className="pointer-events-none absolute right-1.5 top-1.5 flex size-5 items-center justify-center rounded-full bg-ink/80 text-[10px] leading-none text-paper shadow"
    >
      ★
    </span>
  );
}

type JacketCardProps = {
  record: VinylRecord;
  onClick: () => void;
};

export function JacketCard({ record, onClick }: JacketCardProps) {
  // HomePage プレビューはピン状態を表示しない (★ だけ出ても解釈できないため、
  // ピン UI は RecordsAllModal 側に集約)。PinBadge は RecordsAllModal が
  // 直接組み立てるので、こちらは純粋に「ジャケ + クリック」だけを担う。
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
