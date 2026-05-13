import uuid

from sqlmodel import Session, select

from app.models.record import VinylRecord


class RecordRepository:
    """vinyl_records (catalog) 専用 (ADR-006)。

    所有関係 (status / display_order / memo 等) は UserCollectionRepository へ
    移譲した。catalog 行は手動削除しない (ADR-006 §2.7) ため delete を持たない。
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, id: uuid.UUID) -> VinylRecord | None:
        return self.session.get(VinylRecord, id)

    def find_by_spotify_album_id(self, spotify_album_id: str) -> VinylRecord | None:
        """`source='spotify'` 行の dedup 取得用 (find-or-create 経路)。

        partial UNIQUE INDEX が `spotify_album_id IS NOT NULL` を対象に貼って
        あるため、戻り値は高々 1 件。
        """
        stmt = select(VinylRecord).where(VinylRecord.spotify_album_id == spotify_album_id)
        return self.session.exec(stmt).first()

    def add(self, record: VinylRecord) -> VinylRecord:
        return self._persist(record)

    def save(self, record: VinylRecord) -> VinylRecord:
        return self._persist(record)

    def _persist(self, record: VinylRecord) -> VinylRecord:
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record
