import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class PinReorderRequest(BaseModel):
    """The id sequence of pinned records after a drag & drop reorder.

    `ids` is every row the user currently has pinned, in the user's desired
    order. The backend renumbers `pin_order` as 1..N. Missing / duplicate /
    unpinned ids return 409.
    """

    ids: list[uuid.UUID]


RecordSource = Literal["spotify", "manual"]
# ADR-003 §2.1: "owned" is shown in the Home matrix, "wanted" is want-list only.
RecordStatus = Literal["owned", "wanted"]
# Constants for the service layer to reference instead of bare string literals.
RECORD_STATUS_OWNED: RecordStatus = "owned"
RECORD_STATUS_WANTED: RecordStatus = "wanted"
# ADR-013: sort axis for the Hunt list in Digging.
# "artist" = artist name asc (then title); "added" = on-the-hunt date (created_at) desc.
# When omitted, the legacy is_pinned/display_order order is used (for the Home matrix).
RecordSort = Literal["artist", "added"]

_DATE_PATTERN = r"^\d{4}(-\d{2}(-\d{2})?)?$"
_CURRENCY_PATTERN = r"^[A-Z]{3}$"


class FavoriteTrack(BaseModel):
    """ADR-006 §2.8: one "favorite track" within an album.

    `spotify_track_id` is the id from Spotify Get Album Tracks (optional for
    manual records). `note` is a short per-track impression (like a note
    scribbled on the back cover).
    """

    model_config = ConfigDict(from_attributes=True)

    spotify_track_id: str | None = None
    track_name: str
    note: str | None = None


class VinylRecordRead(BaseModel):
    """ADR-006: the response shape stays flat, combining catalog + ownership.

    `id` is `user_collections.id` (the frontend sees it as a single record).
    `favorite_tracks` is a structured list (ascending by position).
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
    # Order among pinned records (rewritten via drag & drop). null for unpinned rows.
    # The frontend uses it to sort the pin list for display.
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
    """ADR-002 lenient PUT: omitted fields are a no-op; a field is cleared only
    when null/`[]` is sent explicitly (via `exclude_unset`).
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
