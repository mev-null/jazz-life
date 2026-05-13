import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock
from sqlmodel import Session

from app.core.settings import Settings, get_settings
from app.main import app
from app.models.artist import Artist
from app.models.user import User
from app.routers.deps import get_current_user, get_spotify_app_client
from app.services.spotify_app_client import SPOTIFY_TOKEN_URL, SpotifyAppClient
from tests.conftest import make_settings

_ARTISTS_URL_PATTERN = re.compile(r"^https://api\.spotify\.com/v1/artists")


def _token_response() -> dict[str, Any]:
    return {"access_token": "BQA-app-token", "token_type": "Bearer", "expires_in": 3600}


def _artists_response(entries: list[dict[str, Any] | None]) -> dict[str, Any]:
    return {"artists": entries}


def test_list_artists_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.get("/api/artists")
    assert res.status_code == 401


def test_artists_empty(authed_client: TestClient) -> None:
    res = authed_client.get("/api/artists")
    assert res.status_code == 200
    assert res.json() == {"items": []}


def test_artists_sorted_by_added_at_desc(authed_client: TestClient, session: Session) -> None:
    """artists が複数件あれば added_at desc で返る。

    seed が空になったので、ソート検証用に fixture artist を直接 2 件投入する。
    """
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    session.add_all(
        [
            Artist(spotify_id="a-old", name="Old", added_at=now - timedelta(days=10)),
            Artist(spotify_id="a-new", name="New", added_at=now),
        ]
    )
    session.commit()

    res = authed_client.get("/api/artists")
    items = res.json()["items"]
    assert [a["spotify_id"] for a in items] == ["a-new", "a-old"]


# ---- POST /api/artists (upsert) ----


@pytest.fixture
def _test_settings() -> Settings:
    return make_settings()


@pytest.fixture
def authed_client(session: Session, _test_settings: Settings) -> Iterator[TestClient]:
    """`get_current_user` を mock した TestClient。POST /api/artists の検証用。"""
    from app.core.db import get_session

    def _override_session() -> Iterator[Session]:
        yield session

    def _override_user() -> User:
        return User(spotify_id="test-owner", display_name="Test Owner", refresh_token="")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: _test_settings
    app.dependency_overrides[get_current_user] = _override_user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def unauthed_client(session: Session, _test_settings: Settings) -> Iterator[TestClient]:
    """`get_current_user` を override せず、未認証時の 401 を検証する用。"""
    from app.core.db import get_session

    def _override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: _test_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_upsert_artist_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.post(
        "/api/artists",
        json={"spotify_id": "newid", "name": "New Artist"},
    )
    assert res.status_code == 401


def test_upsert_artist_creates_new(authed_client: TestClient) -> None:
    res = authed_client.post(
        "/api/artists",
        json={
            "spotify_id": "new-spotify-id",
            "name": "New Artist",
            "image_url": "https://i.scdn.co/image/new.jpg",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["spotify_id"] == "new-spotify-id"
    assert body["name"] == "New Artist"
    assert body["image_url"] == "https://i.scdn.co/image/new.jpg"
    assert body["source"] == "spotify_dynamic"
    # 同 endpoint で確認できる
    listing = authed_client.get("/api/artists").json()
    assert any(a["spotify_id"] == "new-spotify-id" for a in listing["items"])


def test_upsert_artist_idempotent(authed_client: TestClient) -> None:
    payload = {"spotify_id": "dup-id", "name": "Dup Artist"}
    res1 = authed_client.post("/api/artists", json=payload)
    res2 = authed_client.post("/api/artists", json={**payload, "name": "Renamed"})
    assert res1.status_code == 200 and res2.status_code == 200
    # 2 回目は既存を返すので、name は upsert で更新されない (最初の "Dup Artist" のまま)
    assert res2.json()["name"] == "Dup Artist"
    # artists 一覧の件数も増えない
    listing = authed_client.get("/api/artists").json()
    assert sum(1 for a in listing["items"] if a["spotify_id"] == "dup-id") == 1


# ---- GET /api/artists/{spotify_id} (lazy photo hydration) ----


@pytest.fixture
def spotify_client(session: Session, _test_settings: Settings) -> Iterator[TestClient]:
    """GET /api/artists/{id} の Spotify hydrate 経路を検証するための client。

    httpx_mock との連携のため、process-wide cache を避けて毎回新しい
    SpotifyAppClient を返す override を仕込む (test_spotify.py と同じ作法)。
    auth ガードのため get_current_user も override する。
    """
    from app.core.db import get_session

    def _override_session() -> Iterator[Session]:
        yield session

    def _override_app_client() -> SpotifyAppClient:
        return SpotifyAppClient(_test_settings)

    def _override_user() -> User:
        return User(spotify_id="test-owner", display_name="Test Owner", refresh_token="")

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: _test_settings
    app.dependency_overrides[get_spotify_app_client] = _override_app_client
    app.dependency_overrides[get_current_user] = _override_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_artist_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.get("/api/artists/anything")
    assert res.status_code == 401


def test_get_artist_404_when_missing(spotify_client: TestClient) -> None:
    res = spotify_client.get("/api/artists/missing-id")
    assert res.status_code == 404


def test_get_artist_hydrates_image_from_spotify(
    spotify_client: TestClient,
    session: Session,
    httpx_mock: HTTPXMock,
) -> None:
    session.add(Artist(spotify_id="art-99", name="To Be Hydrated", image_url=None))
    session.commit()
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    # get_artists_images は単発 GET /v1/artists/{id} をループする実装
    # (batch endpoint は Spotify Development Mode app で 403 になるため)
    httpx_mock.add_response(
        url="https://api.spotify.com/v1/artists/art-99",
        method="GET",
        json={
            "id": "art-99",
            "name": "To Be Hydrated",
            "images": [{"url": "https://i.scdn.co/image/art99.jpg"}],
        },
    )

    res = spotify_client.get("/api/artists/art-99")

    assert res.status_code == 200, res.text
    assert res.json()["image_url"] == "https://i.scdn.co/image/art99.jpg"
    # DB にも永続化されていること
    session.expire_all()
    assert session.get(Artist, "art-99").image_url == "https://i.scdn.co/image/art99.jpg"


def test_get_artist_skips_spotify_when_image_already_set(
    spotify_client: TestClient,
    session: Session,
    httpx_mock: HTTPXMock,
) -> None:
    # image_url が既に入っている場合、Spotify を一切叩かない。
    # httpx_mock は teardown で「未使用 mock があれば失敗」させるので、
    # add_response しないことで「呼ばれなかった」を表現する。
    session.add(
        Artist(
            spotify_id="art-pre",
            name="Already Has Image",
            image_url="https://existing.example/img.jpg",
        )
    )
    session.commit()

    res = spotify_client.get("/api/artists/art-pre")

    assert res.status_code == 200
    assert res.json()["image_url"] == "https://existing.example/img.jpg"


def test_get_artist_swallows_spotify_error(
    spotify_client: TestClient,
    session: Session,
    httpx_mock: HTTPXMock,
) -> None:
    # Spotify が 5xx を返しても endpoint 自体は 200 を返し、image_url は NULL のまま。
    session.add(Artist(spotify_id="art-fail", name="Spotify Down", image_url=None))
    session.commit()
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url="https://api.spotify.com/v1/artists/art-fail", method="GET", status_code=500
    )

    res = spotify_client.get("/api/artists/art-fail")

    assert res.status_code == 200
    assert res.json()["image_url"] is None


# record-counts は /api/user-follows/record-counts に移設したので
# テストも tests/integration/test_user_follows.py に集約している。
