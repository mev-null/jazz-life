import { useState } from "react";
import type { ReactNode } from "react";

type Props = {
  /** 初期トリガーボタンのラベル (例: "Delete", "Remove from follow")。 */
  triggerLabel: string;
  /** Confirm 状態で表示する説明文 (例: "Delete this record?")。 */
  prompt: ReactNode;
  /** Confirm ボタンのラベル。 */
  confirmLabel?: string;
  /** mutation 実行中に表示するラベル。 */
  pendingLabel?: string;
  /** 実行ハンドラ。確認後に呼ばれる。`onConfirm` 実行で外側が isPending を立てる。 */
  onConfirm: () => void;
  /** mutation 進行中フラグ (両ボタン disable & ラベル切替に使う)。 */
  isPending?: boolean;
  /** トリガーボタンを非活性にする (例: 関連リソースが残っている時)。 */
  disabled?: boolean;
  /** disabled の時に併記する小さなヒント文。 */
  disabledHint?: ReactNode;
  /** 外側 div 用クラス。flex の方向や位置寄せは呼び出し側で指定する。 */
  className?: string;
};

/**
 * 「ボタンを押す → 同じ場所で `prompt + Cancel + Confirm` の確認 UI に切替」
 * を一括で実装するコンポーネント。`window.confirm()` を避けて UI 内に
 * 自前のインライン確認パネルを出すスタイル。
 *
 * ArtistDetailModal の Remove from follow / RecordFormModal の Delete の両方で
 * 同じパターンを共有するため抽出。位置 (左寄せ / 右寄せ) と「disabled 時の
 * hint」はそれぞれ違うので props で外から渡す。
 */
export function InlineConfirm({
  triggerLabel,
  prompt,
  confirmLabel = "Confirm",
  pendingLabel = "…",
  onConfirm,
  isPending = false,
  disabled = false,
  disabledHint,
  className,
}: Props) {
  const [confirming, setConfirming] = useState(false);
  // disabled 状態のトリガー (記録があるアーティストの Remove 等) は確認 UI に
  // 入れないようにする。disabled が真なら強制的に trigger 表示に戻す。
  const showTrigger = !confirming || disabled;
  if (showTrigger) {
    // disabled な時はボタンを隠して、代わりに disabledHint をボタンの位置に
    // 出す (ボタンが押せないことを示しつつ、ユーザが取るべき次の行動を見せる)。
    if (disabled && disabledHint) {
      return (
        <div className={className ?? "flex items-center gap-3"}>
          <span className="italic text-ink-faint">{disabledHint}</span>
        </div>
      );
    }
    return (
      <div className={className ?? "flex items-center gap-3"}>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={disabled}
          className="cursor-pointer italic text-ink-mute transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
        >
          {triggerLabel}
        </button>
      </div>
    );
  }
  return (
    <div className={className ?? "flex items-center gap-4"}>
      <span className="italic text-ink-mute">{prompt}</span>
      <button
        type="button"
        onClick={() => setConfirming(false)}
        disabled={isPending}
        className="cursor-pointer text-ink-mute transition-colors hover:text-ink disabled:opacity-50"
      >
        Cancel
      </button>
      <button
        type="button"
        onClick={onConfirm}
        disabled={isPending}
        className="cursor-pointer font-medium text-ink underline decoration-ink-faint underline-offset-4 transition-opacity hover:opacity-70 disabled:opacity-50"
      >
        {isPending ? pendingLabel : confirmLabel}
      </button>
    </div>
  );
}
