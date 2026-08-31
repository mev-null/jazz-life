from fastapi import APIRouter, Depends, HTTPException, status

from app.models.user import User
from app.routers.deps import (
    get_artist_service,
    get_current_user,
    get_spotify_app_client,
)
from app.schemas.artist import ArtistCreate, ArtistRead
from app.schemas.common import ListResponse
from app.services.artist_service import ArtistService
from app.services.spotify_app_client import SpotifyAppClient

router = APIRouter(prefix="/api/artists", tags=["artists"])


@router.get("", response_model=ListResponse[ArtistRead])
def list_artists(
    service: ArtistService = Depends(get_artist_service),
    _: User = Depends(get_current_user),
) -> ListResponse[ArtistRead]:
    rows = service.list_all()
    return ListResponse(items=[ArtistRead.model_validate(row) for row in rows])


@router.get("/{spotify_id}", response_model=ArtistRead)
def get_artist(
    spotify_id: str,
    service: ArtistService = Depends(get_artist_service),
    spotify: SpotifyAppClient = Depends(get_spotify_app_client),
    _: User = Depends(get_current_user),
) -> ArtistRead:
    """Fetch a single artist, filling in image_url from Spotify when it is NULL.

    The "lazy photo hydration" endpoint called when ArtistDetailModal opens.
    Spotify-side errors are swallowed in the service layer, so when no image
    is available the artist is returned with image_url=null (the UI falls back
    to initials).
    """
    artist = service.get_with_image_hydration(spotify_id, spotify)
    if artist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"artist spotify_id={spotify_id} not found",
        )
    return ArtistRead.model_validate(artist)


@router.post("", response_model=ArtistRead, status_code=status.HTTP_200_OK)
def upsert_artist(
    payload: ArtistCreate,
    service: ArtistService = Depends(get_artist_service),
    _: User = Depends(get_current_user),
) -> ArtistRead:
    """Upsert keyed on spotify_id; returns the existing row if present (200).

    Phase B-3 PR-2: called by RecordFormModal when a Spotify album is selected
    and the album's artist is not yet in the DB. Idempotent by design: a
    duplicate POST never returns 409.
    """
    artist = service.upsert(payload)
    return ArtistRead.model_validate(artist)
