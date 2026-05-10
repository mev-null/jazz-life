from fastapi import Depends
from sqlmodel import Session

from app.core.db import get_session
from app.core.repositories.artist_repository import ArtistRepository
from app.core.repositories.record_repository import RecordRepository
from app.services.artist_service import ArtistService
from app.services.record_service import RecordService


def get_artist_repository(session: Session = Depends(get_session)) -> ArtistRepository:
    return ArtistRepository(session)


def get_artist_service(
    repo: ArtistRepository = Depends(get_artist_repository),
) -> ArtistService:
    return ArtistService(repo)


def get_record_repository(session: Session = Depends(get_session)) -> RecordRepository:
    return RecordRepository(session)


def get_record_service(
    repo: RecordRepository = Depends(get_record_repository),
    artist_repo: ArtistRepository = Depends(get_artist_repository),
) -> RecordService:
    return RecordService(repo, artist_repo)
