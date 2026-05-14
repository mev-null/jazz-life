from typing import Annotated

from pydantic import BaseModel, Field


class UserFollowCreate(BaseModel):
    """`POST /api/user-follows` のリクエスト。

    artist は事前に `artists` テーブルに存在している必要がある (FK 制約)。
    UI 側は Spotify artist search → `POST /api/artists` (upsert) →
    本エンドポイント の 3 段で follow まで到達する想定。
    """

    artist_id: Annotated[str, Field(min_length=1, max_length=64)]
