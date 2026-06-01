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


class SyncRunSummary(BaseModel):
    """直近に完走した sync ジョブの結果サマリ。

    sync_status の last_* (DB 永続) と違い in-memory 由来 (プロセス再起動で消える)。
    フロントが「partial: N ingested / rate limited」等の補足表示に使う。
    artists_succeeded < artists_total なら一部のアーティストが取り込めていない
    (rate limit で打ち切り or per-artist エラー)。
    """

    artists_total: int
    artists_succeeded: int
    albums_ingested: int
    first_error: str | None


class SyncStatusRead(BaseModel):
    """`/api/releases/sync-status` のレスポンス。

    フロント Feed 側で「最終同期日時 / エラー状態」を表示するため (ADR-000 §314)。
    Row が無い (一度も sync していない) ケースでは last_* が null になる。
    """

    model_config = ConfigDict(from_attributes=True)

    source: str
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    last_error: str | None
    # sync が今まさにバックグラウンド実行中か。フロントはこれを polling して
    # ローディング表示する。in-memory フラグ由来で DB には永続化しない。
    is_running: bool
    # 直近完走ジョブの結果サマリ (in-memory)。未実行 / 再起動直後は null。
    last_run: SyncRunSummary | None = None


class SyncRunAccepted(BaseModel):
    """`POST /api/releases/sync` のレスポンス (202 Accepted)。

    sync はバックグラウンド実行に切り出したため、件数などの結果は同期的に
    返さない。フロントは `is_running` を見てローディングし、`/sync-status` を
    polling して完了 / エラーを知る。
    - status=started: 今回ジョブを投入した
    - status=already_running: 既に実行中だったので投入をスキップした
    """

    status: Literal["started", "already_running"]
    is_running: bool


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
