// ====================================================================
// API クライアント抽象（モック / 実 API 切替）
//   ADR-002 §2.7-§2.8 に従い、VITE_USE_MOCK で mock / 実 API を切り替える。
//
//   実 API パス:
//     - artists / records は orval 生成 fetcher (src/api/generated/) を経由
//     - releases / concerts / jacket upload は backend 未実装のため fetch のまま
//       (jacket upload の実 API は Phase B-3 で実装予定)
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
  createRecordApiRecordsPost,
  listRecordsApiRecordsGet,
  updateRecordApiRecordsIdPut,
} from "./generated/records/records";
import type {
  VinylRecordCreate,
  VinylRecordUpdate,
} from "./generated/model";

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

// id / created_at / updated_at / display_order は backend が採番する。
// mock 側でも同じ shape のレコードを返す。
export async function createVinylRecord(
  input: VinylRecordCreate,
): Promise<VinylRecord> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 80));
    const now = new Date().toISOString();
    const created: VinylRecord = {
      id: crypto.randomUUID(),
      artist_id: input.artist_id,
      spotify_album_id: input.spotify_album_id ?? null,
      source: input.source ?? "manual",
      title: input.title,
      image_url: input.image_url ?? null,
      original_release_date: input.original_release_date ?? null,
      pressing_info: input.pressing_info ?? null,
      purchase_date: input.purchase_date ?? null,
      purchase_store: input.purchase_store ?? null,
      purchase_price: input.purchase_price ?? null,
      purchase_currency: input.purchase_currency ?? "JPY",
      rating: input.rating ?? null,
      memo: input.memo ?? null,
      favorite_tracks: input.favorite_tracks ?? null,
      display_order: mockRecordsStore.length + 1,
      created_at: now,
      updated_at: now,
    };
    mockRecordsStore.push(created);
    return created;
  }
  const res = await createRecordApiRecordsPost(input);
  return res.data as VinylRecord;
}

export async function updateVinylRecord(
  id: string,
  input: VinylRecordUpdate,
): Promise<VinylRecord> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 80));
    const idx = mockRecordsStore.findIndex((r) => r.id === id);
    if (idx < 0) throw new Error(`record not found: ${id}`);
    // VinylRecordUpdate は全フィールド optional。undefined を除外して上書きする
    // ことで「指定したフィールドだけ書き換える」backend の寛容 PUT 挙動を再現する。
    const patch: Partial<VinylRecord> = {};
    for (const [key, value] of Object.entries(input)) {
      if (value !== undefined) {
        (patch as Record<string, unknown>)[key] = value;
      }
    }
    const updated: VinylRecord = {
      ...mockRecordsStore[idx],
      ...patch,
      updated_at: new Date().toISOString(),
    };
    mockRecordsStore[idx] = updated;
    return updated;
  }
  const res = await updateRecordApiRecordsIdPut(id, input);
  return res.data as VinylRecord;
}

/**
 * Upload a jacket image for a record.
 *
 * 実 API は Phase B-3 以降で実装する。それまでは mock のみ動作する。
 * Real API: `PUT /api/records/:id/jacket` (multipart/form-data, field name `file`)
 *   サーバは保存して `image_url`（例: `/jackets/{id}-{hash}.jpg`）を返し、
 *   record の image_url も同時に更新する。
 * Mock: ブラウザ blob URL を返し、in-memory store の対象レコードの image_url
 *   も更新する（リロードで消える）。
 */
export async function uploadJacket(
  recordId: VinylRecord["id"],
  file: File,
): Promise<{ image_url: string }> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 80));
    const imageUrl = URL.createObjectURL(file);
    const idx = mockRecordsStore.findIndex((r) => r.id === recordId);
    if (idx >= 0) {
      mockRecordsStore[idx] = { ...mockRecordsStore[idx], image_url: imageUrl };
    }
    return { image_url: imageUrl };
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
