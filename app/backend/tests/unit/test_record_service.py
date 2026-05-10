import datetime as dt
import uuid

import pytest
from sqlmodel import Session

from app.core.exceptions import NotFoundError
from app.core.repositories.record_repository import RecordRepository
from app.models.artist import Artist
from app.schemas.record import VinylRecordCreate, VinylRecordUpdate
from app.services.record_service import RecordService


def _seed_artist(session: Session) -> str:
    artist = Artist(
        spotify_id="test_artist",
        name="Test Artist",
        followed=True,
        added_at=dt.datetime.now(dt.UTC),
    )
    session.add(artist)
    session.commit()
    return artist.spotify_id


def test_create_assigns_display_order_max_plus_one(session: Session) -> None:
    artist_id = _seed_artist(session)
    service = RecordService(RecordRepository(session))

    first = service.create(VinylRecordCreate(artist_id=artist_id, title="A"))
    second = service.create(VinylRecordCreate(artist_id=artist_id, title="B"))

    assert first.display_order == 1
    assert second.display_order == 2


def test_create_uses_uuid_v7_id(session: Session) -> None:
    artist_id = _seed_artist(session)
    service = RecordService(RecordRepository(session))

    record = service.create(VinylRecordCreate(artist_id=artist_id, title="A"))
    assert record.id.version == 7


def test_update_partial_only_changes_sent_fields(session: Session) -> None:
    artist_id = _seed_artist(session)
    service = RecordService(RecordRepository(session))
    record = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            title="Original",
            memo="initial memo",
            original_release_date="1962",
        )
    )
    original_created_at = record.created_at

    updated = service.update_partial(record.id, VinylRecordUpdate(memo="changed"))

    assert updated.memo == "changed"
    assert updated.title == "Original"
    assert updated.original_release_date == "1962"
    assert updated.created_at == original_created_at
    assert updated.updated_at >= original_created_at


def test_update_unknown_id_raises_not_found(session: Session) -> None:
    service = RecordService(RecordRepository(session))
    with pytest.raises(NotFoundError):
        service.update_partial(uuid.uuid4(), VinylRecordUpdate(memo="x"))
