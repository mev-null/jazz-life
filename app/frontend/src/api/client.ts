// ====================================================================
// API クライアント抽象（モック / 実 API 切替）
//   ADR-002 §2.7-§2.8 に従い、VITE_USE_MOCK で mock / 実 API を切り替える。
//
//   実 API パス:
//     - artists / records / releases は orval 生成 fetcher (src/api/generated/) を経由
//     - jacket upload は backend 未実装のため fetch のまま (Phase B-3 以降)
// ====================================================================

import { API_BASE, USE_MOCK } from "../lib/env";
import { PIN_LIMIT } from "../lib/pins";
import type {
  Artist,
  ArtistRecordCount,
  ListResponse,
  Release,
  SyncRunResult,
  SyncStatus,
  VinylRecord,
} from "../types/api";

import {
  getArtistApiArtistsSpotifyIdGet,
  listArtistsApiArtistsGet,
  upsertArtistApiArtistsPost,
} from "./generated/artists/artists";
import {
  createRecordApiRecordsPost,
  deleteRecordApiRecordsIdDelete,
  listRecordsApiRecordsGet,
  reorderPinsApiRecordsPinsOrderPut,
  updateRecordApiRecordsIdPut,
} from "./generated/records/records";
import {
  getSyncStatusApiReleasesSyncStatusGet,
  listReleasesApiReleasesGet,
  setReleaseReadStatusApiReleasesSpotifyIdReadPatch,
  triggerSyncApiReleasesSyncPost,
} from "./generated/releases/releases";
import {
  searchAlbumsApiSpotifyAlbumsSearchGet,
  searchArtistsApiSpotifyArtistsSearchGet,
} from "./generated/spotify/spotify";
import {
  followArtistApiUserFollowsPost,
  listFollowedArtistsApiUserFollowsArtistsGet,
  listRecordCountsApiUserFollowsRecordCountsGet,
  unfollowArtistApiUserFollowsArtistIdDelete,
} from "./generated/user-follows/user-follows";
import type {
  ArtistCreate,
  RecognitionResult,
  SpotifyAlbumSummary,
  SpotifyArtistSummary,
  SyncRunRequest,
  VinylRecordCreate,
  VinylRecordUpdate,
} from "./generated/model";

import artistsMock from "./mocks/artists.json";
import releasesMock from "./mocks/releases.json";
import spotifySearchMock from "./mocks/spotify_search.json";
import vinylRecordsMock from "./mocks/vinyl_records.json";

// In-memory mutable mirror of the records mock — initialised once per page load.
// Mutations modify this so subsequent reads reflect the change. Lost on refresh.
const mockRecordsStore: VinylRecord[] = (
  vinylRecordsMock as ListResponse<VinylRecord>
).items.slice();

// Artists も records と同じく可変ミラーを持つ。upsertArtist / Spotify 検索からの
// follow 追加が一覧 (getArtists / getFollowedArtists) に即反映されるようにするため
// (demo で「検索 → 追加 → 一覧に出る」体験を成立させる)。リロードで初期化。
const mockArtistsStore: Artist[] = (
  artistsMock as ListResponse<Artist>
).items.slice();

// demo の擬似 Spotify 検索結果。実 API と同じ shape の候補を返し、選択 → 自動入力 →
// 保存 / フォロー追加まで mock 経路で完走させる。`keywords` は曲名など別名検索用の
// 内部フィールドで、返却時に除去して SpotifyAlbumSummary 型に合わせる。
type MockAlbum = SpotifyAlbumSummary & { keywords?: string[] };
const mockSearchAlbums = spotifySearchMock.albums as MockAlbum[];
const mockSearchArtists = spotifySearchMock.artists as SpotifyArtistSummary[];

// backend の `is_pinned DESC, pin_order ASC NULLS LAST, display_order ASC`
// 順を mock 経路でも再現する。HomePage のプレビュー (slice 0..previewLimit) が
// pinned 優先で、かつ pin の中では drag & drop で確定した順 (pin_order) で
// 並ぶためには、この順序付けが mock 側にも必要。
function sortedMockRecords(): VinylRecord[] {
  return mockRecordsStore.slice().sort((a, b) => {
    if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;
    const ao = a.pin_order ?? Number.POSITIVE_INFINITY;
    const bo = b.pin_order ?? Number.POSITIVE_INFINITY;
    if (ao !== bo) return ao - bo;
    return a.display_order - b.display_order;
  });
}

const MOCK_PIN_LIMIT = PIN_LIMIT;

export async function getArtists(): Promise<ListResponse<Artist>> {
  if (USE_MOCK) return { items: mockArtistsStore.slice() };
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
    return mockArtistsStore.find((a) => a.spotify_id === spotifyId) ?? null;
  }
  const res = await getArtistApiArtistsSpotifyIdGet(spotifyId);
  if (res.status === 200) {
    return res.data as Artist;
  }
  return null;
}

/**
 * current user の「所有 (status='owned')」レコード件数を artist_id ごとに集計
 * して返す軽量エンドポイント。ArtistsPage 一覧の件数列に使うため、records 本体は
 * 取らずに件数だけ先取りする。実 API は `/api/user-follows/record-counts` (auth
 * 必須、wanted は数えない)。
 *
 * mock 時は user 概念を持たないので records.json 全体を artist_id でグループ化
 * して返す (frontend 単独でも件数が見えるよう、実 API の filter 厳密性より UX
 * を優先する)。
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
  const res = await listRecordCountsApiUserFollowsRecordCountsGet();
  return res.data as ListResponse<ArtistRecordCount>;
}

/**
 * 現ユーザが follow 中 (archived=false) の artists のみ返す。
 *
 * ArtistsPage 一覧専用。HomePage / RecordFormModal が使う `getArtists()` は
 * global registry (全 artists 行) を返す既存挙動のままで、本関数とはキャッシュ
 * キー (`["followed-artists"]`) を分けてある。auth 必須。
 *
 * mock 時は artists.json をそのまま返す (mock store は user_follows を表現
 * しないため、ArtistsPage では全 mock artists が見える)。
 */
export async function getFollowedArtists(): Promise<ListResponse<Artist>> {
  if (USE_MOCK) return { items: mockArtistsStore.slice() };
  const res = await listFollowedArtistsApiUserFollowsArtistsGet();
  return res.data as ListResponse<Artist>;
}

/**
 * Spotify artist の名前検索。ArtistsPage の「追加」モーダルで使う。
 *
 * 結果を選んで `upsertArtist` (POST /api/artists) → `followArtist`
 * (POST /api/user-follows) の 2 段でフォロー作成まで進める。USE_MOCK 時は
 * 実 API を叩かないので空配列を返す (mock では follow 追加 UI を機能させない)。
 */
export async function searchSpotifyArtists(
  q: string,
): Promise<SpotifyArtistSummary[]> {
  if (USE_MOCK) {
    if (!q.trim()) return [];
    await new Promise((r) => setTimeout(r, 250));
    const ql = q.trim().toLowerCase();
    const hit = mockSearchArtists.filter((a) =>
      a.name.toLowerCase().includes(ql),
    );
    // demo は「常に何か出る」方が体験が良いので、部分一致が無ければ全候補を返す。
    return hit.length ? hit : mockSearchArtists;
  }
  if (!q.trim()) return [];
  const res = await searchArtistsApiSpotifyArtistsSearchGet({ q });
  if (res.status === 200) {
    return res.data.items;
  }
  return [];
}

/**
 * artist_id を current user の follow に追加する。
 *
 * artist は事前に DB (`artists` テーブル) に存在している必要がある。
 * Spotify 検索結果から作る場合は先に `upsertArtist` を呼ぶこと。
 *
 * mock 時はネットワークを叩かない (mock store には user_follows 表現を持たない
 * ので no-op)。auth 必須エンドポイント。
 */
export async function followArtist(artistId: string): Promise<Artist | null> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 30));
    return null;
  }
  const res = await followArtistApiUserFollowsPost({ artist_id: artistId });
  return res.data as Artist;
}

/**
 * Spotify ID で artist を follow から外す (soft delete: archived_flag=true)。
 *
 * mock 時はネットワークを叩かない (mock store には user_follows 表現を持たない
 * ので no-op)。auth 必須エンドポイントなので cookie 同梱 (orval mutator 経由)。
 */
export async function unfollowArtist(spotifyId: string): Promise<void> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 30));
    return;
  }
  await unfollowArtistApiUserFollowsArtistIdDelete(spotifyId);
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
    // demo では可変ストアに upsert して、Spotify 検索 → 追加した artist が
    // ArtistsPage 一覧 / HomePage の名前解決に即反映されるようにする。
    const existing = mockArtistsStore.find(
      (a) => a.spotify_id === input.spotify_id,
    );
    if (existing) {
      existing.name = input.name;
      if (input.image_url !== undefined) existing.image_url = input.image_url;
      return existing;
    }
    const created: Artist = {
      spotify_id: input.spotify_id,
      name: input.name,
      image_url: input.image_url ?? null,
      source: input.source ?? "spotify_dynamic",
      added_at: new Date().toISOString(),
    } as Artist;
    mockArtistsStore.push(created);
    return created;
  }
  const res = await upsertArtistApiArtistsPost(input);
  return res.data as Artist;
}

/**
 * Records 一覧。`limit` 指定で paginated (RecordsAllModal の view all 用)、
 * 省略時は全件取得 (HomePage プレビューや ArtistDetailModal が要求する)。
 *
 * mock 経路は `is_pinned DESC, display_order ASC` 順 (backend と同じ) で
 * slice する。`total` は backend が `count_for_user` で出す総件数で、
 * フロント側で `Math.ceil(total / limit)` でページ数を出すのに使う。
 */
export async function getVinylRecords(
  limit?: number,
  offset?: number,
  status?: VinylRecord["status"],
): Promise<ListResponse<VinylRecord>> {
  if (USE_MOCK) {
    // status 指定時はその絞り込み後の集合を slice し、total も絞り込み後の
    // 件数にする (ページ数計算を owned のみで合わせる)。
    const pool = status
      ? sortedMockRecords().filter((r) => r.status === status)
      : sortedMockRecords();
    const start = offset ?? 0;
    const items =
      limit !== undefined ? pool.slice(start, start + limit) : pool;
    return { items, total: pool.length };
  }
  const params: {
    limit?: number;
    offset?: number;
    status?: VinylRecord["status"];
  } = {};
  if (limit !== undefined) params.limit = limit;
  if (offset !== undefined && offset > 0) params.offset = offset;
  if (status !== undefined) params.status = status;
  const res = await listRecordsApiRecordsGet(params);
  return res.data as ListResponse<VinylRecord>;
}

/**
 * Digging の Hunt list 用。`status=wanted` で絞り込み、並び替えは backend 責務
 * (ADR-013)。`sort="artist"` は artist 名昇順(→title)、`sort="added"` は
 * on the hunt 登録日 (created_at) 降順。frontend は backend が返した順を尊重して
 * 見出しグループ化するだけ。
 *
 * mock 経路でも同じ並びを再現する (artist は artistsMock で name lookup)。
 */
export async function getWantedRecords(
  sort: "artist" | "added",
): Promise<ListResponse<VinylRecord>> {
  if (USE_MOCK) {
    const nameById = new Map(
      mockArtistsStore.map((a) => [a.spotify_id, a.name]),
    );
    const items = mockRecordsStore
      .filter((r) => r.status === "wanted")
      .sort((a, b) => {
        if (sort === "added") return b.created_at.localeCompare(a.created_at);
        const an = nameById.get(a.artist_id) ?? "";
        const bn = nameById.get(b.artist_id) ?? "";
        return an.localeCompare(bn) || a.title.localeCompare(b.title);
      });
    return { items, total: items.length };
  }
  const res = await listRecordsApiRecordsGet({ status: "wanted", sort });
  return res.data as ListResponse<VinylRecord>;
}

/**
 * drag & drop で並び替えた pin 一覧の順序を保存する。
 *
 * `ids` は **現在 pin している全行** を、ユーザが望む順序で並べたもの。
 * backend は受け取った順に `pin_order` を 1..N で振り直す。pin セットと
 * 一致しない (欠け/重複/未 pin 行混入) なら 409。
 *
 * mock 経路では mock store の `pin_order` を直接書き換えるので、再 fetch なし
 * でも `sortedMockRecords` の並び順が即時反映される。
 */
export async function reorderPins(ids: string[]): Promise<void> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 60));
    const pinned = mockRecordsStore.filter((r) => r.is_pinned);
    const pinnedIds = new Set(pinned.map((r) => r.id));
    const requested = new Set(ids);
    if (
      pinnedIds.size !== requested.size ||
      [...pinnedIds].some((id) => !requested.has(id))
    ) {
      const err = new Error("pin reorder mismatch") as Error & { status?: number };
      err.status = 409;
      throw err;
    }
    ids.forEach((id, idx) => {
      const i = mockRecordsStore.findIndex((r) => r.id === id);
      if (i >= 0) {
        mockRecordsStore[i] = { ...mockRecordsStore[i], pin_order: idx + 1 };
      }
    });
    return;
  }
  await reorderPinsApiRecordsPinsOrderPut({ ids });
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
 * release の既読フラグを切り替える (PATCH 経由)。auth 必須。
 *
 * frontend では「Digging の release 行をクリック」 / 「ReleaseDetailModal で
 * mark as read / unread」のタイミングで呼ぶ。release.is_read が backend
 * 永続化されるので、ブラウザを跨いでも既読状態が保持される (localStorage
 * 時代との違い)。
 *
 * mock 時はネットワークを叩かず、入力された is_read 状態をそのまま返す。
 */
export async function setReleaseRead(
  spotifyId: string,
  isRead: boolean,
): Promise<Release> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 20));
    const mock = (releasesMock as ListResponse<Release>).items.find(
      (r) => r.spotify_id === spotifyId,
    );
    return {
      ...(mock ?? ({} as Release)),
      is_read: isRead,
      read_at: isRead ? new Date().toISOString() : null,
    };
  }
  const res = await setReleaseReadStatusApiReleasesSpotifyIdReadPatch(spotifyId, {
    is_read: isRead,
  });
  return res.data as Release;
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

// id / created_at / updated_at / display_order は backend が採番する。
// mock 側でも同じ shape のレコードを返す。
export async function createVinylRecord(
  input: VinylRecordCreate,
): Promise<VinylRecord> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 80));
    const now = new Date().toISOString();
    const status = input.status ?? "owned";
    // backend と同じルールで purchase_date を決める:
    // - wanted: 明示値が来ても強制 None
    // - owned + 未指定: 今日 (ブラウザ TZ。Asia/Tokyo の本番と相互運用するので
    //   ロケール `sv-SE` で ISO 形式に揃える)
    const purchaseDate =
      status === "wanted"
        ? null
        : (input.purchase_date ?? new Date().toLocaleDateString("sv-SE"));
    // owned で新規作成かつ pin 枠に空きがあれば auto-pin (backend の
    // _auto_pin_if_room と一致)。末尾 = max(pin_order)+1 で採番。
    const pinnedNow = mockRecordsStore.filter((r) => r.is_pinned);
    const autoPin = status === "owned" && pinnedNow.length < MOCK_PIN_LIMIT;
    const autoPinOrder = autoPin
      ? pinnedNow.reduce((acc, r) => Math.max(acc, r.pin_order ?? 0), 0) + 1
      : null;
    const created: VinylRecord = {
      id: crypto.randomUUID(),
      artist_id: input.artist_id,
      spotify_album_id: input.spotify_album_id ?? null,
      source: input.source ?? "manual",
      status,
      title: input.title,
      image_url: input.image_url ?? null,
      original_release_date: input.original_release_date ?? null,
      pressing_info: input.pressing_info ?? null,
      purchase_date: purchaseDate,
      purchase_store: input.purchase_store ?? null,
      purchase_price: input.purchase_price ?? null,
      purchase_currency: input.purchase_currency ?? "JPY",
      rating: input.rating ?? null,
      memo: input.memo ?? null,
      favorite_tracks: input.favorite_tracks ?? [],
      display_order: mockRecordsStore.length + 1,
      is_pinned: autoPin,
      pin_order: autoPinOrder,
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
    const current = mockRecordsStore[idx];
    // wanted → owned 遷移時、purchase_date が None なら今日 (ブラウザ TZ) を自動打刻。
    // patch に明示 purchase_date があればそちらを優先 (backend 側挙動と一致)。
    if (
      input.status === "owned" &&
      current.status === "wanted" &&
      input.purchase_date === undefined &&
      current.purchase_date === null
    ) {
      patch.purchase_date = new Date().toLocaleDateString("sv-SE");
    }
    // wanted→owned 遷移で owned になった瞬間、is_pinned の明示が無く pin 枠に
    // 空きがあれば auto-pin (backend の _auto_pin_if_room と一致)。
    if (
      input.status === "owned" &&
      current.status === "wanted" &&
      input.is_pinned === undefined &&
      !current.is_pinned
    ) {
      const pinned = mockRecordsStore.filter((r) => r.is_pinned);
      if (pinned.length < MOCK_PIN_LIMIT) {
        patch.is_pinned = true;
        patch.pin_order =
          pinned.reduce((acc, r) => Math.max(acc, r.pin_order ?? 0), 0) + 1;
      }
    }
    // backend の False→True 遷移 + pin 上限到達で 409 を mock 側でも emulate。
    // 新規 pin は pin_order = max+1 で末尾に。unpin は pin_order = null。
    if (input.is_pinned === true && !current.is_pinned) {
      const pinned = mockRecordsStore.filter((r) => r.is_pinned);
      if (pinned.length >= MOCK_PIN_LIMIT) {
        const err = new Error(`pin limit exceeded: max ${MOCK_PIN_LIMIT}`) as Error & {
          status?: number;
        };
        err.status = 409;
        throw err;
      }
      const maxOrder = pinned.reduce(
        (acc, r) => Math.max(acc, r.pin_order ?? 0),
        0,
      );
      patch.pin_order = maxOrder + 1;
    } else if (input.is_pinned === false && current.is_pinned) {
      patch.pin_order = null;
    }
    const updated: VinylRecord = {
      ...current,
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
  if (USE_MOCK) {
    if (!q.trim()) return [];
    await new Promise((r) => setTimeout(r, 250));
    const ql = q.trim().toLowerCase();
    const al = artist?.trim().toLowerCase();
    const matches = (a: MockAlbum): boolean => {
      const hay = [
        a.name.toLowerCase(),
        ...a.artist_names.map((n) => n.toLowerCase()),
        ...(a.keywords ?? []),
      ];
      const byTitle = hay.some((h) => h.includes(ql));
      const byArtist = al
        ? a.artist_names.some((n) => n.toLowerCase().includes(al))
        : false;
      return byTitle || byArtist;
    };
    const hit = mockSearchAlbums.filter(matches);
    // 候補ゼロだと「no results」で体験が途切れるので、未ヒット時は全候補を出す。
    const pool = hit.length ? hit : mockSearchAlbums;
    // keywords は内部用なので除去して API 型 (SpotifyAlbumSummary) に揃える。
    return pool.map(({ keywords: _keywords, ...rest }) => rest);
  }
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

/**
 * 録音した短いクリップ (blob) を AudD で認識し、artist + title + アルバム情報を返す
 * (ADR-016)。Digging の Listen タブから呼ぶ。
 *
 * orval fetch mode は multipart UploadFile body を素直に生成しないので、jacket
 * upload と同じく生 fetch + FormData で送る (credentials は auth cookie 同梱)。
 *
 * USE_MOCK 時はネットワーク / マイクを使わず固定のダミー認識結果を返す。実 API
 * 接続 + マイク許可が無くても、Listen タブ → 追加フォームの導線を UI 検証できる。
 */
export async function recognizeAudio(blob: Blob): Promise<RecognitionResult> {
  if (USE_MOCK) {
    // demo は「実際に検索している」感を出すため、認識 (Reading the groove) を
    // やや長めに取る (Shazam 風の指紋照合を模した待ち時間)。
    await new Promise((r) => setTimeout(r, 2800));
    // UI 確認用ダミー。ジャケット表示を見せるため実在のカバー画像を持たせる。
    return {
      matched: true,
      title: "So What",
      artist_name: "Miles Davis",
      album: "Kind of Blue",
      spotify_album_id: "1weenld61qoidwYuZ1GjTr",
      spotify_artist_id: "0kbYTNQb4Pb1rPbbaF0pT4",
      artist_image_url: null,
      image_url:
        "https://i.scdn.co/image/ab67616d0000b2730ebc17239b6b18ba88cfb8ca",
      original_release_date: "1959-08-17",
    };
  }
  const fd = new FormData();
  // backend は UploadFile.file.read() でバイト列だけ使うので filename は任意。
  fd.append("file", blob, "clip");
  const res = await fetch(`${API_BASE}/api/recognize`, {
    method: "POST",
    body: fd,
    credentials: "include",
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`POST recognize failed: ${res.status}${detail ? ` — ${detail}` : ""}`);
  }
  return (await res.json()) as RecognitionResult;
}
