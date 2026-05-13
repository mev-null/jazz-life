from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session, col, delete, select

from app.models.release_read_state import ReleaseReadState


class ReleaseReadStateRepository:
    """`release_read_states` の CRUD (ADR-007)。

    行があれば既読、無ければ未読。`read_at` は既読化の時刻。
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def mark_read(self, user_id: UUID, release_spotify_id: str) -> ReleaseReadState:
        """既読化 (upsert)。既存行があれば `read_at` を now() に更新する。"""
        now = datetime.now(UTC)
        stmt = (
            pg_insert(ReleaseReadState)
            .values(
                user_id=user_id,
                release_spotify_id=release_spotify_id,
                read_at=now,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "release_spotify_id"],
                set_={"read_at": now},
            )
        )
        self.session.exec(stmt)  # type: ignore[call-overload]
        self.session.commit()
        row = self.session.get(
            ReleaseReadState, {"user_id": user_id, "release_spotify_id": release_spotify_id}
        )
        assert row is not None  # 直前に upsert したので必ず存在
        return row

    def mark_unread(self, user_id: UUID, release_spotify_id: str) -> bool:
        """未読化 (行を DELETE)。存在しなければ no-op。冪等。

        404 は呼び出し側 (Service) で release の存在確認に集約しているので、
        ここでは戻り値の bool だけ (DELETE できたかどうか)。
        """
        stmt = delete(ReleaseReadState).where(  # type: ignore[call-overload]
            col(ReleaseReadState.user_id) == user_id,
            col(ReleaseReadState.release_spotify_id) == release_spotify_id,
        )
        result = self.session.exec(stmt)
        self.session.commit()
        return result.rowcount > 0

    def list_read_at_map_for_user(
        self, user_id: UUID, release_spotify_ids: Iterable[str]
    ) -> dict[str, datetime]:
        """list_window 用に user の既読 read_at を spotify_id でマップ化して返す。

        N+1 回避のため一括取得。release_spotify_ids が空なら DB を叩かず空 dict。
        """
        ids = list(release_spotify_ids)
        if not ids:
            return {}
        stmt = (
            select(
                ReleaseReadState.release_spotify_id,
                ReleaseReadState.read_at,
            )
            .where(col(ReleaseReadState.user_id) == user_id)
            .where(col(ReleaseReadState.release_spotify_id).in_(ids))
        )
        return {spotify_id: read_at for spotify_id, read_at in self.session.exec(stmt).all()}
