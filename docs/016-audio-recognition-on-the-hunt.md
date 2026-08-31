# ADR-016: 音声認識による On the hunt 追加（Digging / Listen タブ）

> **Summary (English).** Adds a third Digging tab, **Listen**: the browser records about 12 seconds with `MediaRecorder`, `POST /api/recognize` forwards the clip to AudD (`return=spotify`) and returns a normalized `RecognitionResult` (track, album, Spotify album/artist ids, cover), which prefills the existing add-record form with `status=wanted`; unknown artists are upserted first. AudD was chosen over shazamio (terms of service, needs ffmpeg), RapidAPI Shazam (raw PCM input) and ACRCloud (overkill for a few calls a day). Tabs are URL-driven (`/digging/:tab`) with per-tab lazy fetching; microphone permission is requested only on tap and released afterwards; "no match" offers Cancel / Try again. A missing API token yields 503, an upstream failure 502.
>
> *The body of this document is in Japanese. See [docs/README.md](./README.md) for the index of all design documents.*

- **Status**: Accepted
- **Date**: 2026-05-30
- **Supersedes**: [ADR-013](./013-digging-tab-and-concert-removal.md) §2.1（Digging を 2 タブ
  「On the hunt / Releases」とした点 → 間に「Listen」を加えた 3 タブに拡張）
- **Related**: ADR-000 (要件), ADR-006 (records user-scope), ADR-013 (Digging タブ), ADR-007 (Spotify album search)

## 1. 背景と課題

レコ屋やラジオ、カフェで流れている曲を、その場で手入力せずに「On the hunt（欲しい
レコード = `status='wanted'`）」へ登録したい。録音した短いクリップから曲を特定し、
そのアルバムをウォントリストに入れる体験を作る。

技術的な制約:
- **公式 Shazam の Web/REST API は存在しない**。Apple が提供する ShazamKit は
  オンデバイス SDK（iOS/Android）で、ブラウザ → FastAPI 構成からは呼べない。
- 認識結果は「曲」だが、On the hunt の登録単位は「アルバム（レコード）」。さらに
  backend の record 作成は DB 在籍の Spotify `artist_id` を必須とする
  (`record_service.py` `_ensure_artist_exists`)。曲 → アルバム + artist_id の
  ギャップを埋める必要がある。
- 友達への配布を想定するため、エンドユーザーへの追加認証は避けたい。

## 2. 決定事項

### 2.1 認識プロバイダは AudD.io を採用
- ToS クリーンで複数ユーザー運用に向く。`multipart/form-data` で webm/opus・mp4/aac
  をそのまま受理するため **サーバ側 ffmpeg 不要**。
- `return=spotify` を付けることで、曲に対応する Spotify トラック情報（アルバム
  `id`/`name`/`images`/`release_date`、アーティスト `id`）まで取得でき、曲 → アルバム +
  Spotify アーティスト ID を一括で解決できる。
- **ユーザー追加認証は不要**。アプリが持つ単一 API トークン（`AUDD_API_TOKEN`、
  Codespaces secret / docker-compose env で注入）を backend が使うだけで、Spotify
  連携とは独立。エンドポイントは既存のアプリログイン（`get_current_user`）で保護する。
- 料金は 300 回無料 → 以降 $5/1000。数人が 1 日数回なら極めて低コスト。

### 2.2 エンドポイント
- `POST /api/recognize`（auth 必須）。`UploadFile` で録音クリップを受け取り、
  `RecognitionService` が AudD に転送して `RecognitionResult` に正規化して返す。
- 失敗は `RecognitionError` → `http_errors()` で HTTP 化。トークン未設定は 503、
  上流失敗・通信失敗は 502。マッチ無しは `matched=false`（200）。

### 2.3 UI は Digging の 3 つ目タブ「Listen」
- `On the hunt | Listen | Releases` の順。`ListenPanel` が `MediaRecorder` で
  ~12 秒録音（`MAX_RECORDING_MS`）し `recognizeAudio()` を呼ぶ。12 秒で自動検索される
  ため、録音中の「Search now」は任意ショートカット（控えめなテキストボタン）。
- 盤は CSS グラデーションのレコード盤 + トーンアームで表現し、録音/認識中は 33⅓ 回転 +
  針が降りる。盤・トーンアームは単一固定サイズ（px）で配置し、画面幅が変わっても
  針が溝の上に着地する位置関係を保つ。認識結果のジャケットは盤の中央レーベルに表示。
- **タブは URL 駆動**（`/digging/:tab` = hunt | listen | releases、`useParams`/`navigate`）。
  無印 `/digging` や未知の値は hunt に正規化。リロード・共有・戻る/進むが効く。
- **タブ別 lazy fetch**: 開いているタブに必要な query だけ走らせ API を節約する
  （`releases`/`release-sync-status` は releases タブ、`wanted` は hunt タブで `enabled`）。
  `artists`/`followed-artists` は全タブでフォーム・名前解決に必要なので常時。
- **マイク許可**: 録音ボタン押下時にのみ `getUserMedia({audio:true})` を呼んで
  ブラウザ/OS 標準の許可ダイアログを出す。secure context（https/localhost）と
  `MediaRecorder` 対応を feature-detect し、拒否（NotAllowedError）/未対応時は
  フォールバック文言を表示。録音後は `track.stop()` でマイクを解放（PWA / iOS 配慮）。
- **見つからなかった時（nomatch）**: 音声検索ユーザーは曲名を知らないのが前提のため
  手動追加へは誘導せず、`Sorry, no match...` + `Cancel`（待機へ戻る）/ `Try again`
  （録り直し）のみを出す。

### 2.4 追加フローは既存 RecordFormModal への prefill
- 認識結果から直接 `POST /api/records` せず、`RecordFormModal` に defaults を流し込む
  （`DiggingPage.handleCollectFromRelease` と同型の `handleRecognizedAdd`）。
- **アーティストフォールバック**: 認識した Spotify アーティストがレジストリ未在籍なら
  `upsertArtist`（`POST /api/artists`）で先に DB 追加してからフォームを開く。さらに
  upsert がまだ反映されていない/失敗したケースでも名前欄が空にならないよう、
  defaults に表示名 `artistName`（認識した `artist_name`）を渡してフォールバック表示する。
- **曲名 → favorite_tracks**: 認識した曲名をフォームの favorite_tracks 欄に自動挿入。
- **アルバム未解決時**: `spotify_album_id` が無ければフォームの Spotify album 検索を
  title で 1 回自動発火（`autoSearchSpotify`）し、ユーザが選択して artist_id / album を
  確定できるようにする。

## 3. 代替案と却下理由

- **shazamio**（Shazam 内部 API の Python ラッパ）: 無料・Shazam 実体だが、ToS グレーで
  配布時にリスク、reverse-engineered で破損リスク、実測レート制限を全ユーザーで共有、
  かつ pydub 経由で ffmpeg が事実上必須。配布前提では却下。
- **RapidAPI Shazam (apidojo)**: detect が raw PCM 44100Hz mono base64 を要求し
  サーバ側で transcode + チャンク分割が必要、認識不安定の報告も多い。却下。
- **ACRCloud**: 高精度だが HMAC 署名・年額パッケージ前提で、数回/日の個人用途には
  オーバースペック。却下。

## 4. 影響範囲

- backend: `core/settings.py`（`audd_api_token`）, `core/exceptions.py`
  （`RecognitionError`）, `routers/_handlers.py`, `schemas/recognition.py`,
  `services/recognition_service.py`, `routers/recognize.py`, `routers/deps.py`,
  `main.py`, `openapi.json`。依存に `python-multipart` を追加。
- frontend: `api/client.ts`（`recognizeAudio` + mock）, `types/api.ts`
  （`RecognitionResult` re-export）, `components/feed/ListenPanel.tsx`（新規）,
  `App.tsx`（`/digging/:tab` ルート追加）,
  `pages/DiggingPage.tsx`（Listen タブ + URL 駆動タブ + lazy fetch + `handleRecognizedAdd`）,
  `components/records/RecordFormModal.tsx`（`favoriteTrackNames` / `autoSearchSpotify` /
  `artistName` prefill）, `index.css`（vinyl-spin / rec-pulse / wave-bar アニメーション）,
  orval 生成物。
- インフラ: `docker-compose.yml` / `.devcontainer/devcontainer.json` に
  `AUDD_API_TOKEN` を配線。

（このファイルは要約版。詳細は実装 PR を参照）
