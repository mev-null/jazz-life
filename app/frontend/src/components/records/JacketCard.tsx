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
};

export function JacketCard({ record, onClick }: JacketCardProps) {
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
