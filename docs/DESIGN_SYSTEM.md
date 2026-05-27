# Jazz-Life Design System

> このドキュメントは jazz-life フロントエンドのビジュアルデザインを別プロジェクトやリデザイン時にそのまま再現できるよう、全デザイントークン・コンポーネントパターンを網羅したものである。LLM コンテキストとしてそのまま渡すことを想定。

---

## 1. デザインコンセプト

**「ヴィンテージ・レコードスリーブ」** — アナログレコードの紙ジャケットを手に取った時の質感。

- ダークモードなし。クリーム紙にダークインクの単一テーマ
- 角丸なし（カード・ボタン・モーダルすべて直角）
- ボックスシャドウは最小限（モーダルの `shadow-xl` のみ）
- 装飾を削ぎ落としたフラットデザイン。余白と書体で階層を表現
- アイコンライブラリ不使用。SVG は必要最小限、文字記号（★ ← → +）で代替
- セリフ体中心の活字的タイポグラフィ

---

## 2. カラーパレット

### 2.1 テーマカラー（CSS Custom Properties）

```css
@theme {
  --color-paper:     #f4efe3;       /* 背景。温かみのあるクリーム */
  --color-ink:       #1a1714;       /* 前景。深いブラウンブラック */
  --color-ink-mute:  #1a171499;     /* 60% opacity — 副テキスト */
  --color-ink-faint: #1a17144d;     /* 30% opacity — 第三テキスト・プレースホルダ */
  --color-rule:      #1a17141f;     /* 12% opacity — 区切り線・ボーダー */
}
```

### 2.2 よく使う opacity バリエーション

| Tailwind クラス | 用途 |
|---|---|
| `bg-ink/5` | ホバー背景（極薄） |
| `bg-ink/10` | ボタン背景・ジャケット未登録プレースホルダ |
| `bg-ink/15` | セクション区切りボーダー |
| `bg-ink/20` | ボタンホバー背景 |
| `bg-ink/35` | Today 区切り線 |
| `bg-ink/70` | 未読インジケーター |
| `bg-ink/80` | ピンバッジ背景 |
| `ring-ink/10` | カード・モーダルの外枠 |
| `text-ink/70` | ピントグル（unpinned 状態） |
| `border-ink/10` | ドロップダウン・検索結果枠 |
| `border-ink/15` | セクション区切り（ヘッダー下・フッター上） |
| `divide-ink-faint/30` | リスト行間ディバイダー |
| `divide-ink/10` | 検索結果リスト間 |

### 2.3 アクセントカラー（動的割当）

レコードジャケットとアーティストアバターの **フォールバック色**。ID の djb2 ハッシュでインデックスを決定。

**SLEEVE_TINTS**（ジャケット未登録時の正方形背景）:
| Hex | 色名 |
|---|---|
| `#1f3d2e` | ディープフォレストグリーン |
| `#e8dec5` | ライトクリーム |
| `#1a1714` | ダークインク |
| `#b08a3a` | ウォームゴールデンブラウン |
| `#6e2a2a` | ディープバーガンディ |
| `#3a4a55` | スレートブルーグレー |

**AVATAR_TINTS**（アーティスト画像未登録時の円形アバター。紙背景とのコントラスト確保のためクリームを除外した 5 色）:
`#1f3d2e`, `#1a1714`, `#6e2a2a`, `#3a4a55`, `#b08a3a`

**アバター文字色ロジック**: `#b08a3a`（ウォームゴールド）のみ暗色テキスト、他は明色テキスト。

---

## 3. タイポグラフィ

### 3.1 フォントスタック

```css
--font-serif: "Source Serif 4", "Noto Serif JP", "Times New Roman", Georgia, serif;
```

- 全テキストにセリフ体を使用（sans-serif は一切使わない）
- `font-smoothing: antialiased` + `text-rendering: optimizeLegibility`

### 3.2 テキストスケール

| 役割 | サイズ | ウェイト | スタイル | 具体例 |
|---|---|---|---|---|
| ヒーロータイトル | `text-6xl sm:text-7xl md:text-8xl` | `font-medium` | — | ログインページ "Analog Life" |
| コンテンツタイトル | `text-2xl` | `font-medium` | `leading-tight` | レコード詳細タイトル、アーティスト名 |
| セクションタイトル | `text-lg` | `font-medium` | — | モーダルヘッダー、フォーム見出し |
| ページタイトル | `text-base` | `font-medium` | — | "Records", "Feed", "Artists" |
| 本文 | `text-[15px]` | normal | `leading-relaxed` | 詳細モーダル内テキスト |
| 一般テキスト | `text-sm` | normal | — | リスト行、ボタンラベル |
| メタデータ | `text-xs` | normal | `italic` | アルバムタイプ、ステータスタグ |
| 数値 | 各種 | normal | `tabular-nums` | 件数、日付（等幅数字で桁揃え） |

### 3.3 イタリック体の運用

イタリックは **副次的情報・ラベル** を示すシグナルとして体系的に使用:
- フォームラベル: `italic text-sm text-ink-mute`
- サブテキスト: `italic text-ink-mute`
- 空状態メッセージ: `italic text-ink-faint`
- 操作ボタン（Cancel 系）: `italic text-ink-mute`
- "Today" ディバイダー: `text-xs italic text-ink-mute`
- メモ表示: `italic leading-relaxed text-ink-mute`

---

## 4. レイアウト

### 4.1 全体構造

```
┌─────────────── viewport ───────────────┐
│  [TopNav]  (desktop)                   │
│  ┌─── main (max-w-5xl mx-auto) ──────┐│
│  │  px-8 py-10                        ││
│  │  <page content>                    ││
│  │                                    ││
│  └────────────────────────────────────┘│
│  [BottomTabBar]  (mobile only)         │
└────────────────────────────────────────┘
```

- デスクトップ: `mx-auto w-full max-w-5xl flex-1 px-8 py-10`
- モバイル: `flex-1 px-5 pt-6 pb-24`（下部タブバー分の余白）

### 4.2 ナビゲーション

**TopNav（デスクトップ）**:
```
mx-auto mt-2 flex max-w-5xl justify-center gap-6 px-8 pb-2 text-ink-mute
```
- アクティブリンク: `text-ink`
- 非アクティブ: `text-ink-mute hover:text-ink`
- フォントサイズ: `text-sm`

**BottomTabBar（モバイル）**:
```
fixed inset-x-0 bottom-0 z-40 border-t border-rule bg-paper pb-[env(safe-area-inset-bottom)]
```
- タブリスト: `flex h-14 items-stretch justify-around`
- タブテキスト: `text-xs uppercase tracking-wider`
- アクティブ: `text-ink` / 非アクティブ: `text-ink-mute`

### 4.3 グリッドシステム

| コンテキスト | グリッド定義 | ギャップ |
|---|---|---|
| ホーム・レコード一覧 | `grid-cols-2 sm:grid-cols-3 lg:grid-cols-4` | `gap-4` |
| モーダル・レコード一覧 | `grid-cols-3 sm:grid-cols-4` | `gap-3` |
| アーティスト詳細レコード | `grid-cols-2 sm:grid-cols-4` | `gap-3` |
| フォーム 2 カラム | `grid-cols-1 sm:grid-cols-2` | `gap-5` |
| フィード（2 カラム） | `grid-cols-1 md:grid-cols-2` | `gap-x-30 gap-y-16` |

### 4.4 レスポンシブブレークポイント

Tailwind v4 デフォルト: `sm: 640px`, `md: 768px`, `lg: 1024px`

---

## 5. コンポーネントパターン

### 5.1 モーダル

**背景オーバーレイ**:
```
fixed inset-0 z-50 flex items-center justify-center p-6
background-color: rgba(244, 239, 227, 0.85)
backdrop-filter: blur(8px)
```

**コンテンツコンテナ共通パターン**:
```
bg-paper text-left text-ink shadow-xl ring-1 ring-ink/10
```

**モーダルサイズバリエーション**:
| 用途 | 幅 | 最大高 |
|---|---|---|
| レコード詳細 | `aspect-square w-[min(72vh,90vw,440px)]` | — |
| レコードフォーム | `w-[min(90vw,560px)]` | `max-h-[90vh]` |
| フィード詳細 | `w-[min(90vw,480px)]` | `max-h-[85vh]` |
| アーティスト追加 | `w-[min(92vw,480px)]` | `max-h-[90vh]` |
| アーティスト詳細 | `w-[min(92vw,720px)]` | `max-h-[90vh]` |
| レコード全表示 | `w-[min(92vw,1200px)]` | `max-h-[92vh]` |

**モーダル内セクション構造**:
- ヘッダー: `border-b border-ink/15 pb-4` + タイトル + サブテキスト
- コンテンツ: `space-y-3 py-5` or `space-y-2 py-5`
- フッター: `border-t border-ink/15 pt-4`

### 5.2 ボタン

**プライマリアクション（保存・送信）**:
```
bg-ink/10 px-4 py-2 text-sm text-ink transition-colors hover:bg-ink/20
disabled:cursor-not-allowed disabled:opacity-50
```

**セカンダリ（キャンセル系）**:
```
text-ink-mute transition-colors hover:text-ink disabled:opacity-50
```

**テキストボタン（italic 操作系）**:
```
cursor-pointer italic text-ink-mute transition-colors hover:text-ink
```

**危険操作の確認（InlineConfirm の Confirm）**:
```
cursor-pointer font-medium text-ink underline decoration-ink-faint underline-offset-4
transition-opacity hover:opacity-70
```

**ログインボタン（特殊: 唯一のボーダー付きボタン）**:
```
border border-ink px-10 py-3 text-sm transition-colors hover:bg-ink hover:text-paper
```

**共通**: すべて `cursor-pointer` かつ角丸なし。disabled 時は `opacity-50` + `cursor-not-allowed`。

### 5.3 フォーム入力

**テキスト入力・セレクト**:
```
w-full border-b border-ink-faint bg-transparent py-1.5 text-[15px] text-ink
placeholder:text-ink-faint focus:border-ink focus:outline-none
```
- **下線のみ**のミニマル入力。枠なし・角丸なし・背景なし
- フォーカス時: 下線が `ink-faint` → `ink` に変化

**テキストエリア**: 入力と同じスタイル + `resize-none`

**ラベル**: `block italic text-sm text-ink-mute mb-1.5`

**ドロップダウン（候補リスト）**:
```
absolute left-0 right-0 top-full z-10 mt-1 max-h-56 overflow-y-auto
border border-ink/10 bg-paper
```
- アイテム: `block w-full px-3 py-1.5 text-left text-sm hover:bg-ink/5`
- 区切り: `divide-y divide-ink/10`

### 5.4 レコードジャケットカード

**カードボタン**:
```
block aspect-square w-full cursor-pointer appearance-none bg-transparent p-0
transition-opacity hover:opacity-90
```
- 画像: `h-full w-full object-cover`
- 画像なし時: `sleeveTintByKey(id)` で背景色を割当（6 色のうち 1 つ）

**ピンバッジ（★）**:
```
pointer-events-none absolute right-1.5 top-1.5
flex size-5 items-center justify-center rounded-full
bg-ink/80 text-[10px] leading-none text-paper shadow
```

**追加タイル（+）**:
```
flex aspect-square w-full cursor-pointer items-center justify-center
border: 1px dashed rgba(26, 23, 20, 0.3)
text-4xl font-light leading-none
```

### 5.5 アーティストアバター

**コンテナ**: `relative aspect-square shrink-0 overflow-hidden`
- 小: `w-10`（リスト用 40px）
- 大: `w-20`（モーダルヘッダー用 80px）

**画像**: `h-full w-full object-cover`

**イニシャルフォールバック**:
```
absolute inset-0 flex items-center justify-center font-medium tracking-wide
```
- 背景: `avatarTintByString(spotifyId)` で 5 色のうち 1 つ
- 文字色: `#b08a3a` の場合は暗色、他は明色（`#f4efe3`）

### 5.6 フィード行

**リリース行**:
```
flex w-full cursor-pointer items-stretch gap-3 py-3 text-left text-sm transition-opacity hover:opacity-80
```
- 過去: `text-ink-mute` 付加
- 既読: `opacity-55` 付加
- 未読ドット: `block h-2 w-2 rounded-full bg-ink/70`
- ジャケット: `aspect-square w-16 shrink-0 overflow-hidden ring-1 ring-ink/10`

**Today 区切り**:
```
my-3 flex items-center gap-3 text-xs italic text-ink-mute
────── Today ──────  (線: h-px flex-1 bg-ink/35)
```

### 5.7 未読インジケーター

| コンテキスト | サイズ | スタイル |
|---|---|---|
| リリース行 | `h-2 w-2` | `rounded-full bg-ink/70` |
| アーティスト行 | `h-1 w-1` | `rounded-full bg-ink/70` |

### 5.8 ページネーション

```
flex items-center justify-center gap-6 text-sm text-ink-mute
```
- ボタン: `cursor-pointer appearance-none bg-transparent p-2 transition-colors hover:text-ink`
- disabled: `opacity-30 cursor-not-allowed`
- ページ表示: `tabular-nums`

### 5.9 InlineConfirm（二段階確認）

状態 1 — トリガー:
```
cursor-pointer italic text-ink-mute transition-colors hover:text-ink
```

状態 2 — 確認プロンプト:
```
[プロンプトテキスト（italic text-ink-mute）]  [Cancel]  [Confirm（underline font-medium）]
```

---

## 6. インタラクション

### 6.1 ホバー

| 対象 | エフェクト |
|---|---|
| テキストボタン | `text-ink-mute` → `text-ink` |
| 背景ボタン | `bg-ink/10` → `bg-ink/20` |
| カード・ジャケット | `opacity: 1` → `opacity: 0.9` |
| リスト行 | `opacity: 1` → `opacity: 0.7` or `0.8` |
| リンク | underline の `decoration-ink-faint` → `decoration-ink` |

### 6.2 disabled

```
disabled:cursor-not-allowed disabled:opacity-50
```
（ページネーションのみ `disabled:opacity-30`）

### 6.3 ドラッグ & ドロップ

- ライブラリ: `@dnd-kit/core` + `@dnd-kit/sortable`
- ドラッグ中: `cursor-grab` → `cursor-grabbing`, `z-index: 10`, `opacity: 0.85`
- タッチ: 200ms 遅延、5px 移動トレランス

### 6.4 トランジション

- カラー変化: `transition-colors`（Tailwind デフォルト 150ms）
- 不透明度: `transition-opacity`
- 汎用: `transition duration-200`（追加タイル等）
- CSS アニメーションは一切なし。すべて transition ベース

---

## 7. シャドウ・ボーダー・角丸

### 7.1 シャドウ

| 対象 | 値 |
|---|---|
| モーダル | `shadow-xl` |
| ピンバッジ | `shadow`（small） |
| その他 | シャドウなし |

### 7.2 ボーダー

- モーダル外枠: `ring-1 ring-ink/10`（box-shadow ring）
- セクション区切り: `border-b border-ink/15` / `border-t border-ink/15`
- リスト区切り: `divide-y divide-ink-faint/30`
- 入力フィールド: `border-b border-ink-faint`（下線のみ）
- ドロップダウン枠: `border border-ink/10`
- ログインボタン: `border border-ink`（唯一の実線ボーダーボタン）

### 7.3 角丸

- アバター・未読ドット・ピンバッジ: `rounded-full`（円形のみ）
- **カード・ボタン・モーダル・入力フィールド: すべて角丸なし**

---

## 8. 依存パッケージ（デザイン関連）

```json
{
  "tailwindcss": "^4.0.0",
  "@tailwindcss/vite": "^4.0.0",
  "@dnd-kit/core": "^6.1.0",
  "@dnd-kit/sortable": "^8.0.0"
}
```

- 外部アイコンライブラリなし
- カラーユーティリティライブラリなし
- CSS-in-JS なし
- コンポーネントライブラリなし（Tailwind ユーティリティクラスのみ）

---

## 9. 特記事項

### Google Fonts 読み込み

`index.html` で "Source Serif 4"（latin + latin-ext）と "Noto Serif JP"（日本語）を読み込み。
ウェイト: 400（本文）と 500（medium、見出し用）。

### Tailwind v4 固有

- `tailwind.config.js` / `postcss.config.js` は**存在しない**（`@tailwindcss/vite` プラグインで完結）
- テーマ拡張は CSS の `@theme {}` ブロックで行う
- カスタムカラーは `--color-*` で定義し、Tailwind が自動的に `text-*` / `bg-*` / `border-*` 等に展開

### デザイン原則まとめ

1. **紙とインク**: 2 色 + opacity バリエーションだけで全 UI を構成
2. **直角**: 円形（アバター・バッジ・ドット）以外すべて直角
3. **セリフ体**: 全テキストに一貫してセリフ体を使用
4. **イタリック = 副次情報**: ラベル・空状態・操作ボタンに体系的に使用
5. **下線入力**: フォーム入力は下線のみ、枠なし
6. **装飾の排除**: アイコンライブラリ不使用、アニメーション不使用、グラデーション不使用
7. **暖色系アクセント**: ジャケット/アバターのフォールバック色はすべてアースカラー
