type Props = {
  onClick: () => void;
};

export function AddRecordTile({ onClick }: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="レコードを追加"
      className="flex aspect-square w-full cursor-pointer appearance-none items-center justify-center bg-transparent p-0 text-ink-mute opacity-0 transition duration-200 hover:bg-ink/5 hover:text-ink hover:opacity-100 focus-visible:opacity-100"
      style={{ border: "1px dashed rgba(26, 23, 20, 0.3)" }}
    >
      <span className="text-4xl font-light leading-none">+</span>
    </button>
  );
}
