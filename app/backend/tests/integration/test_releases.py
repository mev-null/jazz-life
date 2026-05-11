"""`/api/releases` 系エンドポイントの統合テスト。

- GET /api/releases: 期間窓 / ソート / 空状態
- POST /api/releases/sync: 未認証 401、認証済で Spotify を httpx_mock 偽装して 200
- GET /api/releases/sync-status: row なし / 後に成功状態
"""

import re
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock
from sqlmodel import Session

from app.core.db import get_session
from app.core.settings import Settings, get_settings
from app.main import app
from app.models.artist import Artist
from app.models.release import Release
from app.models.user import User
from app.models.user_follow import UserFollow
from app.routers.deps import get_current_user, get_spotify_app_client
from app.services.spotify_app_client import SPOTIFY_TOKEN_URL, SpotifyAppClient
from tests.conftest import make_settings

_ARTIST_ALBUMS_URL_PATTERN = re.compile(r"^https://api\.spotify\.com/v1/artists/[^/]+/albums")


def _token_response() -> dict[str, Any]:
    return {"access_token": "BQA-app-token", "token_type": "Bearer", "expires_in": 3600}


def _albums_page(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"items": items, "limit": 50, "offset": 0, "total": len(items)}


def _album(
    id_: str = "alb-1",
    name: str = "Some Album",
    album_type: str = "album",
    release_date: str = "2026-05-15",
    release_date_precision: str = "day",
) -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "album_type": album_type,
        "release_date": release_date,
        "release_date_precision": release_date_precision,
        "images": [],
    }


@pytest.fixture
def _test_settings() -> Settings:
    return make_settings()


@pytest.fixture
def unauthed_client(session: Session, _test_settings: Settings) -> Iterator[TestClient]:
    """`POST /api/releases/sync` の未認証 → 401 を検証するため auth override 無し。"""

    def _override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: _test_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def authed_client(session: Session, _test_settings: Settings) -> Iterator[TestClient]:
    """auth + Spotify app client を fake で固定した TestClient。

    - get_current_user は固定ユーザを返す
    - get_spotify_app_client は毎回新規インスタンスを返す (httpx_mock の対象になる)
    """

    user = User(spotify_id="test-owner", display_name="Test Owner", refresh_token="")
    session.add(user)
    session.commit()
    session.refresh(user)

    def _override_session() -> Iterator[Session]:
        yield session

    def _override_user() -> User:
        return user

    def _override_spotify() -> SpotifyAppClient:
        return SpotifyAppClient(_test_settings)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: _test_settings
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_spotify_app_client] = _override_spotify
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---- GET /api/releases ----


def test_get_releases_empty(unauthed_client: TestClient) -> None:
    res = unauthed_client.get("/api/releases")
    assert res.status_code == 200
    assert res.json() == {"items": []}


def test_get_releases_returns_within_window_and_sorts_desc(
    unauthed_client: TestClient, session: Session
) -> None:
    today = date.today()
    session.add(Artist(spotify_id="art-1", name="A", source="seeded", added_at=datetime.now(UTC)))
    session.commit()
    session.add_all(
        [
            Release(
                spotify_id="r-old",
                artist_id="art-1",
                title="Old",
                album_type="album",
                release_date=today - timedelta(days=400),  # 窓外 (デフォルト 30 日)
            ),
            Release(
                spotify_id="r-recent",
                artist_id="art-1",
                title="Recent",
                album_type="album",
                release_date=today - timedelta(days=10),
            ),
            Release(
                spotify_id="r-upcoming",
                artist_id="art-1",
                title="Upcoming",
                album_type="single",
                release_date=today + timedelta(days=20),
            ),
        ]
    )
    session.commit()

    res = unauthed_client.get("/api/releases")
    body = res.json()
    ids = [r["spotify_id"] for r in body["items"]]
    # r-old は窓外なので除外、新しい順 (release_date desc)
    assert ids == ["r-upcoming", "r-recent"]


def test_get_releases_accepts_custom_window(unauthed_client: TestClient, session: Session) -> None:
    session.add(Artist(spotify_id="art-1", name="A", source="seeded", added_at=datetime.now(UTC)))
    session.commit()
    session.add(
        Release(
            spotify_id="r-1",
            artist_id="art-1",
            title="T",
            album_type="album",
            release_date=date(2024, 6, 15),
        )
    )
    session.commit()

    # デフォルト窓では取れない 2024 年のリリースを from/to 指定で取れる
    res = unauthed_client.get("/api/releases", params={"from": "2024-01-01", "to": "2024-12-31"})
    assert res.status_code == 200
    assert [r["spotify_id"] for r in res.json()["items"]] == ["r-1"]


# ---- GET /api/releases/sync-status ----


def test_sync_status_returns_null_fields_when_never_synced(
    unauthed_client: TestClient,
) -> None:
    res = unauthed_client.get("/api/releases/sync-status")
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "spotify_releases"
    assert body["last_success_at"] is None
    assert body["last_attempt_at"] is None
    assert body["last_error"] is None


# ---- POST /api/releases/sync ----


def test_post_sync_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.post("/api/releases/sync")
    assert res.status_code == 401


def test_post_sync_seeds_follows_and_ingests_albums(
    authed_client: TestClient,
    session: Session,
    httpx_mock: HTTPXMock,
) -> None:
    """user_follows が空の状態から POST sync 1 発で:
    1. records 由来で user_follows が backfill される (auto-follow 実装前のレガシー
       records を持つユーザの one-shot 移行経路)
    2. 各 artist の Spotify アルバムが releases に upsert される
    3. sync_status が last_success_at 付きで更新される
    """
    from app.models.record import VinylRecord

    # records が先にある状態 (auto-follow 前のレガシー状態を再現)
    now = datetime.now(UTC)
    session.add_all(
        [
            Artist(spotify_id="art-A", name="A", source="manual", added_at=now),
            Artist(spotify_id="art-B", name="B", source="manual", added_at=now),
        ]
    )
    session.commit()
    session.add_all(
        [
            VinylRecord(
                artist_id="art-A",
                title="t1",
                source="manual",
                status="owned",
                display_order=1,
                created_at=now,
                updated_at=now,
            ),
            VinylRecord(
                artist_id="art-B",
                title="t2",
                source="manual",
                status="owned",
                display_order=2,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()
    today = date.today().isoformat()
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN,
        method="GET",
        json=_albums_page([_album(id_="alb-A1", release_date=today)]),
    )
    httpx_mock.add_response(
        url=_ARTIST_ALBUMS_URL_PATTERN,
        method="GET",
        json=_albums_page([_album(id_="alb-B1", release_date=today)]),
    )

    res = authed_client.post("/api/releases/sync")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["artists_total"] == 2
    assert body["artists_succeeded"] == 2
    assert body["albums_ingested"] == 2
    assert body["first_error"] is None

    # follow bootstrap が走ったこと
    session.expire_all()
    from sqlmodel import select

    follows_rows = list(session.exec(select(UserFollow)).all())
    assert {f.artist_id for f in follows_rows} == {"art-A", "art-B"}

    # releases が入っていること
    release_rows = list(session.exec(select(Release)).all())
    assert {r.spotify_id for r in release_rows} == {"alb-A1", "alb-B1"}

    # sync_status が success マークされていること
    status_res = authed_client.get("/api/releases/sync-status").json()
    assert status_res["last_success_at"] is not None
    assert status_res["last_error"] is None


def test_post_sync_marks_error_when_all_artists_fail(
    authed_client: TestClient,
    session: Session,
    httpx_mock: HTTPXMock,
) -> None:
    """全 artist が Spotify 5xx を返したら sync_status.last_error が立ち、
    last_success_at は据え置き (None)。"""
    from app.models.record import VinylRecord

    now = datetime.now(UTC)
    session.add(Artist(spotify_id="art-A", name="A", source="manual", added_at=now))
    session.commit()
    # records 由来で follow が backfill されるよう 1 件挿入
    session.add(
        VinylRecord(
            artist_id="art-A",
            title="t",
            source="manual",
            status="owned",
            display_order=1,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(url=_ARTIST_ALBUMS_URL_PATTERN, method="GET", status_code=500)

    res = authed_client.post("/api/releases/sync")
    assert res.status_code == 200
    body = res.json()
    assert body["artists_total"] == 1
    assert body["artists_succeeded"] == 0
    assert body["first_error"] is not None

    status_res = authed_client.get("/api/releases/sync-status").json()
    assert status_res["last_success_at"] is None
    assert status_res["last_error"] is not None


# ---- PATCH /api/releases/{spotify_id}/read ----


def test_set_read_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.patch("/api/releases/whatever/read", json={"is_read": True})
    assert res.status_code == 401


def test_set_read_unknown_id_returns_404(authed_client: TestClient) -> None:
    res = authed_client.patch("/api/releases/ghost/read", json={"is_read": True})
    assert res.status_code == 404


def test_set_read_true_then_false(authed_client: TestClient, session: Session) -> None:
    """is_read=true で read_at が now、false に戻すと read_at=null。"""
    now = datetime.now(UTC)
    session.add(Artist(spotify_id="art-r", name="A", added_at=now))
    session.commit()
    session.add(
        Release(
            spotify_id="rel-1",
            artist_id="art-r",
            title="x",
            album_type="album",
            release_date=date(2026, 1, 1),
        )
    )
    session.commit()

    # 既読化
    res = authed_client.patch("/api/releases/rel-1/read", json={"is_read": True})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_read"] is True
    assert body["read_at"] is not None

    # 未読に戻す
    res2 = authed_client.patch("/api/releases/rel-1/read", json={"is_read": False})
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["is_read"] is False
    assert body2["read_at"] is None
