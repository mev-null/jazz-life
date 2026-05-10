import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getArtists, getVinylRecords } from "../api/client";
import { AddRecordTile } from "../components/records/AddRecordTile";
import { JacketCard } from "../components/records/JacketCard";
import { RecordDetailModal } from "../components/records/RecordDetailModal";
import {
  RecordFormModal,
  type FormMode,
} from "../components/records/RecordFormModal";
import type { VinylRecord } from "../types/api";

export function HomePage() {
  const records = useQuery({
    queryKey: ["records"],
    queryFn: getVinylRecords,
  });
  const artists = useQuery({ queryKey: ["artists"], queryFn: getArtists });

  const [openRecord, setOpenRecord] = useState<VinylRecord | null>(null);
  const [formMode, setFormMode] = useState<FormMode | null>(null);

  const artistNameById = (id: string) =>
    artists.data?.items.find((a) => a.spotify_id === id)?.name;

  function handleEditCurrent() {
    if (!openRecord) return;
    setFormMode({ kind: "edit", record: openRecord });
    setOpenRecord(null);
  }

  return (
    <section>
      <h1 className="flex items-baseline gap-3 text-base">
        <span className="font-medium">Records</span>
        <span className="text-ink-faint tabular-nums">
          {records.data ? records.data.items.length : ""}
        </span>
      </h1>

      <div className="mt-10">
        {records.isLoading && (
          <p className="text-sm text-ink-faint">loading…</p>
        )}
        {records.isError && (
          <p className="text-sm text-ink-mute">読み込みに失敗しました</p>
        )}
        {records.data && (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {records.data.items.map((r) => (
              <JacketCard
                key={r.id}
                record={r}
                onClick={() => setOpenRecord(r)}
              />
            ))}
            <AddRecordTile onClick={() => setFormMode({ kind: "add" })} />
          </div>
        )}
      </div>

      <RecordDetailModal
        record={openRecord}
        artistName={
          openRecord ? artistNameById(openRecord.artist_id) : undefined
        }
        onClose={() => setOpenRecord(null)}
        onEdit={handleEditCurrent}
      />

      <RecordFormModal
        mode={formMode}
        artists={artists.data?.items ?? []}
        onClose={() => setFormMode(null)}
      />
    </section>
  );
}
