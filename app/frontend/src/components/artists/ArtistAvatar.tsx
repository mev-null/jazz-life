import { avatarTintByString } from "../../lib/palette";
import type { Artist } from "../../types/api";

function initials(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length === 0) return "—";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

/**
 * Artist の正方形アバター。image_url があれば画像、無ければ spotify_id ハッシュ
 * 由来の色背景 + イニシャル fallback。
 *
 * `size` で表示サイズを切り替える:
 * - "sm": 一覧行用 (40px 相当)
 * - "lg": detail modal ヘッダ用 (80px 相当)
 *
 * 共通レイアウト要件 (正方形, 余白詰め) はここで持つ。呼び出し側は外側の
 * gap / shrink で並べる。
 */
export function ArtistAvatar({
  artist,
  size = "lg",
}: {
  artist: Artist;
  size?: "sm" | "lg";
}) {
  const sizeClass = size === "sm" ? "w-10" : "w-20";
  const textClass = size === "sm" ? "text-xs" : "text-base";
  if (artist.image_url) {
    return (
      <img
        src={artist.image_url}
        alt=""
        className={`aspect-square ${sizeClass} shrink-0 object-cover`}
      />
    );
  }
  const bg = avatarTintByString(artist.spotify_id);
  // palette の warm 系 (#b08a3a) は文字を黒、それ以外は紙色に倒して可読性を担保。
  const isWarm = bg === "#b08a3a";
  return (
    <div
      className={`flex aspect-square ${sizeClass} shrink-0 items-center justify-center`}
      style={{
        backgroundColor: bg,
        color: isWarm ? "#1a1714" : "#f4efe3",
      }}
    >
      <span className={`${textClass} font-medium tracking-wide`}>
        {initials(artist.name)}
      </span>
    </div>
  );
}
