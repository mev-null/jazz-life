// ====================================================================
// Phase A-3: API クライアント抽象（モック / 実 API 切替）
//   ADR §4 「モック切り替え機構」に従い、VITE_USE_MOCK で挙動を切り替える。
//   Phase B 以降の実 API 接続では、ここの fetch 部分が本格化する想定。
//
//   書き込み系（upsertVinylRecord / uploadJacket）も同じパターンで分岐。
//   実 API では PUT /api/records/:id と PUT /api/records/:id/jacket を想定。
// ====================================================================

import { API_BASE, USE_MOCK } from "../lib/env";
import type {
  Artist,
  Concert,
  ListResponse,
  Release,
  VinylRecord,
} from "../types/api";

import artistsMock from "./mocks/artists.json";
import concertsMock from "./mocks/concerts.json";
import releasesMock from "./mocks/releases.json";
import vinylRecordsMock from "./mocks/vinyl_records.json";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${path}`);
  }
  return (await res.json()) as T;
}

// In-memory mutable mirror of the records mock — initialised once per page load.
// Mutations modify this so subsequent reads reflect the change. Lost on refresh.
const mockRecordsStore: VinylRecord[] = (
  vinylRecordsMock as ListResponse<VinylRecord>
).items.slice();

export async function getArtists(): Promise<ListResponse<Artist>> {
  if (USE_MOCK) return artistsMock as ListResponse<Artist>;
  return fetchJson<ListResponse<Artist>>("/api/artists");
}

export async function getVinylRecords(): Promise<ListResponse<VinylRecord>> {
  if (USE_MOCK) return { items: mockRecordsStore.slice() };
  return fetchJson<ListResponse<VinylRecord>>("/api/records");
}

export async function getReleases(): Promise<ListResponse<Release>> {
  if (USE_MOCK) return releasesMock as ListResponse<Release>;
  return fetchJson<ListResponse<Release>>("/api/releases");
}

export async function getConcerts(): Promise<ListResponse<Concert>> {
  if (USE_MOCK) return concertsMock as ListResponse<Concert>;
  return fetchJson<ListResponse<Concert>>("/api/concerts");
}

/**
 * Create-or-update a vinyl record.
 *
 * Mock: in-memory mockRecordsStore を直接書き換える（id 衝突リスクは Phase A 限定として受容）。
 *
 * Phase B（ADR-001 §2.3）: 新規は `POST /api/records`（サーバ側 auto-increment）、
 * 既存更新は `PUT /api/records/:id` に分割する。本関数は呼び出し側ごとに
 * `createVinylRecord` / `updateVinylRecord` の 2 関数へ分解する想定。
 * 暫定として PUT のみ実装している。
 */
export async function upsertVinylRecord(
  record: VinylRecord,
): Promise<VinylRecord> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 80)); // mimic small latency
    const idx = mockRecordsStore.findIndex((r) => r.id === record.id);
    if (idx >= 0) {
      mockRecordsStore[idx] = record;
    } else {
      mockRecordsStore.push(record);
    }
    return record;
  }
  const res = await fetch(`${API_BASE}/api/records/${record.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(record),
  });
  if (!res.ok) throw new Error(`PUT record ${record.id} failed: ${res.status}`);
  return (await res.json()) as VinylRecord;
}

/**
 * Upload a jacket image for a record.
 *
 * Real API: `PUT /api/records/:id/jacket` (multipart/form-data, field name `file`)
 *   サーバは保存して `image_url`（例: `/jackets/{id}-{hash}.jpg`）を返す。
 * Mock: ブラウザ blob URL を返す（リロードで消える）
 */
export async function uploadJacket(
  recordId: number,
  file: File,
): Promise<{ image_url: string }> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 80));
    return { image_url: URL.createObjectURL(file) };
  }
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_BASE}/api/records/${recordId}/jacket`, {
    method: "PUT",
    body: fd,
  });
  if (!res.ok)
    throw new Error(`PUT jacket ${recordId} failed: ${res.status}`);
  return (await res.json()) as { image_url: string };
}
