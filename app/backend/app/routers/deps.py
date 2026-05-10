from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from app.core.db import get_session
from app.core.exceptions import AuthError
from app.core.repositories.artist_repository import ArtistRepository
from app.core.repositories.record_repository import RecordRepository
from app.core.repositories.user_repository import UserRepository
from app.core.settings import Settings, get_settings
from app.models.user import User
from app.services.artist_service import ArtistService
from app.services.auth_service import AuthService
from app.services.record_service import RecordService
from app.services.spotify_oauth_client import SpotifyOAuthClient


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


def get_user_repository(session: Session = Depends(get_session)) -> UserRepository:
    return UserRepository(session)


def get_spotify_oauth_client(settings: Settings = Depends(get_settings)) -> SpotifyOAuthClient:
    return SpotifyOAuthClient(settings)


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
    spotify: SpotifyOAuthClient = Depends(get_spotify_oauth_client),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    return AuthService(user_repo=user_repo, spotify=spotify, settings=settings)


def get_current_user(
    request: Request,
    settings: Settings = Depends(get_settings),
    user_repo: UserRepository = Depends(get_user_repository),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    token = request.cookies.get(settings.cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    try:
        user_id = auth_service.decode_session_token(token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    user = user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="session subject missing",
        )
    return user
