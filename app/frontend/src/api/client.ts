// ====================================================================
// API クライアント抽象（モック / 実 API 切替）
//   ADR-002 §2.7-§2.8 に従い、VITE_USE_MOCK で mock / 実 API を切り替える。
//
//   実 API パス:
//     - artists / records / releases は orval 生成 fetcher (src/api/generated/) を経由
//     - concerts / jacket upload は backend 未実装のため fetch のまま
//       (jacket upload の実 API は Phase B-3 以降)
// ====================================================================

import { API_BASE, USE_MOCK } from "../lib/env";
import type {
  Artist,
  ArtistRecordCount,
  Concert,
  ListResponse,
  Release,
  SyncRunResult,
  SyncStatus,
  VinylRecord,
} from "../types/api";

import {
  getArtistApiArtistsSpotifyIdGet,
  listArtistsApiArtistsGet,
  listRecordCountsApiArtistsRecordCountsGet,
  upsertArtistApiArtistsPost,
} from "./generated/artists/artists";
import {
  createRecordApiRecordsPost,
  deleteRecordApiRecordsIdDelete,
  listRecordsApiRecordsGet,
  updateRecordApiRecordsIdPut,
} from "./generated/records/records";
import {
  getSyncStatusApiReleasesSyncStatusGet,
  listReleasesApiReleasesGet,
  triggerSyncApiReleasesSyncPost,
} from "./generated/releases/releases";
import { searchAlbumsApiSpotifyAlbumsSearchGet } from "./generated/spotify/spotify";
import type {
  ArtistCreate,
  SpotifyAlbumSummary,
  SyncRunRequest,
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

/**
 * 単一 artist の lazy fetch。ArtistDetailModal を開いた時に呼び、
 * backend 側で image_url が NULL なら Spotify から補完されて返ってくる。
 *
 * mock モードでは artists.json から spotify_id 一致を引くだけで Spotify は
 * 叩かない (実 API 切替時にだけ画像 hydration が走る)。
 */
export async function getArtist(spotifyId: string): Promise<Artist | null> {
  if (USE_MOCK) {
    const mock = artistsMock as ListResponse<Artist>;
    return mock.items.find((a) => a.spotify_id === spotifyId) ?? null;
  }
  const res = await getArtistApiArtistsSpotifyIdGet(spotifyId);
  if (res.status === 200) {
    return res.data as Artist;
  }
  return null;
}

/**
 * artist_id ごとの所有レコード件数を集計して返す軽量エンドポイント。
 * ArtistsPage 一覧の件数列に使うため、records 本体は取らずに件数だけ先取りする。
 */
export async function getRecordCounts(): Promise<ListResponse<ArtistRecordCount>> {
  if (USE_MOCK) {
    const records = (vinylRecordsMock as ListResponse<VinylRecord>).items;
    const counts = new Map<string, number>();
    for (const r of records) {
      counts.set(r.artist_id, (counts.get(r.artist_id) ?? 0) + 1);
    }
    return {
      items: [...counts.entries()].map(([artist_id, count]) => ({
        artist_id,
        count,
      })),
    };
  }
  const res = await listRecordCountsApiArtistsRecordCountsGet();
  return res.data as ListResponse<ArtistRecordCount>;
}

/**
 * Spotify ID をキーに artist を upsert する。
 *
 * RecordFormModal で Spotify album を選んだ時、その album.artists[0] が DB に
 * 無ければこの関数で追加してから records POST に進む。重複呼び出しは backend が
 * 冪等処理するので呼び出し側でガードしなくて良い。USE_MOCK 時はネットワークを
 * 叩かず入力を mock store にだけ追加して既存挙動を維持する。
 */
export async function upsertArtist(input: ArtistCreate): Promise<Artist> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 30));
    // mock では artists.json をディープに更新する設計まではしない。
    // 呼び出し側の record 作成と form 上の整合だけ保てれば十分なので、
    // 入力をそのまま Artist 互換で返して上位の cache に任せる。
    const now = new Date().toISOString();
    return {
      spotify_id: input.spotify_id,
      name: input.name,
      image_url: input.image_url ?? null,
      source: input.source ?? "spotify_dynamic",
      added_at: now,
    } as Artist;
  }
  const res = await upsertArtistApiArtistsPost(input);
  return res.data as Artist;
}

export async function getVinylRecords(): Promise<ListResponse<VinylRecord>> {
  if (USE_MOCK) return { items: mockRecordsStore.slice() };
  const res = await listRecordsApiRecordsGet();
  return res.data as ListResponse<VinylRecord>;
}

/**
 * 期間窓内 (デフォルト today-30d .. today+30d) の release 一覧を取る。
 *
 * mock モードでは releases.json の items をそのまま返し (frontend 側で期間
 * フィルタは行わない、検証用)、実 API モードでは backend のデフォルト窓に
 * 任せる (from/to 省略時 today-30d/today+30d)。
 */
export async function getReleases(
  from?: string,
  to?: string,
): Promise<ListResponse<Release>> {
  if (USE_MOCK) return releasesMock as ListResponse<Release>;
  const params: { from?: string; to?: string } = {};
  if (from) params.from = from;
  if (to) params.to = to;
  const res = await listReleasesApiReleasesGet(params);
  return res.data as ListResponse<Release>;
}

/**
 * Spotify Get Artist's Albums をフォロー中アーティスト全件に対し走らせて
 * releases テーブルを upsert する。認証必須 (current_user 経由で
 * user_follows を絞る)。
 *
 * USE_MOCK 時はネットワークを叩かず、ダミー結果を返す (mock は再同期不要)。
 */
export async function triggerReleaseSync(
  payload?: SyncRunRequest,
): Promise<SyncRunResult> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 30));
    return {
      artists_total: 0,
      artists_succeeded: 0,
      albums_ingested: 0,
      first_error: null,
    };
  }
  const res = await triggerSyncApiReleasesSyncPost(payload ?? null);
  return res.data as SyncRunResult;
}

/**
 * release sync の最終実行ステータス。空状態 (一度も sync していない) を
 * 区別するため、source 以外は null になり得る。Feed 画面の「最終同期日時 /
 * エラー状態」表示 (ADR-000 §314) に使う想定。
 */
export async function getReleaseSyncStatus(): Promise<SyncStatus> {
  if (USE_MOCK) {
    return {
      source: "spotify_releases",
      last_success_at: null,
      last_attempt_at: null,
      last_error: null,
    };
  }
  const res = await getSyncStatusApiReleasesSyncStatusGet();
  return res.data as SyncStatus;
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
      status: input.status ?? "owned",
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

/**
 * 1 件削除。auth 必須 (backend で get_current_user ガード済み)。
 *
 * user_follows は触らないので、最後の 1 件を消しても follow と sync 対象は
 * 残ったまま。「興味なくなった」を反映したい場合は将来 unfollow UI を別途。
 */
export async function deleteVinylRecord(id: string): Promise<void> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 30));
    const idx = mockRecordsStore.findIndex((r) => r.id === id);
    if (idx < 0) throw new Error(`record not found: ${id}`);
    mockRecordsStore.splice(idx, 1);
    return;
  }
  await deleteRecordApiRecordsIdDelete(id);
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
 * Spotify album search (Phase B-3 PR-2 / ADR-002 §2.7 連携)
 *
 * backend が認証必須の `/api/spotify/albums/search` を立てて Spotify Search API を
 * プロキシする。Record 追加時に呼び、選択した album の `image_url` /
 * `spotify_album_id` / `original_release_date` をフォームに自動入力する用途。
 *
 * USE_MOCK 時はネットワークを叩かず空配列を返す。検索 UI は実 API 接続時にのみ
 * 機能する（モック表示を充実させるよりも、実際に画像が並ぶことを優先）。
 */
export async function searchSpotifyAlbums(
  q: string,
  artist?: string,
): Promise<SpotifyAlbumSummary[]> {
  if (USE_MOCK) return [];
  if (!q.trim()) return [];
  const params = artist ? { q, artist } : { q };
  const res = await searchAlbumsApiSpotifyAlbumsSearchGet(params);
  if (res.status === 200) {
    return res.data.items;
  }
  return [];
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
