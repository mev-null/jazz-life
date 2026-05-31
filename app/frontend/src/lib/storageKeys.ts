// ブラウザストレージで使うキーを一覧化する。
// 同じプレフィックス `jazz-life:` をベースに、用途で分ける。

export const STORAGE_KEYS = {
  /** mock 認証で使用するユーザ情報。本物のトークンは保存しない */
  AUTH_MOCK: "jazz-life:auth-mock",
  /** demo の機能ツアーを一度見たかどうか (初回自動起動の抑制に使う) */
  TOUR_SEEN: "jazz-life:tour-seen",
} as const;
