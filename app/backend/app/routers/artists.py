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
    """単一 artist を取り、image_url が NULL なら Spotify から補完する。

    ArtistDetailModal を開いた時に呼ぶ「lazy photo hydration」エンドポイント。
    Spotify 側エラーは service 層で握り潰されるので、画像が無い場合は
    image_url=null のまま返る (UI 側で initials fallback)。
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
    """spotify_id をキーに upsert。既存なら既存を返す (200)。

    Phase B-3 PR-2: RecordFormModal が Spotify album を選んだ時、その album の
    artist がまだ DB に無い場合に呼び出す。重複 POST でも 409 を返さない冪等設計。
    """
    artist = service.upsert(payload)
    return ArtistRead.model_validate(artist)
