from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ArtistSource = Literal["spotify", "manual"]


class ArtistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    spotify_id: str
    name: str
    image_url: str | None
    followed: bool
    source: ArtistSource
    added_at: datetime
