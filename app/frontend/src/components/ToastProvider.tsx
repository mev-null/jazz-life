import { createContext, useCallback, useContext, useRef, useState } from "react";
import type { ReactNode } from "react";

/** トーストの表示位置。警告系は下 (既定)、祝事 (棚入れ) は上。 */
type ToastPosition = "top" | "bottom";

type ToastContextValue = {
  /**
   * 短いメッセージを画面中央 (既定 bottom) に出す。~3 秒で自動的に消える。
   * `position: "top"` で上部に出す (棚入れの祝福など、祝事は上・警告は下)。
   */
  showToast: (message: string, options?: { position?: ToastPosition }) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const AUTO_DISMISS_MS = 3000;

/**
 * アプリ共通のトースト基盤。`window.alert` を避け、デザイン（paper/ink・
 * ミニマル）に合わせた小さな通知を画面下中央に出す。ModalShell と同じく
 * portal は使わず fixed div で最前面 (z-[60]) に描画する。
 *
 * 単一トースト方式。新しい `showToast` は前のものを置き換える（積まない）。
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{
    id: number;
    message: string;
    position: ToastPosition;
  } | null>(null);
  const idRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback(
    (message: string, options?: { position?: ToastPosition }) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      idRef.current += 1;
      setToast({
        id: idRef.current,
        message,
        position: options?.position ?? "bottom",
      });
      timerRef.current = setTimeout(() => setToast(null), AUTO_DISMISS_MS);
    },
    [],
  );

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {toast && (
        <div
          aria-live="polite"
          className={`pointer-events-none fixed inset-x-0 z-[60] flex justify-center px-6 ${
            toast.position === "top" ? "top-6" : "bottom-6"
          }`}
        >
          <div
            className={`rounded-full bg-paper px-4 py-2 text-sm text-ink shadow-lg ring-1 ring-ink/15 ${
              toast.position === "top"
                ? "animate-toast-in-top"
                : "animate-toast-in"
            }`}
          >
            {toast.message}
          </div>
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}
