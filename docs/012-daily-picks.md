# ADR-012: On This Day — 日次ピックと蓄積メタデータ

> **Summary (English).** A proposal (not implemented) for a quiet "Now On Air" ticker showing a classic album released on today's date decades ago. A daily batch selects from a curated `featured_albums.json` (matching month and day), persists the pick to a `daily_picks` table (unique per date) so picks are reproducible and accumulate as material for a future "monthly personal magazine", and exposes `GET /api/daily-pick`. Phase 1 is text only (no 30-second preview). Open questions cover the candidate source, behaviour on days without a match (stay silent), tie-breaking (oldest wins), placement relative to the Feed's "today" label and click behaviour.
>
> *The body of this document is in Japanese. See [docs/README.md](./README.md) for the index of all design documents.*

**Status**: Proposed | **Date**: 2026-05-13
**Related**: UI 設計原則（雑誌的デザインシステム。ADR-990、未公開）§2.7 Feed, プロダクトビジョン（未公開）Phase 6 月刊個人誌

---

## このドキュメントの読み方

| 目的 | 読む場所 |
|---|---|
| なぜこの機能か | **Part 1: Philosophy** |
| 何を作るか (データ/動線) | **Part 2: Specification** |
| 実装で詰めること | **Part 3: Implementation Sketch** |
| 個別判断の根拠と未決事項 | **Appendix: Rationale / Open Questions** |

---

# Part 1: Philosophy

## 1.1 なぜ作るか

「**今日**」を中心軸にしたジャズライフを編集する (UI 設計原則 §2.7「上が未来 / 中央が今日 / 下が過去」) という思想を、**過去側にもう一段拡張する** ための機能。

具体的には:

> **その日の何十年か前にリリースされた名盤を、雑誌の「Now On Air」風に右上に静かに流す。**

これによって:

- 開いたその日に「Kind of Blue は 1959 年の今日リリース」のような偶発的な発見が生まれる
- 「**時間が編集者になる**」([ADR-003](./003-artist-management.md) §1.2 原則 2) を体感する仕組みになる
- 日々のピックをデータとして残せば、**過去に何が選ばれたか** が蓄積され、Phase 6「月刊個人誌」の素材として再利用できる

## 1.2 雑誌としてのメタファ

雑誌の Now On Air コーナーは「**今この瞬間に流れている音**」を読者に意識させる装置。
本アプリでは音は流さない (Phase 1) が、**「今日が誰かの何周年か」を文字で淡く流す** ことで、
ジャケット棚 (Home) / Feed (今月の予定) / アーティスト一覧 という静的な情報構造に、
**時間の流れの感触** を一筆加える。

UI 設計原則 §2.5 の「動きは情報の伝達のためだけに使う」原則からすると、
ticker の横スクロールは「時間が流れていることそのもの」を伝達する動きなので、例外的に許容される。

---

# Part 2: Specification

## 2.1 ユーザー体験 (Phase 1 = テキストのみ)

- Feed (もしくは共通ヘッダ) の右上に小さく `NOW ON AIR · Kind of Blue (1959-08-17) — Miles Davis` 等を表示
- フォント: サンセリフ体、`text-xs uppercase tracking-wider` (UI 設計原則 §2.1 メタ情報スタイル)
- 動き: 右→左に CSS `@keyframes translateX`、`overflow-hidden` で切り取り
- クリック挙動: 暫定で「何もしない」(後述 Open Questions)
- 今日に対応する pick がない日は何も表示しない (沈黙する自由を残す)

## 2.2 データモデル

### 新規テーブル: `daily_picks`

| カラム | 型 | 説明 |
|---|---|---|
| `id` | UUID v7 | PK |
| `pick_date` | DATE | この pick が「何日のもの」か (`UNIQUE`) |
| `title` | str (500) | アルバム名 |
| `artist_name` | str (300) | アーティスト名 (denormalize) |
| `original_release_date` | DATE | オリジナルリリース日 (年月日揃ったもののみ採用) |
| `spotify_album_id` | str (64) NULL | Phase 2 で 30 秒再生に使う |
| `image_url` | str (1000) NULL | ジャケ画像 (任意、ticker は文字だけで OK) |
| `created_at` | TIMESTAMPTZ | DB レベルで `now()` |

**位置づけ**: `releases` (新譜通知用、流動的) と別軸の「**歴史的事実の固定スナップショット**」テーブル。
将来「その日のジャズ名盤」「その日のレーベル設立」「その日の名演」など軸が増える場合は
カラム追加 or 別テーブルに分離するが、初期は albums 限定で素直に運用。

### 候補リソース: `backend/seeds/featured_albums.json`

歴史的名盤のキュレーションリスト (例: Kind of Blue, A Love Supreme, Saxophone Colossus …)。
20〜50 件で開始、運用しながら追加。各エントリは:

```json
{
  "title": "Kind of Blue",
  "artist_name": "Miles Davis",
  "original_release_date": "1959-08-17",
  "spotify_album_id": "1weenld61qoidwYuZ1GESA"
}
```

`pick_date` ではなく `original_release_date` を持つ点に注意 (バッチが「今日と月日が一致するもの」を引く)。

## 2.3 バッチ処理

- **頻度**: 1 日 1 回 (00:00 JST 想定、APScheduler はすでに依存に入っている)
- **処理**:
  1. 候補リストから `MONTH(original_release_date) = MONTH(today)` かつ `DAY(...) = DAY(today)` かつ `YEAR(...) < YEAR(today)` のレコードを抽出
  2. 該当が複数なら 1 つに絞る (選択ルールは Open Questions 参照)
  3. `daily_picks` に `pick_date = today` で upsert (date 一意)
  4. 該当無しなら何も書かない (フロントは「今日は沈黙」と解釈)
- **冪等性**: 同日中に複数回走っても `(pick_date)` UNIQUE で安全
- **再実行**: 過去日付の再生成は手動コマンドで実行可能にする (`alembic.ini` レベルではなくスクリプト or CLI)

## 2.4 API

- `GET /api/daily-pick` — 今日 (サーバの JST 0:00 基準) の pick を返す。無ければ 204 (or `{ "item": null }`)
- 認証: ユーザ依存しないグローバルデータなので auth 不要 (要設計)
- レスポンス: `pick_date / title / artist_name / original_release_date / spotify_album_id / image_url`

将来:
- `GET /api/daily-pick/history?from=YYYY-MM-DD&to=YYYY-MM-DD` — 期間範囲で履歴閲覧 (月刊個人誌で利用)

## 2.5 フロントエンドの配置

- UI 設計原則 §2.7 で Feed の上部に「今日」のラベルが既にある (現状 `text-right text-lg italic`)
- Now On Air ticker をどう共存させるかは Open Questions §A4
- 配置候補: Feed ページ右上 / 全画面共通ヘッダ / Home の隅に小さく

---

# Part 3: Implementation Sketch

実装着手時のおおまかな PR 分割:

1. **DB / model / migration**: `daily_picks` テーブル定義、Alembic autogenerate、`featured_albums.json` シード配置
2. **service + repository + batch**: ピック選択ロジック、APScheduler 登録、CLI からの手動再生成
3. **API endpoint**: `GET /api/daily-pick` (+ openapi.json 再生成 + orval gen)
4. **Frontend ticker**: コンポーネント `NowOnAir.tsx` 新規、CSS marquee、Feed (or 共通ヘッダ) 右上に配置

各 PR は独立して merge 可能。3 までは ticker が見えないが、API は手で叩いて確認可能。

---

# Appendix A: Open Questions

実装着手前に決めたいもの:

1. **候補ソースの方針**
   - (a) こちらでキュレーションした静的 JSON
   - (b) ユーザの `vinyl_records` から月日一致を引く (自分のコレクションが流れる)
   - (c) (a) を優先、なければ (b) フォールバック
   - **暫定推奨**: (a) — 歴史的名盤としての「重み」が一定保たれるため。(b) は「自分の棚にあるから」流すと逆に偶発性が失われる
2. **当日マッチが無い日の挙動**
   - (a) 何も表示しない (沈黙)
   - (b) 最も近い日付の名盤にフォールバック
   - (c) ランダムな名盤
   - **暫定推奨**: (a) — UI 設計原則の「静かである」原則に従い、無理に何かを流さない
3. **複数候補の選択ルール**
   - (a) 最も古い (= 何十年前感が強い)
   - (b) ランダム
   - (c) `original_release_date` との年差が大きい順
   - **暫定推奨**: (a) — 「**何十年か前**」を強調するため最古を優先
4. **Ticker と既存「今日ラベル」の共存**
   - (a) 並べて出す (ラベル左、ticker 右)
   - (b) Now On Air を持つ日は ticker が今日ラベルを兼ねる
   - (c) Feed ページのみ ticker、Home / Artists には影響なし
   - **暫定推奨**: (c) — Feed は時間を扱うページなので Now On Air と相性が良く、Home / Artists は静かなまま保つ
5. **クリック挙動**
   - (a) 何もしない (純粋なヘッドライン)
   - (b) アルバム詳細モーダルを開く (Spotify メタ取得)
   - (c) `RecordFormModal` を defaults 込みで開いて「集めたい」導線
   - **暫定推奨**: (a) → 慣れたら (c) — まずは「読み物」として置き、欲求が育ってから操作を足す
6. **メタテーブルの今後の拡張**
   - albums 限定で運用するか、ジャンル別 / 軸別に拡張する設計の余地を持たせるか
   - 当面 albums 専用テーブル、軸が増えたら別テーブル切る方針で OK?

---

# Appendix B: Rationale

## §1. なぜ「リアルタイムに算出」ではなく「バッチ + 永続化」か

- **再現性**: 同じ日に同じ pick が再現される (タイムゾーン跨ぎや候補リスト更新で揺らがない)
- **蓄積価値**: 日々の pick がログとして残り、後から「**この一年で何が流れたか**」を編集素材にできる
- **負荷**: API リクエストごとに候補検索する必要がなく、ヒット率 1 クエリ

## §2. なぜ Phase 1 で 30 秒再生を入れないか

- Spotify Web API の preview_url は全曲にあるわけではない
- 自動再生は UX 微妙 (突然音が出る)、クリックでも CORS / SDK のハマりどころが多い
- 文字だけでも「Now On Air」感は十分に成立する (むしろ静謐な雑誌的体験に近い)
- Phase 2 で `spotify_album_id` 経由で preview 取得を後付けできる設計にしておけば、いつでも昇格できる

## §3. なぜ `releases` テーブルを使い回さないか

- `releases` は「**フォロー中アーティストの新譜通知**」用 ([ADR-003](./003-artist-management.md))、つまり**未来〜近い過去の流動的なフィード**
- `daily_picks` は「**歴史的事実の静的スナップショット**」で、性格が全く違う
- 同じテーブルに混ぜると「is_read」「artist_id (フォロー対象?)」などの意味が壊れる
- 別テーブルに分けることで、`daily_picks` 側で素直なスキーマ進化ができる

## §4. なぜ JST 0:00 切替か

- 個人用アプリ、ユーザの生活は日本時間中心
- UTC 切替だと「日付が変わったのに pick が変わらない朝」が発生する
- Settings で TZ 切替可にする要望が出たら拡張する

---

# Consequences

### Positive

- 「時間が編集者になる」([ADR-003](./003-artist-management.md) §1.2 原則 2) を過去側へ拡張する具体的な装置
- 日々のピック蓄積が Phase 6 (月刊個人誌) の素材として自然に成長する
- 候補リスト (featured_albums.json) を育てる楽しみが運用に生まれる

### Negative

- backend に新テーブル + バッチ + 候補シードを足すので、Phase B-2 (orval 移行中) のスコープが少し膨らむ
- キュレーション JSON のメンテナンスコスト (薄め、年に数回追加すれば十分)
- TZ 跨ぎ・夏時間など細かいエッジケースは初期は無視 (JST 固定)

### Neutral

- Phase 2 で 30 秒再生を後付ける際、`spotify_album_id` カラムを最初から持っておくので追加マイグレーション不要
