# newsletter/

Analog Life の「What's new」ニュースレター（HTML メール）と、その素材。

## ファイル

| ファイル | 役割 |
|---|---|
| `2026-05-whats-new.html` | 第1号メール本体。インライン CSS / `<table>` レイアウトの self-contained HTML。Resend / Loops / Buttondown 等の「HTML を貼る」欄にそのまま貼れる |
| `listen.gif` | ヒーロー GIF（盤が回る → 認識 → 結果 → "To the hunt" タップ → 追加トースト） |
| `nav.gif` | 導線 GIF（Home →[Digging]→ On the hunt →[Listen タブ]→ 盤タップ→回転） |
| `listen-demo.html` | `listen.gif` の収録元。本物の `ListenPanel` の Disc/Tonearm/Waveform と `app/frontend/src/index.css` の keyframes を vanilla 移植し自動ループ再生 |
| `nav-demo.html` | `nav.gif` の収録元。本物の下タブ / Digging タブを再現 |

## 送信前に差し替える箇所（2 つ）

1. **GIF の src** … `listen.gif` / `nav.gif` を配信サービス or 画像ホストに上げ、`<img src>` を**絶対 URL** に。
   （ローカルプレビューは相対パスのまま動く）
2. **CTA の href** … `試してみよう` ボタンの `https://YOUR-APP-URL/digging/listen` を本番 URL に。

## GIF の再生成

メールクライアントは CSS animation / JS を実行しないため、動きは GIF にベイクしている。
`*-demo.html` を Playwright + 純 JS エンコーダ（`gifenc`）で画面収録 → GIF 化している。

```
# 例（リポジトリ外の作業ディレクトリで）
npm i playwright pngjs gifenc
npx playwright install chromium
node capture.mjs       # listen-demo.html → listen.gif
node capture-nav.mjs   # nav-demo.html   → nav.gif
```

`*-demo.html?capture=1` で自動ループを止め、収録スクリプトがフェーズを駆動する。
