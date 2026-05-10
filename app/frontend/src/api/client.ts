// ====================================================================
// Phase A-3: API クライアント抽象（モック / 実 API 切替）
//   ADR §4 「モック切り替え機構」に従い、VITE_USE_MOCK で挙動を切り替える。
//   Phase B 以降の実 API 接続では、ここの fetch 部分が本格化する想定。
// ====================================================================

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

const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${path}`);
  }
  return (await res.json()) as T;
}

export async function getArtists(): Promise<ListResponse<Artist>> {
  if (USE_MOCK) return artistsMock as ListResponse<Artist>;
  return fetchJson<ListResponse<Artist>>("/api/artists");
}

export async function getVinylRecords(): Promise<ListResponse<VinylRecord>> {
  if (USE_MOCK) return vinylRecordsMock as ListResponse<VinylRecord>;
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
