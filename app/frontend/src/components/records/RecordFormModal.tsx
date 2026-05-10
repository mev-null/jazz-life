import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  createVinylRecord,
  updateVinylRecord,
  uploadJacket,
} from "../../api/client";
import type { Artist, VinylRecord } from "../../types/api";
import type {
  VinylRecordCreate,
  VinylRecordUpdate,
} from "../../api/generated/model";
import { ModalShell } from "../ModalShell";

export type FormMode =
  | { kind: "add" }
  | { kind: "edit"; record: VinylRecord };

type Props = {
  mode: FormMode | null;
  artists: Artist[];
  onClose: () => void;
};

const labelClass = "block italic text-sm text-ink-mute mb-1.5";
const inputClass =
  "w-full border-b border-ink-faint bg-transparent py-1.5 text-[15px] text-ink placeholder:text-ink-faint focus:border-ink focus:outline-none";

export function RecordFormModal({ mode, artists, onClose }: Props) {
  const queryClient = useQueryClient();
  const isEdit = mode?.kind === "edit";

  const [title, setTitle] = useState("");
  const [artistId, setArtistId] = useState("");
  const [releaseDate, setReleaseDate] = useState("");
  const [pressingInfo, setPressingInfo] = useState("");
  const [purchaseStore, setPurchaseStore] = useState("");
  const [purchaseDate, setPurchaseDate] = useState("");
  const [memo, setMemo] = useState("");
  const [favoriteTracks, setFavoriteTracks] = useState("");

  // image: existing url (from record) and pending file (new selection)
  const [existingImageUrl, setExistingImageUrl] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const previewBlobRef = useRef<string | null>(null);

  const create = useMutation({
    mutationFn: createVinylRecord,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["records"] }),
  });

  const update = useMutation({
    mutationFn: ({ id, input }: { id: string; input: VinylRecordUpdate }) =>
      updateVinylRecord(id, input),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["records"] }),
  });

  const upload = useMutation({
    mutationFn: ({ recordId, file }: { recordId: string; file: File }) =>
      uploadJacket(recordId, file),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["records"] }),
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
      setReleaseDate(r.original_release_date ?? "");
      setPressingInfo(r.pressing_info ?? "");
      setPurchaseStore(r.purchase_store ?? "");
      setPurchaseDate(r.purchase_date ?? "");
      setMemo(r.memo ?? "");
      setFavoriteTracks(r.favorite_tracks ?? "");
      setExistingImageUrl(r.image_url);
      setPreviewUrl(r.image_url);
    } else {
      setTitle("");
      setArtistId(""); // 別 effect が artists 到着後に補完する
      setReleaseDate("");
      setPressingInfo("");
      setPurchaseStore("");
      setPurchaseDate("");
      setMemo("");
      setFavoriteTracks("");
      setExistingImageUrl(null);
      setPreviewUrl(null);
    }
    setPendingFile(null);
    // pending blob はモーダル切替（mode→null 含む）/ unmount で確実に解放する
    return () => {
      if (previewBlobRef.current) {
        URL.revokeObjectURL(previewBlobRef.current);
        previewBlobRef.current = null;
      }
    };
  }, [mode]);

  // add モード時、ユーザが未選択かつ artists が利用可能になったら先頭をデフォルトに。
  // edit モード or 既にユーザが選択済みの場合は触らない。
  useEffect(() => {
    if (mode?.kind !== "add") return;
    if (artistId) return;
    if (artists.length === 0) return;
    setArtistId(artists[0].spotify_id);
  }, [mode, artists, artistId]);

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
        original_release_date: releaseDate.trim() || null,
        pressing_info: pressingInfo.trim() || null,
        purchase_date: purchaseDate || null,
        purchase_store: purchaseStore.trim() || null,
        memo: memo.trim() || null,
        favorite_tracks: favoriteTracks.trim() || null,
      };
      await update.mutateAsync({ id: mode.record.id, input: updateInput });
    } else {
      // add: id は backend が UUID v7 で採番するため、まず POST して採番された
      // id を受け取り、必要があれば jacket をその id 宛にアップロードする。
      const createInput: VinylRecordCreate = {
        artist_id: artistId,
        title: title.trim(),
        original_release_date: releaseDate.trim() || null,
        pressing_info: pressingInfo.trim() || null,
        purchase_date: purchaseDate || null,
        purchase_store: purchaseStore.trim() || null,
        memo: memo.trim() || null,
        favorite_tracks: favoriteTracks.trim() || null,
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
        className="max-h-[90vh] w-[min(90vw,560px)] overflow-y-auto bg-paper p-8 text-left text-ink shadow-xl ring-1 ring-ink/10"
      >
        <h2 className="border-b border-ink/15 pb-3 text-lg font-medium">
          {isEdit ? "Edit Record" : "Add a Record"}
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

          <label className="block">
            <span className={labelClass}>Title</span>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              autoFocus
              className={inputClass}
            />
          </label>

          <label className="block">
            <span className={labelClass}>Artist</span>
            <select
              value={artistId}
              onChange={(e) => setArtistId(e.target.value)}
              required
              className={inputClass}
            >
              {artists.map((a) => (
                <option key={a.spotify_id} value={a.spotify_id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <label className="block">
              <span className={labelClass}>Released</span>
              <input
                type="text"
                value={releaseDate}
                onChange={(e) => setReleaseDate(e.target.value)}
                placeholder="1962-01 or 1962"
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
                className={inputClass}
              />
            </label>

            <label className="block">
              <span className={labelClass}>Purchase date</span>
              <input
                type="date"
                value={purchaseDate}
                onChange={(e) => setPurchaseDate(e.target.value)}
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
              className={inputClass}
            />
          </label>
        </div>

        <div className="mt-8 flex justify-end gap-6 text-sm">
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
