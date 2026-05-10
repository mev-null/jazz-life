import { useState } from "react";

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

/**
 * 既読状態を localStorage で永続化するフック。
 *
 * key の規約: `${kind}:${id}` （例: `release:release_001`, `concert:blue_note_tokyo_...`）
 *
 * Phase B でバックエンドが立ったら read_at を DB に保存する設計に差し替え可能。
 * その時はこのフック内部だけ書き換えれば呼び出し側は変えなくて済む。
 */
export function useReadState() {
  const [readSet, setReadSet] = useState<Set<string>>(loadInitial);

  function isRead(key: string): boolean {
    return readSet.has(key);
  }

  function markRead(key: string) {
    setReadSet((prev) => {
      if (prev.has(key)) return prev;
      const next = new Set(prev);
      next.add(key);
      persist(next);
      return next;
    });
  }

  function markUnread(key: string) {
    setReadSet((prev) => {
      if (!prev.has(key)) return prev;
      const next = new Set(prev);
      next.delete(key);
      persist(next);
      return next;
    });
  }

  return { isRead, markRead, markUnread };
}

function persist(set: Set<string>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...set]));
  } catch {
    /* ignore quota / disabled storage */
  }
}
