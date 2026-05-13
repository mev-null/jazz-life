"""Spotify Get Artist's Albums を user_follows 経由で日次同期するサービス層。

設計概要:
- artists マスタ全件ではなく、`user_follows` の archived_flag=false な行を対象に
  Spotify からアルバムを取り、releases テーブルに upsert する
- 1 アーティストが Spotify 側で 4xx / 5xx / network エラーを返しても他のアーティストの
  ingest は継続する (best-effort)。全件失敗時のみ SyncStatus.last_error にエラー
  メッセージを残し、それ以外は last_success_at を更新する
- ADR-006 以降 auto-follow が `user_collections` create と同 TX で走るため、
  follow の backfill seed は不要 (旧 `seed_user_follows_if_empty` は削除)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.core.exceptions import SpotifyApiError
from app.core.repositories.release_repository import ReleaseRepository
from app.core.repositories.sync_status_repository import SyncStatusRepository
from app.core.repositories.user_follow_repository import UserFollowRepository
from app.models.release import Release
from app.services.spotify_app_client import SpotifyAlbumIngest, SpotifyAppClient

logger = logging.getLogger("uvicorn.error")

# SyncStatus.source の値。Phase B-4 で concerts などを足すときに重複を避けるため
# 定数で固定する。
RELEASE_SYNC_SOURCE = "spotify_releases"


@dataclass(frozen=True)
class SyncResult:
    artists_total: int
    artists_succeeded: int
    albums_ingested: int
    first_error: str | None


class ReleaseService:
    def __init__(
        self,
        release_repo: ReleaseRepository,
        follow_repo: UserFollowRepository,
        sync_repo: SyncStatusRepository,
    ) -> None:
        self.release_repo = release_repo
        self.follow_repo = follow_repo
        self.sync_repo = sync_repo

    def list_window(self, from_date: date, to_date: date) -> list[Release]:
        return self.release_repo.list_window(from_date, to_date)

    def sync_for_user(
        self,
        user_id: UUID,
        spotify: SpotifyAppClient,
        since_date: date,
        until_date: date,
    ) -> SyncResult:
        """フォロー中アーティストの新譜を Spotify から取り込んで upsert する。

        フロー:
        1. follow 中の artist_id 配列を取得 (auto-follow が record 作成時に走る
           ため、record を持っていれば既に follow にも入っている)
        2. 各 artist について `spotify.get_artist_albums` → `Release` に map →
           `release_repo.upsert_many` で 1 アーティストずつ commit
        3. 全成功 / 部分成功 → mark_success、全件失敗 → mark_error
        """
        self.sync_repo.mark_attempt(RELEASE_SYNC_SOURCE)
        artist_ids = self.follow_repo.list_artist_ids(user_id)
        total = len(artist_ids)
        succeeded = 0
        albums_ingested = 0
        first_error: str | None = None
        for artist_id in artist_ids:
            try:
                ingests = spotify.get_artist_albums(
                    artist_id, since_date=since_date, until_date=until_date
                )
            except SpotifyApiError as exc:
                logger.warning("release sync failed for artist_id=%s: %s", artist_id, exc)
                if first_error is None:
                    first_error = f"{artist_id}: {exc}"
                if exc.status_code == 429:
                    # Spotify rate limit (rolling 30s window) を踏んだ。残りの artist を
                    # 続けて叩いてもどの request も 429 で返ってくるだけで、limit window
                    # を延ばしてしまうので即中断する。残りは次回 sync で取り込む。
                    # https://developer.spotify.com/documentation/web-api/concepts/rate-limits
                    logger.warning(
                        "release sync stopped early due to spotify rate limit; "
                        "remaining artists deferred to next sync"
                    )
                    break
                continue
            rows = [_to_release(item) for item in ingests]
            self.release_repo.upsert_many(rows)
            succeeded += 1
            albums_ingested += len(rows)
        if total > 0 and succeeded == 0:
            # 全件失敗 → エラー状態。last_success_at は据え置き。
            assert first_error is not None
            self.sync_repo.mark_error(RELEASE_SYNC_SOURCE, first_error)
        else:
            # 0 件 follow (no-op) も「失敗ではない」ので success 扱い。
            self.sync_repo.mark_success(RELEASE_SYNC_SOURCE)
        return SyncResult(
            artists_total=total,
            artists_succeeded=succeeded,
            albums_ingested=albums_ingested,
            first_error=first_error,
        )


def _to_release(item: SpotifyAlbumIngest) -> Release:
    return Release(
        spotify_id=item.id,
        artist_id=item.artist_id,
        title=item.name,
        album_type=item.album_type,
        release_date=item.release_date,
        image_url=item.image_url,
    )
