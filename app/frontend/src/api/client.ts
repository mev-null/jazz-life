// ====================================================================
// API クライアント抽象（モック / 実 API 切替）
//   ADR-002 §2.7-§2.8 に従い、VITE_USE_MOCK で mock / 実 API を切り替える。
//
//   実 API パス:
//     - artists / records は orval 生成 fetcher (src/api/generated/) を経由
//     - releases / concerts / jacket upload は backend 未実装のため fetch のまま
//
//   書き込み系 (upsertVinylRecord) は当面 PUT のみ。Phase B-2 PR-B で
//   POST (新規) と PUT (更新) に分解する。
// ====================================================================

import { API_BASE, USE_MOCK } from "../lib/env";
import type {
  Artist,
  Concert,
  ListResponse,
  Release,
  VinylRecord,
} from "../types/api";

import { listArtistsApiArtistsGet } from "./generated/artists/artists";
import {
  listRecordsApiRecordsGet,
  updateRecordApiRecordsIdPut,
} from "./generated/records/records";

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
  const res = await listArtistsApiArtistsGet();
  return res.data as ListResponse<Artist>;
}

export async function getVinylRecords(): Promise<ListResponse<VinylRecord>> {
  if (USE_MOCK) return { items: mockRecordsStore.slice() };
  const res = await listRecordsApiRecordsGet();
  return res.data as ListResponse<VinylRecord>;
}

// backend 未実装。実 API 接続は Phase B-3 以降。
export async function getReleases(): Promise<ListResponse<Release>> {
  if (USE_MOCK) return releasesMock as ListResponse<Release>;
  return fetchJson<ListResponse<Release>>("/api/releases");
}

// backend 未実装。実 API 接続は Phase B-3 以降。
export async function getConcerts(): Promise<ListResponse<Concert>> {
  if (USE_MOCK) return concertsMock as ListResponse<Concert>;
  return fetchJson<ListResponse<Concert>>("/api/concerts");
}

/**
 * Create-or-update a vinyl record.
 *
 * Mock: in-memory mockRecordsStore を直接書き換える。
 *
 * 実 API: 当面 PUT のみ実装。新規 (id 既存なし) は backend で 404 になる。
 * Phase B-2 PR-B で createRecordApiRecordsPost (新規) と
 * updateRecordApiRecordsIdPut (更新) の出し分けに分解する。
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
  const res = await updateRecordApiRecordsIdPut(record.id, record);
  return res.data as VinylRecord;
}

/**
 * Upload a jacket image for a record.
 *
 * 実 API は Phase B-3 以降で実装する。それまでは mock のみ動作する。
 * Real API: `PUT /api/records/:id/jacket` (multipart/form-data, field name `file`)
 *   サーバは保存して `image_url`（例: `/jackets/{id}-{hash}.jpg`）を返す。
 * Mock: ブラウザ blob URL を返す（リロードで消える）。
 */
export async function uploadJacket(
  recordId: VinylRecord["id"],
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
