import type { Artist, Concert } from "../types/api";

/**
 * コンサートのタイトルにアーティスト名が含まれているかの単純判定。
 * 単一情報源とすることで、Phase B の concert_artists リレーション導入時に
 * ここだけ書き換えれば全箇所差し替わる。
 */
export function concertMatchesArtist(
  concert: Concert,
  artist: Artist,
): boolean {
  return concert.title.includes(artist.name);
}

/**
 * 与えられたコンサートに対し、最初にマッチするアーティストを返す。
 */
export function findArtistInConcert(
  concert: Concert,
  artists: Artist[],
): Artist | undefined {
  return artists.find((a) => concertMatchesArtist(concert, a));
}
