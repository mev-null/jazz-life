import { sleeveTintByKey } from "../../lib/palette";
import type { Release } from "../../types/api";

/**
 * Feed の Releases リスト行で「左にジャケット画像」を表示するための小さな
 * 正方形コンポーネント。VinylRecord 用の `JacketArt` (records/JacketCard.tsx)
 * と役割は同じだが、palette lookup の key が `Release.spotify_id` で違うのと、
 * Release 型の image_url 取り扱いに揃えるためコンポーネントを分けている。
 *
 * 共通の SleeveFallback ロジックを抽出するほどの規模ではないので、薄く 1
 * ファイル複製で割り切る (将来 image_url 補完経路が複雑化したら抽象化を検討)。
 */
export function ReleaseJacket({ release }: { release: Release }) {
  if (release.image_url) {
    return (
      <img
        src={release.image_url}
        alt=""
        className="h-full w-full object-cover"
      />
    );
  }
  return (
    <div
      className="h-full w-full"
      style={{ backgroundColor: sleeveTintByKey(release.spotify_id) }}
    />
  );
}
