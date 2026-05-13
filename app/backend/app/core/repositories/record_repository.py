import uuid
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session, col, func, select

from app.models.record import VinylRecord
from app.models.user_follow import UserFollow


class RecordRepository:
    # Arbitrary fixed key for the display_order serialization advisory lock.
    # pg_advisory_xact_lock takes a signed bigint; any constant works as long as
    # callers across the codebase agree.
    _DISPLAY_ORDER_LOCK_KEY = 0x1A22_DE51_0001

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[VinylRecord]:
        stmt = select(VinylRecord).order_by(col(VinylRecord.display_order).asc())
        return list(self.session.exec(stmt).all())

    def count_owned_by_artist_for_user(self, user_id: UUID) -> dict[str, int]:
        """current user の「所有」レコード数を artist_id ごとに集計して返す。

        ArtistsPage 一覧の「N records」表示用。VinylRecord に user_id を持たない
        現スキーマでは user_follows を経由してユーザを絞り込む (auto-follow on
        record create により、自分が持つ record == 自分が follow している artist
        の record とほぼ一致する)。status='owned' に絞ることで want list の
        wanted は数えない。archived な follow も除外し、ArtistsPage に出る
        followed_artists の列と整合させる。
        """
        stmt = (
            select(VinylRecord.artist_id, func.count())
            .join(UserFollow, col(UserFollow.artist_id) == col(VinylRecord.artist_id))
            .where(col(UserFollow.user_id) == user_id)
            .where(col(UserFollow.archived_flag).is_(False))
            .where(col(VinylRecord.status) == "owned")
            .group_by(col(VinylRecord.artist_id))
        )
        rows = self.session.exec(stmt).all()
        return {artist_id: count for artist_id, count in rows}

    def get(self, id: uuid.UUID) -> VinylRecord | None:
        return self.session.get(VinylRecord, id)

    def delete(self, record: VinylRecord) -> None:
        """1 件を hard delete。user_follows は触らない方針 (record の生死と
        フォロー状態を独立スコープに保つ)。soft delete は導入していないので
        単純な物理削除で OK。"""
        self.session.delete(record)
        self.session.commit()

    def add(self, record: VinylRecord) -> VinylRecord:
        return self._persist(record)

    def save(self, record: VinylRecord) -> VinylRecord:
        return self._persist(record)

    def lock_for_display_order(self) -> None:
        # Transaction-scoped advisory lock; auto-released on COMMIT/ROLLBACK.
        # Serializes display_order assignment across concurrent INSERTs.
        # FOR UPDATE on `ORDER BY ... LIMIT 1` doesn't work here because, under
        # READ COMMITTED, the waiter re-locks the originally-selected row rather
        # than the new MAX after the holder commits.
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(:k)"),
            {"k": self._DISPLAY_ORDER_LOCK_KEY},
        )

    def max_display_order(self) -> int:
        stmt = select(func.max(col(VinylRecord.display_order)))
        result = self.session.exec(stmt).one_or_none()
        return result if result is not None else 0

    def _persist(self, record: VinylRecord) -> VinylRecord:
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record
