"""Feed の releases API。

- GET /api/releases: 期間窓 (デフォルト today-1y .. today+1m) の release 一覧
- POST /api/releases/sync: 認証必須。Spotify Get Artist's Albums を follow 中
  アーティスト全件に対して呼び出し、release テーブルを upsert する
- GET /api/releases/sync-status: 最終同期時刻 / エラー状態を返す (空状態の
  ステータス表示用、ADR-000 §314)
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, status

from app.core.repositories.sync_status_repository import SyncStatusRepository
from app.models.user import User
from app.routers._handlers import http_errors
from app.routers.deps import (
    get_current_user,
    get_release_service,
    get_spotify_app_client,
    get_sync_status_repository,
)
from app.schemas.common import ListResponse
from app.schemas.release import (
    ReleaseRead,
    ReleaseReadStatusUpdate,
    SyncRunRequest,
    SyncRunResult,
    SyncStatusRead,
)
from app.services.release_service import RELEASE_SYNC_SOURCE, ReleaseService
from app.services.spotify_app_client import SpotifyAppClient

router = APIRouter(prefix="/api/releases", tags=["releases"])

# Feed タブ「直近30日 / 今後の予定」用のデフォルト窓。
# 開発段階では取り込み量を絞るため過去 30 日 + 未来 30 日 (≒ ±1 ヶ月)。
# 本番投入時には ADR-000 §220 の「直近30日 / 今後の予定」を満たすかチェックし、
# 必要なら過去側を 365 日などに広げる。
_DEFAULT_LOOKBACK_DAYS = 30
_DEFAULT_LOOKAHEAD_DAYS = 30


def _default_window() -> tuple[date, date]:
    today = date.today()
    return (
        today - timedelta(days=_DEFAULT_LOOKBACK_DAYS),
        today + timedelta(days=_DEFAULT_LOOKAHEAD_DAYS),
    )


@router.get("", response_model=ListResponse[ReleaseRead])
def list_releases(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    service: ReleaseService = Depends(get_release_service),
    current_user: User = Depends(get_current_user),
) -> ListResponse[ReleaseRead]:
    """current user が follow 中 (archived=false) の artist の release を返す
    (ADR-007 §2.4)。既読状態は user 単位で計算される (ADR-007 §2.3)。"""
    default_from, default_to = _default_window()
    items = service.list_window(current_user.id, from_date or default_from, to_date or default_to)
    return ListResponse(items=items)


# 注意: `/sync-status` を `/{spotify_id}` 風の path より先に宣言したいが
# こちらは平らな 2 endpoint なので順序衝突は起きない。それでも明示順で
# 一覧 → status → sync の順に並べる。
@router.get("/sync-status", response_model=SyncStatusRead)
def get_sync_status(
    repo: SyncStatusRepository = Depends(get_sync_status_repository),
    _: User = Depends(get_current_user),
) -> SyncStatusRead:
    row = repo.get(RELEASE_SYNC_SOURCE)
    if row is None:
        return SyncStatusRead(
            source=RELEASE_SYNC_SOURCE,
            last_success_at=None,
            last_attempt_at=None,
            last_error=None,
        )
    return SyncStatusRead.model_validate(row)


@router.patch("/{spotify_id}/read", response_model=ReleaseRead)
def set_release_read_status(
    spotify_id: str,
    payload: ReleaseReadStatusUpdate,
    service: ReleaseService = Depends(get_release_service),
    current_user: User = Depends(get_current_user),
) -> ReleaseRead:
    """release の既読フラグを user 単位でトグル (Feed の未読 dot 用、ADR-007)。

    `is_read=true` で `release_read_states` に upsert (read_at = now())、`false`
    で行を DELETE。release catalog が無ければ 404。
    """
    with http_errors():
        return service.set_read_status(spotify_id, payload.is_read, current_user.id)


@router.post("/sync", response_model=SyncRunResult, status_code=status.HTTP_200_OK)
def trigger_sync(
    payload: SyncRunRequest | None = None,
    service: ReleaseService = Depends(get_release_service),
    spotify: SpotifyAppClient = Depends(get_spotify_app_client),
    current_user: User = Depends(get_current_user),
) -> SyncRunResult:
    """フォロー中アーティスト全件の releases を Spotify から取り込む。

    Phase B-3 では同期実行 (long poll、数十秒の可能性)。Phase B-4 で
    APScheduler の日次バッチに移行する前提のため、ここは shim 実装。
    """
    default_from, default_to = _default_window()
    since = (payload.since_date if payload else None) or default_from
    until = (payload.until_date if payload else None) or default_to
    result = service.sync_for_user(current_user.id, spotify, since, until)
    return SyncRunResult(
        artists_total=result.artists_total,
        artists_succeeded=result.artists_succeeded,
        albums_ingested=result.albums_ingested,
        first_error=result.first_error,
    )
