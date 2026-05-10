// ジャケットスリーブ / アーティストアバターのフォールバック塗りに使う色。
//
// SLEEVE: ジャケット未登録時に正方形を塗りつぶす。クリーム (#e8dec5) を含む 6 色。
// AVATAR: アーティスト画像未登録時の円形アバターに使う。紙背景とのコントラスト確保のため
//         明るいクリームは除外した 5 色。

export const SLEEVE_TINTS = [
  "#1f3d2e",
  "#e8dec5",
  "#1a1714",
  "#b08a3a",
  "#6e2a2a",
  "#3a4a55",
] as const;

export const AVATAR_TINTS = [
  "#1f3d2e",
  "#1a1714",
  "#6e2a2a",
  "#3a4a55",
  "#b08a3a",
] as const;

export function sleeveTintByIndex(i: number): string {
  return SLEEVE_TINTS[i % SLEEVE_TINTS.length];
}

export function avatarTintByString(key: string): string {
  // djb2: アナグラム衝突を避けるため積算 + XOR で順序を反映する。
  // `^` が暗黙に 32bit int 化するので hash はオーバーフローしない。
  let hash = 5381;
  for (let i = 0; i < key.length; i++) {
    hash = (hash * 33) ^ key.charCodeAt(i);
  }
  return AVATAR_TINTS[Math.abs(hash) % AVATAR_TINTS.length];
}
