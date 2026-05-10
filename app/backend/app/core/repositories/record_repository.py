import uuid

from sqlalchemy import text
from sqlmodel import Session, col, func, select

from app.models.record import VinylRecord


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

    def get(self, id: uuid.UUID) -> VinylRecord | None:
        return self.session.get(VinylRecord, id)

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
