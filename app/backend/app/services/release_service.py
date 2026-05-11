"""Spotify Get Artist's Albums を user_follows 経由で日次同期するサービス層。

設計概要:
- artists マスタ全件ではなく、`user_follows` の archived_flag=false な行を対象に
  Spotify からアルバムを取り、releases テーブルに upsert する
- 1 アーティストが Spotify 側で 4xx / 5xx / network エラーを返しても他のアーティストの
  ingest は継続する (best-effort)。全件失敗時のみ SyncStatus.last_error にエラー
  メッセージを残し、それ以外は last_success_at を更新する
- `user_follows` が空のユーザに対しては artists マスタを bootstrap として seed
  する (Phase B-3 では Spotify follow 同期が未実装のため)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.core.exceptions import SpotifyApiError
from app.core.repositories.record_repository import RecordRepository
from app.core.repositories.release_repository import ReleaseRepository
from app.core.repositories.sync_status_repository import SyncStatusRepository
from app.core.repositories.user_follow_repository import UserFollowRepository
from app.models.release import Release
from app.seed import seed_user_follows_if_empty
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
        record_repo: RecordRepository,
        sync_repo: SyncStatusRepository,
    ) -> None:
        self.release_repo = release_repo
        self.follow_repo = follow_repo
        self.record_repo = record_repo
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
        1. user_follows が空なら既存 records の artist_id を backfill seed
           (auto-follow 実装前から records を持っているユーザ向けの one-shot)
        2. follow 中の artist_id 配列を取得
        3. 各 artist について `spotify.get_artist_albums` → `Release` に map →
           `release_repo.upsert_many` で 1 アーティストずつ commit
        4. 全成功 / 部分成功 → mark_success、全件失敗 → mark_error
        """
        self.sync_repo.mark_attempt(RELEASE_SYNC_SOURCE)
        seed_user_follows_if_empty(user_id, self.follow_repo, self.record_repo)
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
