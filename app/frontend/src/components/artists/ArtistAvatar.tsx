import { useState } from "react";

import { avatarTintByString } from "../../lib/palette";
import type { Artist } from "../../types/api";

function initials(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length === 0) return "—";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

/**
 * Artist の正方形アバター。
 *
 * 表示の決定木:
 * - image_url が無い、または画像読み込みに失敗 (`onError` 発火) → イニシャル
 * - image_url 有り、ロード中含めて成功経路 → 画像 (まだ来てない間は背景色のみ
 *   見えてイニシャルは出さない: 「成功するはずの画像」の前にチラつかせない)
 *
 * 共通の色背景 (spotify_id ハッシュ由来) は `<div>` に常に乗せて、画像ロード
 * 中の素の白枠を防ぐ役を兼ねさせる。
 *
 * `size`:
 * - "sm": 一覧行用 (40px 相当)
 * - "lg": detail modal ヘッダ用 (80px 相当)
 */
export function ArtistAvatar({
  artist,
  size = "lg",
}: {
  artist: Artist;
  size?: "sm" | "lg";
}) {
  const [imageError, setImageError] = useState(false);
  const sizeClass = size === "sm" ? "w-10" : "w-20";
  const textClass = size === "sm" ? "text-xs" : "text-base";
  const bg = avatarTintByString(artist.spotify_id);
  // palette の warm 系 (#b08a3a) は文字を黒、それ以外は紙色に倒して可読性を担保。
  const isWarm = bg === "#b08a3a";
  const showImage = artist.image_url && !imageError;
  return (
    <div
      className={`relative aspect-square ${sizeClass} shrink-0 overflow-hidden`}
      style={{
        backgroundColor: bg,
        color: isWarm ? "#1a1714" : "#f4efe3",
      }}
    >
      {showImage ? (
        <img
          src={artist.image_url ?? undefined}
          alt=""
          onError={() => setImageError(true)}
          className="h-full w-full object-cover"
        />
      ) : (
        <span
          className={`absolute inset-0 flex items-center justify-center ${textClass} font-medium tracking-wide`}
        >
          {initials(artist.name)}
        </span>
      )}
    </div>
  );
}
