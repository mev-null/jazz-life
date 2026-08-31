type Props = {
  onClick: () => void;
  /**
   * `true` のとき hover を待たず常時表示する。Records 一覧が 0 件の時は
   * hover で初めて出現する隠れタイルだとユーザに追加導線が見えないため、
   * empty state を検知した HomePage 側からこのフラグを立てて目立たせる。
   */
  prominent?: boolean;
  // true で高さ基準の正方形にする (mobile showcase で利用可能な高さに収める用)。
  fillHeight?: boolean;
};

export function AddRecordTile({
  onClick,
  prominent = false,
  fillHeight = false,
}: Props) {
  const visibility = prominent
    ? "text-ink opacity-100"
    : "text-ink-mute opacity-0 hover:text-ink hover:opacity-100 focus-visible:opacity-100";
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Add a record"
      className={`flex aspect-square cursor-pointer appearance-none items-center justify-center bg-transparent p-0 transition duration-200 hover:bg-ink/5 ${fillHeight ? "h-full" : "w-full"} ${visibility}`}
      style={{ border: "1px dashed rgba(26, 23, 20, 0.3)" }}
    >
      <span className="text-4xl font-light leading-none">+</span>
    </button>
  );
}
