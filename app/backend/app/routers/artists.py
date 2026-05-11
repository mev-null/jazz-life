from fastapi import APIRouter, Depends, HTTPException, status

from app.models.user import User
from app.routers.deps import (
    get_artist_service,
    get_current_user,
    get_record_service,
    get_spotify_app_client,
)
from app.schemas.artist import ArtistCreate, ArtistRead, ArtistRecordCount
from app.schemas.common import ListResponse
from app.services.artist_service import ArtistService
from app.services.record_service import RecordService
from app.services.spotify_app_client import SpotifyAppClient

router = APIRouter(prefix="/api/artists", tags=["artists"])


@router.get("", response_model=ListResponse[ArtistRead])
def list_artists(service: ArtistService = Depends(get_artist_service)) -> ListResponse[ArtistRead]:
    rows = service.list_all()
    return ListResponse(items=[ArtistRead.model_validate(row) for row in rows])


# 注意: `/{spotify_id}` より先に `/record-counts` を宣言する。FastAPI は
# 宣言順でマッチングするため、逆順にすると `/record-counts` が
# `spotify_id="record-counts"` として吸われる。
@router.get("/record-counts", response_model=ListResponse[ArtistRecordCount])
def list_record_counts(
    service: RecordService = Depends(get_record_service),
) -> ListResponse[ArtistRecordCount]:
    """artist_id ごとの所有レコード数を集計して返す。

    ArtistsPage 一覧の件数列専用。records 全件取得を避けて軽量化する。
    """
    counts = service.count_by_artist()
    return ListResponse(items=[ArtistRecordCount(artist_id=k, count=v) for k, v in counts.items()])


@router.get("/{spotify_id}", response_model=ArtistRead)
def get_artist(
    spotify_id: str,
    service: ArtistService = Depends(get_artist_service),
    spotify: SpotifyAppClient = Depends(get_spotify_app_client),
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
