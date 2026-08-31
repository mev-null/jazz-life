import uuid

from fastapi import APIRouter, Depends, Query, status

from app.models.user import User
from app.routers._handlers import http_errors
from app.routers.deps import get_current_user, get_record_service
from app.schemas.common import ListResponse
from app.schemas.record import (
    PinReorderRequest,
    RecordSort,
    RecordStatus,
    VinylRecordCreate,
    VinylRecordRead,
    VinylRecordUpdate,
)
from app.services.record_service import RecordService

router = APIRouter(prefix="/api/records", tags=["records"])


@router.get("", response_model=ListResponse[VinylRecordRead])
def list_records(
    limit: int | None = Query(None, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: RecordStatus | None = Query(None),
    sort: RecordSort | None = Query(None),
    service: RecordService = Depends(get_record_service),
    current_user: User = Depends(get_current_user),
) -> ListResponse[VinylRecordRead]:
    """Return the current user's collection (ADR-006 §3.4).

    Passing `limit` paginates. The response `total` is the size of the user's
    collection (after the `status` filter), so the frontend can derive the page
    count with `Math.ceil(total / limit)`.

    - `status`: filter by owned / wanted (the ADR-013 Hunt list uses `wanted`).
    - `sort`: `artist` (artist name, then title, ascending) / `added`
      (created_at descending). Defaults to
      `is_pinned DESC, pin_order ASC, display_order ASC` (for the Home matrix).
    """
    items, total = service.list_for_user(
        current_user.id, limit=limit, offset=offset, status=status, sort=sort
    )
    return ListResponse(items=items, total=total)


@router.post("", response_model=VinylRecordRead, status_code=status.HTTP_201_CREATED)
def create_record(
    body: VinylRecordCreate,
    service: RecordService = Depends(get_record_service),
    current_user: User = Depends(get_current_user),
) -> VinylRecordRead:
    """Create one record: catalog find-or-create + user_collections INSERT +
    auto-follow in a single transaction. UNIQUE(user_id, vinyl_record_id)
    violations return 409."""
    with http_errors():
        return service.create(body, current_user.id)


@router.put("/pins/order", status_code=status.HTTP_204_NO_CONTENT)
def reorder_pins(
    body: PinReorderRequest,
    service: RecordService = Depends(get_record_service),
    current_user: User = Depends(get_current_user),
) -> None:
    """Persist the order of pinned records after a drag & drop.

    `ids` in the body is every currently pinned user_collection.id in the
    desired order. 409 if it does not match the current pin set.
    """
    with http_errors():
        service.reorder_pins(current_user.id, body.ids)


@router.put("/{id}", response_model=VinylRecordRead)
def update_record(
    id: uuid.UUID,
    body: VinylRecordUpdate,
    service: RecordService = Depends(get_record_service),
    current_user: User = Depends(get_current_user),
) -> VinylRecordRead:
    """Partially update user_collections, guarded by user_id. Catalog fields
    are written only when `source='manual'` (ADR-006 §2.5). Setting
    `spotify_album_id` takes the manual→spotify promotion path (§2.9)."""
    with http_errors():
        return service.update_partial(id, body, current_user.id)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(
    id: uuid.UUID,
    service: RecordService = Depends(get_record_service),
    current_user: User = Depends(get_current_user),
) -> None:
    """Hard-delete the user_collections row (favorites CASCADE). The catalog is untouched."""
    with http_errors():
        service.delete(id, current_user.id)
