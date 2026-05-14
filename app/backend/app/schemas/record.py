import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class PinReorderRequest(BaseModel):
    """drag & drop で並び替えた pinned レコードの id 列。

    `ids` は user が現在 pin している全行を、ユーザが望む順序で並べたもの。
    backend は 1..N で `pin_order` を再採番する。欠け/重複/未 pin 行混入は 409。
    """

    ids: list[uuid.UUID]


RecordSource = Literal["spotify", "manual"]
# ADR-003 §2.1: "owned" は Home マトリクスに表示、"wanted" は want list 専用。
RecordStatus = Literal["owned", "wanted"]

_DATE_PATTERN = r"^\d{4}(-\d{2}(-\d{2})?)?$"
_CURRENCY_PATTERN = r"^[A-Z]{3}$"


class FavoriteTrack(BaseModel):
    """ADR-006 §2.8: アルバム内の「お気に入り曲」1 件分。

    `spotify_track_id` は Spotify Get Album Tracks の id (manual 時は省略可)。
    `note` は曲ごとの短い所感 (裏ジャケに走り書きしたメモ)。
    """

    model_config = ConfigDict(from_attributes=True)

    spotify_track_id: str | None = None
    track_name: str
    note: str | None = None


class VinylRecordRead(BaseModel):
    """ADR-006: response shape は catalog + ownership を flat に並べて維持。

    `id` は `user_collections.id` を返す (frontend からは 1 件の record と見える)。
    `favorite_tracks` は構造化リスト (position 昇順)。
    """

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
    favorite_tracks: list[FavoriteTrack]
    display_order: int
    is_pinned: bool
    # ピン済みレコードの並び順 (drag & drop で書き換える)。非 pin 行は null。
    # フロントが pin リストを表示順で並べるのに使う。
    pin_order: int | None
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
    favorite_tracks: list[FavoriteTrack] | None = None


class VinylRecordUpdate(BaseModel):
    """ADR-002 寛容 PUT: omit したフィールドは no-op、明示的に null/`[]` を
    送った場合のみ clear する (`exclude_unset` 経由)。
    """

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
    favorite_tracks: list[FavoriteTrack] | None = None
    display_order: int | None = None
    is_pinned: bool | None = None
