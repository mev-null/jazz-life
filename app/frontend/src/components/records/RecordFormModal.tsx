import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  createVinylRecord,
  deleteVinylRecord,
  searchSpotifyAlbums,
  updateVinylRecord,
  uploadJacket,
  upsertArtist,
} from "../../api/client";
import type { Artist, VinylRecord } from "../../types/api";
import type {
  FavoriteTrack,
  SpotifyAlbumSummary,
  VinylRecordCreate,
  VinylRecordCreateStatus,
  VinylRecordUpdate,
} from "../../api/generated/model";
import { useBreakpoint } from "../../hooks/useBreakpoint";
import { MOBILE_UI_ENABLED } from "../../lib/featureFlags";
import { InlineConfirm } from "../InlineConfirm";
import { ModalShell } from "../ModalShell";

export type FormMode =
  | {
    kind: "add";
    // ArtistDetailModal / FeedDetailModal から呼ぶ際の事前デフォルト。
    // - artistId / status: 必須に近い (どこから呼ぶかで決まる)
    // - title / imageUrl / spotifyAlbumId / originalReleaseDate: FeedDetailModal の
    //   「買った/ほしい」経路で Release のメタデータを流し込む用 (ユーザが
    //   そのまま保存してもよし、編集してもよし)
    defaults?: {
      artistId?: string;
      status?: VinylRecordCreateStatus;
      title?: string;
      imageUrl?: string | null;
      spotifyAlbumId?: string | null;
      originalReleaseDate?: string | null;
    };
  }
  | { kind: "edit"; record: VinylRecord };

type Props = {
  mode: FormMode | null;
  artists: Artist[];
  onClose: () => void;
};

const labelClass = "block italic text-sm text-ink-mute mb-1.5";
const inputClass =
  "w-full border-b border-ink-faint bg-transparent py-1.5 text-[15px] text-ink placeholder:text-ink-faint focus:border-ink focus:outline-none";

// ADR-006 で favorite_tracks は string → FavoriteTrack[] に構造化された。本 UI は
// 暫定で「改行区切りのテキストエリア」を維持し、submit 時に [{track_name: line}, ...]
// に変換する。Spotify track 検索 + note 入力の本格 UI は別 PR で。
const favoritesToString = (favs: readonly FavoriteTrack[] | null | undefined): string =>
  (favs ?? []).map((t) => t.track_name).join("\n");

const stringToFavorites = (s: string): FavoriteTrack[] =>
  s
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => ({ spotify_track_id: null, track_name: line, note: null }));

export function RecordFormModal({ mode, artists, onClose }: Props) {
  const queryClient = useQueryClient();
  const isEdit = mode?.kind === "edit";
  const { isMobile } = useBreakpoint();
  const mobile = MOBILE_UI_ENABLED && isMobile;
  // Mobile では autoFocus で keyboard が即立ち上がるとモーダル本体が下に押し下げられて
  // 操作しづらいので、初回フォーカスを抑止する。タップで明示的に focus する運用に倒す。
  const autoFocusTitle = !mobile;

  const [title, setTitle] = useState("");
  // artistId は spotify_id を保持。artistQuery は input に表示する name の現値。
  // 両者は手動入力 (typeahead クリック or Spotify album 選択) のいずれかで同期する。
  const [artistId, setArtistId] = useState("");
  const [artistQuery, setArtistQuery] = useState("");
  const [artistDropdownOpen, setArtistDropdownOpen] = useState(false);
  const [releaseDate, setReleaseDate] = useState("");
  const [pressingInfo, setPressingInfo] = useState("");
  const [purchaseStore, setPurchaseStore] = useState("");
  const [purchaseDate, setPurchaseDate] = useState("");
  const [memo, setMemo] = useState("");
  const [favoriteTracks, setFavoriteTracks] = useState("");

  // image: existing url (from record / Spotify) と pending file (new selection)
  const [existingImageUrl, setExistingImageUrl] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const previewBlobRef = useRef<string | null>(null);

  // Spotify album search result (album selection で image_url / spotify_album_id を流し込む)
  const [spotifyAlbumId, setSpotifyAlbumId] = useState<string | null>(null);
  const [spotifyResults, setSpotifyResults] = useState<SpotifyAlbumSummary[]>([]);
  const [spotifyOpen, setSpotifyOpen] = useState(false);
  const [spotifySearching, setSpotifySearching] = useState(false);
  const [spotifyError, setSpotifyError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: createVinylRecord,
    // record 作成は auto-follow 経路で user_follows に行を作る / archived を解除
    // するので、ArtistsPage の followed-artists 一覧と件数も再取得対象。
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["records"] });
      queryClient.invalidateQueries({ queryKey: ["followed-artists"] });
      queryClient.invalidateQueries({ queryKey: ["record-counts"] });
    },
  });

  const update = useMutation({
    mutationFn: ({ id, input }: { id: string; input: VinylRecordUpdate }) =>
      updateVinylRecord(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["records"] });
      queryClient.invalidateQueries({ queryKey: ["record-counts"] });
    },
  });

  const upload = useMutation({
    mutationFn: ({ recordId, file }: { recordId: string; file: File }) =>
      uploadJacket(recordId, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["records"] }),
  });

  // 編集モードの「削除」ボタン。共通 InlineConfirm に切替えたので、ローカル
  // state は不要 (内側でハンドリング)。
  const remove = useMutation({
    mutationFn: deleteVinylRecord,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["records"] });
      queryClient.invalidateQueries({ queryKey: ["record-counts"] });
    },
  });

  // load fields when modal opens / mode changes.
  // 依存は mode のみ。artists を deps に入れると、TanStack Query の refetch で
  // artists 参照が変わった際に effect が再走 → ユーザの編集中の入力が初期値に
  // 戻されるため除外する。add 時の default artist 埋めは別 effect で扱う。
  useEffect(() => {
    if (!mode) return;
    if (mode.kind === "edit") {
      const r = mode.record;
      setTitle(r.title);
      setArtistId(r.artist_id);
      setArtistQuery(
        artists.find((a) => a.spotify_id === r.artist_id)?.name ?? "",
      );
      setReleaseDate(r.original_release_date ?? "");
      setPressingInfo(r.pressing_info ?? "");
      setPurchaseStore(r.purchase_store ?? "");
      setPurchaseDate(r.purchase_date ?? "");
      setMemo(r.memo ?? "");
      setFavoriteTracks(favoritesToString(r.favorite_tracks));
      setExistingImageUrl(r.image_url);
      setPreviewUrl(r.image_url);
      setSpotifyAlbumId(r.spotify_album_id);
    } else {
      const d = mode.defaults;
      setTitle(d?.title ?? "");
      // add mode: defaults.artistId が渡されていればその場で artists を引いて
      // name も埋める。artists 未到着のケースは下の追い焚き effect が補完する。
      const defaultArtistId = d?.artistId ?? "";
      setArtistId(defaultArtistId);
      setArtistQuery(
        defaultArtistId
          ? artists.find((a) => a.spotify_id === defaultArtistId)?.name ?? ""
          : "",
      );
      setReleaseDate(d?.originalReleaseDate ?? "");
      setPressingInfo("");
      setPurchaseStore("");
      setPurchaseDate("");
      setMemo("");
      setFavoriteTracks("");
      // Release 由来の image URL は Spotify CDN なので blob revoke 不要。
      // existingImageUrl / previewUrl の両方にセットして form 上にプレビュー表示する。
      const defaultImage = d?.imageUrl ?? null;
      setExistingImageUrl(defaultImage);
      setPreviewUrl(defaultImage);
      setSpotifyAlbumId(d?.spotifyAlbumId ?? null);
    }
    setPendingFile(null);
    setSpotifyResults([]);
    setSpotifyOpen(false);
    setSpotifyError(null);
    setArtistDropdownOpen(false);
    // pending blob はモーダル切替（mode→null 含む）/ unmount で確実に解放する
    return () => {
      if (previewBlobRef.current) {
        URL.revokeObjectURL(previewBlobRef.current);
        previewBlobRef.current = null;
      }
    };
  }, [mode]);

  // edit モードで開いた時、artists が後から到着するパターンでも artistQuery を
  // 補完する。add モードでは空のままにし、ユーザの自由入力 / Spotify 選択で埋める。
  useEffect(() => {
    if (mode?.kind !== "edit") return;
    if (artistQuery) return;
    const name = artists.find((a) => a.spotify_id === mode.record.artist_id)?.name;
    if (name) setArtistQuery(name);
  }, [mode, artists, artistQuery]);

  // add モードで defaults.artistId が指定されている場合、artists が後から到着
  // するパターン用に name を補完する。
  useEffect(() => {
    if (mode?.kind !== "add") return;
    const defaultArtistId = mode.defaults?.artistId;
    if (!defaultArtistId) return;
    if (artistQuery) return;
    const name = artists.find((a) => a.spotify_id === defaultArtistId)?.name;
    if (name) setArtistQuery(name);
  }, [mode, artists, artistQuery]);

  if (!mode) return null;

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (previewBlobRef.current) {
      URL.revokeObjectURL(previewBlobRef.current);
    }
    const url = URL.createObjectURL(file);
    previewBlobRef.current = url;
    setPendingFile(file);
    setPreviewUrl(url);
  }

  function handleClearImage() {
    if (previewBlobRef.current) {
      URL.revokeObjectURL(previewBlobRef.current);
      previewBlobRef.current = null;
    }
    setPendingFile(null);
    setPreviewUrl(null);
    setExistingImageUrl(null);
  }

  async function handleSpotifySearch() {
    if (!title.trim()) return;
    setSpotifySearching(true);
    setSpotifyError(null);
    setSpotifyOpen(true);
    try {
      // artistQuery が入っていればそれを refine 用に Spotify に渡す。
      // typeahead 選択 / 自由入力どちらでも、現在の表示値をそのまま使う。
      const refineArtist = artistQuery.trim() || undefined;
      const items = await searchSpotifyAlbums(title.trim(), refineArtist);
      setSpotifyResults(items);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setSpotifyError(msg);
      setSpotifyResults([]);
    } finally {
      setSpotifySearching(false);
    }
  }

  async function handleSelectSpotifyAlbum(album: SpotifyAlbumSummary) {
    setTitle(album.name);
    setSpotifyAlbumId(album.id);
    if (album.release_date) setReleaseDate(album.release_date);
    if (album.image_url) {
      // Spotify CDN の URL を既存 image として preview に流し込む。
      // pending file があれば user 選択を優先して上書きしない。
      if (previewBlobRef.current) {
        URL.revokeObjectURL(previewBlobRef.current);
        previewBlobRef.current = null;
      }
      setPendingFile(null);
      setExistingImageUrl(album.image_url);
      setPreviewUrl(album.image_url);
    }
    // 正規 Spotify artist ID で artists を識別する。
    // album.primary_artist_id が無い (極めて稀) 場合はフォーム上は name だけ反映する。
    const primaryArtistName = album.artist_names[0];
    const primaryArtistId = album.primary_artist_id;
    if (primaryArtistId && primaryArtistName) {
      const existing = artists.find((a) => a.spotify_id === primaryArtistId);
      if (existing) {
        setArtistId(existing.spotify_id);
        setArtistQuery(existing.name);
      } else {
        try {
          const created = await upsertArtist({
            spotify_id: primaryArtistId,
            name: primaryArtistName,
            image_url: null,
            source: "spotify_dynamic",
          });
          setArtistId(created.spotify_id);
          setArtistQuery(created.name);
          queryClient.invalidateQueries({ queryKey: ["artists"] });
        } catch {
          // upsert に失敗しても UI 上は name だけ反映して、保存時に backend に
          // バリデーションさせる。
          setArtistQuery(primaryArtistName);
        }
      }
    } else if (primaryArtistName) {
      setArtistQuery(primaryArtistName);
    }
    setSpotifyOpen(false);
  }

  // Artist input の現値で部分一致 filter した候補。typeahead dropdown 表示用。
  const artistMatches = artistQuery.trim()
    ? artists
      .filter((a) =>
        a.name.toLowerCase().includes(artistQuery.trim().toLowerCase()),
      )
      .slice(0, 8)
    : artists.slice(0, 8);

  function handleSelectArtistFromDropdown(artist: Artist) {
    setArtistId(artist.spotify_id);
    setArtistQuery(artist.name);
    setArtistDropdownOpen(false);
  }

  function handleArtistInputChange(value: string) {
    setArtistQuery(value);
    // 既存 artist を入力中の name と完全一致した場合は artistId を保持。
    // それ以外は artistId を一旦クリアし、Spotify album 選択 / dropdown 選択で
    // 改めてセットする方針 (中途半端な不一致 ID で保存しないため)。
    const match = artists.find(
      (a) => a.name.toLowerCase() === value.trim().toLowerCase(),
    );
    setArtistId(match?.spotify_id ?? "");
  }

  const submitting =
    create.isPending || update.isPending || upload.isPending;

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!title.trim() || !artistId || !mode) return;

    if (mode.kind === "edit") {
      // edit: 先に jacket を上げ（成功時 backend 側で image_url が更新される）、
      // その上で全フィールドの PUT を投げて他項目の変更を保存する。
      let imageUrl: string | null = existingImageUrl;
      if (pendingFile) {
        const result = await upload.mutateAsync({
          recordId: mode.record.id,
          file: pendingFile,
        });
        imageUrl = result.image_url;
      }
      const updateInput: VinylRecordUpdate = {
        artist_id: artistId,
        title: title.trim(),
        image_url: imageUrl,
        spotify_album_id: spotifyAlbumId,
        original_release_date: releaseDate.trim() || null,
        pressing_info: pressingInfo.trim() || null,
        purchase_date: purchaseDate || null,
        purchase_store: purchaseStore.trim() || null,
        memo: memo.trim() || null,
        favorite_tracks: stringToFavorites(favoriteTracks),
      };
      await update.mutateAsync({ id: mode.record.id, input: updateInput });
    } else {
      // add: id は backend が UUID v7 で採番するため、まず POST して採番された
      // id を受け取り、必要があれば jacket をその id 宛にアップロードする。
      // Spotify から選んだ album があれば source = "spotify" にして image_url も同梱。
      // pendingFile があれば後段の jacket upload で image_url が上書きされる。
      const createInput: VinylRecordCreate = {
        artist_id: artistId,
        title: title.trim(),
        spotify_album_id: spotifyAlbumId,
        source: spotifyAlbumId ? "spotify" : "manual",
        status: mode.defaults?.status,
        image_url: pendingFile ? null : existingImageUrl,
        original_release_date: releaseDate.trim() || null,
        pressing_info: pressingInfo.trim() || null,
        purchase_date: purchaseDate || null,
        purchase_store: purchaseStore.trim() || null,
        memo: memo.trim() || null,
        favorite_tracks: stringToFavorites(favoriteTracks),
      };
      const created = await create.mutateAsync(createInput);
      if (pendingFile) {
        await upload.mutateAsync({
          recordId: created.id,
          file: pendingFile,
        });
      }
    }

    // ownership of preview blob URL passes to the saved record; don't revoke.
    previewBlobRef.current = null;
    onClose();
  }

  return (
    <ModalShell onClose={onClose}>
      <form
        onSubmit={handleSubmit}
        autoComplete="off"
        className={
          mobile
            ? "flex max-h-[90vh] w-[min(90vw,560px)] flex-col bg-paper text-left text-ink shadow-xl ring-1 ring-ink/10"
            : "max-h-[90vh] w-[min(90vw,560px)] overflow-y-auto bg-paper p-8 text-left text-ink shadow-xl ring-1 ring-ink/10"
        }
      >
        <div className={mobile ? "min-h-0 flex-1 overflow-y-auto p-8" : "contents"}>
        <h2 className="border-b border-ink/15 pb-3 text-lg font-medium">
          {isEdit
            ? "Edit Record"
            : mode.kind === "add" && mode.defaults?.status === "wanted"
              ? "Add to Want List"
              : "Add a Record"}
        </h2>

        <div className="mt-6 space-y-5">
          <div>
            <span className={labelClass}>Jacket</span>
            <div className="flex items-start gap-4">
              <div className="aspect-square w-24 shrink-0 overflow-hidden bg-ink/5 ring-1 ring-ink/10">
                {previewUrl ? (
                  <img
                    src={previewUrl}
                    alt=""
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="flex h-full w-full items-center justify-center text-3xl font-light text-ink-faint">
                    +
                  </div>
                )}
              </div>
              <div className="flex flex-col gap-2 pt-1 text-sm">
                <label className="cursor-pointer text-ink transition-opacity hover:opacity-70">
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleFile}
                    className="hidden"
                  />
                  <span>Choose file…</span>
                </label>
                {previewUrl && (
                  <button
                    type="button"
                    onClick={handleClearImage}
                    className="text-left italic text-ink-mute transition-colors hover:text-ink"
                  >
                    remove
                  </button>
                )}
              </div>
            </div>
          </div>

          <div>
            <div
              className={
                mobile ? "space-y-4" : "flex items-end gap-3"
              }
            >
              <div className={mobile ? "" : "flex-1"}>
                <span className={labelClass}>Title</span>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                  autoFocus={autoFocusTitle}
                  autoComplete="off"
                  className={inputClass}
                />
              </div>
              <div className={mobile ? "relative" : "relative flex-1"}>
                <span className={labelClass}>Artist</span>
                <input
                  type="text"
                  value={artistQuery}
                  onChange={(e) => handleArtistInputChange(e.target.value)}
                  onFocus={() => setArtistDropdownOpen(true)}
                  onBlur={() =>
                    // クリック反映のため少し遅らせる (dropdown 内の button click が
                    // 走る前に blur で閉じてしまうのを回避)
                    setTimeout(() => setArtistDropdownOpen(false), 150)
                  }
                  required
                  autoComplete="off"
                  placeholder="既存から選ぶ or Spotify 検索で追加"
                  className={inputClass}
                />
                {artistDropdownOpen && artistMatches.length > 0 && (
                  <ul className="absolute left-0 right-0 top-full z-10 mt-1 max-h-56 overflow-y-auto border border-ink/10 bg-paper">
                    {artistMatches.map((a) => (
                      <li key={a.spotify_id}>
                        <button
                          type="button"
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => handleSelectArtistFromDropdown(a)}
                          className="block w-full px-3 py-1.5 text-left text-sm text-ink transition-colors hover:bg-ink/5"
                        >
                          {a.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <button
                type="button"
                onClick={handleSpotifySearch}
                disabled={!title.trim() || spotifySearching}
                className={
                  mobile
                    ? "w-full bg-ink/10 px-4 py-2.5 text-sm text-ink transition-colors hover:bg-ink/20 disabled:cursor-not-allowed disabled:opacity-50"
                    : "shrink-0 bg-ink/10 px-4 py-2 text-sm text-ink transition-colors hover:bg-ink/20 disabled:cursor-not-allowed disabled:opacity-50"
                }
              >
                {spotifySearching ? "Searching…" : "Search"}
              </button>
            </div>
            {spotifyOpen && (
              <div className="mt-3 max-h-72 overflow-y-auto border border-ink/10 bg-paper">
                {spotifyError ? (
                  <div className="p-3 text-sm italic text-ink-mute">
                    {spotifyError}
                  </div>
                ) : !spotifySearching && spotifyResults.length === 0 ? (
                  <div className="p-3 text-sm italic text-ink-mute">
                    no results
                  </div>
                ) : (
                  <ul className="divide-y divide-ink/10">
                    {spotifyResults.map((album) => (
                      <li key={album.id}>
                        <button
                          type="button"
                          onClick={() => handleSelectSpotifyAlbum(album)}
                          className="flex w-full items-center gap-3 p-2 text-left transition-colors hover:bg-ink/5"
                        >
                          <div className="aspect-square w-12 shrink-0 overflow-hidden bg-ink/5">
                            {album.image_url ? (
                              <img
                                src={album.image_url}
                                alt=""
                                className="h-full w-full object-cover"
                              />
                            ) : null}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-sm text-ink">
                              {album.name}
                            </div>
                            <div className="truncate text-xs italic text-ink-mute">
                              {album.artist_names.join(", ")}
                              {album.release_date
                                ? ` · ${album.release_date}`
                                : ""}
                            </div>
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <label className="block">
              <span className={labelClass}>Released</span>
              <input
                type="text"
                value={releaseDate}
                onChange={(e) => setReleaseDate(e.target.value)}
                placeholder="1962-01 or 1962"
                autoComplete="off"
                className={inputClass}
              />
            </label>

            <label className="block">
              <span className={labelClass}>Pressing</span>
              <input
                type="text"
                value={pressingInfo}
                onChange={(e) => setPressingInfo(e.target.value)}
                placeholder="Riverside RLP-9399"
                autoComplete="off"
                className={inputClass}
              />
            </label>
          </div>

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <label className="block">
              <span className={labelClass}>Purchased at</span>
              <input
                type="text"
                value={purchaseStore}
                onChange={(e) => setPurchaseStore(e.target.value)}
                placeholder="ディスクユニオン..."
                autoComplete="off"
                className={inputClass}
              />
            </label>

            <label className="block">
              <span className={labelClass}>Purchase date</span>
              <input
                type="date"
                value={purchaseDate}
                onChange={(e) => setPurchaseDate(e.target.value)}
                autoComplete="off"
                className={inputClass}
              />
            </label>
          </div>

          <label className="block">
            <span className={labelClass}>Memo</span>
            <textarea
              value={memo}
              onChange={(e) => setMemo(e.target.value)}
              rows={3}
              autoComplete="off"
              className={`${inputClass} resize-none`}
            />
          </label>

          <label className="block">
            <span className={labelClass}>Favorites</span>
            <input
              type="text"
              value={favoriteTracks}
              onChange={(e) => setFavoriteTracks(e.target.value)}
              placeholder="Track 1 · Track 2"
              autoComplete="off"
              className={inputClass}
            />
          </label>
        </div>

        </div>

        <div
          className={
            mobile
              ? "flex items-center gap-6 border-t border-rule bg-paper px-8 py-5 text-sm"
              : "mt-8 flex items-center gap-6 text-sm"
          }
        >
          {isEdit && mode.kind === "edit" && (
            <InlineConfirm
              // edit A → edit B のとき confirm 状態が引き継がれないよう
              // record.id で remount させる。
              key={mode.record.id}
              className="mr-auto flex items-center gap-4"
              triggerLabel="Remove"
              prompt="Remove this record?"
              pendingLabel="Removing…"
              isPending={remove.isPending}
              disabled={submitting}
              onConfirm={() =>
                remove.mutate(mode.record.id, {
                  onSuccess: () => {
                    previewBlobRef.current = null;
                    onClose();
                  },
                })
              }
            />
          )}
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="text-ink-mute transition-colors hover:text-ink disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="font-medium text-ink transition-opacity hover:opacity-70 disabled:opacity-50"
          >
            {submitting ? "Saving…" : isEdit ? "Update" : "Save"}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}
