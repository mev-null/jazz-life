import datetime as dt
import uuid

from app.core.exceptions import NotFoundError
from app.core.repositories.artist_repository import ArtistRepository
from app.core.repositories.record_repository import RecordRepository
from app.models.record import VinylRecord
from app.schemas.record import VinylRecordCreate, VinylRecordUpdate


class RecordService:
    def __init__(self, repo: RecordRepository, artist_repo: ArtistRepository) -> None:
        self.repo = repo
        self.artist_repo = artist_repo

    def list_all(self) -> list[VinylRecord]:
        return self.repo.list_all()

    def create(self, data: VinylRecordCreate) -> VinylRecord:
        self._ensure_artist_exists(data.artist_id)
        # Serialize display_order assignment across concurrent POSTs. Released
        # with the transaction inside repo.add(...).
        self.repo.lock_for_display_order()
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
        patch_data = patch.model_dump(exclude_unset=True)
        new_artist_id = patch_data.get("artist_id")
        if new_artist_id is not None and new_artist_id != record.artist_id:
            self._ensure_artist_exists(new_artist_id)
        for key, value in patch_data.items():
            setattr(record, key, value)
        record.updated_at = dt.datetime.now(dt.UTC)
        return self.repo.save(record)

    def _ensure_artist_exists(self, artist_id: str) -> None:
        if self.artist_repo.get(artist_id) is None:
            raise NotFoundError(f"artist spotify_id={artist_id}")
