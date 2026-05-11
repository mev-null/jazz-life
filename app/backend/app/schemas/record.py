import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

RecordSource = Literal["spotify", "manual"]
# ADR-003 §2.1: "owned" は Home マトリクスに表示、"wanted" は want list 専用。
RecordStatus = Literal["owned", "wanted"]

_DATE_PATTERN = r"^\d{4}(-\d{2}(-\d{2})?)?$"
_CURRENCY_PATTERN = r"^[A-Z]{3}$"


class VinylRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    artist_id: str
    spotify_album_id: str | None
    source: RecordSource
    status: RecordStatus
    title: str
    image_url: str | None
    original_release_date: str | None
    pressing_info: str | None
    purchase_date: date | None
    purchase_store: str | None
    purchase_price: int | None
    purchase_currency: str
    rating: int | None
    memo: str | None
    favorite_tracks: str | None
    display_order: int
    created_at: datetime
    updated_at: datetime


class VinylRecordCreate(BaseModel):
    artist_id: str
    spotify_album_id: str | None = None
    source: RecordSource = "manual"
    status: RecordStatus = "owned"
    title: str
    image_url: str | None = None
    original_release_date: Annotated[str | None, Field(pattern=_DATE_PATTERN)] = None
    pressing_info: str | None = None
    purchase_date: date | None = None
    purchase_store: str | None = None
    purchase_price: int | None = None
    purchase_currency: Annotated[str, Field(pattern=_CURRENCY_PATTERN)] = "JPY"
    rating: Annotated[int | None, Field(ge=1, le=5)] = None
    memo: str | None = None
    favorite_tracks: str | None = None


class VinylRecordUpdate(BaseModel):
    artist_id: str | None = None
    spotify_album_id: str | None = None
    source: RecordSource | None = None
    status: RecordStatus | None = None
    title: str | None = None
    image_url: str | None = None
    original_release_date: Annotated[str | None, Field(pattern=_DATE_PATTERN)] = None
    pressing_info: str | None = None
    purchase_date: date | None = None
    purchase_store: str | None = None
    purchase_price: int | None = None
    purchase_currency: Annotated[str | None, Field(pattern=_CURRENCY_PATTERN)] = None
    rating: Annotated[int | None, Field(ge=1, le=5)] = None
    memo: str | None = None
    favorite_tracks: str | None = None
    display_order: int | None = None
