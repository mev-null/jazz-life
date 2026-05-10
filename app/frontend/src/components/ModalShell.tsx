import { useEffect } from "react";
import type { ReactNode } from "react";

type Props = {
  onClose: () => void;
  children: ReactNode;
};

/**
 * モーダルの共通フレーム。
 *
 *  - 紙背景 85% 透過 + blur 8px のバックドロップ
 *  - バックドロップクリックで onClose
 *  - Escape で onClose
 *  - children は中央配置のラッパ内に置かれ、クリックは backdrop に伝播しない
 *
 * 使用側は「開いている時のみ <ModalShell> をレンダリング」する責務を持つ
 * （未開時に null を返すか、条件レンダリングする）。
 * これにより本コンポーネントは状態を持たず、合成しやすい。
 */
export function ModalShell({ onClose, children }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{
        backgroundColor: "rgba(244, 239, 227, 0.85)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
      }}
    >
      <div onClick={(e) => e.stopPropagation()}>{children}</div>
    </div>
  );
}
