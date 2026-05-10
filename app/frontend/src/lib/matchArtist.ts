import type { Artist, Concert } from "../types/api";

/**
 * コンサートのタイトルにアーティスト名が含まれているかの単純判定。
 * 単一情報源とすることで、Phase B の concert_artists リレーション導入時に
 * ここだけ書き換えれば全箇所差し替わる。
 *
 * 意味論: 「本人出演」ではなく「そのアーティストに *関連* する公演」を拾う。
 * 例えば "Bill Evans Tribute" は Bill Evans 本人の出演ではないが、
 * 関連公演として Artist 詳細の Activity に表示する意図でマッチさせている。
 * 大文字小文字は無視する。
 */
export function concertMatchesArtist(
  concert: Concert,
  artist: Artist,
): boolean {
  return concert.title.toLowerCase().includes(artist.name.toLowerCase());
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
