import uuid

from fastapi import APIRouter, Depends, status

from app.models.user import User
from app.routers._handlers import http_errors
from app.routers.deps import get_current_user, get_record_service
from app.schemas.common import ListResponse
from app.schemas.record import VinylRecordCreate, VinylRecordRead, VinylRecordUpdate
from app.services.record_service import RecordService

router = APIRouter(prefix="/api/records", tags=["records"])


@router.get("", response_model=ListResponse[VinylRecordRead])
def list_records(
    service: RecordService = Depends(get_record_service),
    _: User = Depends(get_current_user),
) -> ListResponse[VinylRecordRead]:
    """auth 必須。records が user-scope されるのは別 PR (ADR-006) で対応。
    本 PR は「未認証で全レコードが list できる」状態を閉塞するための入口ガード。"""
    rows = service.list_all()
    return ListResponse(items=[VinylRecordRead.model_validate(row) for row in rows])


@router.post("", response_model=VinylRecordRead, status_code=status.HTTP_201_CREATED)
def create_record(
    body: VinylRecordCreate,
    service: RecordService = Depends(get_record_service),
    current_user: User = Depends(get_current_user),
) -> VinylRecordRead:
    """record を 1 件作成。RecordService.create が同時に user_follows に
    auto-follow を入れるので、続く release sync で正しく対象になる。"""
    with http_errors():
        record = service.create(body, current_user.id)
        return VinylRecordRead.model_validate(record)


@router.put("/{id}", response_model=VinylRecordRead)
def update_record(
    id: uuid.UUID,
    body: VinylRecordUpdate,
    service: RecordService = Depends(get_record_service),
    _: User = Depends(get_current_user),
) -> VinylRecordRead:
    with http_errors():
        record = service.update_partial(id, body)
        return VinylRecordRead.model_validate(record)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(
    id: uuid.UUID,
    service: RecordService = Depends(get_record_service),
    _: User = Depends(get_current_user),
) -> None:
    """record を物理削除。auth 必須 (POST と揃える)。

    user_follows は意図的に触らないので、最後の 1 件を消しても follow は残り、
    次の sync では引き続き対象になる。
    """
    with http_errors():
        service.delete(id)
