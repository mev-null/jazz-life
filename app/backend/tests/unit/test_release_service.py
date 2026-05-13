"""ReleaseService.sync_for_user の挙動テスト。

Spotify API は SpotifyAppClient ごと Fake クラスで差し替えて、Repository は
DB セッションを通った実体を使う (Postgres trip により upsert / on-conflict /
foreign key constraint の挙動も含めて検証する)。

ADR-006 後 auto-follow が `user_collections` create と同 TX で走るため、follow の
backfill seed は無くなった。本ファイルでは user_follows を直接 INSERT して各
ケースを構築する。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.core.exceptions import SpotifyApiError
from app.core.repositories.release_repository import ReleaseRepository
from app.core.repositories.sync_status_repository import SyncStatusRepository
from app.core.repositories.user_follow_repository import UserFollowRepository
from app.models.artist import Artist
from app.models.release import Release
from app.models.user import User
from app.models.user_follow import UserFollow
from app.services.release_service import (
    RELEASE_SYNC_SOURCE,
    ReleaseService,
)
from app.services.spotify_app_client import SpotifyAlbumIngest


class FakeSpotifyClient:
    """SpotifyAppClient の get_artist_albums だけを差し替えるテストダブル。

    artist_id ごとに「返すデータ」または「投げる例外」を事前登録できる。
    呼び出し回数も記録する (rate limit のリトライ無効化の検証用)。
    """

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses: dict[str, Any] = responses or {}
        self.calls: list[str] = []

    def get_artist_albums(
        self,
        artist_id: str,
        since_date: date | None = None,
        until_date: date | None = None,
    ) -> list[SpotifyAlbumIngest]:
        self.calls.append(artist_id)
        resp = self.responses.get(artist_id, [])
        if isinstance(resp, Exception):
            raise resp
        return resp  # type: ignore[no-any-return]


def _seed_user(session: Session, spotify_id: str = "test-owner") -> User:
    user = User(spotify_id=spotify_id, display_name="Test Owner", refresh_token="")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _seed_artist(session: Session, spotify_id: str, name: str = "X") -> Artist:
    artist = Artist(
        spotify_id=spotify_id,
        name=name,
        source="seeded",
        added_at=datetime.now(UTC),
    )
    session.add(artist)
    session.commit()
    return artist


def _seed_follow(session: Session, user_id: UUID, artist_id: str) -> None:
    session.add(UserFollow(user_id=user_id, artist_id=artist_id))
    session.commit()


def _make_service(session: Session) -> ReleaseService:
    return ReleaseService(
        release_repo=ReleaseRepository(session),
        follow_repo=UserFollowRepository(session),
        sync_repo=SyncStatusRepository(session),
    )


def _ingest(
    id_: str,
    artist_id: str,
    name: str = "T",
    album_type: str = "album",
    release_date: date | None = None,
) -> SpotifyAlbumIngest:
    return SpotifyAlbumIngest(
        id=id_,
        name=name,
        album_type=album_type,
        release_date=release_date or date(2026, 1, 1),
        image_url=None,
        artist_id=artist_id,
    )


def test_sync_for_user_no_follows_is_noop_success(session: Session) -> None:
    """user_follows 空 → 何も叩かず success のみ更新。"""
    user = _seed_user(session)

    service = _make_service(session)
    spotify = FakeSpotifyClient()
    result = service.sync_for_user(
        user.id, spotify, since_date=date(2025, 1, 1), until_date=date(2027, 1, 1)
    )

    assert result.artists_total == 0
    assert result.albums_ingested == 0
    assert result.first_error is None
    status = SyncStatusRepository(session).get(RELEASE_SYNC_SOURCE)
    assert status is not None
    assert status.last_success_at is not None


def test_sync_for_user_continues_on_per_artist_5xx(session: Session) -> None:
    """1 アーティストが Spotify 5xx を返しても他のアーティストは ingest 継続。"""
    user = _seed_user(session)
    _seed_artist(session, "art-ok-1")
    _seed_artist(session, "art-server-error")
    _seed_artist(session, "art-ok-2")
    _seed_follow(session, user.id, "art-ok-1")
    _seed_follow(session, user.id, "art-server-error")
    _seed_follow(session, user.id, "art-ok-2")

    spotify = FakeSpotifyClient(
        responses={
            "art-ok-1": [_ingest("alb-1", "art-ok-1")],
            "art-server-error": SpotifyApiError("server error", status_code=500),
            "art-ok-2": [_ingest("alb-2", "art-ok-2")],
        }
    )
    result = _make_service(session).sync_for_user(
        user.id, spotify, since_date=date(2025, 1, 1), until_date=date(2027, 1, 1)
    )

    assert result.artists_total == 3
    assert result.artists_succeeded == 2
    assert result.albums_ingested == 2
    assert result.first_error is not None and "server error" in result.first_error
    status = SyncStatusRepository(session).get(RELEASE_SYNC_SOURCE)
    assert status is not None
    assert status.last_success_at is not None
    assert status.last_error is None


def test_sync_for_user_stops_early_on_rate_limit(session: Session) -> None:
    """Spotify 429 を踏んだら残りの artist は叩かず即中断する (limit window を延ばさないため)。"""
    user = _seed_user(session)
    _seed_artist(session, "art-ok-1")
    _seed_artist(session, "art-rate-limit")
    _seed_artist(session, "art-never-called")
    _seed_follow(session, user.id, "art-ok-1")
    _seed_follow(session, user.id, "art-rate-limit")
    _seed_follow(session, user.id, "art-never-called")

    spotify = FakeSpotifyClient(
        responses={
            "art-ok-1": [_ingest("alb-1", "art-ok-1")],
            "art-rate-limit": SpotifyApiError("rate limit", status_code=429),
            "art-never-called": [_ingest("alb-2", "art-never-called")],
        }
    )
    result = _make_service(session).sync_for_user(
        user.id, spotify, since_date=date(2025, 1, 1), until_date=date(2027, 1, 1)
    )

    assert result.artists_total == 3
    assert result.artists_succeeded == 1
    assert result.albums_ingested == 1
    assert result.first_error is not None and "rate limit" in result.first_error
    assert "art-never-called" not in spotify.calls
    status = SyncStatusRepository(session).get(RELEASE_SYNC_SOURCE)
    assert status is not None
    assert status.last_success_at is not None
    assert status.last_error is None


def test_sync_for_user_marks_error_when_all_artists_fail(session: Session) -> None:
    user = _seed_user(session)
    _seed_artist(session, "art-1")
    _seed_artist(session, "art-2")
    _seed_follow(session, user.id, "art-1")
    _seed_follow(session, user.id, "art-2")

    spotify = FakeSpotifyClient(
        responses={
            "art-1": SpotifyApiError("server error", status_code=500),
            "art-2": SpotifyApiError("rate limit", status_code=429),
        }
    )
    result = _make_service(session).sync_for_user(
        user.id, spotify, since_date=date(2025, 1, 1), until_date=date(2027, 1, 1)
    )

    assert result.artists_total == 2
    assert result.artists_succeeded == 0
    status = SyncStatusRepository(session).get(RELEASE_SYNC_SOURCE)
    assert status is not None
    assert status.last_error is not None and "server error" in status.last_error


def test_sync_for_user_upsert_preserves_is_read(session: Session) -> None:
    """既存の Release.is_read=True は sync 再実行で上書きされない。"""
    user = _seed_user(session)
    _seed_artist(session, "art-1")
    _seed_follow(session, user.id, "art-1")
    existing = Release(
        spotify_id="alb-1",
        artist_id="art-1",
        title="OLD TITLE",
        album_type="album",
        release_date=date(2026, 1, 1),
        is_read=True,
        read_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    session.add(existing)
    session.commit()

    spotify = FakeSpotifyClient(responses={"art-1": [_ingest("alb-1", "art-1", name="NEW TITLE")]})
    _make_service(session).sync_for_user(
        user.id, spotify, since_date=date(2025, 1, 1), until_date=date(2027, 1, 1)
    )

    session.expire_all()
    refreshed = session.get(Release, "alb-1")
    assert refreshed is not None
    assert refreshed.title == "NEW TITLE"
    assert refreshed.is_read is True
    assert refreshed.read_at is not None
