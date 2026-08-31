// demo の機能紹介ツアーのステップ定義。
//
// 各ステップは「そのルートへ遷移 → selector の要素をスポットライト → 吹き出しで
// 解説」する。selector が無いステップ (end) は中央にカードだけ出す。
// selector は対象コンポーネントに付けた `data-tour="..."` 属性と対応する。

export type TourPlacement = "top" | "bottom" | "left" | "right" | "center";

export type TourStep = {
  id: string;
  /** ステップ表示前に遷移するルート。 */
  route: string;
  /** スポットライト対象の CSS セレクタ。省略時は中央にカードのみ。 */
  selector?: string;
  /**
   * 「タブ移動」を動的に見せるための導入スポットライト先 (移動先タブ/ナビ)。
   * 指定すると、ステップ開始時にまずこの要素をスポットライト → 少し置いて
   * selector のコンテンツへスポットライトが滑って移る。
   */
  navSelector?: string;
  /**
   * このステップで「Next」の代わりに出す実演ボタン。actionTarget の要素を
   * クリックして実際の挙動を走らせる (例: Listen の盤をタップして音声認識)。
   * 実演後はボタンが Next/Finish に戻る。
   */
  actionLabel?: string;
  actionTarget?: string;
  title: string;
  body: string;
  /** 吹き出しを対象の上/下どちらに出すか。省略時は bottom。 */
  placement?: TourPlacement;
};

export const TOUR_STEPS: TourStep[] = [
  {
    id: "home",
    route: "/",
    // 導入は最終ステップ (end) と同じく、特定要素をスポットライトせず
    // 全面ディム + 上部カードで見せる。
    placement: "center",
    title: "Your analog collection",
    body: "A showcase of the records you own.\nYour six favorites sit large at the top.\nClick a jacket to see pressing details, purchase notes, and favorite tracks.",
  },
  {
    id: "digging",
    route: "/digging",
    selector: '[data-tour="nav-digging"]',
    placement: "bottom",
    title: "Digging",
    body: "Everything you don't own yet lives here.\nThree tabs: records you're looking for (On the hunt), search by sound (Listen), and a feed of new releases (Releases).",
  },
  {
    id: "hunt",
    route: "/digging/hunt",
    selector: '[data-tour="hunt-list"]',
    navSelector: '[data-tour="subtab-hunt"]',
    placement: "bottom",
    title: "On the hunt — your wishlist",
    body: "A wishlist of records you're hoping to buy. Use it as your shopping list when digging in a record shop; once you find one, move it to your shelf.",
  },
  {
    id: "listen",
    route: "/digging/listen",
    // 検索結果 (盤 + 認識結果のキャプション) をまるごとハイライトする。
    selector: '[data-tour="listen-area"]',
    navSelector: '[data-tour="subtab-listen"]',
    actionLabel: "Try a search",
    actionTarget: '[data-tour="listen-disc"] button',
    // 盤を隠さないよう、カードは左側に寄せる。
    placement: "left",
    title: "Find a record by sound",
    body: "Search for a record by the music playing (in this demo nothing is recorded — a sample track is recognized instead).\nTap “Try a search” below to see it in action. From the result you can add the record straight to the hunt.",
  },
  {
    id: "releases",
    route: "/digging/releases",
    selector: '[data-tour="releases-feed"]',
    navSelector: '[data-tour="subtab-releases"]',
    placement: "top",
    title: "New releases",
    body: "New releases from the artists you follow, in date order.\nThey split into upcoming and past around today, and you can mark them as read.",
  },
  {
    id: "artists",
    route: "/artists",
    selector: '[data-tour="artists"]',
    navSelector: '[data-tour="nav-artists"]',
    placement: "bottom",
    title: "Artists",
    body: "The artists you follow. Use “+ add” in the top right to search Spotify (the demo shows sample results) and follow more.",
  },
  {
    id: "end",
    route: "/",
    placement: "center",
    title: "That's the tour",
    body: "To add a record, go to Home → “view all” → “+” and enter it by hand, or let a Spotify album search fill it in. From here, explore freely. You can replay this tour anytime from “tour” in the top right.",
  },
];
