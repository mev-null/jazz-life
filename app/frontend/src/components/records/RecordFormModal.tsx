import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { uploadJacket, upsertVinylRecord } from "../../api/client";
import type { Artist, VinylRecord } from "../../types/api";
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

  const upsert = useMutation({
    mutationFn: upsertVinylRecord,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["records"] }),
  });

  const upload = useMutation({
    mutationFn: ({ recordId, file }: { recordId: number; file: File }) =>
      uploadJacket(recordId, file),
  });

  // load fields when modal opens
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
      setArtistId(artists[0]?.spotify_id ?? "");
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
    return () => {
      if (previewBlobRef.current) {
        URL.revokeObjectURL(previewBlobRef.current);
        previewBlobRef.current = null;
      }
    };
  }, [mode, artists]);

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

  const submitting = upsert.isPending || upload.isPending;

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!title.trim() || !artistId || !mode) return;

    const now = new Date().toISOString();
    const baseId = mode.kind === "edit" ? mode.record.id : Date.now();

    // 1) upload jacket if a new file was chosen
    let imageUrl: string | null = existingImageUrl;
    if (pendingFile) {
      const result = await upload.mutateAsync({
        recordId: baseId,
        file: pendingFile,
      });
      imageUrl = result.image_url;
    }

    // 2) upsert the record
    const base: VinylRecord =
      mode.kind === "edit"
        ? mode.record
        : {
            id: baseId,
            artist_id: artistId,
            spotify_album_id: null,
            title: "",
            image_url: null,
            original_release_date: null,
            pressing_info: null,
            purchase_date: null,
            purchase_store: null,
            purchase_price: null,
            rating: null,
            memo: null,
            favorite_tracks: null,
            display_order:
              (queryClient.getQueryData<{ items: VinylRecord[] }>([
                "records",
              ])?.items.length ?? 0) + 1,
            created_at: now,
            updated_at: now,
          };

    const next: VinylRecord = {
      ...base,
      artist_id: artistId,
      title: title.trim(),
      image_url: imageUrl,
      original_release_date: releaseDate.trim() || null,
      pressing_info: pressingInfo.trim() || null,
      purchase_date: purchaseDate || null,
      purchase_store: purchaseStore.trim() || null,
      memo: memo.trim() || null,
      favorite_tracks: favoriteTracks.trim() || null,
      updated_at: now,
    };

    await upsert.mutateAsync(next);
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
