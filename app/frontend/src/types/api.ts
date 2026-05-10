// 既実装 (artists / records) は orval 生成から re-export し、未実装は
// 手書きの暫定型として残す。backend 実装が進むたびに対応する手書き型を
// generated 由来へ置換していく。詳細は ADR-002 §2.7 を参照。

export type {
  ArtistRead as Artist,
  VinylRecordRead as VinylRecord,
} from "../api/generated/model";

export type ListResponse<T> = {
  items: T[];
};

// ---------- アーティストエイリアス（backend 未実装）----------
export type ArtistAlias = {
  id: number;
  artist_id: string;
  alias_name: string;
  created_at: string;
};

// ---------- 新譜（backend 未実装）----------
export type AlbumType = "album" | "single" | "compilation" | "appears_on";

export type Release = {
  spotify_id: string;
  artist_id: string;
  title: string;
  album_type: AlbumType;
  release_date: string; // ISO 8601 date
  image_url: string | null;
};

// ---------- 公演（backend 未実装）----------
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

// ---------- 同期ステータス（backend 未実装）----------
export type SyncStatus = {
  source: string;
  last_success_at: string | null;
  last_attempt_at: string | null;
  last_error: string | null;
};

// ---------- 認証（backend 未実装）----------
// 注: アクセストークン / リフレッシュトークンはサーバ側のみで保持し、
//     フロントには絶対に渡さない。フロントが受け取るのは表示用のプロフィールのみ。
export type AuthUser = {
  spotify_id: string;
  display_name: string;
  image_url: string | null;
};
