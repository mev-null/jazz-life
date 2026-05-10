// ====================================================================
// Phase A-？: 認証クライアント
//   ADR §15 / §11（Spotify認証フローの使い分け）に基づく実装。
//
//   設計上の不変条件（Phase B でも維持すること）:
//     1. アクセストークン / リフレッシュトークンはサーバ側のみが保持し、
//        フロントエンドには絶対に渡さない。
//     2. セッションは HttpOnly + SameSite=Lax + Secure cookie で管理する。
//     3. OAuth の state パラメータはサーバ側で発行・検証する（CSRF 防御）。
//     4. 許可される Spotify ID の allowlist 判定はサーバ側で行う。
//        フロントは 401 を受け取ったらログイン画面へ遷移するのみ。
//     5. login のリダイレクト URL は環境変数で固定し、フロントから自由には決めない。
//
//   mock 実装（USE_MOCK=true）はあくまで UI 動作確認用であり、本物の認証ではない。
//   偽トークンを localStorage に持たない（実装ミスで本物を流すリスクを構造的に排除）。
// ====================================================================

import { API_BASE, USE_MOCK } from "../lib/env";
import { STORAGE_KEYS } from "../lib/storageKeys";
import type { AuthUser } from "../types/api";

const MOCK_STORAGE_KEY = STORAGE_KEYS.AUTH_MOCK;

// backend が `/api/auth/*` を実装するまで mock 経路を強制する。Phase B-3 で
// 認証エンドポイントが入ったら true にして USE_MOCK 経由の分岐に戻す。
// `USE_MOCK || !AUTH_BACKEND_READY` のうち後者が真の間は常に mock 側。
const AUTH_BACKEND_READY = false;
const useAuthMock = USE_MOCK || !AUTH_BACKEND_READY;

const MOCK_USER: AuthUser = {
  spotify_id: "owner_mock",
  display_name: "Jazz Life Owner",
  image_url: null,
};

function readMockUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(MOCK_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

/**
 * 現在の認証ユーザを取得。未認証なら null を返す。
 *
 * 実 API: `GET /api/auth/me`（HttpOnly cookie が必要なので credentials: include）
 * mock: localStorage から仮ユーザを取り出す
 */
export async function getMe(): Promise<AuthUser | null> {
  if (useAuthMock) {
    await new Promise((r) => setTimeout(r, 50)); // mimic small latency
    return readMockUser();
  }
  const res = await fetch(`${API_BASE}/api/auth/me`, {
    credentials: "include",
  });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error(`auth/me failed: ${res.status}`);
  return (await res.json()) as AuthUser;
}

/**
 * Spotify ログインを開始する。
 *
 * 実 API: backend の `/api/auth/login` にフルブラウザ遷移させる。
 *   backend が state を発行し、Spotify Authorize エンドポイントへ 302 リダイレクトする。
 *   コールバックは backend の `/api/auth/callback` で受ける（フロントは介在しない）。
 *
 * mock: 仮ユーザを localStorage に保存して即「ログイン済み」状態にする。
 */
export async function login(): Promise<void> {
  if (useAuthMock) {
    localStorage.setItem(MOCK_STORAGE_KEY, JSON.stringify(MOCK_USER));
    return;
  }
  // フルブラウザ遷移（OAuth は SPA 内 fetch では完結しない）
  window.location.href = `${API_BASE}/api/auth/login`;
}

/**
 * ログアウト。
 *
 * 実 API: `POST /api/auth/logout` でサーバ側セッションを破棄、cookie を Set-Cookie で空にする
 * mock: localStorage からエントリ削除
 */
export async function logout(): Promise<void> {
  if (useAuthMock) {
    localStorage.removeItem(MOCK_STORAGE_KEY);
    return;
  }
  const res = await fetch(`${API_BASE}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) throw new Error(`logout failed: ${res.status}`);
}
