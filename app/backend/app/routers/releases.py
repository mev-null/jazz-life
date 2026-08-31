"""Releases API for the Feed.

- GET /api/releases: releases within a date window (default today-1y .. today+1m)
- POST /api/releases/sync: auth required. Calls Spotify Get Artist's Albums for
  every followed artist and upserts the release table
- GET /api/releases/sync-status: last sync time / error state (for the
  empty-state status display, ADR-000 §314)
"""

from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.core.db import SessionFactory, get_session_factory
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
    SyncRunAccepted,
    SyncRunRequest,
    SyncRunSummary,
    SyncStatusRead,
)
from app.services.release_service import RELEASE_SYNC_SOURCE, ReleaseService
from app.services.release_sync_runner import release_sync_runner
from app.services.spotify_app_client import SpotifyAppClient

router = APIRouter(prefix="/api/releases", tags=["releases"])

# Default window for the Feed tab's "last 30 days / upcoming" view.
# During development it is 30 days back + 30 days ahead (roughly ±1 month) to
# limit ingestion volume. Before going to production, check that this satisfies
# the "last 30 days / upcoming" requirement in ADR-000 §220 and widen the
# lookback to e.g. 365 days if needed.
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
    """Return releases of artists the current user follows (archived=false)
    (ADR-007 §2.4). Read state is computed per user (ADR-007 §2.3)."""
    default_from, default_to = _default_window()
    items = service.list_window(current_user.id, from_date or default_from, to_date or default_to)
    return ListResponse(items=items)


# Note: `/sync-status` would need to be declared before a `/{spotify_id}`-style
# path, but these are two flat endpoints so there is no ordering conflict.
# We still keep an explicit order: list → status → sync.
@router.get("/sync-status", response_model=SyncStatusRead)
def get_sync_status(
    repo: SyncStatusRepository = Depends(get_sync_status_repository),
    _: User = Depends(get_current_user),
) -> SyncStatusRead:
    row = repo.get(RELEASE_SYNC_SOURCE)
    is_running = release_sync_runner.is_running
    result = release_sync_runner.last_result
    last_run = (
        SyncRunSummary(
            artists_total=result.artists_total,
            artists_succeeded=result.artists_succeeded,
            albums_ingested=result.albums_ingested,
            first_error=result.first_error,
        )
        if result is not None
        else None
    )
    if row is None:
        return SyncStatusRead(
            source=RELEASE_SYNC_SOURCE,
            last_success_at=None,
            last_attempt_at=None,
            last_error=None,
            is_running=is_running,
            last_run=last_run,
        )
    return SyncStatusRead(
        source=row.source,
        last_success_at=row.last_success_at,
        last_attempt_at=row.last_attempt_at,
        last_error=row.last_error,
        is_running=is_running,
        last_run=last_run,
    )


@router.patch("/{spotify_id}/read", response_model=ReleaseRead)
def set_release_read_status(
    spotify_id: str,
    payload: ReleaseReadStatusUpdate,
    service: ReleaseService = Depends(get_release_service),
    current_user: User = Depends(get_current_user),
) -> ReleaseRead:
    """Toggle a release's read flag per user (for the Feed unread dot, ADR-007).

    `is_read=true` upserts into `release_read_states` (read_at = now());
    `false` DELETEs the row. 404 if the release is not in the catalog.
    """
    with http_errors():
        return service.set_read_status(spotify_id, payload.is_read, current_user.id)


@router.post("/sync", response_model=SyncRunAccepted, status_code=status.HTTP_202_ACCEPTED)
def trigger_sync(
    background_tasks: BackgroundTasks,
    payload: SyncRunRequest | None = None,
    spotify: SpotifyAppClient = Depends(get_spotify_app_client),
    session_factory: SessionFactory = Depends(get_session_factory),
    current_user: User = Depends(get_current_user),
) -> SyncRunAccepted:
    """Ingest releases for all followed artists from Spotify (asynchronously).

    Because of Spotify rate limits a sync can take tens of seconds to minutes,
    so instead of running it inside the request we enqueue a background job and
    return 202 immediately. The frontend tracks progress by polling `is_running`
    on `/sync-status`. If a sync is already running we return already_running
    to avoid concurrent runs (Phase B-4 moves this to an APScheduler daily batch).
    """
    default_from, default_to = _default_window()
    since = (payload.since_date if payload else None) or default_from
    until = (payload.until_date if payload else None) or default_to
    if not release_sync_runner.try_begin():
        return SyncRunAccepted(status="already_running", is_running=True)
    background_tasks.add_task(
        release_sync_runner.run,
        current_user.id,
        spotify,
        since,
        until,
        session_factory,
    )
    return SyncRunAccepted(status="started", is_running=True)
