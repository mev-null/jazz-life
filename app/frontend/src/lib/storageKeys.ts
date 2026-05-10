// ブラウザストレージで使うキーを一覧化する。
// 同じプレフィックス `jazz-life:` をベースに、用途で分ける。

export const STORAGE_KEYS = {
  /** Feed の既読状態。値は `${kind}:${id}` の文字列配列 (JSON) */
  READ: "jazz-life:read",
  /** mock 認証で使用するユーザ情報。本物のトークンは保存しない */
  AUTH_MOCK: "jazz-life:auth-mock",
} as const;
