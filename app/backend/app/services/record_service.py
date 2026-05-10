import datetime as dt
import uuid

from app.core.exceptions import NotFoundError
from app.core.repositories.record_repository import RecordRepository
from app.models.record import VinylRecord
from app.schemas.record import VinylRecordCreate, VinylRecordUpdate


class RecordService:
    def __init__(self, repo: RecordRepository) -> None:
        self.repo = repo

    def list_all(self) -> list[VinylRecord]:
        return self.repo.list_all()

    def create(self, data: VinylRecordCreate) -> VinylRecord:
        next_order = self.repo.max_display_order() + 1
        now = dt.datetime.now(dt.UTC)
        record = VinylRecord(
            **data.model_dump(),
            display_order=next_order,
            created_at=now,
            updated_at=now,
        )
        return self.repo.add(record)

    def update_partial(self, id: uuid.UUID, patch: VinylRecordUpdate) -> VinylRecord:
        record = self.repo.get(id)
        if record is None:
            raise NotFoundError(f"vinyl_record id={id}")
        for key, value in patch.model_dump(exclude_unset=True).items():
            setattr(record, key, value)
        record.updated_at = dt.datetime.now(dt.UTC)
        return self.repo.save(record)
