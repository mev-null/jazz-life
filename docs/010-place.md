# ADR-010: 場所マスタと訪問体験の設計

**Status**: Proposed | **Date**: 2026-05-11
**Related**: ADR-001, ADR-002, ADR-003 (アーティスト管理), vision.md

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

## 1.1 このADRが追加するもの

ジャズの体験は、レコードを聴くことや公演に行くことだけではない。
**ジャズ喫茶やジャズバーで、マスターが選んだ 1 枚と出会う体験** こそ、
アルゴリズムでは決して起こせない種類の出会いである。

このADRは、その体験をアプリ内に取り込むための設計を定義する。

vision.md の核:
> コンテキストとして好きな本、音楽、場所を **溜めていって**、そこから新たな提案をもらう

vision.md は「場所」を Phase 3 の機能として描いていたが、ジャズ体験における場所の重要性、
そして「場所がレコード・アーティストとの出会いを生む」という体験の本質を踏まえ、
**ジャズ喫茶・ジャズバーに限定して** MVP 段階で先取り実装する。

## 1.2 場所機能の3つの設計原則

### 原則 1: 訪問が中心にある

場所そのものは抽象的な情報 (名前、住所、開閉店)。
**意味を持つのは「いつ、どんな状況でその場所に行ったか」という訪問体験**。

「メグで Bill Evans を聴いた」という記録の核は、メグという店ではなく、
**ある日のメグ訪問の中で Bill Evans に出会った** という時空間の出来事。

データモデルは訪問 (visits) を中心に据える。場所とレコード・アーティストの
リレーションは「訪問を介して」のみ表現する。

### 原則 2: シードしない、訪問が場所を作る

アーティストには「誰でも知っている定番」が存在し、100 人シードする意味がある (ADR-003)。
だが場所は違う。**ユーザーが実際に足を運んだ店だけが、そのユーザーにとって意味を持つ**。

「東京の有名なジャズ喫茶 30 軒」を事前に並べても、それは単なる情報。
このアプリでは、**訪問という行為が場所をアプリ内に存在させる**。

### 原則 3: 出会いは訪問の中で起きる、レコードの属性ではない

「Bill Evans の Kind of Blue に出会った」のは、ある日のある店での出来事。
それは Kind of Blue というレコードの属性ではなく、**訪問という出来事の中の出来事**。

なので出会いの記録は visits を介する別テーブル (`visit_record_discoveries`,
`visit_artist_discoveries`) として独立させる。既存の `vinyl_records` や
`user_follows` には触らない。

これにより:
- 「複数の店で同じレコードに再会した」が記録できる
- 「マスターと話していてアーティストを教わったが、その日は曲を聴かなかった」が記録できる
- レコードと出会いの責務が分離される

## 1.3 拡張される体験のライフサイクル

ADR-003 で確立した体験のライフサイクルに、場所が追加される:

```
[訪問]    ジャズ喫茶「メグ」に行く
   ↓
[出会い]   マスターがかけた Bill Evans の "Sunday at the Village Vanguard" に心を奪われる
            → visit に memo を記録、visit_record_discovery で出会いを記録
   ↓
[興味の表明]   want list に追加 (ADR-003 の動線へ合流)
   ↓
[行動]    後日レコード屋でオリジナル盤を探す
   ↓
[所有]    手に入れて、Home のマトリクスに加わる
   ↓
(数年後)
[振り返り]   レコードを開くと「メグの2026/5/11の訪問で出会った」が見える
            メグのページを開くと「この店で出会ったレコード」が並ぶ
```

vision.md の Phase 4「時系列での文脈の振り返り」がここで実装される。
**場所はアプリの中で、過去と現在を繋ぐアンカーになる**。

## 1.4 この機能で表現したい体験

- 「あの店で初めて聴いたあの曲」が永久に残る
- 「マスターから教わったあのアーティスト」が記録される
- 行きつけの店は訪問回数として自然に蓄積される
- 閉店した店も含めて、自分のジャズ人生の地図ができる

これは SNS の「チェックイン」とは違う。誰かに見せるためではなく、
**自分が未来の自分に渡すための記録**である。

---

# Part 2: Specification

## 2.1 データモデル一覧

| テーブル | 役割 |
|---|---|
| `places` | 場所マスタ (ジャズ喫茶・バー、ユーザー手動追加のみ) |
| `visits` | 訪問記録 (時空間の交差点) |
| `visit_record_discoveries` | 訪問で出会ったレコードの記録 |
| `visit_artist_discoveries` | 訪問で出会ったアーティストの記録 |

### places

```python
class Place(SQLModel, table=True):
    __tablename__ = "places"

    id: UUID = Field(default_factory=uuid6.uuid7, primary_key=True)
    name: str = Field(max_length=200, index=True)
    type: str = Field(max_length=20)
    # MVP: "jazz_kissa" | "jazz_bar"
    # Phase 3+ で "literary_cafe" 等が追加される可能性
    city: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=2000)
    # 場所そのものへの自由記述 (「マスターは○○さん」「2階の窓際が良い」等)
    closed_at: date | None = Field(default=None)
    # 閉店した店も記録できるように
    source: str = Field(default="manual", max_length=20)
    # MVP は "manual" のみ。Phase 3+ で "places_api" 等が増える可能性
    added_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
```

シードなし、ユーザー手動追加のみ。

### visits

```python
class Visit(SQLModel, table=True):
    __tablename__ = "visits"

    id: UUID = Field(default_factory=uuid6.uuid7, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    place_id: UUID = Field(foreign_key="places.id", ondelete="RESTRICT", index=True)
    visited_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    memo: str | None = Field(default=None, max_length=2000)
    # その訪問の自由記述 (誰と行った、何を聴いた、マスターとの会話、印象)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
```

place 削除は RESTRICT (訪問履歴を保護)。
複数回訪問は visits の複数エントリとして自然に表現される。

### visit_record_discoveries

```python
class VisitRecordDiscovery(SQLModel, table=True):
    __tablename__ = "visit_record_discoveries"

    visit_id: UUID = Field(
        foreign_key="visits.id",
        ondelete="CASCADE",
        primary_key=True,
    )
    record_id: UUID = Field(
        foreign_key="vinyl_records.id",
        ondelete="CASCADE",
        primary_key=True,
    )
    memo: str | None = Field(default=None, max_length=2000)
    # この出会いに特化したメモ (「3曲目が特に良かった」「45回転盤を聴いた」等)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
```

複合 PK で同一訪問内の重複登録を防止。
**前提**: 出会ったレコードは vinyl_records に存在している必要がある。
出会った時点で wanted として登録され、後日 owned に遷移する流れ。

### visit_artist_discoveries

```python
class VisitArtistDiscovery(SQLModel, table=True):
    __tablename__ = "visit_artist_discoveries"

    visit_id: UUID = Field(
        foreign_key="visits.id",
        ondelete="CASCADE",
        primary_key=True,
    )
    artist_id: str = Field(
        foreign_key="artists.spotify_id",
        ondelete="CASCADE",
        primary_key=True,
        max_length=64,
    )
    memo: str | None = Field(default=None, max_length=2000)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
```

レコードの出会いと別管理する理由 (§Rationale §2 参照):
- レコードの出会い = 曲・盤・ジャケットへの接触
- アーティストの出会い = 人・名前・存在への接触
- 両方同時に起きることも、別々に起きることもある

## 2.2 主要動線

### 動線 1: 場所マスタへの追加

ユーザーが新しい場所を訪れる前後で:

```
[場所追加 UI]
  名前: メグ
  種別: ジャズ喫茶
  都市: 吉祥寺
  住所: 自由記述
  メモ: 任意 (店全体の印象、行き方の覚え書き)
   ↓
POST /api/places で places にエントリ作成
```

### 動線 2: 訪問記録の作成

```
[訪問追加 UI]
  場所: メグ (検索 or 新規追加)
  訪問日時: 2026/5/11 19:30
  メモ: 自由記述
   ↓
POST /api/users/me/visits
```

### 動線 3: 訪問内での出会い記録

訪問記録の中から、出会ったレコード/アーティストを追加:

```
[訪問詳細ページ]
  メグ, 2026/5/11
  memo: "マスターと Bill Evans の話で盛り上がった..."

  📀 この訪問で出会ったレコード
    [♡ レコードを追加] ボタン
     ↓
    アーティスト検索 → アルバム検索 → 選択
     ↓
    vinyl_records に status='wanted' で INSERT (まだ持っていないので)
    visit_record_discoveries にエントリ作成

  🎤 この訪問で出会ったアーティスト
    [♡ アーティストを追加] ボタン
     ↓
    アーティスト検索 (マスタ + Spotify 動的)
     ↓
    user_follows に INSERT (まだフォローしていなければ)
    visit_artist_discoveries にエントリ作成
```

### 動線 4: 場所ページからの振り返り

```
[場所ページ: メグ]

📍 メグ (吉祥寺・ジャズ喫茶)
住所: ...
全体メモ: ...

📅 訪問履歴 (12 回)
  ・2026/5/11 - "Bill Evans の話で盛り上がった..."
  ・2026/3/2  - "雨の日、客は自分だけ..."
  ・2025/12/24 - ...

📀 この店で出会ったレコード (8 枚)
  ジャケットグリッド (visit_record_discoveries 経由で集約)

🎤 この店で出会ったアーティスト (5 人)
```

### 動線 5: レコード/アーティストページからの逆引き

ADR-003 で定義したアーティストページに、出会いの情報セクションが追加される:

```
[アーティストページ: Bill Evans]

... (既存セクション: 所有レコード、欲しいレコード、Feed)

🎯 このアーティストとの出会い
  ・2026/5/11 メグで出会った
  ・2025/8/17 DUG でも会話に出た
```

レコード詳細ページにも同様:

```
[レコード裏面 (フリップ)]

... (既存: 購入情報、メモ、評価)

🎯 このレコードとの出会い
  ・2026/5/11 メグで聴いた
```

## 2.3 API 一覧

### places

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/api/places` | 一覧 (検索 q=, type=) |
| GET | `/api/places/{id}` | 詳細 (訪問履歴 + 出会い集約付き) |
| POST | `/api/places` | 場所追加 |
| PUT | `/api/places/{id}` | 編集 |
| DELETE | `/api/places/{id}` | 削除 (訪問記録があれば 409) |

### visits

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/api/users/me/visits` | 自分の訪問一覧 (時系列、place_id フィルタ可) |
| GET | `/api/users/me/visits/{id}` | 訪問詳細 (出会い記録含む) |
| POST | `/api/users/me/visits` | 訪問記録作成 |
| PUT | `/api/users/me/visits/{id}` | 編集 (memo, visited_at) |
| DELETE | `/api/users/me/visits/{id}` | 削除 |

### 出会いの記録

| メソッド | パス | 用途 |
|---|---|---|
| POST | `/api/users/me/visits/{id}/record-discoveries` | レコードとの出会いを記録 |
| DELETE | `/api/users/me/visits/{visit_id}/record-discoveries/{record_id}` | 解除 |
| POST | `/api/users/me/visits/{id}/artist-discoveries` | アーティストとの出会いを記録 |
| DELETE | `/api/users/me/visits/{visit_id}/artist-discoveries/{artist_id}` | 解除 |

### 場所統合 API (詳細ページ用)

```python
GET /api/places/{id}/detail

class PlaceDetailResponse(BaseModel):
    place: PlaceRead
    visit_count: int
    recent_visits: list[VisitRead]  # 直近 10 件
    discovered_records: list[VinylRecordRead]  # この店で出会ったレコード集約
    discovered_artists: list[ArtistRead]  # この店で出会ったアーティスト集約
```

---

# Part 3: Implementation Plan

## 3.1 PR 分割

ADR-003 の PR-1〜9 の後に続く形:

| # | 内容 | 主な変更 |
|---|---|---|
| **PR-10** | places + visits テーブル (Alembic migration) | テーブル新規作成 |
| **PR-11** | places API | CRUD、検索 |
| **PR-12** | visits API | 訪問記録 CRUD |
| **PR-13** | 出会い記録 API (record / artist discoveries) | 訪問内での出会い登録 |
| **PR-14** | 場所統合 API + 逆引き API | place detail、レコード/アーティストからの逆引き |
| **PR-15** | フロント実装 | 場所ページ、訪問追加 UI、既存ページへの統合 |

## 3.2 PR-10: Migration スクリプト

```python
# alembic/versions/xxxx_places_and_visits.py
def upgrade():
    op.create_table(
        'places',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('type', sa.String(20), nullable=False),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('address', sa.String(300), nullable=True),
        sa.Column('note', sa.String(2000), nullable=True),
        sa.Column('closed_at', sa.Date(), nullable=True),
        sa.Column('source', sa.String(20), server_default='manual', nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_places_name', 'places', ['name'])

    op.create_table(
        'visits',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('place_id', sa.UUID(), sa.ForeignKey('places.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('visited_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('memo', sa.String(2000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_visits_user_id', 'visits', ['user_id'])
    op.create_index('ix_visits_place_id', 'visits', ['place_id'])
    op.create_index('ix_visits_visited_at', 'visits', ['visited_at'])

    op.create_table(
        'visit_record_discoveries',
        sa.Column('visit_id', sa.UUID(),
                  sa.ForeignKey('visits.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('record_id', sa.UUID(),
                  sa.ForeignKey('vinyl_records.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('memo', sa.String(2000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        'visit_artist_discoveries',
        sa.Column('visit_id', sa.UUID(),
                  sa.ForeignKey('visits.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('artist_id', sa.String(64),
                  sa.ForeignKey('artists.spotify_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('memo', sa.String(2000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
```

## 3.3 主要コードパターン

### パターン A: 訪問記録の作成

```python
# services/visit_service.py
def create(self, user_id: UUID, data: VisitCreate) -> Visit:
    # place の存在確認
    if not self.place_repo.exists(data.place_id):
        raise NotFoundError(f"place not found: {data.place_id}")

    visit = Visit(
        user_id=user_id,
        place_id=data.place_id,
        visited_at=data.visited_at,
        memo=data.memo,
    )
    return self.visit_repo.add(visit)
```

### パターン B: 訪問内での出会い記録 (レコード)

```python
# services/discovery_service.py
def add_record_discovery(
    self, user_id: UUID, visit_id: UUID, record_id: UUID, memo: str | None
) -> VisitRecordDiscovery:
    # 訪問の所有者チェック
    visit = self.visit_repo.get(visit_id)
    if not visit or visit.user_id != user_id:
        raise NotFoundError(f"visit not found: {visit_id}")

    # レコードの所有者チェック
    record = self.record_repo.get(record_id)
    if not record:
        raise NotFoundError(f"record not found: {record_id}")
    # vinyl_records.user_id があれば user_id チェックも

    # 既存チェック (複合 PK の衝突防止)
    if self.discovery_repo.exists_record(visit_id, record_id):
        raise DomainError("既に登録済みの出会いです")

    discovery = VisitRecordDiscovery(
        visit_id=visit_id,
        record_id=record_id,
        memo=memo,
    )
    return self.discovery_repo.add_record(discovery)
```

### パターン C: 場所統合 API (逆引き集約)

```python
# services/place_service.py
def get_detail(self, place_id: UUID, user_id: UUID) -> PlaceDetailResponse:
    place = self.repo.get(place_id)
    if not place:
        raise NotFoundError(f"place not found: {place_id}")

    visit_count = self.visit_repo.count_for_place(user_id, place_id)
    recent_visits = self.visit_repo.list_for_place(user_id, place_id, limit=10)

    # この場所で出会ったレコード (visit_record_discoveries を visits 経由で集約)
    discovered_records = self._aggregate_discovered_records(user_id, place_id)
    discovered_artists = self._aggregate_discovered_artists(user_id, place_id)

    return PlaceDetailResponse(
        place=place,
        visit_count=visit_count,
        recent_visits=recent_visits,
        discovered_records=discovered_records,
        discovered_artists=discovered_artists,
    )

def _aggregate_discovered_records(
    self, user_id: UUID, place_id: UUID
) -> list[VinylRecord]:
    stmt = (
        select(VinylRecord)
        .join(VisitRecordDiscovery, VinylRecord.id == VisitRecordDiscovery.record_id)
        .join(Visit, VisitRecordDiscovery.visit_id == Visit.id)
        .where(Visit.user_id == user_id, Visit.place_id == place_id)
        .distinct()
        .order_by(VisitRecordDiscovery.created_at.desc())
    )
    return list(self.session.exec(stmt).all())
```

### パターン D: レコードからの逆引き (どこで出会ったか)

```python
# services/record_service.py の get_detail に追加
def list_discoveries_for_record(
    self, user_id: UUID, record_id: UUID
) -> list[VisitWithPlaceRead]:
    """このレコードに出会った訪問の一覧"""
    stmt = (
        select(Visit, Place)
        .join(VisitRecordDiscovery, Visit.id == VisitRecordDiscovery.visit_id)
        .join(Place, Visit.place_id == Place.id)
        .where(
            VisitRecordDiscovery.record_id == record_id,
            Visit.user_id == user_id,
        )
        .order_by(Visit.visited_at.desc())
    )
    return [
        VisitWithPlaceRead(visit=visit, place=place)
        for visit, place in self.session.exec(stmt).all()
    ]
```

## 3.4 既存設計との接続点

ADR-003 で定義した既存 API への追加:

### アーティストページ統合 API への拡張

```python
class ArtistDetailResponse(BaseModel):
    # ... 既存フィールド (ADR-003 §3.4)
    discovery_visits: list[VisitWithPlaceRead]  # 追加
    # このアーティストに出会った訪問の一覧
```

### レコード詳細への拡張

```python
class VinylRecordDetailResponse(BaseModel):
    record: VinylRecordRead
    discovery_visits: list[VisitWithPlaceRead]  # 追加
    # このレコードに出会った訪問の一覧
```

---

# Appendix A: Rationale

### §1. なぜ場所機能を MVP に取り込むか

vision.md では Phase 3 だったが、ジャズの体験における場所の重要性、特に
「店での出会いがレコード収集の起点になる」体験の本質を考えると、後回しにすると
体験のライフサイクル (Feed → Collection) に「店」というアンカーが欠けたままになる。

「ジャズ喫茶・バー」に限定することで、Phase 3 全体 (文学カフェ、テラスカフェ等) を
一気に作る必要はなく、ジャズ体験の核を補完する形で先取りできる。

### §2. なぜレコードとアーティストの出会いを別テーブルにするか

両者は性質が異なる:

- **レコードの出会い**: 「曲・盤・ジャケットへの接触」。具体的なアルバムを聴いた、ジャケットを見た。
- **アーティストの出会い**: 「人・名前・存在への接触」。マスターから名前を教わった、別のアーティストとの繋がりで知った。

両方同時に起きることもある (「Bill Evans の Kind of Blue を聴いて、Bill Evans を知った」)。
だが別々に起きることも多い:
- 「マスターと話していてある人を教わったが、その日は曲を聴かなかった」 → アーティストのみ
- 「ジャケットだけ見せてもらって心に残ったが、アーティストの他作品は知らない」 → レコードのみ

別テーブルにすることで、それぞれの体験を独立に記録できる。

### §3. なぜ既存テーブル (vinyl_records, user_follows) に discovered_at_visit_id を持たせないか

候補:
- (a) `vinyl_records.discovered_at_visit_id` カラム追加
- (b) 出会いはあくまで visit_*_discoveries に独立して持つ

(b) を採用する理由:

**(a) は責務違反**

`vinyl_records` は所有・興味の状態を表すマスタ的なもの。
出会いという時間的イベントを混ぜると、レコードの本質と関係ない情報がカラムとして肥大化する。

**複数の出会いを表現できる**

(a) だと「最初の出会い 1 件」しか記録できない。
(b) なら「メグで初めて聴いて、後日 DUG でも会話に出た」という複数の出会いを記録可能。
これは振り返り体験として大事。

**逆引きが対称的**

(b) なら:
- 場所 → 出会ったレコード一覧 (visits 経由)
- レコード → 出会った場所一覧 (visit_record_discoveries 経由)

どちらも JOIN で取れる対称な設計になる。

### §4. なぜシードしないか、訪問が場所を作るか

アーティストは「誰でも知っている」共通言語として 100 人シードする意味がある (ADR-003)。
だが場所は違う。**ユーザーが実際に足を運んだ店だけが、そのユーザーにとって意味を持つ**。

「東京の有名なジャズ喫茶 30 軒」を事前に並べても:
- 行ったことがない店は単なる情報、訪問データに紐づかない
- 「行きたい店リスト」と「行った店リスト」の区別が必要になる (複雑化)
- 「個人記録」の場所感が薄れる

**訪問という行為が場所をアプリ内に存在させる** ことで、
- データが必要最小限になる (実際に意味を持つ店だけ)
- 訪問前のリサーチは外部 (Google マップ、口コミ等) で済む
- アプリは「行った後の記録」に専念できる

### §5. なぜ訪問を中心に据えるか (visits を噛ませる)

候補:
- (a) places と vinyl_records/artists を直接リレーション
- (b) visits を介してリレーション

(b) を採用する理由:

**出会いは訪問の中で起きる、抽象的な場所ではなく**

「メグで Bill Evans に出会った」というのは抽象的な記録ではなく、
「2026/5/11 のメグ訪問で、マスターと Bill Evans の話で盛り上がった時に出会った」という
**特定の時空間の出来事**。

(a) だと「メグで出会った」しか残せず、いつ・どんな状況で、が抜け落ちる。

**訪問履歴型と整合する**

複数回訪問を毎回記録する方針 (今回の判断) と、visits を中心にする設計は自然に一致する。
それぞれの訪問が独立した記憶として残る。

**「いつもの店」と「初訪問の店」が同じ構造で扱える**

行きつけは訪問が 100 回、初訪問は 1 回。
どちらも visits テーブルにエントリされる。
「お気に入り度合い」は訪問回数として行動の蓄積で表現される。
フラグや評価で表現するより自然。

### §6. なぜ closed_at カラムを持つか

ジャズ喫茶・バーは時代とともに閉店する。Body & Soul のように長年愛された店も閉店する。
**閉店した店の記憶も大切な人生の一部** であり、削除するのではなく `closed_at` で記録する。

これにより:
- 過去の訪問記録は残り続ける
- 場所一覧で「閉店」表示ができる
- 振り返り時に「閉店した思い出の店」が見える

### §7. なぜ type を持つか (MVP で 2 種類だけ)

将来の Phase 3 拡張を見据えて、最初から `type` カラムを持たせる。
MVP では "jazz_kissa" と "jazz_bar" だけ実装する。

Phase 3 で文学カフェ、テラスカフェ、書店等を追加する時、テーブル変更は不要。
type 値を増やすだけで対応できる。

ADR-002 の「マスタを汚さない、責務を分離」原則と整合的。

---

# Appendix B: Alternatives Considered

| 案 | なぜ却下したか |
|---|---|
| 場所と音楽を直接リレーション (visit を介さない) | 出会いの時空間情報が抜け落ちる、複数回の出会いを表現できない |
| vinyl_records に discovered_at_place_id カラム追加 | レコードの責務違反、複数回の出会いを表現できない |
| レコードとアーティストの出会いを 1 テーブルに統合 | 性質が異なる、別々に起きるケースが扱いにくい |
| 場所マスタに 30 件シード | 訪問していない店は意味を持たない、思想と整合しない |
| 場所機能を Phase 3 まで先送り | ジャズ体験の核を補完する機能、後回しにすると Collection に「店」アンカーが欠ける |
| places の type を持たず jazz_venues 専用テーブル | Phase 3 拡張時にマイグレーションコスト |
| 行きたい/行った フラグの 2 値 (公演と同じパターン) | 訪問は継続的な関係、複数回訪問を 1 フラグで表現できない |

---

# Appendix C: Deferred Decisions

### D-1: 場所の検索を Google Places API 等で動的補完

**現状**: 完全に手動で名前・住所を入力。
**将来**: Phase 3 で文学カフェ・テラスカフェ等に拡張する時、検索の利便性のために
Google Places API や類似のサービスとの連携を検討。

**先送りの理由**: MVP では「ジャズ喫茶・バー」に限定し、数十件程度の場所を想定。
手動入力で十分。外部 API 連携はスコープを広げすぎる。

### D-2: 場所のピン留め (行きつけ表現)

**現状**: 行きつけは「訪問回数」で自然に表現される。明示的なピン留めはなし。
**将来**: 場所が増えてきて「お気に入り」「行きつけ」を明示したくなったら検討。

**先送りの理由**: アーティストのピン留めと違い、場所は訪問回数で自然に序列化できる。
当面は不要。

### D-3: 場所の地図表示

**現状**: 住所はテキストのみ。
**将来**: 訪問場所を地図上にプロットする UI を Phase 3 で。

**先送りの理由**: vision.md の Phase 3 機能。MVP では場所の記録に専念。

---

# Appendix D: Open Questions

| 項目 | 判断時期 |
|---|---|
| 訪問記録時に出会いを必須にするか (訪問だけのエントリも許す?) | 実装中 |
| 場所削除時の挙動 (訪問があれば 409? 警告のみ?) | PR-11 着手時 |
| 過去の訪問を遡って記録する UI の作り込み度 | PR-12 着手時 |
| 複数ユーザー時の places マスタの共有範囲 | Phase 6 |
| Phase 3 拡張時の type 増加に伴う UI 分岐 | Phase 3 |

---

# Consequences

### Positive
- ジャズ文化の核 (店での出会い) がアプリで記録できる
- 体験のライフサイクルに「店」というアンカーが加わる
- vision.md Phase 4 (時系列での文脈の振り返り) の実装
- 場所マスタの責務が綺麗 (シードなし、訪問が場所を作る)
- 出会いの責務分離 (レコードとアーティスト別、vinyl_records は触らない)
- Phase 3 拡張の伏線 (type カラム、places テーブル名)

### Negative
- テーブル 4 つ追加 (places, visits, visit_record_discoveries, visit_artist_discoveries)
- アプリのスコープが「ジャズリスナーのコレクション + Feed」から
  「ジャズライフ全体の母艦」に拡大、実装範囲増
- 場所手動追加の入力 UI が必要 (名前、住所、メモ)
- 訪問記録の入力負荷 (毎回 memo を書くかは任意だが、空でも気になる可能性)

### Neutral
- 訪問データは年に数十件レベル、性能影響なし
- Phase 3 で文学カフェ等を追加する時、places テーブルはそのまま使える