import datetime as dt
import uuid
from uuid import UUID

import pytest
from sqlmodel import Session

from app.core.exceptions import NotFoundError
from app.core.repositories.artist_repository import ArtistRepository
from app.core.repositories.record_repository import RecordRepository
from app.core.repositories.user_follow_repository import UserFollowRepository
from app.models.artist import Artist
from app.models.user import User
from app.schemas.record import VinylRecordCreate, VinylRecordUpdate
from app.services.record_service import RecordService


def _seed_artist(session: Session, spotify_id: str = "test_artist") -> str:
    artist = Artist(
        spotify_id=spotify_id,
        name=f"Artist {spotify_id}",
        added_at=dt.datetime.now(dt.UTC),
    )
    session.add(artist)
    session.commit()
    return artist.spotify_id


def _seed_user(session: Session) -> UUID:
    """auto-follow が user_follows.user_id (FK → users.id) を要求するので
    テストでも実 user を作って ID を返す。"""
    user = User(spotify_id="test-owner", display_name="Test Owner", refresh_token="")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user.id


def _service(session: Session) -> RecordService:
    return RecordService(
        RecordRepository(session),
        ArtistRepository(session),
        UserFollowRepository(session),
    )


def test_create_assigns_display_order_max_plus_one(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    first = service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)
    second = service.create(VinylRecordCreate(artist_id=artist_id, title="B"), user_id)

    assert first.display_order == 1
    assert second.display_order == 2


def test_create_uses_uuid_v7_id(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    record = service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)
    assert record.id.version == 7


def test_create_auto_follows_artist(session: Session) -> None:
    """records.create が user_follows に (user_id, artist_id) を追加すること。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)

    follows = UserFollowRepository(session).list_artist_ids(user_id)
    assert follows == [artist_id]


def test_create_auto_follow_is_idempotent(session: Session) -> None:
    """同じ artist の record を 2 件作っても follow は 1 行のまま。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)
    service.create(VinylRecordCreate(artist_id=artist_id, title="B"), user_id)

    follows = UserFollowRepository(session).list_artist_ids(user_id)
    assert follows == [artist_id]


def test_update_partial_only_changes_sent_fields(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            title="Original",
            memo="initial memo",
            original_release_date="1962",
        ),
        user_id,
    )
    original_created_at = record.created_at

    updated = service.update_partial(record.id, VinylRecordUpdate(memo="changed"))

    assert updated.memo == "changed"
    assert updated.title == "Original"
    assert updated.original_release_date == "1962"
    assert updated.created_at == original_created_at
    assert updated.updated_at >= original_created_at


def test_update_unknown_id_raises_not_found(session: Session) -> None:
    service = _service(session)
    with pytest.raises(NotFoundError):
        service.update_partial(uuid.uuid4(), VinylRecordUpdate(memo="x"))


def test_create_with_unknown_artist_raises_not_found(session: Session) -> None:
    user_id = _seed_user(session)
    service = _service(session)
    with pytest.raises(NotFoundError, match="artist"):
        service.create(VinylRecordCreate(artist_id="ghost_artist", title="A"), user_id)


def test_update_can_swap_artist_id(session: Session) -> None:
    src = _seed_artist(session, "artist_src")
    dst = _seed_artist(session, "artist_dst")
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(VinylRecordCreate(artist_id=src, title="A"), user_id)

    updated = service.update_partial(record.id, VinylRecordUpdate(artist_id=dst))

    assert updated.artist_id == dst


def test_update_swap_to_unknown_artist_raises_not_found(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)

    with pytest.raises(NotFoundError, match="artist"):
        service.update_partial(record.id, VinylRecordUpdate(artist_id="ghost_artist"))
