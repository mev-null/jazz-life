// ====================================================================
// API 型の集約ポイント。
//
// Phase B-2 PR-A 以降:
//   - backend 実装済み (artists / records) の型は orval 生成
//     (src/api/generated/model/) から re-export する。
//   - backend 未実装 (releases / concerts / sync_status / auth / artist_aliases)
//     は Phase A の手書き暫定型をそのまま残す。
//
// 後続 PR で backend が拡張されたら、対応する手書き型を generated 由来に
// 順次置換していく。最終的にこのファイルは re-export のみとなる想定。
//
// ADR-002 §6 / §2.7 を参照。
// ====================================================================

// ---------- backend 実装済み（orval 生成からの re-export）----------
export type {
  ArtistRead as Artist,
  VinylRecordRead as VinylRecord,
} from "../api/generated/model";

// ---------- 共通レスポンス（手書きジェネリック）----------
// 生成側に `ListResponseArtistRead` / `ListResponseVinylRecordRead` の
// concrete 型はあるが、mock や useQuery の汎用ラッパで使うため
// ジェネリック版を手書きで保持する。
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
