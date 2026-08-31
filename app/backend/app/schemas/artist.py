from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ADR-003 §2.1: source takes one of three values
# - "seeded": initial seed data (from artists.json)
# - "spotify_dynamic": added dynamically from Spotify search (upsert from RecordFormModal)
# - "manual": from a future manual-entry endpoint
ArtistSource = Literal["seeded", "spotify_dynamic", "manual"]


class ArtistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    spotify_id: str
    name: str
    image_url: str | None
    source: ArtistSource
    added_at: datetime


class ArtistRecordCount(BaseModel):
    """Lightweight row for the count column of the ArtistsPage list.

    Records themselves are not fetched until ArtistDetailModal opens, so the
    list gets just the "N records" figure up front from the separate endpoint
    `/api/user-follows/record-counts` (auth required; counts only the current
    user's owned records).
    """

    artist_id: str
    count: int


class ArtistCreate(BaseModel):
    """Create-artist request; upserts (returns the existing row if spotify_id exists).

    Called by the Phase B-3 PR-2 RecordFormModal when a Spotify album is
    selected and the album's artist is not yet in the DB.
    """

    spotify_id: Annotated[str, Field(min_length=1, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    image_url: str | None = None
    source: ArtistSource = "spotify_dynamic"
