// 実行環境のフラグ・接続先設定。
// VITE_* を読む箇所をここに集約する。

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";
export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
