from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Phase B-3 では Get Artist's Albums の include_groups を `album,single` に絞って
# ingest しているので、UI 側でも 2 値だけが流れてくる前提。compilation /
# appears_on を将来追加するときはここを拡張して openapi 再生成する。
AlbumType = Literal["album", "single"]


class ReleaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    spotify_id: str
    artist_id: str
    title: str
    album_type: AlbumType
    release_date: date
    image_url: str | None
    is_read: bool
    read_at: datetime | None


class SyncStatusRead(BaseModel):
    """`/api/releases/sync-status` のレスポンス。

    フロント Feed 側で「最終同期日時 / エラー状態」を表示するため (ADR-000 §314)。
    Row が無い (一度も sync していない) ケースでは全フィールドが null になる。
    """

    model_config = ConfigDict(from_attributes=True)

    source: str
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    last_error: str | None


class SyncRunResult(BaseModel):
    """`POST /api/releases/sync` のレスポンス。

    artists_total = フォロー中アーティスト数 (= sync 対象の母数)。
    artists_succeeded = Spotify からアルバム取得に成功した数。
    albums_ingested = 取り込んだ release 行数 (upsert 含む)。
    first_error = 最初に発生したエラー (続行可能だったもの)。null なら全件成功。
    """

    artists_total: int
    artists_succeeded: int
    albums_ingested: int
    first_error: str | None


class SyncRunRequest(BaseModel):
    """`POST /api/releases/sync` の任意 body。

    省略時は service 側で `today - 365d` / `today + 30d` を採用する。
    """

    since_date: date | None = None
    until_date: date | None = None


class ReleaseReadStatusUpdate(BaseModel):
    """`PATCH /api/releases/{spotify_id}/read` の body。

    既読 / 未読のトグル用。True で既読 (read_at が now)、False で未読
    (read_at が null)。
    """

    is_read: bool = Field(...)
