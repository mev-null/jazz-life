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
    title: "あなたのアナログ・コレクション",
    body: "所有レコードのショーケースです。\nお気に入りの6枚をトップに大きく並べます。\nジャケットをクリックすると、盤情報・購入メモ・お気に入り曲まで見られます。",
  },
  {
    id: "digging",
    route: "/digging",
    selector: '[data-tour="nav-digging"]',
    placement: "bottom",
    title: "Digging",
    body: "所有していないレコードの管理を行います。\n探している盤（On the hunt）・音声検索（Listen）・新譜フィード（Releases）の3つのタブをまとめています。",
  },
  {
    id: "hunt",
    route: "/digging/hunt",
    selector: '[data-tour="hunt-list"]',
    navSelector: '[data-tour="subtab-hunt"]',
    placement: "bottom",
    title: "On the hunt — 探求中リスト",
    body: "「これから買いたい」レコードのウィッシュリストです。レコード屋でディグる時の探し物リストとして使い、手に入れたら所有（棚）へ移せます。",
  },
  {
    id: "listen",
    route: "/digging/listen",
    // 検索結果 (盤 + 認識結果のキャプション) をまるごとハイライトする。
    selector: '[data-tour="listen-area"]',
    navSelector: '[data-tour="subtab-listen"]',
    actionLabel: "検索してみる",
    actionTarget: '[data-tour="listen-disc"] button',
    // 盤を隠さないよう、カードは左側に寄せる。
    placement: "left",
    title: "音声でレコードを探す",
    body: "盤で流れている曲を音から検索できます（このデモでは録音せずサンプル曲を認識します）。\n下の「検索してみる」で実際に試せます。結果からそのまま「棚に迎え入れる」候補に追加できます。",
  },
  {
    id: "releases",
    route: "/digging/releases",
    selector: '[data-tour="releases-feed"]',
    navSelector: '[data-tour="subtab-releases"]',
    placement: "top",
    title: "新譜フィード",
    body: "フォロー中アーティストの新譜を時系列で表示します。\ntoday を境に upcoming / past へ分かれ、既読の管理もできます。",
  },
  {
    id: "artists",
    route: "/artists",
    selector: '[data-tour="artists"]',
    navSelector: '[data-tour="nav-artists"]',
    placement: "bottom",
    title: "アーティスト管理",
    body: "フォロー中アーティストの一覧です。右上の「+ add」から Spotify 検索（デモはサンプル候補）でフォローを追加できます。",
  },
  {
    id: "end",
    route: "/",
    placement: "center",
    title: "ツアーは以上です",
    body: "レコードの追加は、Home の「view all」→「+」から手動入力、または Spotify アルバム検索で自動入力できます。あとは自由に触ってみてください。右上の「tour」からいつでも再生できます。",
  },
];
