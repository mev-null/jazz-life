type Props = {
  onClick: () => void;
};

export function AddRecordTile({ onClick }: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="レコードを追加"
      className="flex aspect-square w-full cursor-pointer appearance-none items-center justify-center bg-transparent p-0 text-ink-mute transition-colors hover:bg-ink/5 hover:text-ink"
      style={{ border: "1px dashed rgba(26, 23, 20, 0.3)" }}
    >
      <span className="text-4xl font-light leading-none">+</span>
    </button>
  );
}
