# ADR-003: アーティスト管理の3層構造と体験のライフサイクル

> **Summary (English).** Part 1 sets the product philosophy in seven principles — records come first and artists are a by-product; time, not a follow limit, prunes the list (follows without activity for two years fade); ownership is permanent while interest is fluid; only deliberate actions (adding a record, opening an artist page) update a relationship; Home shows only physically owned records; the artist page is where Feed meets Collection; the degree of physicality decides the granularity of notes — and it explicitly rejects algorithmic recommendation. Part 2 splits artists into a master catalog (`artists`), per-user `user_follows` (follow + pin + `archived_flag` decay) and `vinyl_records` with an `owned`/`wanted` status, adds concert attendance tables, and lists APIs and flows. Part 3 is the PR plan with code patterns (auto-follow on record creation, the 5-pin constraint, the "touch" logic). Appendices record rationale, alternatives considered, deliberately deferred decisions and open questions.
>
> *The body of this document is in Japanese. See [docs/README.md](./README.md) for the index of all design documents.*

**Status**: Proposed | **Date**: 2026-05-11
**Supersedes**: ADR-001 §1 における "followed" 概念
**Related**: ADR-001, ADR-002, プロダクトビジョン（未公開）

---

## このドキュメントの読み方

| 目的 | 読む場所 |
|---|---|
| 何を作るか、なぜ作るか | **Part 1: Philosophy** |
| データモデル・API・動線を確認したい | **Part 2: Specification** |
| PR に着手する、実装パターンを参照する | **Part 3: Implementation Plan** |
| 個別の決定の根拠を確認したい | **Appendix: Rationale / Alternatives** |

---

# Part 1: Philosophy

## 1.1 アプリのコンセプト

このアプリは「ジャズリスナーのコレクション + Feed ダッシュボード」だが、その根底にあるのは
**自分の生活を編集する場所** という設計思想である。

プロダクトビジョンの核:
> コンテキストとして好きな本、音楽、場所を **溜めていって**、そこから新たな提案をもらう

このアプリが他の音楽管理アプリと根本的に違うのは、以下の7つの原則を貫いていることである。

## 1.2 7つの設計原則

### 原則 1: 主従の反転 — レコードが先、アーティストは副産物

> 登録できるアーティストは基本レコードを所有しているアーティスト。
> どうしても追加したい時だけフォローできる。

「アーティストをフォローしてレコードがついてくる」のではなく、
「**レコードを所有していてアーティストが現れる**」。
溜めるのはレコードであり、アーティストはレコードを溜めた副産物。

### 原則 2: 時間が編集者になる

フォロー数を上限で抑えるのではなく、**2 年アクションのないフォローを自然に薄く表示する**。
SNS のように整理を急かす通知は出さない。フェードしているだけで、見たい時には見える。
時間が淘汰の主体。

### 原則 3: 所有は永続、興味は流動

物理的に所有しているアーティストは減衰対象外。物理的に所有している以上、
自分の生活に組み込まれているから。
**「持っているのにアプリで触っていない」というだけで薄く表示するのは失礼**。

### 原則 4: アクションは「向き合う行為」に限る

アーティストとの関係を更新するアクションは、**レコード追加** と **アーティスト個別ページ閲覧** の 2 つだけ。
一覧スクロール、ピン留め切替、メモ編集などは対象外。
「アーティストにきちんと向き合った」時だけ、関係が更新される。

### 原則 5: 物質感を損なわない

Home のジャケットマトリクスは **物理的に所有しているレコードだけ** が並ぶ。
欲しいレコード (want list) は混ぜない。
実物のレコード棚にあるのは持っているレコードだけ、というシンプルな事実をデジタル上でも保つ。

### 原則 6: アーティストページが Feed と Collection の交差点

アーティストページから、Feed (新譜・公演) を見て直接 Collection (want list / 行きたい) に
変換できる動線を作る。
**情報を受信して → 興味を表明して → 行動して → 記録に残る** という流れが
ひとつの画面で完結する。

### 原則 7: 物質性の度合いがメモの粒度を決める

レコードは「物質を所有する」体験 → プレス情報・購入店・購入日などフルセット
公演は「時間と空間の体験」 → status + rating + memo (自由記述に語らせる)

### アンチパターン: アルゴリズム推薦は採用しない

協調フィルタリング、暗黙的シグナル、LLM による「あなたへのおすすめ」は採用しない。
これは技術的判断ではなく **思想的判断**:
- 編集権の喪失を防ぐ
- フィルターバブルから自由でいる
- 時間を搾取されない
- 自分の輪郭を保つ

ユーザーは編集者であり、アプリは編集者の道具である。

## 1.3 体験のライフサイクル

このアプリで完結するべき体験の流れ:

```
[閲覧]   アーティストページを開く
   ↓
[興味の表明]   「♡ 欲しい」「✓ 行きたい」をタップ
   ↓
[行動]   中古屋でレコード入手、Blue Note へ行く
   ↓
[記憶]   「入手しました」「行った + memo」で記録
```

この 4 フェーズが、ひとつのアプリの中で循環する。
**情報の受信から記憶の蓄積まで、ユーザーが編集者として関わる**。

---

# Part 2: Specification

## 2.1 データモデル一覧

| テーブル | 役割 | 主な変更 |
|---|---|---|
| `artists` | ジャズアーティスト・マスタカタログ | `followed` カラム削除、`source` 追加 |
| `user_follows` | ユーザーのフォロー状態 + ピン留め (新規) | 新規作成 |
| `vinyl_records` | レコード (所有 + 欲しい) | `status` カラム追加 |
| `concerts` | 公演マスタ (スクレイピング + 手動) | `source` `venue_name_freetext` 追加 |
| `user_concert_attendances` | 「行きたい / 行った」(新規) | 新規作成 |

### artists

```python
class Artist(SQLModel, table=True):
    spotify_id: str = Field(primary_key=True, max_length=64)
    name: str = Field(max_length=200, index=True)
    image_url: str | None = Field(default=None, max_length=500)
    source: str = Field(default="seeded", max_length=20)
    # "seeded" | "spotify_dynamic" | "manual"
    added_at: datetime
```

旧 `followed` カラムは削除。マスタの責務に専念する。

### user_follows (新規)

```python
class UserFollow(SQLModel, table=True):
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", primary_key=True)
    artist_id: str = Field(foreign_key="artists.spotify_id", ondelete="CASCADE",
                            primary_key=True, max_length=64)
    pinned: bool = Field(default=False, index=True)
    followed_at: datetime
    pinned_at: datetime | None
    last_action_at: datetime
    archived_flag: bool = Field(default=False, index=True)
```

「所有か興味か」は持たない (vinyl_records の存在で派生判定)。
ピン留め上限 5 件はサービス層でチェック。

### vinyl_records (status 追加)

```python
class VinylRecord(SQLModel, table=True):
    # ... 既存カラム (Phase B-Home で確定済み)
    status: str = Field(default="owned", max_length=20)
    # "owned": Home のマトリクスに表示
    # "wanted": want list、アーティストページのみ
```

want list の上限なし (個人記録として何枚でも)。

### concerts (source 追加)

```python
class Concert(SQLModel, table=True):
    # ... 既存カラム
    source: str = Field(default="scraped", max_length=20)
    # "scraped": スクレイピング由来
    # "manual": ユーザー手動追加 (過去公演、海外、閉鎖会場等)
    venue_name_freetext: str | None = Field(default=None, max_length=200)
    # venue_id が null の時の自由記述
```

### user_concert_attendances (新規)

```python
class UserConcertAttendance(SQLModel, table=True):
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", primary_key=True)
    concert_id: str = Field(foreign_key="concerts.id", ondelete="CASCADE",
                             primary_key=True, max_length=128)
    status: str = Field(max_length=20)
    # "wanted": 行きたい / "attended": 行った
    rating: int | None  # 1-5
    memo: str | None = Field(max_length=2000)
    created_at: datetime
    updated_at: datetime
```

レコードのフルセットと違い、シンプルセット (status + rating + memo)。
公演体験は自由記述に語らせる。

## 2.2 主要動線

### 動線 1: ホーム画面 (Home)

```
Home (ジャケットマトリクス)
  └ status='owned' のレコードのみ表示
  └ 並び順: デフォルト (display_order) / 購入日 / リリース順 / アーティストごと
  └ クリックでフリップ → 裏面にメモ・購入情報
```

### 動線 2: アーティストページ (3 セクション構造)

```
[アーティスト名 + 写真]

📀 所有しているレコード (status='owned')
  ジャケットグリッド

💭 欲しいレコード (status='wanted')
  ジャケットグリッド
  各レコード → [入手しました] で owned に遷移

📡 Feed
  📀 最新リリース (未所有)
    "New Album 2026" → [♡ 欲しいリストに追加]

  🎤 今後の来日公演
    2026/8/15 Blue Note Tokyo → [✓ 行きたい]

  📝 過去の公演 (手動追加可)
    2019/5/15 Village Vanguard → [済 行った]
```

ページを開く行為 = `last_action_at` 更新トリガー。

### 動線 3: 状態遷移

| トリガー | 遷移 | 効果 |
|---|---|---|
| Release アイテムの「♡ 欲しいリストに追加」 | `vinyl_records` INSERT (status='wanted') | want list に追加、Spotify由来データを流用 |
| want レコードの「入手しました」 | `vinyl_records` UPDATE (status='owned' + purchase_date入力) | コレクション加入、Home に出現 |
| 未来 Concert の「✓ 行きたい」 | `user_concert_attendances` INSERT (status='wanted') | 行きたい登録 |
| 過去 Concert の「済 行った」 | `user_concert_attendances` INSERT (status='attended') | 行った記録 |
| 行きたい → 行った | `user_concert_attendances` UPDATE (status='attended' + rating + memo) | 体験を記録 |

### 動線 4: 時限性自然減衰

```
アーティストページを開く
   ↓
follow.last_action_at が 2年以上前?
   ├ Yes → archived_flag = true (一覧で薄く表示候補に)
   └ No  → archived_flag = false (活性化)
   ↓
last_action_at = now() に更新
   ↓
ただし: vinyl_records に owned があるなら、archived_flag = false に強制
   (所有は永続)
```

## 2.3 API 一覧

### マスタ管理 (artists)

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/api/artists` | 一覧 (検索 q=, ページング) |
| GET | `/api/artists/{spotify_id}/detail` | アーティスト詳細 (3セクション一括) |
| POST | `/api/artists` | 1人追加 (Spotify検索結果から) |
| POST | `/api/artists/bulk` | 複数追加 |
| POST | `/api/admin/artists/bulk` | 初期シード用 (admin) |

### フォロー・ピン留め (user_follows)

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/api/users/me/follows` | フォロー一覧 |
| POST | `/api/users/me/follows` | 1人フォロー |
| POST | `/api/users/me/follows/bulk` | 複数フォロー |
| DELETE | `/api/users/me/follows/{artist_id}` | フォロー解除 |
| PUT | `/api/users/me/follows/{artist_id}/pin` | ピン留め (409 で入れ替え促す) |
| DELETE | `/api/users/me/follows/{artist_id}/pin` | ピン解除 |
| PUT | `/api/users/me/follows/pin/replace` | 入れ替え (原子的) |

### レコード (vinyl_records)

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/api/records?status=owned` | コレクション (default) |
| GET | `/api/records?status=wanted` | want list |
| POST | `/api/records` | 追加 (status を指定) |
| POST | `/api/records/from-release` | Release から want に変換 |
| PUT | `/api/records/{id}` | 編集 |
| PUT | `/api/records/{id}/acquire` | wanted → owned |
| DELETE | `/api/records/{id}` | 削除 |
| PATCH | `/api/records/reorder` | ドラッグ並び替え |

### 公演 (concerts, attendances)

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/api/concerts` | 一覧 |
| POST | `/api/concerts` | 手動追加 (過去公演等、source='manual') |
| GET | `/api/users/me/concert-attendances` | 行きたい/行った一覧 |
| POST | `/api/users/me/concert-attendances` | 1件登録 |
| PUT | `/api/users/me/concert-attendances/{concert_id}` | 編集 (status遷移、memo) |
| DELETE | `/api/users/me/concert-attendances/{concert_id}` | 削除 |

### Feed

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/api/releases?pinned_only=true` | 新譜 (ピン留め優先表示) |
| GET | `/api/concerts/feed?pinned_only=true` | 公演 |
| POST | `/api/admin/sync/releases` | 手動同期トリガー |
| POST | `/api/admin/sync/concerts/{venue_id}` | スクレイピング手動トリガー |

---

# Part 3: Implementation Plan

## 3.1 PR 分割

| # | 内容 | 主な変更 |
|---|---|---|
| **PR-1** | Alembic migration + データモデル変更 | テーブル変更を 1 migration に集約 |
| **PR-2** | user_follows API | フォロー / ピン留め / 入れ替え |
| **PR-3** | vinyl_records.status + want list API | status カラム対応、acquire 遷移 |
| **PR-4** | artists API + マスタカタログ | シード 100 人、Spotify動的補完、touch ロジック |
| **PR-5** | user_concert_attendances API | 行きたい / 行った |
| **PR-6** | 公演マスタ手動追加 API | 過去公演対応、自由記述会場 |
| **PR-7** | アーティストページ統合 API | `/api/artists/{id}/detail` (3セクション一括返却) |
| **PR-8** | Release バッチ | Spotify Client Credentials, APScheduler 日次 |
| **PR-9〜** | Concert スクレイピング | Blue Note Tokyo から 4 会場 |

## 3.2 PR-1: Migration スクリプト

```python
# alembic/versions/xxxx_artist_management.py
def upgrade():
    # 1. 新規テーブル
    op.create_table('user_follows', ...)
    op.create_table('user_concert_attendances', ...)

    # 2. 既存テーブル変更
    op.add_column('vinyl_records', sa.Column('status', sa.String(20),
                                              server_default='owned', nullable=False))
    op.add_column('concerts', sa.Column('source', sa.String(20),
                                         server_default='scraped', nullable=False))
    op.add_column('concerts', sa.Column('venue_name_freetext', sa.String(200), nullable=True))

    # 3. 既存データのマイグレーション
    # artists.followed=true を user_follows に転記
    op.execute("""
        INSERT INTO user_follows (user_id, artist_id, followed_at, last_action_at)
        SELECT
            (SELECT id FROM users LIMIT 1) as user_id,
            spotify_id, added_at, added_at
        FROM artists
        WHERE followed = true
    """)

    # 4. 旧カラム削除
    op.drop_column('artists', 'followed')

def downgrade():
    # 逆順で実行 (本番運用前なのでスキップ可)
    pass
```

## 3.3 主要コードパターン

### パターン A: レコード追加時の自動フォロー

```python
# services/record_service.py
def create(self, user_id: UUID, data: VinylRecordCreate) -> VinylRecord:
    record = VinylRecord(**data.model_dump(), ...)
    self.record_repo.add(record)

    # user_follows がなければ自動作成、あれば last_action_at 更新
    follow = self.follow_repo.get(user_id, data.artist_id)
    if follow is None:
        self.follow_repo.add(UserFollow(
            user_id=user_id,
            artist_id=data.artist_id,
            last_action_at=datetime.now(UTC),
        ))
    else:
        follow.last_action_at = datetime.now(UTC)
        follow.archived_flag = False  # 所有が確定するので解除
        self.follow_repo.save(follow)

    return record
```

### パターン B: ピン留め 5 人制約

```python
# services/follow_service.py
def pin(self, user_id: UUID, artist_id: str) -> UserFollow:
    follow = self.repo.get(user_id, artist_id)
    if follow is None:
        raise NotFoundError("フォローしていないアーティストはピン留めできません")
    if follow.pinned:
        return follow
    current = self.repo.count_pinned(user_id)
    if current >= 5:
        raise PinLimitExceeded(current_pins=self.repo.list_pinned(user_id))
    follow.pinned = True
    follow.pinned_at = datetime.now(UTC)
    return self.repo.save(follow)
```

### パターン C: アーティストページの touch ロジック

```python
# services/artist_service.py
def get_detail_with_touch(self, user_id: UUID, spotify_id: str) -> ArtistDetailResponse:
    artist = self.repo.get(spotify_id)
    if not artist:
        raise NotFoundError(f"artist not found: {spotify_id}")

    follow = self.follow_repo.get(user_id, spotify_id)
    is_owner = self.record_repo.exists_owned(user_id, spotify_id)

    if follow:
        if not is_owner:
            inactive = follow.last_action_at < datetime.now(UTC) - timedelta(days=730)
            follow.archived_flag = inactive
        else:
            follow.archived_flag = False  # 所有なら常に false
        follow.last_action_at = datetime.now(UTC)
        self.follow_repo.save(follow)

    return ArtistDetailResponse(
        artist=artist,
        follow=follow,
        is_owner=is_owner,
        owned_records=self.record_repo.list_for_artist(user_id, spotify_id, "owned"),
        wanted_records=self.record_repo.list_for_artist(user_id, spotify_id, "wanted"),
        upcoming_releases=self.release_repo.list_for_artist(spotify_id, future_only=True),
        upcoming_concerts=self.concert_repo.list_with_attendance(
            spotify_id, user_id, future=True),
        past_concerts=self.concert_repo.list_with_attendance(
            spotify_id, user_id, future=False),
    )
```

### パターン D: 派生クエリ (所有 / 興味のみ)

```python
# repositories/follow_repository.py
def list_owned_artists(self, user_id: UUID) -> list[Artist]:
    """所有しているアーティスト"""
    stmt = (
        select(Artist)
        .join(VinylRecord, Artist.spotify_id == VinylRecord.artist_id)
        .where(VinylRecord.status == "owned")
        .distinct()
    )
    return list(self.session.exec(stmt).all())

def list_interest_only_artists(self, user_id: UUID) -> list[Artist]:
    """興味のみ (フォロー中だが未所有)"""
    owned_subquery = (
        select(VinylRecord.artist_id)
        .where(VinylRecord.status == "owned")
        .distinct()
    )
    stmt = (
        select(Artist)
        .join(UserFollow, Artist.spotify_id == UserFollow.artist_id)
        .where(
            UserFollow.user_id == user_id,
            Artist.spotify_id.not_in(owned_subquery),
        )
    )
    return list(self.session.exec(stmt).all())
```

## 3.4 アーティストページ統合 API のレスポンス

```python
class ArtistDetailResponse(BaseModel):
    artist: ArtistRead
    follow: UserFollowRead | None  # 未フォローなら null
    is_owner: bool
    owned_records: list[VinylRecordRead]   # status='owned'
    wanted_records: list[VinylRecordRead]  # status='wanted'
    upcoming_releases: list[ReleaseRead]   # 未所有の最新リリース
    upcoming_concerts: list[ConcertWithAttendanceRead]
    past_concerts: list[ConcertWithAttendanceRead]

class ConcertWithAttendanceRead(BaseModel):
    concert: ConcertRead
    attendance: UserConcertAttendanceRead | None  # 未登録なら null
```

フロントが 1 リクエストで必要な情報を取れる設計。
`attendance` が null なら「行きたい/行ったボタン」、ある場合は編集 UI を出す。

---

# Appendix A: Rationale (個別決定の根拠)

各 Decision の根拠を 1〜2 段落で。詳細は議論の経緯を見たい時にだけ読む。

### artists をマスタカタログにする理由
- マスタ化により検索の UX が向上 (DB 内 LIKE で即時応答、Spotify API は補完だけ)
- artists の責務が「マスタ」と「フォロー一覧」で混ざっていた問題を解消
- 複数ユーザー対応の伏線 (プロダクトビジョン Phase 6)

### user_follows に pin を統合する理由
- 「フォローしていないのにピン留め」が DB レベルで不可能になる
- フォロー解除でピン留めも自動消失、孤児レコードが出ない
- クエリがシンプル

### 「所有か興味か」をカラムで持たない理由
- 真実の源 (single source of truth) を vinyl_records 1 つにする
- レコード追加・削除時に user_follows.follow_type も更新する必要がなくなる
- 派生クエリで十分 (個人規模では性能影響なし)

### レコード追加で user_follows 自動 INSERT する理由
- 「所有しているのにフォロー外」状態を防ぐ
- ユーザーが「フォローする」を別操作として意識する必要がない

### ピン留めは所有も興味も対象にする理由
- 「来日が決まったから絶対行きたい」(まだレコードなし) のケースに対応
- 所有 vs 興味の境界は時間で変わる、ピン留めをそれに振り回されないようにする

### 6 人目を「入れ替え強制 UI」にする理由
- エラーは行動を促さない、「誰を外す」は引き算
- 「入れ替え」は **5 人という枠を選び続けている** 認識を毎回与える
- 「自分が編集者である」思想の現れ方として最も誠実

### 時限性減衰を 2 年にする理由
- ジャズの新譜サイクル (1〜2年) を踏まえ「丸 1 回の活動サイクルがあって何もなかった」幅
- 1 年だとシビアすぎ、3 年だと長すぎる

### アクションを 2 つ (レコード追加 + 個別ページ閲覧) に絞る理由
- すべての書き込みをカウントすると「うっかり操作」もアクション扱いになる
- この 2 つだけが「アーティストにきちんと向き合った」感覚と一致
- 一覧スクロールやピン留め切替はアクションではない

### Home を owned のみにする理由 (物質感)
- Home = レコード棚の視覚的シミュレーション
- want が混ざると「棚を見ているのか欲しいものリストを見ているのか」分からなくなる
- want list はアーティストページの 1 セクションとして集約

### want list の上限を設けない理由
- want list は「個人記録」の場所、編集された Home や Feed とは性格が違う
- 「買えなかったレコードのストーリー」を気軽に残せることが大事
- 上限ありだと「記録する価値があるか」を毎回考えて萎縮する

### 公演メモを status + rating + memo に絞る理由
- 物質性の度合いがレコードと違う
- 公演は時間と空間の体験、構造化フィールドに分解すると味気ない
- 自由記述に語らせる方が物語として読める

### 公演マスタへの手動追加を許す理由
- スクレイピング範囲外の過去公演を記録できないと、振り返りの価値が薄れる
- 「2015 年に行った Bill Frisell」を残せるアプリでありたい
- プロダクトビジョン Phase 4「時系列での文脈の振り返り」の MVP 実装

### user_concert_attendances を別テーブルにする理由
- concerts はマスタ、ユーザー個別状態は分離するべき
- 複数ユーザー対応で同じ公演に複数の状態を持たせる場合に必要

### アーティストページから Collection への動線を作る理由
- 情報を見て心が動いた瞬間に、最小の操作で記録に残せる
- プロダクトビジョンの「情報を受信して → 興味を表明して → 行動して → 記録に残る」流れを実現
- アーティストページが Feed と Collection の交差点になる

### アルゴリズム推薦を採用しない理由 (思想的判断)
- 編集権の喪失、フィルターバブル、時間の搾取、自分の輪郭が薄まる
- このアプリはこれら全てに対するアンチテーゼ
- ユーザーは編集者であり、アプリは編集者の道具

### マスタ追加とフォロー追加でエンドポイントを分ける理由
- 操作の意味が違う (世界の宣言 vs 私の宣言)
- 権限の境界が違う (admin vs user)
- エラーハンドリングが違う

---

# Appendix B: Alternatives Considered

| 案 | なぜ却下したか |
|---|---|
| LLM ベース推薦の採用 | 思想的判断で却下 (§Aルゴリズム不採用) |
| フォロー自体を 5 人上限 | Spotify との同期柔軟性を失う |
| artists.followed のまま単一ユーザー前提 | 後の migration コストが高い、今正しい構造にする方が安い |
| want list を別テーブル | 「want → owned」遷移が 2 ステップになる、共通フィールド重複 |
| 公演メモにフルセット | 物質性の度合いが違う、過剰 |
| 公演マスタ手動追加なし | 過去公演を記録できない、振り返り価値が落ちる |
| concerts に user_id 持たせる | マスタの責務が壊れる |
| バッチでアーカイブ判定 | 個人利用規模では遅延評価で十分 |
| 「興味のみ」枠の上限設定 | 時限性減衰で溢れない、上限不要 |

---

# Appendix C: Deferred Decisions (意識的に先送り)

決定済みだが、運用後の見直し対象。今は MVP の本質ではないため簡易実装。

### D-1: archived_flag 更新をバッチ処理に移行

**現状の実装** (§Decision §6): アーティストページの GET 副作用として
`last_action_at` / `archived_flag` を UPDATE。

**将来の改善**: 日次バッチで全 user_follows をスキャンして archived_flag を再計算。
GET 副作用を排除し REST 原則に沿う設計に移行。

**先送りの理由**:
- 個人利用規模では GET 副作用の問題 (キャッシュ、リトライ、性能) はほぼ起きない
- バッチ実装は APScheduler ジョブ追加が必要、MVP 完成を優先
- 本質的な体験 (時間が編集者になる) は GET 副作用でもバッチでも変わらない

**移行のトリガー**: クラウドデプロイ、複数ユーザー対応、キャッシュ層導入のいずれか

---

# Appendix D: Open Questions

実装中・運用中に判断するもの。

| 項目 | 判断時期 |
|---|---|
| アーカイブ解除タイミング (自動 vs 確認) | 実装中 |
| 公演メモの編集タイミング (強制 vs 任意) | 実装中 |
| want list の表示順 (追加日 / 発売年 / 優先度) | 実装中 |
| 過去公演手動追加 UI の作り込み度 | PR-6 着手時 |
| 複数ユーザー時の concerts マスタ共有範囲 | Phase 6 |
| LLM 提案の明示的リクエスト型 | 数年後 |
| ニュース機能の Phase 2 での扱い | 運用後 |

---

# Consequences

### Positive
- 設計思想が一貫 (Feed / ピン / Collection / want list / 公演体験すべて同じ思想)
- 複数ユーザー対応の伏線 (user_follows, user_concert_attendances)
- マスタの責務が守られる (artists, concerts)
- 実装がシンプル (アルゴリズムなし、派生クエリ)
- 物質感が保たれる (Home は所有のみ)
- アーティストページが体験の交差点
- 時間が淘汰の主体 (SNS とは違う時間感覚)

### Negative
- 「便利な発見」が減る (アルゴリズム推薦の便利さは失う)
- 手動運用の負荷 (5 人選び、want / 公演メモの手入力)
- テーブル変更 4 件 (migration が必要)
- GET の副作用 (D-1 で先送り)

### Neutral
- want list / 過去公演記録で行数増加するが性能影響なし