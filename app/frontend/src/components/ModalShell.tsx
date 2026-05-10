import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

type Props = {
  onClose: () => void;
  children: ReactNode;
};

// マウント順スタック。Escape は最後にマウントされた（= 最前面）モーダルだけが受ける。
// ネストモーダル時に Escape で複数階層が同時に閉じる事故を防ぐ。
const modalStack: symbol[] = [];

/**
 * モーダルの共通フレーム。
 *
 *  - 紙背景 85% 透過 + blur 8px のバックドロップ
 *  - バックドロップクリックで onClose
 *  - Escape で onClose（ただし最前面モーダルのみ）
 *  - children は中央配置のラッパ内に置かれ、クリックは backdrop に伝播しない
 *
 * 使用側は「開いている時のみ <ModalShell> をレンダリング」する責務を持つ
 * （未開時に null を返すか、条件レンダリングする）。
 * これにより本コンポーネントは状態を持たず、合成しやすい。
 */
export function ModalShell({ onClose, children }: Props) {
  // 最新の onClose を ref で保持。effect は mount/unmount でのみ走らせ、
  // onClose の参照変化で stack が再編されないようにする。
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const id = Symbol("modal");
    modalStack.push(id);
    const handler = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (modalStack[modalStack.length - 1] !== id) return;
      onCloseRef.current();
    };
    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
      const idx = modalStack.indexOf(id);
      if (idx >= 0) modalStack.splice(idx, 1);
    };
  }, []);

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
