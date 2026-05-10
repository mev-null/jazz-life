from fastapi import APIRouter, Depends

from app.routers.deps import get_artist_service
from app.schemas.artist import ArtistRead
from app.schemas.common import ListResponse
from app.services.artist_service import ArtistService

router = APIRouter(prefix="/api/artists", tags=["artists"])


@router.get("", response_model=ListResponse[ArtistRead])
def list_artists(service: ArtistService = Depends(get_artist_service)) -> ListResponse[ArtistRead]:
    rows = service.list_all()
    return ListResponse(items=[ArtistRead.model_validate(row) for row in rows])
