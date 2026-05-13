from datetime import date
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session, and_, col, select

from app.models.release import Release
from app.models.user_follow import UserFollow


class ReleaseRepository:
    """releases (catalog) 専用 (ADR-007)。

    既読状態は ReleaseReadStateRepository に分離済み。配信スコープ (current user
    が follow 中の artist だけ) は `list_window_for_user` の JOIN で適用する。
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, spotify_id: str) -> Release | None:
        return self.session.get(Release, spotify_id)

    def list_window_for_user(self, user_id: UUID, from_date: date, to_date: date) -> list[Release]:
        """current user が follow 中 (archived=false) の artist の release を
        期間窓 `[from_date, to_date]` で取得して新しい順に返す (ADR-007 §2.4)。

        unfollow した artist の release は自然に Feed から消える。
        """
        stmt = (
            select(Release)
            .join(UserFollow, col(UserFollow.artist_id) == col(Release.artist_id))
            .where(col(UserFollow.user_id) == user_id)
            .where(col(UserFollow.archived_flag).is_(False))
            .where(
                and_(
                    col(Release.release_date) >= from_date,
                    col(Release.release_date) <= to_date,
                )
            )
            .order_by(col(Release.release_date).desc())
        )
        return list(self.session.exec(stmt).all())

    def upsert_many(self, rows: list[Release]) -> int:
        """`spotify_id` を key にして bulk upsert する。

        ADR-007 後は `is_read` / `read_at` 列は catalog から無くなり、既読は
        独立テーブル `release_read_states` に持つ。catalog の upsert は metadata
        のみ更新すれば自然に既読状態が preserve される (独立テーブルを触らない
        ため)。戻り値は新規 + 既存を区別しないラフな件数。
        """
        if not rows:
            return 0
        payloads = [
            {
                "spotify_id": r.spotify_id,
                "artist_id": r.artist_id,
                "title": r.title,
                "album_type": r.album_type,
                "release_date": r.release_date,
                "image_url": r.image_url,
            }
            for r in rows
        ]
        stmt = pg_insert(Release).values(payloads)
        stmt = stmt.on_conflict_do_update(
            index_elements=["spotify_id"],
            set_={
                "artist_id": stmt.excluded.artist_id,
                "title": stmt.excluded.title,
                "album_type": stmt.excluded.album_type,
                "release_date": stmt.excluded.release_date,
                "image_url": stmt.excluded.image_url,
            },
        )
        self.session.exec(stmt)  # type: ignore[call-overload]
        self.session.commit()
        return len(rows)
