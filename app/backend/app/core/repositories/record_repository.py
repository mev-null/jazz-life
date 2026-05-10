import uuid

from sqlmodel import Session, col, func, select

from app.models.record import VinylRecord


class RecordRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[VinylRecord]:
        stmt = select(VinylRecord).order_by(col(VinylRecord.display_order).asc())
        return list(self.session.exec(stmt).all())

    def get(self, id: uuid.UUID) -> VinylRecord | None:
        return self.session.get(VinylRecord, id)

    def add(self, record: VinylRecord) -> VinylRecord:
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def save(self, record: VinylRecord) -> VinylRecord:
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def max_display_order(self) -> int:
        stmt = select(func.max(col(VinylRecord.display_order)))
        result = self.session.exec(stmt).one_or_none()
        return result or 0
