from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ArtistSource = Literal["spotify", "manual"]


class ArtistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    spotify_id: str
    name: str
    image_url: str | None
    followed: bool
    source: ArtistSource
    added_at: datetime


class ArtistCreate(BaseModel):
    """新規 artist 作成リクエスト。upsert 動作 (spotify_id 既存なら既存を返す)。

    Phase B-3 PR-2 の RecordFormModal が Spotify album を選んだ時、
    その album の artist がまだ DB に無い場合に呼び出す。
    """

    spotify_id: Annotated[str, Field(min_length=1, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    image_url: str | None = None
    source: ArtistSource = "spotify"
