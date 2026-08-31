from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Phase B-3 ingests Get Artist's Albums with include_groups limited to
# `album,single`, so the UI only ever sees these two values. When adding
# compilation / appears_on later, extend this and regenerate the openapi spec.
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


class SyncRunSummary(BaseModel):
    """Result summary of the most recently completed sync job.

    Unlike the last_* fields of sync_status (persisted in the DB), this is
    in-memory and lost on process restart. The frontend uses it for
    supplementary text such as "partial: N ingested / rate limited".
    artists_succeeded < artists_total means some artists were not ingested
    (cut off by rate limiting, or a per-artist error).
    """

    artists_total: int
    artists_succeeded: int
    albums_ingested: int
    first_error: str | None


class SyncStatusRead(BaseModel):
    """Response of `/api/releases/sync-status`.

    Lets the Feed show "last synced at / error state" (ADR-000 §314).
    When no row exists (never synced), the last_* fields are null.
    """

    model_config = ConfigDict(from_attributes=True)

    source: str
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    last_error: str | None
    # Whether a sync is currently running in the background. The frontend polls
    # this to show a loading state. Comes from an in-memory flag, not persisted.
    is_running: bool
    # Summary of the last completed job (in-memory). null if never run or right after restart.
    last_run: SyncRunSummary | None = None


class SyncRunAccepted(BaseModel):
    """Response of `POST /api/releases/sync` (202 Accepted).

    Since the sync runs in the background, results such as counts are not
    returned synchronously. The frontend shows a loading state based on
    `is_running` and polls `/sync-status` to learn about completion / errors.
    - status=started: a job was enqueued by this request
    - status=already_running: a sync was already running, so enqueueing was skipped
    """

    status: Literal["started", "already_running"]
    is_running: bool


class SyncRunRequest(BaseModel):
    """Optional body of `POST /api/releases/sync`.

    When omitted, the service falls back to `today - 365d` / `today + 30d`.
    """

    since_date: date | None = None
    until_date: date | None = None


class ReleaseReadStatusUpdate(BaseModel):
    """Body of `PATCH /api/releases/{spotify_id}/read`.

    Toggles read / unread. True marks as read (read_at = now), False marks as
    unread (read_at = null).
    """

    is_read: bool = Field(...)
