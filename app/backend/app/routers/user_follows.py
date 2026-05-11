"""user_follows 操作の API。

- GET /api/user-follows/artists: 現ユーザが follow 中 (archived=false) の artists
- DELETE /api/user-follows/{artist_id}: follow 解除 (soft delete)

follow 追加は records 登録時の auto-follow (RecordService.create 経由) で
カバーしてあり、明示的な follow POST endpoint は持たない。Phase B-4 で
Spotify follow 同期や手動 pin を入れる時に拡張する。
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.repositories.artist_repository import ArtistRepository
from app.core.repositories.user_follow_repository import UserFollowRepository
from app.models.user import User
from app.routers.deps import (
    get_artist_repository,
    get_current_user,
    get_user_follow_repository,
)
from app.schemas.artist import ArtistRead
from app.schemas.common import ListResponse

router = APIRouter(prefix="/api/user-follows", tags=["user-follows"])


@router.get("/artists", response_model=ListResponse[ArtistRead])
def list_followed_artists(
    current_user: User = Depends(get_current_user),
    artist_repo: ArtistRepository = Depends(get_artist_repository),
) -> ListResponse[ArtistRead]:
    """現ユーザが follow 中 (archived=false) の artists を返す。

    ArtistsPage 一覧専用。`GET /api/artists` は global registry (HomePage の
    record→artist 名前引きなどで利用) なので別エンドポイントに切る。
    """
    rows = artist_repo.list_followed_by(current_user.id)
    return ListResponse(items=[ArtistRead.model_validate(row) for row in rows])


@router.delete("/{artist_id}", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_artist(
    artist_id: str,
    current_user: User = Depends(get_current_user),
    follow_repo: UserFollowRepository = Depends(get_user_follow_repository),
) -> None:
    """Spotify ID の artist を follow から外す (soft delete: archived_flag=true)。

    archived_flag を立てるだけなので「以前 follow してた」履歴は残る。
    list_artist_ids は archived_flag=false のみ返すので、次の release sync は
    このアーティストを対象から外す。

    無いものを消そうとしたら 404、既に archived なら 204 (冪等)。
    """
    ok = follow_repo.archive(current_user.id, artist_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"user_follows not found: artist_id={artist_id}",
        )
