import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  followArtist,
  searchSpotifyArtists,
  upsertArtist,
} from "../../api/client";
import type { SpotifyArtistSummary } from "../../api/generated/model";
import { USE_MOCK } from "../../lib/env";
import { ModalShell } from "../ModalShell";

type Props = {
  open: boolean;
  onClose: () => void;
};

const inputClass =
  "w-full border-b border-ink-faint bg-transparent py-1.5 text-[15px] text-ink placeholder:text-ink-faint focus:border-ink focus:outline-none";

/**
 * ArtistsPage の「+ Add」から開く、Spotify アーティスト検索 → フォロー追加モーダル。
 *
 * 流れ:
 *   1. 入力 → `searchSpotifyArtists` で Spotify から候補取得
 *   2. 候補をクリック → `upsertArtist` で `artists` テーブルに upsert
 *   3. 続いて `followArtist` で current user の follow 行を作成
 *   4. `followed-artists` / `artists` query を invalidate して閉じる
 *
 * Spotify 検索は USE_MOCK では空配列を返すため、mock 環境では UX として
 * 機能しない (空のドロップダウンが出るだけ)。実 API 接続時にだけ意味を持つ。
 */
export function AddArtistModal({ open, onClose }: Props) {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SpotifyArtistSummary[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
      setSearching(false);
      setError(null);
      setPendingId(null);
    }
  }, [open]);

  const followMutation = useMutation({
    mutationFn: async (artist: SpotifyArtistSummary) => {
      await upsertArtist({
        spotify_id: artist.spotify_id,
        name: artist.name,
        image_url: artist.image_url,
        source: "spotify_dynamic",
      });
      await followArtist(artist.spotify_id);
      return artist;
    },
    onSuccess: () => {
      // 一覧 (followed-artists) と global registry (artists, HomePage が参照)
      // を両方更新する。record-counts は変わらない (新規 follow なら 0 件)。
      queryClient.invalidateQueries({ queryKey: ["followed-artists"] });
      queryClient.invalidateQueries({ queryKey: ["artists"] });
      onClose();
    },
    onSettled: () => {
      setPendingId(null);
    },
  });

  async function handleSearch() {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const items = await searchSpotifyArtists(query.trim());
      setResults(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  function handleSelect(artist: SpotifyArtistSummary) {
    setPendingId(artist.spotify_id);
    followMutation.mutate(artist);
  }

  if (!open) return null;

  return (
    <ModalShell onClose={onClose}>
      <div className="max-h-[90vh] w-[min(92vw,480px)] overflow-y-auto bg-paper p-6 text-left text-ink shadow-xl ring-1 ring-ink/10">
        <header className="flex items-baseline justify-between border-b border-ink/15 pb-3">
          <h2 className="text-base font-medium">Add artist</h2>
          <button
            type="button"
            onClick={onClose}
            className="cursor-pointer text-xs italic text-ink-faint transition-colors hover:text-ink"
          >
            close
          </button>
        </header>

        <div className="mt-4 flex items-center gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleSearch();
              }
            }}
            placeholder="Search Spotify…"
            autoFocus
            className={inputClass}
          />
          <button
            type="button"
            onClick={handleSearch}
            disabled={!query.trim() || searching}
            className="shrink-0 bg-ink/10 px-4 py-2 text-sm text-ink transition-colors hover:bg-ink/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {searching ? "Searching…" : "Search"}
          </button>
        </div>

        <div className="mt-4 min-h-[8rem] border border-ink/10 bg-paper">
          {error ? (
            <div className="p-3 text-sm italic text-ink-mute">{error}</div>
          ) : searching ? (
            <div className="p-3 text-sm italic text-ink-faint">loading…</div>
          ) : results.length === 0 ? (
            <div className="p-3 text-sm italic text-ink-mute">
              {query.trim()
                ? "no results"
                : "type an artist name and press search"}
            </div>
          ) : (
            <ul className="divide-y divide-ink/10">
              {USE_MOCK && (
                <li className="px-3 py-1.5 text-xs italic text-ink-faint">
                  demo — showing sample search results
                </li>
              )}
              {results.map((a) => {
                const isPending = pendingId === a.spotify_id;
                return (
                  <li key={a.spotify_id}>
                    <button
                      type="button"
                      onClick={() => handleSelect(a)}
                      disabled={followMutation.isPending}
                      className="flex w-full items-center gap-3 p-2 text-left transition-colors hover:bg-ink/5 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <div className="aspect-square w-12 shrink-0 overflow-hidden bg-ink/5">
                        {a.image_url ? (
                          <img
                            src={a.image_url}
                            alt=""
                            className="h-full w-full object-cover"
                          />
                        ) : null}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm text-ink">
                          {a.name}
                        </div>
                      </div>
                      <span className="shrink-0 text-xs italic text-ink-faint">
                        {isPending ? "adding…" : "follow"}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {followMutation.isError && (
          <p className="mt-3 text-sm italic text-ink-mute">
            failed to follow: {(followMutation.error as Error).message}
          </p>
        )}
      </div>
    </ModalShell>
  );
}
