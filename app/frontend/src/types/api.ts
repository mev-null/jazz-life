// ====================================================================
// Phase A: 手書き暫定型
//   ADR §12「データモデル」を TypeScript に写経したもの。
//   バックエンドの Pydantic モデルが立ち上がり次第（Phase B-2）、
//   `make gen` で生成される `api.generated.ts` に置き換えてこのファイルは破棄する。
// ====================================================================

// ---------- アーティスト ----------
export type Artist = {
  spotify_id: string;
  name: string;
  image_url: string | null;
  followed: boolean;
  added_at: string; // ISO 8601 datetime
};

export type ArtistAlias = {
  id: number;
  artist_id: string;
  alias_name: string;
  created_at: string;
};

// ---------- 新譜 ----------
export type AlbumType = "album" | "single" | "compilation" | "appears_on";

export type Release = {
  spotify_id: string;
  artist_id: string;
  title: string;
  album_type: AlbumType;
  release_date: string; // ISO 8601 date
  image_url: string | null;
};

// ---------- レコードコレクション ----------
export type VinylRecord = {
  id: number;
  artist_id: string;
  spotify_album_id: string | null;
  title: string;
  image_url: string | null;
  original_release_year: number | null;
  pressing_info: string | null;
  purchase_date: string | null;
  purchase_store: string | null;
  purchase_price: number | null;
  rating: number | null; // 1-5
  memo: string | null;
  display_order: number;
  created_at: string;
  updated_at: string;
};

// ---------- 公演 ----------
export type Venue = {
  id: string;
  name: string;
  city: string;
};

export type ConcertStatus = "scheduled" | "cancelled" | "postponed";

export type Concert = {
  id: string;
  venue_id: string;
  date: string;
  title: string;
  url: string | null;
  stage_times: string | null; // カンマ区切り
  status: ConcertStatus;
  first_seen_at: string;
  last_seen_at: string;
};

export type ConcertArtist = {
  concert_id: string;
  artist_id: string;
};

// ---------- 同期ステータス ----------
export type SyncStatus = {
  source: string;
  last_success_at: string | null;
  last_attempt_at: string | null;
  last_error: string | null;
};

// ---------- 共通レスポンス ----------
export type ListResponse<T> = {
  items: T[];
};
