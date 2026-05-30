"""Records (catalog) + UserCollections (ownership) + RecordFavoriteTracks の
orchestration 層 (ADR-006)。

外側から見た API 表面 (`/api/records`) は ADR-006 §2.5 で response shape を維持する
方針。Service 内部で 3 テーブルを跨いだ flat row を組み立てて `VinylRecordRead` に
詰める。
"""

import datetime as dt
import uuid
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, NotFoundError
from app.core.repositories.artist_repository import ArtistRepository
from app.core.repositories.record_favorite_track_repository import (
    RecordFavoriteTrackRepository,
)
from app.core.repositories.record_repository import RecordRepository
from app.core.repositories.user_collection_repository import UserCollectionRepository
from app.core.repositories.user_follow_repository import UserFollowRepository
from app.models.record import VinylRecord
from app.models.record_favorite_track import RecordFavoriteTrack
from app.models.user_collection import UserCollection
from app.schemas.record import (
    RECORD_STATUS_OWNED,
    RECORD_STATUS_WANTED,
    FavoriteTrack,
    VinylRecordCreate,
    VinylRecordRead,
    VinylRecordUpdate,
)

# `VinylRecordUpdate` のうち catalog 側 (vinyl_records) に属するキー。
# `source='manual'` 行に限って書き込む (ADR-006 §2.5)。
_CATALOG_FIELDS = (
    "title",
    "image_url",
    "original_release_date",
    "artist_id",
    "spotify_album_id",
    "source",
)
# `VinylRecordUpdate` のうち ownership 側 (user_collections) に属するキー。
# `is_pinned` は寛容 PUT で is_pinned だけ送るパターンを意図しているが、
# pinned_at は service が自動セットするので `_COLLECTION_FIELDS` には含めない。
_COLLECTION_FIELDS = (
    "status",
    "pressing_info",
    "purchase_date",
    "purchase_store",
    "purchase_price",
    "purchase_currency",
    "rating",
    "memo",
    "display_order",
    "is_pinned",
)

# Home プレビュー (PC 8 / モバイル 6) に何を見せるか をユーザが選ぶ手段。
# 上限は PC プレビュー数に合わせる。モバイル側でもこの上限を共有し、
# 表示はクライアント側で先頭 6 件に切る (UserCollection の order_by が
# is_pinned DESC, display_order ASC なので先頭 6 件は自動的に pin 優先になる)。
_PIN_LIMIT = 8


def _today_jst() -> dt.date:
    # purchase_date のデフォルト/wanted→owned 遷移時の自動打刻に使う。
    # サーバ側で TZ を固定することで、ユーザのブラウザ TZ に依存させない。
    return dt.datetime.now(ZoneInfo("Asia/Tokyo")).date()


class RecordService:
    def __init__(
        self,
        record_repo: RecordRepository,
        collection_repo: UserCollectionRepository,
        favorite_track_repo: RecordFavoriteTrackRepository,
        artist_repo: ArtistRepository,
        follow_repo: UserFollowRepository,
    ) -> None:
        self.record_repo = record_repo
        self.collection_repo = collection_repo
        self.favorite_track_repo = favorite_track_repo
        self.artist_repo = artist_repo
        self.follow_repo = follow_repo

    # ---- queries ----

    def list_for_user(
        self,
        user_id: UUID,
        limit: int | None = None,
        offset: int = 0,
        status: str | None = None,
        sort: str | None = None,
    ) -> tuple[list[VinylRecordRead], int]:
        """user の record 一覧と total を返す。

        `status` で owned/wanted を絞り込み、`sort` で並び替える (ADR-013)。
        limit を渡すと paginated。`total` は `status` 絞り込み後の全件数なので、
        フロント側で `Math.ceil(total / limit)` でページ数を出せる。
        """
        rows = self.collection_repo.list_for_user_with_catalog(
            user_id, limit=limit, offset=offset, status=status, sort=sort
        )
        favorites_map = self.favorite_track_repo.list_by_collection_ids([c.id for c, _ in rows])
        items = [self._to_read(c, vr, favorites_map.get(c.id, [])) for c, vr in rows]
        total = self.collection_repo.count_for_user(user_id, status=status)
        return items, total

    def count_owned_by_artist_for_user(self, user_id: UUID) -> dict[str, int]:
        return self.collection_repo.count_owned_by_artist_for_user(user_id)

    # ---- commands ----

    def create(self, data: VinylRecordCreate, user_id: UUID) -> VinylRecordRead:
        """Record を 1 件 catalog + ownership 同時に作る (ADR-006 §3.4)。

        1. catalog 行を find-or-create (`spotify_album_id` 有 → dedup、無 → 新規)
        2. user_collections 行を INSERT (display_order を advisory lock 下で採番)
        3. auto-follow (record があるアーティストは自動でフォロー)
        4. favorite_tracks があれば置換

        UNIQUE(user_id, vinyl_record_id) 違反は 409 (既に同じ catalog 行を所有)。
        """
        self._ensure_artist_exists(data.artist_id)

        catalog = self._find_or_create_catalog(data)

        # display_order を user 単位で直列化
        self.collection_repo.lock_for_display_order(user_id)
        next_order = self.collection_repo.max_display_order_for_user(user_id) + 1
        now = dt.datetime.now(dt.UTC)
        # purchase_date は「登録 = 購入」を既定にする。owned で未指定なら今日 (JST)。
        # wanted はまだ買っていない状態なので、明示値が来ても None に強制する。
        if data.status == RECORD_STATUS_WANTED:
            purchase_date: dt.date | None = None
        else:
            purchase_date = data.purchase_date if data.purchase_date is not None else _today_jst()
        collection = UserCollection(
            user_id=user_id,
            vinyl_record_id=catalog.id,
            status=data.status,
            pressing_info=data.pressing_info,
            purchase_date=purchase_date,
            purchase_store=data.purchase_store,
            purchase_price=data.purchase_price,
            purchase_currency=data.purchase_currency,
            rating=data.rating,
            memo=data.memo,
            display_order=next_order,
            created_at=now,
            updated_at=now,
        )
        try:
            saved_collection = self.collection_repo.add(collection)
        except IntegrityError as exc:
            self.collection_repo.session.rollback()
            raise ConflictError(f"already in collection: vinyl_record_id={catalog.id}") from exc

        # auto-follow: record があるアーティストは自動でフォロー対象に
        self.follow_repo.upsert(user_id, catalog.artist_id)

        if data.favorite_tracks is not None:
            self._set_favorite_tracks(saved_collection.id, data.favorite_tracks)

        favs = self.favorite_track_repo.list_for_collection(saved_collection.id)
        return self._to_read(saved_collection, catalog, favs)

    def update_partial(
        self, id: uuid.UUID, patch: VinylRecordUpdate, user_id: UUID
    ) -> VinylRecordRead:
        """User 単位で part-update。

        - ownership 系フィールド: 常に user_collections に反映
        - catalog 系フィールド: `source='manual'` の時のみ反映。`source='spotify'`
          は他 user と共有しているので silently ignore (ADR-006 §2.5)
        - `spotify_album_id` を埋め直すリクエストは manual→spotify promote 経路
          (ADR-006 §2.9)。他 user が同じ Spotify 行を既に持っていれば
          user_collections の `vinyl_record_id` を付け替える
        - `favorite_tracks` が patch に含まれていれば全置換
        """
        collection = self.collection_repo.get_for_user(id, user_id)
        if collection is None:
            raise NotFoundError(f"user_collection id={id}")
        catalog = self.record_repo.get(collection.vinyl_record_id)
        if catalog is None:
            # FK ON DELETE CASCADE で本来あり得ないが safety net。
            raise NotFoundError(f"vinyl_record id={collection.vinyl_record_id}")

        patch_data = patch.model_dump(exclude_unset=True)

        # wanted → owned 遷移時に「買った日 = 今日」を自動打刻するための前置判定。
        # patch に明示的な purchase_date が含まれていればそちらを優先 (ユーザの過去日
        # 補正を尊重)。既存値が残っていれば preserve (履歴を上書きしない)。
        was_wanted_to_owned = (
            "status" in patch_data
            and patch_data["status"] == RECORD_STATUS_OWNED
            and collection.status == RECORD_STATUS_WANTED
        )

        # is_pinned の False→True 遷移時のみ上限 (_PIN_LIMIT) を enforce。
        # 既に True の collection を再度 True で送るのは no-op。
        # `pinned_at` は True 時に now()、False 時に None を自動セット。
        # `pin_order` は drag & drop の並び順 (RecordsAllModal で書き換える)。
        # 新規 pin 時に「末尾 = max(pin_order)+1」で採番する。unpin 時は NULL。
        if "is_pinned" in patch_data:
            new_pinned = bool(patch_data["is_pinned"])
            if new_pinned and not collection.is_pinned:
                if self.collection_repo.count_pinned_for_user(user_id) >= _PIN_LIMIT:
                    raise ConflictError(f"pin limit exceeded: max {_PIN_LIMIT}")
                collection.pinned_at = dt.datetime.now(dt.UTC)
                collection.pin_order = self.collection_repo.max_pin_order_for_user(user_id) + 1
            elif not new_pinned and collection.is_pinned:
                collection.pinned_at = None
                collection.pin_order = None

        # 1) collection 系フィールド
        for key in _COLLECTION_FIELDS:
            if key in patch_data:
                setattr(collection, key, patch_data[key])

        # wanted→owned 遷移で purchase_date が未指定/null のままなら今日 (JST) で埋める。
        # 明示 patch があれば上の loop で既に反映されているので、ここでは触らない。
        if (
            was_wanted_to_owned
            and "purchase_date" not in patch_data
            and collection.purchase_date is None
        ):
            collection.purchase_date = _today_jst()

        # 2) catalog 系フィールド (manual のみ書く、promote 経路を吸収)
        catalog_changes = {k: patch_data[k] for k in _CATALOG_FIELDS if k in patch_data}
        if catalog_changes and catalog.source == "manual":
            catalog, collection = self._apply_catalog_changes(catalog, collection, catalog_changes)

        collection.updated_at = dt.datetime.now(dt.UTC)
        try:
            saved_collection = self.collection_repo.save(collection)
        except IntegrityError as exc:
            self.collection_repo.session.rollback()
            raise ConflictError(
                f"already in collection: vinyl_record_id={collection.vinyl_record_id}"
            ) from exc

        # 3) favorite_tracks (omit → no-op、`[]` 明示 → 全削除)
        if "favorite_tracks" in patch_data:
            self._set_favorite_tracks(saved_collection.id, patch.favorite_tracks or [])

        favs = self.favorite_track_repo.list_for_collection(saved_collection.id)
        return self._to_read(saved_collection, catalog, favs)

    def reorder_pins(self, user_id: UUID, ordered_ids: list[uuid.UUID]) -> None:
        """drag & drop でユーザが並び替えた pin 一覧を 1..N で再採番する。

        - `ordered_ids` は user のピン済み行 (`is_pinned=True`) の id を「並べたい
          順序」で並べたリスト。
        - リクエストが現在のピン済みセットと一致しない (欠け / 多い / 他 user の
          id が混ざる) 場合は `ConflictError` を返す。 pinning 操作と reorder が
          競合 (1 件外した直後の reorder 等) して状態がズレた時の安全弁。
        - 採番は `1..len(ordered_ids)` に書き換える。`pinned_at` は触らない。
        """
        current = self.collection_repo.list_pinned_for_user(user_id)
        current_ids = {c.id for c in current}
        requested_ids = set(ordered_ids)
        if current_ids != requested_ids or len(ordered_ids) != len(requested_ids):
            raise ConflictError(
                "pin reorder mismatch: request must include exactly the currently pinned ids"
            )

        by_id = {c.id: c for c in current}
        now = dt.datetime.now(dt.UTC)
        for new_order, cid in enumerate(ordered_ids, start=1):
            row = by_id[cid]
            if row.pin_order != new_order:
                row.pin_order = new_order
                row.updated_at = now
                self.collection_repo.save(row)

    def delete(self, id: uuid.UUID, user_id: UUID) -> None:
        """user_collections を物理削除。`record_favorite_tracks` は CASCADE、
        `vinyl_records` (catalog) は触らない (ADR-006 §2.7)。"""
        collection = self.collection_repo.get_for_user(id, user_id)
        if collection is None:
            raise NotFoundError(f"user_collection id={id}")
        self.collection_repo.delete(collection)

    # ---- helpers ----

    def _find_or_create_catalog(self, data: VinylRecordCreate) -> VinylRecord:
        if data.spotify_album_id is not None:
            existing = self.record_repo.find_by_spotify_album_id(data.spotify_album_id)
            if existing is not None:
                return existing
        now = dt.datetime.now(dt.UTC)
        return self.record_repo.add(
            VinylRecord(
                artist_id=data.artist_id,
                spotify_album_id=data.spotify_album_id,
                source=data.source,
                title=data.title,
                image_url=data.image_url,
                original_release_date=data.original_release_date,
                created_at=now,
                updated_at=now,
            )
        )

    def _apply_catalog_changes(
        self,
        catalog: VinylRecord,
        collection: UserCollection,
        changes: dict,
    ) -> tuple[VinylRecord, UserCollection]:
        """ADR-006 §2.9: manual→spotify promote と通常 manual 編集を分岐。

        `spotify_album_id` を新たに埋めるリクエストは promote 経路。他 user が
        既に catalog 化していれば collection の `vinyl_record_id` を付け替え、
        元の manual catalog は orphan として残す (§2.7)。
        """
        now = dt.datetime.now(dt.UTC)
        new_spotify_id = changes.get("spotify_album_id")
        promote = new_spotify_id is not None and new_spotify_id != catalog.spotify_album_id
        if promote:
            assert new_spotify_id is not None  # narrow for type checker
            existing = self.record_repo.find_by_spotify_album_id(new_spotify_id)
            if existing is not None and existing.id != catalog.id:
                # 他 user の catalog 行に乗り換え。元の manual 行は orphan。
                collection.vinyl_record_id = existing.id
                return existing, collection
            # 既存無し → 自分の manual 行を spotify catalog に昇格
            catalog.spotify_album_id = new_spotify_id
            catalog.source = changes.get("source", "spotify")
        for key in ("title", "image_url", "original_release_date", "artist_id"):
            if key in changes:
                if key == "artist_id" and changes[key] != catalog.artist_id:
                    self._ensure_artist_exists(changes[key])
                setattr(catalog, key, changes[key])
        catalog.updated_at = now
        saved_catalog = self.record_repo.save(catalog)
        return saved_catalog, collection

    def _set_favorite_tracks(
        self, user_collection_id: uuid.UUID, tracks: list[FavoriteTrack]
    ) -> None:
        models = [
            RecordFavoriteTrack(
                user_collection_id=user_collection_id,
                position=i,
                spotify_track_id=t.spotify_track_id,
                track_name=t.track_name,
                note=t.note,
            )
            for i, t in enumerate(tracks)
        ]
        try:
            self.favorite_track_repo.replace_for_collection(user_collection_id, models)
        except IntegrityError as exc:
            self.favorite_track_repo.session.rollback()
            raise ConflictError("duplicate spotify_track_id in favorite_tracks") from exc

    def _ensure_artist_exists(self, artist_id: str) -> None:
        if self.artist_repo.get(artist_id) is None:
            raise NotFoundError(f"artist spotify_id={artist_id}")

    def _to_read(
        self,
        collection: UserCollection,
        catalog: VinylRecord,
        favs: list[RecordFavoriteTrack],
    ) -> VinylRecordRead:
        return VinylRecordRead(
            id=collection.id,
            artist_id=catalog.artist_id,
            spotify_album_id=catalog.spotify_album_id,
            source=catalog.source,  # type: ignore[arg-type]
            status=collection.status,  # type: ignore[arg-type]
            title=catalog.title,
            image_url=catalog.image_url,
            original_release_date=catalog.original_release_date,
            pressing_info=collection.pressing_info,
            purchase_date=collection.purchase_date,
            purchase_store=collection.purchase_store,
            purchase_price=collection.purchase_price,
            purchase_currency=collection.purchase_currency,
            rating=collection.rating,
            memo=collection.memo,
            favorite_tracks=[
                FavoriteTrack(
                    spotify_track_id=f.spotify_track_id,
                    track_name=f.track_name,
                    note=f.note,
                )
                for f in favs
            ],
            display_order=collection.display_order,
            is_pinned=collection.is_pinned,
            pin_order=collection.pin_order,
            created_at=collection.created_at,
            updated_at=collection.updated_at,
        )
