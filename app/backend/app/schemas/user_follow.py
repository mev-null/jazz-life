from typing import Annotated

from pydantic import BaseModel, Field


class UserFollowCreate(BaseModel):
    """Request body of `POST /api/user-follows`.

    The artist must already exist in the `artists` table (FK constraint).
    The UI is expected to reach a follow in three steps: Spotify artist
    search → `POST /api/artists` (upsert) → this endpoint.
    """

    artist_id: Annotated[str, Field(min_length=1, max_length=64)]
