from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ADR-003 §2.1: source は 3 値を取る
# - "seeded": 初期投入 (artists.json から)
# - "spotify_dynamic": Spotify 検索由来で動的追加 (RecordFormModal から upsert)
# - "manual": 将来の手入力エンドポイント由来
ArtistSource = Literal["seeded", "spotify_dynamic", "manual"]


class ArtistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    spotify_id: str
    name: str
    image_url: str | None
    source: ArtistSource
    added_at: datetime


class ArtistRecordCount(BaseModel):
    """ArtistsPage 一覧の件数列に渡す軽量行。

    records 本体は ArtistDetailModal を開くまで fetch しない方針のため、
    一覧では「N records」表示だけ別エンドポイント `/api/user-follows/record-counts`
    から先に取れるようにする (auth 必須、current user 所有 owned のみ集計)。
    """

    artist_id: str
    count: int


class ArtistCreate(BaseModel):
    """新規 artist 作成リクエスト。upsert 動作 (spotify_id 既存なら既存を返す)。

    Phase B-3 PR-2 の RecordFormModal が Spotify album を選んだ時、
    その album の artist がまだ DB に無い場合に呼び出す。
    """

    spotify_id: Annotated[str, Field(min_length=1, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    image_url: str | None = None
    source: ArtistSource = "spotify_dynamic"
