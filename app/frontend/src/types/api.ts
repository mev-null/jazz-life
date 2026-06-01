// 既実装 (artists / records) は orval 生成から re-export し、未実装は
// 手書きの暫定型として残す。backend 実装が進むたびに対応する手書き型を
// generated 由来へ置換していく。詳細は ADR-002 §2.7 を参照。

export type {
  ArtistRead as Artist,
  ArtistRecordCount,
  RecognitionResult,
  ReleaseRead as Release,
  ReleaseReadAlbumType as AlbumType,
  SyncRunAccepted,
  SyncStatusRead as SyncStatus,
  VinylRecordRead as VinylRecord,
} from "../api/generated/model";

export type ListResponse<T> = {
  items: T[];
  // backend の `ListResponse.total` (デフォルト 0)。paginated endpoint
  // (`getVinylRecords(limit, offset)`) で使うので optional にして既存呼び出しを
  // 壊さない。フロントは `total ?? items.length` でフォールバックする。
  total?: number;
};

// ---------- アーティストエイリアス（backend 未実装）----------
export type ArtistAlias = {
  id: number;
  artist_id: string;
  alias_name: string;
  created_at: string;
};

// 公演 (Concert) は ADR-013 で UI から撤去した。backend モデルは温存しているが
// frontend では型・参照を持たない。将来再導入する場合は ADR-007 の方針
// (catalog を backend に降ろす) に沿って generated 由来で復活させる。

// ---------- 認証（backend 未実装）----------
// 注: アクセストークン / リフレッシュトークンはサーバ側のみで保持し、
//     フロントには絶対に渡さない。フロントが受け取るのは表示用のプロフィールのみ。
export type AuthUser = {
  spotify_id: string;
  display_name: string;
  image_url: string | null;
};
