import { useSyncExternalStore } from "react";

import { STORAGE_KEYS } from "./storageKeys";

const STORAGE_KEY = STORAGE_KEYS.READ;

function loadInitial(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw) as string[]);
  } catch {
    return new Set();
  }
}

// モジュールレベルの singleton。複数の useReadState() インスタンス間で
// 状態を共有し、片側の markRead が即座に他方の UI に反映されるようにする。
let currentSet: Set<string> = loadInitial();
const listeners = new Set<() => void>();

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...currentSet]));
  } catch {
    /* ignore quota / disabled storage */
  }
}

function notify() {
  for (const l of listeners) l();
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

function getSnapshot() {
  return currentSet;
}

/**
 * 既読状態を localStorage で永続化するフック。
 *
 * key の規約: `${kind}:${id}` （例: `release:release_001`, `concert:blue_note_tokyo_...`）
 *
 * 状態はモジュール singleton で共有する。同一 SPA セッション内で複数のページ /
 * コンポーネントから呼ばれても整合する。
 *
 * Phase B でバックエンドが立ったら read_at を DB に保存する設計に差し替え可能。
 * その時はこのフック内部だけ書き換えれば呼び出し側は変えなくて済む。
 */
export function useReadState() {
  const set = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  function isRead(key: string): boolean {
    return set.has(key);
  }

  function markRead(key: string) {
    if (currentSet.has(key)) return;
    const next = new Set(currentSet);
    next.add(key);
    currentSet = next;
    persist();
    notify();
  }

  function markUnread(key: string) {
    if (!currentSet.has(key)) return;
    const next = new Set(currentSet);
    next.delete(key);
    currentSet = next;
    persist();
    notify();
  }

  return { isRead, markRead, markUnread };
}
