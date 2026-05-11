from fastapi import APIRouter, Depends, status

from app.models.user import User
from app.routers.deps import get_artist_service, get_current_user
from app.schemas.artist import ArtistCreate, ArtistRead
from app.schemas.common import ListResponse
from app.services.artist_service import ArtistService

router = APIRouter(prefix="/api/artists", tags=["artists"])


@router.get("", response_model=ListResponse[ArtistRead])
def list_artists(service: ArtistService = Depends(get_artist_service)) -> ListResponse[ArtistRead]:
    rows = service.list_all()
    return ListResponse(items=[ArtistRead.model_validate(row) for row in rows])


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
