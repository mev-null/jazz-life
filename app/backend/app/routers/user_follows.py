"""API for user_follows operations.

- GET /api/user-follows/artists: artists the current user follows (archived=false)
- GET /api/user-follows/record-counts: current user's owned record count per artist_id
- POST /api/user-follows: explicitly follow an artist (for the "add" UI on ArtistsPage)
- DELETE /api/user-follows/{artist_id}: unfollow (soft delete)

Alongside the auto-follow that happens on record creation (RecordService.create),
this router also handles the path where a user picks an artist from Spotify search
on ArtistsPage and creates a follow.
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
    """Return the artists the current user follows (archived=false).

    Dedicated to the ArtistsPage list. `GET /api/artists` is the global registry
    (used e.g. for record→artist name lookup on HomePage), hence a separate
    endpoint.
    """
    rows = artist_repo.list_followed_by(current_user.id)
    return ListResponse(items=[ArtistRead.model_validate(row) for row in rows])


# Note: `/record-counts` is declared before `/{artist_id}` (DELETE).
# FastAPI matches in declaration order, but the HTTP methods differ (GET vs
# DELETE) so there is no ordering conflict. Listing endpoints are grouped first
# for readability.
@router.get("/record-counts", response_model=ListResponse[ArtistRecordCount])
def list_record_counts(
    current_user: User = Depends(get_current_user),
    service: RecordService = Depends(get_record_service),
) -> ListResponse[ArtistRecordCount]:
    """Return the current user's owned record count aggregated per artist_id.

    Dedicated to the count column of the ArtistsPage list; avoids fetching all
    records. Moved here from the old `/api/artists/record-counts` because the
    aggregation unit matches follows (semantically consistent under
    user-follows), and scoped by user_id at the same time. Only status='owned'
    is counted (the want list is excluded).
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
    """Add `artist_id` to the current user's follows.

    Idempotent because it uses `UserFollowRepository.upsert`:
    - already an active follow: overwrite is a no-op, 201 + existing artist
    - an archived row exists: reset archived_flag=false and re-follow
    - no row: new INSERT

    404 if the artist is not in the `artists` table. The UI is expected to
    upsert it first via `POST /api/artists` (passing the Spotify search result
    metadata as-is).
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
    """Unfollow the artist with this Spotify ID (soft delete: archived_flag=true).

    Only sets archived_flag, so the "previously followed" history is kept.
    list_artist_ids returns archived_flag=false rows only, so the next release
    sync excludes this artist.

    404 if there is nothing to remove; 204 if already archived (idempotent).
    """
    ok = follow_repo.archive(current_user.id, artist_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"user_follows not found: artist_id={artist_id}",
        )
