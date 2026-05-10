# ジャズ・アーティスト ダッシュボード 要件定義書

**バージョン**: v1.6 (MVP)
**最終更新**: 2026-05-10

### バージョン履歴

**v1.6**
- 型契約戦略をハイブリッドに変更（Phase Aは手書き、Phase B以降は openapi-typescript による自動生成）
- `make gen` コマンドによる型同期フローを定義
- Makefile を成果物に追加

**v1.5**
- レコードマトリクスの並び替え仕様を確定（4モード、ドラッグ&ドロップ対応）
- レコードのフリップ（裏返し）インタラクションを定義（クリックのみ、3D回転）
- アーティストごと表示はセクション見出し付き
- `display_order` カラムを `vinyl_records` に追加

**v1.4**
- アナログレコードコレクション機能を追加（ホーム画面のメイン機能化）
- アプリのコンセプトを「フィードアプリ」から「コレクション+フィード」に拡張
- 画面構成を Home（コレクション） / Feed（新譜・公演） / Artists（アーティスト管理）の3タブに整理
- `vinyl_records` テーブルとレコード詳細・メモ機能を追加

**v1.3**
- 開発フローをモックファーストに変更（Phase A: フロントモック → Phase B: バックエンド）
- API契約をPhase Aの早期に確定させる方針を追加
- 画面の空状態・ロード状態・エラー状態を要件として明文化

**v1.2**
- Docker / docker-compose による環境構築を要件化
- SQLModelの採用を明記、ORMとマイグレーション戦略を追加
- バッチ実行方式を APScheduler に確定

**v1.1**
- Spotify認証を「ユーザー認証フロー」と「Client Credentialsフロー」に分離
- `artist_aliases` テーブルを追加（名前の表記ゆれ対策）
- `concerts` テーブルにステージ表現と公演ステータスを追加
- 新譜取得時の `appears_on` の扱いを明確化
- システム同期状態の表示要件を追加

---

## 1. 背景・目的

ジャズリスナーとして、(1) フォロー対象アーティストの新譜・来日情報を能動的にキャッチアップしたい、 (2) 自分のアナログレコードコレクションをジャケットでビジュアル管理し、それぞれのレコードの「ストーリー」を残したい。

SNSはノイズが多くこの2つを両立できる場所がないため、自分専用の「コレクション + 情報フィード」ダッシュボードを構築する。

## 2. アプリのコンセプト

```
┌──────────────────────────────────────┐
│   自分のジャズライフの母艦アプリ      │
│                                      │
│  Home  → 持っているレコードの        │
│           マトリクス表示             │
│           （視覚的コレクション）     │
│                                      │
│  Feed  → 新譜・公演情報の流入        │
│           （外からの情報）           │
│                                      │
│  Artists → アーティスト管理          │
│           （リスト・エイリアス）     │
└──────────────────────────────────────┘
```

「コレクションを眺めることで音楽体験が深まる」「外部情報は受動的に流入する」という、能動と受動を両立させた設計。

## 3. スコープ（MVP）

### やること

- **アナログレコードのコレクション管理**（ホーム画面のメイン機能）
  - ジャケット画像のグリッド表示（4種類の並び替え対応）
  - クリックでレコードが裏返り、メモが見える3Dフリップ
  - レコードごとのメモ・評価・購入情報（ストーリー）
  - アーティスト一覧から登録
- フォロー中ジャズアーティストの新譜トラッキング
- 登録アーティストの日本公演（来日・国内ツアー）情報の表示
- アーティストリストの管理（Spotifyフォロー同期 + 手動追加）
- アーティスト名のエイリアス管理（表記ゆれ対応）
- Docker化された環境で動作

### やらないこと（Phase 2以降に保留）

- ジャズフェス出演ラインナップの自動照合
- メールやプッシュ通知
- メディアRSSの集約・記事検索
- アーティスト詳細ページ・ディスコグラフィ
- スマホ対応・PWA化
- Apple Music連携
- CD・デジタル購入のコレクション管理（アナログのみ）
- Discogs連携

## 4. 開発アプローチ

### モックファースト開発

本プロジェクトは **モックファースト** で進める。バックエンドの実装は後回しにし、まずフロントエンドをダミーデータで完成させ、画面を触りながら要件と設計を磨く。

```
Phase A: フロントモック完成
  ↓ ここで要件・データ形状を確定、要件定義書をレビュー
Phase B: バックエンド設計・実装
  ↓ Pydanticモデル → SQLModel → エンドポイント
Phase C: 統合・データ取得バッチ
  ↓ モックを実APIに切り替え、Spotify連携・スクレイピング
```

### 型契約のハイブリッド戦略

フロント/バックエンド間の型ズレ防止に、**ハイブリッド戦略**を採用する。

#### Phase A: 手書き暫定型

Phase A 中はバックエンドが存在しないため、`frontend/src/types/api.ts` に **TypeScript型を手書き** で定義する。これがモックJSONとフロント実装の指針となる。

```typescript
// frontend/src/types/api.ts (手書き、Phase A中の暫定)
export type VinylRecord = {
  id: number;
  artist_id: string;
  title: string;
  // ...
};
```

#### Phase B 以降: 自動生成への切り替え

Phase B でバックエンドのPydanticモデルが立ち上がり、FastAPIが `/openapi.json` を返すようになったら、**openapi-typescript** で型を自動生成する仕組みに切り替える。

```bash
make gen
# 内部実行: npx openapi-typescript http://localhost:8000/openapi.json -o frontend/src/types/api.generated.ts
```

- 自動生成されたファイル: `frontend/src/types/api.generated.ts`
- 手書きの `api.ts` は **B-2完了時点で破棄**、`api.generated.ts` から型を再エクスポート
- 型の単一情報源は **バックエンドのPydanticモデル** に集約される

#### 型の伝播戦略（最終形）

```
SQLModel (DBスキーマ) ←→ Pydantic (APIスキーマ)
                            ↓
                    OpenAPI仕様 (/openapi.json)
                            ↓
                    make gen (openapi-typescript)
                            ↓
                    api.generated.ts (TypeScript型)
                            ↓
                    フロント実装が import
```

#### make gen の運用

- バックエンドを起動した状態で `make gen` を実行
- 生成された `api.generated.ts` はコミット対象（CI環境でも生成不要にするため）
- API変更時は「Pydanticを修正 → `make gen` 実行 → フロントの型エラーを修正」という流れ
- 型エラーがコンパイル時に検出されるので、API変更時のフロント追従漏れを防げる

### モック切り替え機構

フロントの全API呼び出しは抽象クライアント経由とし、環境変数でモック/実APIを切り替える:

```typescript
const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true';
```

これによりPhase A→B→Cの移行時に画面側の修正が最小化される。

## 5. ユーザーストーリー

| ID | ストーリー |
|---|---|
| US-1 | アーティストを登録すると、最新アルバム/EPリリース情報が一覧で見られる |
| US-2 | 登録アーティストの日本公演が予定されていれば、日付・会場とともに表示される |
| US-3 | Spotifyのフォロー中アーティストからリストを自動インポート＆同期できる |
| US-4 | 手動でもアーティストを追加・削除できる |
| US-5 | 自分以外がアプリにアクセスできないように認証されている |
| US-6 | 表記ゆれのあるアーティストに別名を登録すると、会場サイトの日本語表記でもヒットする |
| US-7 | データの最終同期日時を確認できる |
| US-8 | `docker compose up` 一発でアプリが起動する |
| US-9 | データ取得中はローディング状態が分かる、エラー時は何が起きたか分かる |
| US-10 | ホーム画面で自分のアナログレコードのジャケットがマトリクスで一覧できる |
| US-11 | アーティスト一覧から、そのアーティストのアルバムをレコードコレクションに追加できる |
| US-12 | 各レコードに購入日・購入店・プレス情報・評価・自由記述を記録できる |
| US-13 | コレクションをデフォルト順（自分でカスタム）/ 購入日 / リリース順 / アーティストごとで切り替え表示できる |
| US-14 | Spotify未配信のジャズ盤も手動でレコードコレクションに登録できる |
| US-15 | デフォルト並び順では、ドラッグ&ドロップでレコードを自分の好みの順に並び替えられる |
| US-16 | レコードのジャケットをクリックすると裏返り、購入情報・プレス情報・メモが見られる |
| **US-17** | **`make gen` でバックエンドの型変更がフロントに自動同期される** |

## 6. 機能要件（MVP）

### Home（コレクション）

| ID | 機能 | 備考 |
|---|---|---|
| F-H1 | レコードのグリッドマトリクス表示 | ジャケット画像メイン、均等タイル |
| F-H2 | レコードのフリップ表示（クリックで3D回転） | 表面=ジャケット、裏面=メモ・購入情報 |
| F-H3 | 並び替え4モード切り替え | デフォルト/購入日/リリース順/アーティストごと |
| F-H4 | デフォルト順のドラッグ&ドロップ並び替え | dnd-kitで実装、`display_order`保存 |
| F-H5 | レコード追加（アーティスト一覧から選択） | アーティスト→アルバム→登録のフロー |
| F-H6 | レコード追加（手動入力） | Spotify未配信盤対応、画像URLも手動 |
| F-H7 | レコード編集・削除 | 全フィールド編集可、編集は別画面/モーダル |
| F-H8 | 絞り込み | アーティスト、評価 |

### Feed（新譜・公演）

| ID | 機能 | 備考 |
|---|---|---|
| F-F1 | 新譜タブ（直近30日 / 今後の予定） | release_date順、`album` / `single` のみ表示 |
| F-F2 | 公演タブ（今後の日本公演） | 会場×日付順、複数ステージは1日として表示 |
| F-F3 | システムステータス表示 | 各データソースの最終同期日時とエラー状態 |
| F-F4 | 各タブの空状態・ロード状態・エラー状態の表示 | 共通UX |
| F-F5 | フィードからレコード追加 | 新譜に「コレクションに追加」ボタン |

### Artists（アーティスト管理）

| ID | 機能 | 備考 |
|---|---|---|
| F-A1 | Spotifyログイン（OAuth Authorization Code Flow） | 自分のSpotify IDのみ許可するシンプル認証 |
| F-A2 | フォロー中アーティスト同期 | `Get User's Followed Artists`、ログイン時 + 手動同期ボタン |
| F-A3 | アーティストの手動追加・削除 | Spotify検索APIで補完 |
| F-A4 | アーティストエイリアス管理（追加・削除） | 1アーティストに複数エイリアス登録可 |
| F-A5 | アーティスト詳細（持っているレコード一覧） | アーティストごとの所有レコード表示 |

## 7. レコードマトリクス詳細仕様

### 並び替えモード

| モード | 並び順 | UI上の表示 |
|---|---|---|
| デフォルト（カスタム） | `display_order` 昇順 | 通常のグリッド、ドラッグ&ドロップ可能 |
| 購入日順 | `purchase_date` 降順（新しい順） | 通常のグリッド、ドラッグ無効 |
| リリース順 | `original_release_year` 昇順（古い順） | 通常のグリッド、ドラッグ無効 |
| アーティストごと | `artist_id` でグループ化、グループ内は`display_order` | アーティスト名のセクション見出し付き、棚を整理した雰囲気 |

並び替えモード切り替えはタブ or プルダウンUI（Phase Aで決定）。デフォルト以外のモード時は、ドラッグ&ドロップは無効化（モード切り替えで戻せばOK）。

### ドラッグ&ドロップ並び替え

- ライブラリ: **dnd-kit** を採用（Reactのモダンなドラッグ&ドロップ、`react-dnd`より軽量で扱いやすい）
- 並び順は `display_order`（int）カラムで管理
- ドラッグ完了時にバルク更新APIを呼ぶ（`PATCH /api/records/reorder`）
- 新規追加時は `display_order = MAX + 1` で末尾に追加

### フリップ（裏返し）インタラクション

**トリガー**: クリックのみ（ホバーは使わない）

理由:
- マウスが偶然通っただけで裏返るのを防ぐ
- 並び替えのドラッグ操作と競合しない
- PC/モバイルで一貫した操作感
- 「読みたい時だけ裏返る」という明示的な意思表示と合致する

**動作**:
- カードをクリック → 3D回転（Y軸180度）で裏返る
- もう一度クリック → 表に戻る
- 別のカードをクリック → 前のカードは表に戻り、新しいカードが裏返る（同時に複数開かない）

**実装**:
- CSS `transform: rotateY(180deg)` + `transform-style: preserve-3d`
- アニメーション速度は 600ms 程度、`ease-in-out`
- `will-change: transform` でパフォーマンス最適化

**裏面に表示する情報**:
- アルバムタイトル + アーティスト名
- 原盤発売年（`original_release_year`）
- プレス情報（`pressing_info`）
- 購入日 + 購入店 + 価格（小さめの文字）
- 評価（★1-5の表示）
- メモ（`memo`、長い場合は省略表示、詳細編集は別画面へ）
- 「編集」「削除」ボタン

詳細編集はあくまで別画面/モーダル経由。裏面はあくまで「眺める」用。

### マトリクスのカラム数

- デスクトップ: 6列を目安（画面幅により可変）
- 中サイズ画面: 4列
- 狭い画面: 3列
- スマホ対応はPhase 2、MVPはPC前提

Tailwindの `grid-cols-3 md:grid-cols-4 lg:grid-cols-6` 等のレスポンシブクラスで実装。

## 8. UI状態の定義（モックで決めるべきこと）

各画面で以下の状態を網羅すること。Phase Aのモック作成時に全状態をスクリーンとして実装する。

### 共通状態

| 状態 | 表示内容 |
|---|---|
| ロード中 | スケルトンUI（コンテンツ形状を保持したプレースホルダ） |
| エラー | エラーメッセージ + リトライボタン |
| 認証エラー | Spotifyトークン切れ → 再ログインボタン |

### 各画面固有の空状態

| 画面 | 空状態の表現 |
|---|---|
| Home（コレクション） | 「まだレコードが登録されていません」+ アーティスト一覧へのリンク |
| アーティスト一覧 | 「Spotifyからフォロー中のアーティストを取り込みます」+ 同期ボタン |
| 新譜タブ | 「直近の新譜はありません」+ 同期日時表示 |
| 公演タブ | 「今後の日本公演予定はありません」+ 同期日時表示 |
| エイリアス管理 | 「エイリアス未登録」+ 追加ボタン |
| アーティスト詳細 | 「このアーティストのレコードはまだ持っていません」+ 追加ボタン |

### Phase Aで決定するUI仕様（モック作成中に確定）

- 共通レイアウト（ヘッダー、ナビゲーション、フッター）
- 3タブ（Home / Feed / Artists）の切り替えUI
- レコードマトリクスのカラム数（画面幅により可変、6列目安）
- 並び替えモード切り替えUI（タブ or プルダウン）
- フリップアニメーションのスピード調整
- レコード編集の表示形式（モーダル / 別画面）
- レコード追加フローのUI（アーティスト選択→アルバム選択→メモ入力）
- 絞り込みのUI（プルダウン / ボタン群）
- 新譜から「コレクションに追加」を呼ぶ動線
- アーティスト追加UI（モーダル / インライン / 別画面）
- エイリアス管理UI（一覧行展開 / 別画面）
- 同期ボタンの位置（ヘッダー固定 / 各タブ）
- sync_status表示の場所（フッター / 設定画面 / トースト）
- 画像（アルバムジャケット、アーティスト写真）の遅延読み込み

## 9. データソース

| 情報 | ソース | 手段 |
|---|---|---|
| アーティストリスト | Spotify | OAuthでフォロー同期（user token） + 手動追加 |
| 新譜・新EP | Spotify | `Get Artist's Albums` 日次バッチ（**Client Credentials**） |
| 日本公演 | ジャズ会場5サイト | 日次スクレイピング + 名前照合 |
| レコードコレクション | 手動入力（Spotifyアルバムから選択 or 完全手動） | APIでDB登録、画像はSpotifyのジャケットURL or 手動URL |
| ジャズフェス（Phase 2） | 各フェス公式サイト | 年1〜2回手動チェック |

### スクレイピング対象会場

- Blue Note Tokyo
- Cotton Club（東京・丸の内）
- Billboard Live Tokyo
- Billboard Live Osaka
- Motion Blue Yokohama

会場リストは利用実態に合わせて調整可能。

### データソース選定の判断記録

- **SNS（Twitter/X、Instagram）**: 2026年現在、無料API枠が事実上廃止、Instagramは個人アカウントAPI廃止済み。スクレイピングはToS違反リスクあり。除外。
- **Spotify Concertsタブ**: APIで公開されていない。Spotify自身がBandsintown/Songkickから引いているだけ。利用不可。
- **Songkick API**: 個人開発者向け新規発行は事実上停止。利用不可。
- **Bandsintown API**: 利用条件が厳しいため、MVPでは使わない。
- **MusicBrainz**: 補完用として有効だが、MVPの新譜情報はSpotifyで十分なため、MVPでは使わない。
- **Discogs API**: レコードコレクション管理では事実上の標準だが、MVPでは手動入力で進め、必要になればPhase 2で連携を検討。

## 10. 非機能要件

- 個人利用、同時ユーザー1名
- データ更新: 日次バッチで全アーティストの新譜・全会場のスケジュールを取得
- レスポンス: 取得済みデータをDBから返すので、UIは即時表示
- ホスティング: ローカルDocker環境で運用、必要に応じてクラウドデプロイ
- 想定アーティスト数: 10〜30人
- 想定レコード枚数: 50〜500枚（個人コレクションの一般的範囲）
- 100枚程度までフリップアニメーションが快適に動作（500枚規模は仮想スクロール検討、Phase 2）
- ホスト環境を汚さない（Python/Node.jsはコンテナ内に閉じる）

## 11. アーキテクチャ

### コンテナ構成

```
┌────────────────────────────────────────┐
│  docker-compose                        │
│                                        │
│  ┌──────────────┐  ┌────────────────┐  │
│  │ frontend     │  │ backend        │  │
│  │ (Vite/Nginx) │  │ (FastAPI +     │  │
│  │ port: 5173   │◀▶│  APScheduler)  │  │
│  │   or 80      │  │ port: 8000     │  │
│  └──────────────┘  └───────┬────────┘  │
│                            │           │
│                    ┌───────▼────────┐  │
│                    │ volume:        │  │
│                    │ ./data/jazz.db │  │
│                    └────────────────┘  │
└────────────────────────────────────────┘
            │
            ▼
   外部API: Spotify / 会場サイト
```

backend コンテナは FastAPI と APScheduler を同居させ、API応答と日次バッチを単一プロセスで担う。SQLite ファイルはホスト側 `./data/` にボリュームマウントし、コンテナ破棄時もデータが残る構成。

### Spotify認証フローの使い分け

| 用途 | フロー | トークン | 実行タイミング |
|---|---|---|---|
| ログイン認証・本人特定 | Authorization Code Flow | user access token | ログイン時 |
| フォロー中アーティスト同期 | Authorization Code Flow | user access token (refresh tokenをDB保存) | ログイン時 + 手動同期ボタン |
| 新譜取得（日次バッチ） | **Client Credentials Flow** | app token | APScheduler毎日 |
| アルバム検索（レコード追加用） | Client Credentials Flow | app token | レコード追加時 |

新譜取得とレコード追加用のアルバム検索はユーザー情報に依存しないため、Client Credentials Flowを使う。

## 12. データモデル

### ORM

**SQLModel** を採用。pydantic v2ベースで型安全、FastAPIのレスポンスモデルとそのまま連携可能。SQLAlchemyの薄いラッパーなので、複雑なクエリにも逃げ道がある。

### マイグレーション戦略

MVP段階では **SQLModel + Alembic** の組み合わせで運用。Alembicはコンテナ内で `alembic revision --autogenerate` を実行する形でマイグレーションを生成する。

ただし個人開発・スキーマ変更頻度が低い前提のため、初期は `SQLModel.metadata.create_all()` でテーブル自動生成し、Phase B終盤でAlembic導入する2段階アプローチで進める。

### artists
| カラム | 型 | 備考 |
|---|---|---|
| spotify_id | string | PK |
| name | string | Spotifyの正式名 |
| image_url | string | |
| followed | bool | Spotifyでフォロー中かどうか |
| added_at | datetime | |

### artist_aliases
| カラム | 型 | 備考 |
|---|---|---|
| id | int | PK (auto increment) |
| artist_id | string | FK → artists.spotify_id |
| alias_name | string | 例: "小曽根真", "オゾネマコト", "Makoto Ozone Trio" |
| created_at | datetime | |

照合時は `artists.name` + `artist_aliases.alias_name` の両方を対象に部分一致検索する。

### releases（Spotifyの新譜トラッキング用）
| カラム | 型 | 備考 |
|---|---|---|
| spotify_id | string | PK |
| artist_id | string | FK → artists |
| title | string | |
| album_type | string | album / single / compilation / appears_on |
| release_date | date | |
| image_url | string | |

MVPでは `album_type IN ('album', 'single')` のみUI表示。`appears_on` と `compilation` はDBには保存するが非表示（Phase 2で別タブ化）。

### vinyl_records（レコードコレクションのコア）
| カラム | 型 | 備考 |
|---|---|---|
| id | int | PK (auto increment) |
| artist_id | string | FK → artists.spotify_id |
| spotify_album_id | string | FK → releases.spotify_id (nullable、Spotify未配信盤対応) |
| title | string | アルバムタイトル（Spotify連携時は自動入力、未連携時は手動） |
| image_url | string | ジャケット画像URL（Spotify由来 or 手動） |
| original_release_year | int | 原盤発売年（例: 1959） |
| pressing_info | string | プレス情報（"オリジナル1959年プレス", "1980年再発", "180g 限定盤"等） |
| purchase_date | date | 購入日 (nullable) |
| purchase_store | string | 購入店 (nullable) |
| purchase_price | int | 価格（円）(nullable) |
| rating | int | 評価 1-5 (nullable) |
| memo | text | 自由記述（ストーリー、思い出）(nullable) |
| display_order | int | デフォルト並び順、新規追加は MAX+1 |
| created_at | datetime | DB登録日時 |
| updated_at | datetime | 最終更新日時 |

設計の要点:
- `spotify_album_id` は nullable: 「Spotifyで見つからないジャズの希少盤」も登録できる
- `pressing_info` は文字列で柔軟に: 「オリジナル」「再発」「180g」など多様な表現を許容
- 同じアルバムでもプレス違いで複数レコード登録可能（同じ`spotify_album_id`を持つレコードが複数あってOK）
- `display_order` でユーザーの並び替えを永続化、ドラッグ&ドロップでバルク更新

### venues
| カラム | 型 | 備考 |
|---|---|---|
| id | string | PK（例: "blue_note_tokyo"） |
| name | string | |
| city | string | |

### concerts
| カラム | 型 | 備考 |
|---|---|---|
| id | string | PK（venue_id + date + title のハッシュから生成） |
| venue_id | string | FK → venues |
| date | date | 公演日 |
| title | string | 公演タイトル（例: "Avishai Cohen Trio"） |
| url | string | 会場サイトの詳細ページ |
| stage_times | string | カンマ区切り（例: "18:30,21:00"）、不明ならnull |
| status | string | scheduled / cancelled / postponed |
| first_seen_at | datetime | DB初登録時刻 |
| last_seen_at | datetime | スクレイピングで最後に確認できた時刻 |

### concert_artists（concertとartistの多対多）
| カラム | 型 | 備考 |
|---|---|---|
| concert_id | string | FK → concerts |
| artist_id | string | FK → artists |

スクレイピング時にtitle中にフォロー中アーティスト名（or エイリアス）が含まれていれば、このテーブルにレコードを作成。1公演に複数アーティストが該当する可能性あり。

### sync_status
| カラム | 型 | 備考 |
|---|---|---|
| source | string | PK（例: "spotify_releases", "blue_note_tokyo"） |
| last_success_at | datetime | 最後に成功した時刻 |
| last_attempt_at | datetime | 最後に試行した時刻 |
| last_error | string | 直近のエラーメッセージ（成功時はnull） |

### UPSERT設計

公演データは「日次スクレイピングで毎回上書き」が基本。各バッチ実行時に:

1. 取得した公演レコードを `id`（venue_id + date + title のハッシュ）でUPSERT
2. `last_seen_at` を更新
3. その会場で「今回見つからなかったが過去に登録されていた未来日の公演」は `status = 'cancelled'` にマーク

これにより中止・延期がUIに反映される。

## 13. 技術スタック

### フロントエンド

- React 19+ (Vite)
- TypeScript
- React Router
- TanStack Query（サーバ状態管理）
- Tailwind CSS
- dnd-kit（ドラッグ&ドロップ並び替え）
- **openapi-typescript**（OpenAPI仕様からTS型自動生成）

### バックエンド

- Python 3.11+
- FastAPI + Uvicorn
- SQLModel + Alembic（DB操作・マイグレーション）
- httpx（Spotify API呼び出し）
- BeautifulSoup4（HTMLパース）
- APScheduler（日次バッチのスケジューリング）
- python-dotenv

### インフラ・開発ツール

- Docker / docker-compose でローカル運用
- DB: SQLite（ホストの `./data` ボリュームに永続化）
  - Phase 2でクラウドデプロイ時にPostgreSQLへ移行（接続文字列変更のみで対応可能）
- バッチ実行: APScheduler（backendコンテナ内）
- **Makefile**（`make gen` 等の頻出コマンドをまとめる）

## 14. Docker構成

### サービス構成

| サービス | 役割 | ポート | ベースイメージ |
|---|---|---|---|
| backend | FastAPI + APScheduler | 8000 | python:3.11-slim |
| frontend | Vite dev server (開発) / Nginx配信 (本番) | 5173 / 80 | node:20-alpine / nginx:alpine |

### ファイル構成

```
jazz-dashboard/
├── docker-compose.yml          # 共通定義（本番想定）
├── docker-compose.override.yml # 開発時上書き（Vite dev server等）
├── Makefile                    # make gen, make up, make down 等
├── .env                        # 環境変数（gitignore）
├── .env.example                # サンプル
├── data/                       # SQLite永続化先（gitignore）
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── app/
└── frontend/
    ├── Dockerfile              # マルチステージ (dev / prod)
    ├── package.json
    └── src/
        ├── api/
        │   ├── client.ts       # モック/実API切り替え
        │   └── mocks/          # モック用JSONファイル
        ├── types/
        │   ├── api.ts          # Phase A中の手書き暫定型（B-2で破棄）
        │   └── api.generated.ts # openapi-typescriptで自動生成（Phase B以降）
        ├── pages/
        │   ├── HomePage.tsx        # レコードコレクション
        │   ├── FeedPage.tsx        # 新譜・公演タブ
        │   └── ArtistsPage.tsx     # アーティスト管理
        └── components/
            ├── records/        # レコード関連（マトリクス、フリップカード等）
            ├── feed/           # フィード関連コンポーネント
            └── artists/        # アーティスト関連コンポーネント
```

### Makefile（主要ターゲット）

```makefile
.PHONY: up down gen migrate

up:
	docker compose up -d

down:
	docker compose down

# OpenAPI仕様からTypeScript型を自動生成
# 事前条件: backendが起動していること
gen:
	npx openapi-typescript http://localhost:8000/openapi.json -o frontend/src/types/api.generated.ts

# Alembicマイグレーション生成（Phase C-4以降）
migrate:
	docker compose exec backend alembic revision --autogenerate -m "$(name)"
	docker compose exec backend alembic upgrade head
```

### 環境変数

`.env` で以下を管理:

- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- `SPOTIFY_REDIRECT_URI` (例: `http://localhost:8000/auth/callback`)
- `ALLOWED_SPOTIFY_USER_ID`
- `JWT_SECRET`
- `DATABASE_URL` (例: `sqlite:////app/data/jazz.db`)
- `VITE_USE_MOCK` (フロント用、Phase A中はtrue)

### ボリューム

- `./data` → `/app/data` (SQLiteファイル永続化)
- 開発時のみ: `./backend/app` → `/app/app` (ホットリロード用)
- 開発時のみ: `./frontend/src` → `/app/src` (Vite HMR用)

### 起動コマンド

```bash
# 初回セットアップ
cp .env.example .env
# .env を編集してSpotifyクレデンシャル等を設定

# 開発起動（HMR有効）
make up

# 型同期（Phase B以降、バックエンド起動後）
make gen

# 停止
make down
```

## 15. 認証方式

### アプリ利用者の認証
- Spotify OAuth Authorization Code Flow
- ログイン後、ユーザーのSpotify IDを取得して環境変数 `ALLOWED_SPOTIFY_USER_ID` と一致するか確認
- 一致しない場合は403で拒否
- セッション管理: HTTPOnly Cookie（JWT）

### Spotify API用トークン管理
- ユーザートークン: ログイン時に取得した `refresh_token` を暗号化してDBに保存（フォロー同期用）
- アプリトークン: Client Credentialsで取得、メモリ上にキャッシュ（有効期限内は再利用）

## 16. 開発手順

### Step 0: 環境構築

| Step | 内容 | 完了条件 |
|---|---|---|
| 0 | Docker環境セットアップ（compose, Dockerfile, .env.example, Makefile） | `make up` で空のFastAPIとReactが立ち上がる |

### Phase A: フロントエンドモック開発

**目的**: 画面を触れる状態で要件・データ形状を確定させる。バックエンドはまだ実装しない（コンテナは立ち上げるが、エンドポイントは固定JSON返却のスタブのみ）。

| Step | 内容 | 完了条件 |
|---|---|---|
| A-1 | API契約のTypeScript型定義（手書き暫定 `frontend/src/types/api.ts`） | データモデル章と整合する型が揃う、`VinylRecord` 含む |
| A-2 | モックJSONファイル作成 (`frontend/src/api/mocks/*.json`) | 全エンドポイント分のダミーデータが揃う、レコード10件程度のサンプル含む |
| A-3 | APIクライアント抽象化（モック/実API切り替え機構） | `VITE_USE_MOCK=true`で全画面が動く |
| A-4 | 共通レイアウト + ルーティング（Home/Feed/Artistsの3タブ） | ヘッダー、ナビ、3タブ切替が動く |
| A-5 | Home: レコードマトリクス画面（基本グリッド） | グリッド表示、空状態あり |
| A-6 | Home: フリップ機能（クリックで3D裏返し） | 表→裏切り替え、別カードクリックで前のカード閉じる |
| A-7 | Home: 並び替えモード切り替え（4種類） | 4モード切替、見え方が変わる |
| A-8 | Home: ドラッグ&ドロップ（dnd-kit導入） | デフォルトモードで並び替え可能、`display_order` 仮想更新 |
| A-9 | Home: アーティストごと表示（セクション見出し） | アーティスト名が見出しとして並ぶ |
| A-10 | Home: レコード追加フロー（アーティスト選択→アルバム選択→メモ入力） | フルフローで追加できる |
| A-11 | Home: レコード編集・削除 | 全フィールド編集可、削除確認 |
| A-12 | Home: 絞り込み（アーティスト、評価） | フィルタが効く |
| A-13 | Artists: アーティスト一覧画面 | 一覧表示、追加・削除UI、空状態あり |
| A-14 | Artists: エイリアス管理UI | 追加・削除ができる、空状態あり |
| A-15 | Artists: アーティスト詳細（持っているレコード表示） | アーティストごとの所有レコードが見える |
| A-16 | Feed: 新譜タブ | 一覧表示、空状態あり、「コレクションに追加」ボタン |
| A-17 | Feed: 公演タブ | 一覧表示、空状態あり |
| A-18 | 同期ボタン・sync_status表示 | 全タブから同期できる、最終同期日時が見える |
| A-19 | 各種ロード状態（スケルトン） | 全画面でローディング中表示が出る |
| A-20 | エラー状態（リトライ可能） | エラー時に何が起きたか分かる |
| A-21 | 触ってみての改善反映 | 実用上問題ないUIになる |

**Phase A 終了時**: 要件定義書をレビューし、必要に応じて改訂する。データ形状の変更はここで行う。

### Phase B: バックエンド設計と実装

**目的**: フロントが実APIに接続できる状態にする。Phase A の手書き型を Pydantic に写経し、`make gen` で自動生成型に切り替える。

| Step | 内容 | 完了条件 |
|---|---|---|
| B-1 | Pydanticモデル定義（フロントの手書き型を写経） | OpenAPI仕様（`/openapi.json`）が手書き型と一致 |
| B-2 | **`make gen` で `api.generated.ts` 生成、手書き`api.ts`を破棄** | フロントが自動生成型でビルドできる |
| B-3 | FastAPIスタブ実装（固定JSONを返す） | `VITE_USE_MOCK=false`でフロントが動く |
| B-4 | SQLModelスキーマ定義 + `create_all()` | コンテナ起動時にテーブル作成（vinyl_records含む） |
| B-5 | アーティスト・エイリアスCRUDエンドポイント | DBから返るようになる |
| B-6 | vinyl_records CRUDエンドポイント | レコード追加・編集・削除・一覧・絞り込みが動く |
| B-7 | vinyl_records 並び替えエンドポイント (`PATCH /api/records/reorder`) | フロントからのドラッグ&ドロップでDB反映 |
| B-8 | Spotify Client Credentials認証 + アルバム検索エンドポイント | レコード追加時にアーティストのアルバム一覧を返せる |
| B-9 | Spotify OAuth Authorization Code + フォロー同期 | ログインしてフォローリストが取れる |
| B-10 | 新譜取得バッチ（APScheduler） + `/releases` | 日次自動取得が動く |
| B-11 | 公演エンドポイント（DBから返すだけ） | スクレイピング前でも一覧APIは完成 |

### Phase C: スクレイピングと統合

**目的**: 実データで全機能を動かす。

| Step | 内容 | 完了条件 |
|---|---|---|
| C-1 | Blue Note Tokyo スクレイパー（UPSERT、cancelled対応含む） | 1会場分のスケジュールがDBに入る、再実行で重複しない |
| C-2 | 残り4会場のスクレイパー追加 | 全5会場対応 |
| C-3 | sync_status実装 | バッチ成否がUIに反映される |
| C-4 | Alembic導入 + 初期マイグレーション生成 | 以降のスキーマ変更を安全に追跡できる |

## 17. リスク・論点

| リスク | 影響 | 対応案 |
|---|---|---|
| 会場サイトのHTML構造変更 | スクレイパー停止 | 各会場別にエラーハンドリング、`sync_status`にエラー記録、UIで可視化 |
| Spotify API仕様変更 | 新譜取得不可 | Client Credentialsを採用しており影響範囲は限定的、変更時に個別対応 |
| 「日本公演」判定の精度 | 関係ない公演が混ざる | スクレイピング元が日本会場のみなので問題なし |
| アーティスト名の表記ゆれ | 会場名↔アーティスト名の照合失敗 | `artist_aliases` テーブルで手動補正、UI上で随時追加 |
| `appears_on` のノイズ | コンピレーション盤が新譜として大量検出 | MVPでは `album_type IN ('album', 'single')` のみ表示 |
| 公演の中止・延期 | DBに古い情報が残る | UPSERT方式 + 未検出の未来日公演を `cancelled` マーク |
| 1日複数ステージの扱い | DBで表現できない | `stage_times` カラムにカンマ区切りで保持、UIは1日1行表示 |
| バッチの静かな停止 | 古い情報を見続けてしまう | `sync_status` テーブルとUI表示で気づける |
| Dockerコンテナ再起動でAPSchedulerのジョブが消える | バッチが走らない期間が出る | コンテナ起動時にジョブ登録、起動時に直近未実行があれば即実行 |
| SQLiteとボリュームマウントのパーミッション | 書き込みエラー | コンテナ内ユーザーIDをホストと揃える、またはvolume初期化を明示 |
| Phase Aで決めた型契約とPhase BのPydanticの乖離 | 統合時に手戻り | B-1で手書き型をPydanticに写経、B-2で `make gen` 実行して型エラーを潰す |
| **`make gen` 実行時にbackendが落ちている** | **生成失敗** | **Makefileに前提条件チェックを入れる、またはCI環境ではPydanticから直接OpenAPI仕様を生成** |
| **OpenAPI生成型がPydanticの設計に強く依存** | **API変更時にフロント側の修正範囲が広がる** | **頻繁な変更が見込まれる箇所はラッパー型で吸収、`api.generated.ts`を直接importしないパターン** |
| モックデータが現実離れしている | UIが実データで崩れる | モックは実際のSpotifyレスポンス・会場サイト表記をベースに作る |
| Spotify未配信盤の登録時、アーティスト紐付けが面倒 | 手動入力時のUXが悪い | アーティストはまず`artists`に登録（手動追加機能経由）してから、レコード登録でそのアーティストを選ぶ運用 |
| 同じアルバムを複数プレス所有時の重複表示 | UI上で見分けがつかない | `pressing_info`を一覧/裏面に表示、フィルタはアーティスト+タイトルで絞れる |
| レコード画像URLの永続性 | Spotify画像URLが将来変わる | 重要なら画像をローカル保存する選択肢あり、MVPではURL保持のみ |
| メモのバックアップ | DBが飛ぶとストーリーが消える | SQLiteファイルの定期バックアップを運用上推奨（Phase 2でエクスポート機能） |
| 3Dフリップアニメーションのパフォーマンス | 多数カード時にカクつく | `will-change: transform`、100枚程度まではMVPで問題なし、500枚規模は仮想スクロール（Phase 2） |
| dnd-kitとフリップの操作競合 | ドラッグ意図がフリップ発火する | dnd-kitの`activationConstraint`（最小ドラッグ距離8px）でクリックと区別 |
| 並び替えモード切り替え時のドラッグ無効化忘れ | モード違反でDB破壊 | `useSortable`の`disabled`プロパティで明示制御 |

## 18. Phase 2以降の候補

- スマホUI最適化、PWA化
- 通知機能（メール / Web Push）
- ジャズフェス出演ラインナップの自動チェック
- メディアRSS統合（Jazz Tokyo, JazzTimes等）
- アーティスト詳細ページの強化（ディスコグラフィ全表示）
- クラウドデプロイ（Railway / Fly.io / Render等）
  - Docker化済みなのでデプロイは `docker-compose.yml` を流用可能
  - DBはPostgreSQLへ移行（接続文字列変更のみ）
- Bandsintown API統合（必要なら）
- `appears_on` / コンピレーション専用タブ
- **CI環境での型生成自動化**: backendを起動せず、Pydanticから直接OpenAPI仕様を吐いて型生成するスクリプト
- **コレクション機能の拡張**:
  - Discogs API連携（プレス情報の自動補完、コレクション価値推定）
  - レコードのエクスポート（CSV/JSON）
  - 統計（レーベル別、年代別、評価分布）
  - 「今日のレコード」ランダムピックアップ
  - 画像のローカル保存
  - レコードのジャンルタグ管理
  - 「貸出中」「修理中」などのステータス管理
  - 仮想スクロール対応（500枚以上のコレクション）
  - CD・デジタル購入も含む拡張
- **YouTube出演情報の取得**（YouTube Data API v3、無料、1日10,000ユニット）
  - 監視対象チャンネルリストを事前登録（レーベル系、本人公式、ジャズ番組系等）
  - 各チャンネルの新着動画を日次取得 → タイトル/説明にフォロー中アーティスト名（+エイリアス）が含まれていれば抽出
- **ラジオ出演情報の取得**（radiko / NHKらじる★らじるの番組表XML）
  - 監視対象局を事前登録（NHK-FM、TOKYO FM、InterFM897、bayfm等のジャズ番組がある局）
  - 番組表を週次取得 → 出演者欄（`<pfm>`）にフォロー中アーティスト名（+エイリアス）が含まれていれば抽出
  - radiko APIは非公式エンドポイント（10年来コミュニティで利用、ただし破壊的変更リスクあり）