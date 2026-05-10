import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../lib/useAuth";

/**
 * 認証が確認できるまで子要素をレンダリングしない。未認証なら /login へ。
 *
 * セキュリティ上の注意:
 *   フロント側のこの判定は UX のためのものであり、保護の最終判断はサーバ側で行う。
 *   API 呼び出しが 401 を返したら useAuth が null を保持するため、ガードがすり抜ける
 *   ことはない。
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm italic text-ink-faint">loading…</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
