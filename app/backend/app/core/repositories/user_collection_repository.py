import uuid

from sqlalchemy import text
from sqlmodel import Session, col, func, select

from app.models.record import VinylRecord
from app.models.user_collection import UserCollection


class UserCollectionRepository:
    """User の所有関係 (ownership) repository (ADR-006)。

    display_order は user 単位で advisory lock により直列化採番する
    (`pg_advisory_xact_lock(k1, hashtext(user_id::text))`)。
    """

    # 2-arg pg_advisory_xact_lock(int4, int4) は両引数とも int4。bigint 単一引数版とは
    # 別の lock space を使う。`hashtext(user_id)` も int4 を返す。
    _DISPLAY_ORDER_LOCK_KEY = 0x0006_0002

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, id: uuid.UUID) -> UserCollection | None:
        return self.session.get(UserCollection, id)

    def get_for_user(self, id: uuid.UUID, user_id: uuid.UUID) -> UserCollection | None:
        """user_id でガード付き取得。cross-user アクセスを 404 化するための前処理。"""
        stmt = (
            select(UserCollection)
            .where(col(UserCollection.id) == id)
            .where(col(UserCollection.user_id) == user_id)
        )
        return self.session.exec(stmt).first()

    def get_by_user_and_record(
        self, user_id: uuid.UUID, vinyl_record_id: uuid.UUID
    ) -> UserCollection | None:
        """UNIQUE (user_id, vinyl_record_id) を活かした dedup 検索。

        Spotify album が catalog で dedup された後、同じ user が同じ catalog 行を
        2 度 POST した場合のハンドリングに使う。
        """
        stmt = (
            select(UserCollection)
            .where(col(UserCollection.user_id) == user_id)
            .where(col(UserCollection.vinyl_record_id) == vinyl_record_id)
        )
        return self.session.exec(stmt).first()

    def list_for_user_with_catalog(
        self,
        user_id: uuid.UUID,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[tuple[UserCollection, VinylRecord]]:
        """user_id の collection と catalog を JOIN して flat row を返す。

        Home マトリクスの一覧用。並び順は次の通り (pinned > 非 pinned、
        pinned 内は drag & drop で決まる `pin_order` 昇順):

            is_pinned DESC, pin_order ASC NULLS LAST, display_order ASC

        フロント側は Home プレビューを slice するだけで「ピン順 → display_order
        で補完」が成立する。

        `limit=None` で全件、`limit` が指定された時のみページネーション。
        """
        stmt = (
            select(UserCollection, VinylRecord)
            .join(VinylRecord, col(VinylRecord.id) == col(UserCollection.vinyl_record_id))
            .where(col(UserCollection.user_id) == user_id)
            .order_by(
                col(UserCollection.is_pinned).desc(),
                col(UserCollection.pin_order).asc().nulls_last(),
                col(UserCollection.display_order).asc(),
            )
        )
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.exec(stmt).all())

    def count_for_user(self, user_id: uuid.UUID) -> int:
        """user の collection 総件数 (paginated レスポンスの `total` 用)。"""
        stmt = (
            select(func.count())
            .select_from(UserCollection)
            .where(col(UserCollection.user_id) == user_id)
        )
        return self.session.exec(stmt).one()

    def count_pinned_for_user(self, user_id: uuid.UUID) -> int:
        """is_pinned=True の件数。pin 上限 (8) を service 層で enforce する用。"""
        stmt = (
            select(func.count())
            .select_from(UserCollection)
            .where(col(UserCollection.user_id) == user_id)
            .where(col(UserCollection.is_pinned).is_(True))
        )
        return self.session.exec(stmt).one()

    def max_pin_order_for_user(self, user_id: uuid.UUID) -> int:
        """user のピン済み行の最大 `pin_order`。新規 pin は max+1 で末尾に置く。"""
        stmt = (
            select(func.max(col(UserCollection.pin_order)))
            .where(col(UserCollection.user_id) == user_id)
            .where(col(UserCollection.is_pinned).is_(True))
        )
        result = self.session.exec(stmt).one_or_none()
        return result if result is not None else 0

    def list_pinned_for_user(self, user_id: uuid.UUID) -> list[UserCollection]:
        """user のピン済み行を `pin_order ASC` で返す (reorder API の前段検証用)。"""
        stmt = (
            select(UserCollection)
            .where(col(UserCollection.user_id) == user_id)
            .where(col(UserCollection.is_pinned).is_(True))
            .order_by(col(UserCollection.pin_order).asc().nulls_last())
        )
        return list(self.session.exec(stmt).all())

    def count_owned_by_artist_for_user(self, user_id: uuid.UUID) -> dict[str, int]:
        """current user の status='owned' レコード数を artist_id ごとに集計する。

        ArtistsPage の件数列専用。`user_collections JOIN vinyl_records` で catalog
        の artist_id にぶら下げる。`user_follows` の archived 状態は問わない
        (collection が user に直接 scope されているため follow 状態と独立)。
        """
        stmt = (
            select(VinylRecord.artist_id, func.count())
            .select_from(UserCollection)
            .join(VinylRecord, col(VinylRecord.id) == col(UserCollection.vinyl_record_id))
            .where(col(UserCollection.user_id) == user_id)
            .where(col(UserCollection.status) == "owned")
            .group_by(col(VinylRecord.artist_id))
        )
        rows = self.session.exec(stmt).all()
        return {artist_id: count for artist_id, count in rows}

    def lock_for_display_order(self, user_id: uuid.UUID) -> None:
        """user 単位の advisory lock。他 user の INSERT はブロックされない。

        2 引数版 `pg_advisory_xact_lock(k1, k2)` の k1 を固定キー、k2 を
        `hashtext(user_id::text)` (int4) にすることで user 単位スロットを作る。
        """
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(:k1, hashtext(:k2))"),
            {"k1": self._DISPLAY_ORDER_LOCK_KEY, "k2": str(user_id)},
        )

    def max_display_order_for_user(self, user_id: uuid.UUID) -> int:
        stmt = select(func.max(col(UserCollection.display_order))).where(
            col(UserCollection.user_id) == user_id
        )
        result = self.session.exec(stmt).one_or_none()
        return result if result is not None else 0

    def add(self, collection: UserCollection) -> UserCollection:
        return self._persist(collection)

    def save(self, collection: UserCollection) -> UserCollection:
        return self._persist(collection)

    def delete(self, collection: UserCollection) -> None:
        """user_collections を物理削除。`record_favorite_tracks` は CASCADE で
        自動削除、`vinyl_records` (catalog) は触らない (ADR-006 §2.7)。"""
        self.session.delete(collection)
        self.session.commit()

    def list_artist_ids_for_user(self, user_id: uuid.UUID) -> list[str]:
        """user_collections から user に紐づく artist_id (重複除去) を返す。

        `release_service` の follow seed (auto-follow 実装前のレガシー records
        backfill 経路) で使う想定。ADR-006 後は auto-follow が user_collections
        作成と同 TX で走るので通常空になる。
        """
        stmt = (
            select(VinylRecord.artist_id)
            .select_from(UserCollection)
            .join(VinylRecord, col(VinylRecord.id) == col(UserCollection.vinyl_record_id))
            .where(col(UserCollection.user_id) == user_id)
            .distinct()
        )
        return list(self.session.exec(stmt).all())

    def _persist(self, collection: UserCollection) -> UserCollection:
        self.session.add(collection)
        self.session.commit()
        self.session.refresh(collection)
        return collection
