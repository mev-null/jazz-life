"""user_follows 操作の API。

- GET /api/user-follows/artists: 現ユーザが follow 中 (archived=false) の artists
- GET /api/user-follows/record-counts: 現ユーザの artist_id ごとの所有レコード数
- POST /api/user-follows: 明示的に artist を follow に追加 (ArtistsPage の「追加」UI 用)
- DELETE /api/user-follows/{artist_id}: follow 解除 (soft delete)

records 登録経由の auto-follow (RecordService.create) と並行して、
ArtistsPage から Spotify 検索で artist を選んで follow を作る経路も
このルータが受け持つ。
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.repositories.artist_repository import ArtistRepository
from app.core.repositories.user_follow_repository import UserFollowRepository
from app.models.user import User
from app.routers.deps import (
    get_artist_repository,
    get_current_user,
    get_record_service,
    get_user_follow_repository,
)
from app.schemas.artist import ArtistRead, ArtistRecordCount
from app.schemas.common import ListResponse
from app.schemas.user_follow import UserFollowCreate
from app.services.record_service import RecordService

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


# 注意: `/{artist_id}` (DELETE) より先に `/record-counts` を宣言する。
# FastAPI は宣言順でマッチングするが、HTTP メソッドが異なる (GET vs DELETE)
# ので順序衝突は起きない。ただし可読性のため一覧系を先にまとめる。
@router.get("/record-counts", response_model=ListResponse[ArtistRecordCount])
def list_record_counts(
    current_user: User = Depends(get_current_user),
    service: RecordService = Depends(get_record_service),
) -> ListResponse[ArtistRecordCount]:
    """current user の所有レコード数を artist_id ごとに集計して返す。

    ArtistsPage 一覧の件数列専用。records 全件取得を避けて軽量化する。
    旧 `/api/artists/record-counts` を user-follows 配下に移設し (集計の単位が
    follow と一致するため意味論として整合する)、同時に user_id でスコープを
    切るようにした。status='owned' のみ数える (want list は除外)。
    """
    counts = service.count_owned_by_artist_for_user(current_user.id)
    return ListResponse(items=[ArtistRecordCount(artist_id=k, count=v) for k, v in counts.items()])


@router.post("", response_model=ArtistRead, status_code=status.HTTP_201_CREATED)
def follow_artist(
    payload: UserFollowCreate,
    current_user: User = Depends(get_current_user),
    artist_repo: ArtistRepository = Depends(get_artist_repository),
    follow_repo: UserFollowRepository = Depends(get_user_follow_repository),
) -> ArtistRead:
    """`artist_id` を current user の follow に追加する。

    `UserFollowRepository.upsert` を使うので冪等:
    - 既に active follow なら上書きで no-op、201 + 既存 artist
    - archived 行があれば archived_flag=false に戻して再 follow
    - 行が無ければ新規 INSERT

    artist が `artists` テーブルに無い場合は 404。UI 側で先に `POST /api/artists`
    で upsert する想定 (Spotify 検索結果のメタデータをそのまま投入する)。
    """
    artist = artist_repo.get(payload.artist_id)
    if artist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"artist not found: spotify_id={payload.artist_id}",
        )
    follow_repo.upsert(current_user.id, payload.artist_id)
    return ArtistRead.model_validate(artist)


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
