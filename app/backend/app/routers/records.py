import uuid

from fastapi import APIRouter, Depends, Query, status

from app.models.user import User
from app.routers._handlers import http_errors
from app.routers.deps import get_current_user, get_record_service
from app.schemas.common import ListResponse
from app.schemas.record import (
    PinReorderRequest,
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
    service: RecordService = Depends(get_record_service),
    current_user: User = Depends(get_current_user),
) -> ListResponse[VinylRecordRead]:
    """current user の collection を返す (ADR-006 §3.4)。

    `limit` を渡すと paginated。レスポンス `total` は user の collection 全件数
    なので、フロント側で `Math.ceil(total / limit)` でページ数を出せる。limit
    省略時は全件 + total を返す (従来挙動を維持)。並び順は
    `is_pinned DESC, display_order ASC` 固定。
    """
    items, total = service.list_for_user(current_user.id, limit=limit, offset=offset)
    return ListResponse(items=items, total=total)


@router.post("", response_model=VinylRecordRead, status_code=status.HTTP_201_CREATED)
def create_record(
    body: VinylRecordCreate,
    service: RecordService = Depends(get_record_service),
    current_user: User = Depends(get_current_user),
) -> VinylRecordRead:
    """record を 1 件作成。catalog find-or-create + user_collections INSERT +
    auto-follow を 1 TX で行う。UNIQUE(user_id, vinyl_record_id) 違反は 409。"""
    with http_errors():
        return service.create(body, current_user.id)


@router.put("/pins/order", status_code=status.HTTP_204_NO_CONTENT)
def reorder_pins(
    body: PinReorderRequest,
    service: RecordService = Depends(get_record_service),
    current_user: User = Depends(get_current_user),
) -> None:
    """ピン済みレコードの並び順を drag & drop 後に保存する。

    body の `ids` は現在 pin しているすべての user_collection.id を、望む順序で
    並べたもの。current pin セットと一致しない場合は 409。
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
    """user_collections を user_id ガード付きで部分更新。catalog 系は
    `source='manual'` のみ書く (ADR-006 §2.5)。`spotify_album_id` を埋め直すと
    manual→spotify promote 経路 (§2.9)。"""
    with http_errors():
        return service.update_partial(id, body, current_user.id)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(
    id: uuid.UUID,
    service: RecordService = Depends(get_record_service),
    current_user: User = Depends(get_current_user),
) -> None:
    """user_collections を物理削除 (favorites も CASCADE)。catalog は触らない。"""
    with http_errors():
        service.delete(id, current_user.id)
