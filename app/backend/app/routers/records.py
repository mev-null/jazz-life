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
) -> ListResponse[VinylRecordRead]:
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
) -> VinylRecordRead:
    with http_errors():
        record = service.update_partial(id, body)
        return VinylRecordRead.model_validate(record)
