import uuid
from collections.abc import Iterable

from sqlmodel import Session, col, delete, select

from app.models.record_favorite_track import RecordFavoriteTrack


class RecordFavoriteTrackRepository:
    """`record_favorite_tracks` の CRUD (ADR-006 §2.8)。

    アルバム単位の編集 UX を想定し、`replace_for_collection` で全置換する。
    部分編集はやらない (1 collection の track 数はせいぜい数曲〜10 曲程度なので
    DELETE → INSERT で十分軽い)。
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_collection(self, user_collection_id: uuid.UUID) -> list[RecordFavoriteTrack]:
        stmt = (
            select(RecordFavoriteTrack)
            .where(col(RecordFavoriteTrack.user_collection_id) == user_collection_id)
            .order_by(col(RecordFavoriteTrack.position).asc())
        )
        return list(self.session.exec(stmt).all())

    def list_by_collection_ids(
        self, user_collection_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, list[RecordFavoriteTrack]]:
        """N+1 を避けるためまとめて取得して collection_id でグルーピング。"""
        ids = list(user_collection_ids)
        result: dict[uuid.UUID, list[RecordFavoriteTrack]] = {cid: [] for cid in ids}
        if not ids:
            return result
        stmt = (
            select(RecordFavoriteTrack)
            .where(col(RecordFavoriteTrack.user_collection_id).in_(ids))
            .order_by(
                col(RecordFavoriteTrack.user_collection_id).asc(),
                col(RecordFavoriteTrack.position).asc(),
            )
        )
        for row in self.session.exec(stmt).all():
            result[row.user_collection_id].append(row)
        return result

    def replace_for_collection(
        self,
        user_collection_id: uuid.UUID,
        tracks: list[RecordFavoriteTrack],
    ) -> list[RecordFavoriteTrack]:
        """当該 collection の favorite tracks を全削除 → 全 INSERT で置換する。

        UNIQUE (user_collection_id, spotify_track_id) 違反は呼び出し側で
        IntegrityError として捕捉する想定 (Service 層で 4xx に変換)。
        """
        self.session.exec(
            delete(RecordFavoriteTrack).where(  # type: ignore[call-overload]
                col(RecordFavoriteTrack.user_collection_id) == user_collection_id
            )
        )
        for t in tracks:
            t.user_collection_id = user_collection_id
            self.session.add(t)
        self.session.commit()
        return self.list_for_collection(user_collection_id)
