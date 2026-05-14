import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock
from sqlmodel import Session

from app.core.settings import Settings, get_settings
from app.main import app
from app.models.user import User
from app.routers.deps import get_current_user, get_spotify_app_client
from app.services.spotify_app_client import SPOTIFY_TOKEN_URL, SpotifyAppClient
from tests.conftest import make_settings

_SEARCH_URL_PATTERN = re.compile(r"^https://api\.spotify\.com/v1/search")


def _token_response() -> dict[str, Any]:
    return {"access_token": "BQA-app-token", "token_type": "Bearer", "expires_in": 3600}


def _search_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"albums": {"items": items}}


def _album() -> dict[str, Any]:
    return {
        "id": "spot-album-1",
        "name": "Kind of Blue",
        "release_date": "1959-08-17",
        "images": [{"url": "https://i.scdn.co/image/koh.jpg"}],
        "artists": [{"id": "art-1", "name": "Miles Davis"}],
    }


@pytest.fixture
def test_settings() -> Settings:
    return make_settings()


@pytest.fixture
def spotify_client(session: Session, test_settings: Settings) -> Iterator[TestClient]:
    """`get_current_user` を mock しつつ、Spotify app client は httpx mock 対象の実体を注入する。"""
    from app.core.db import get_session

    def _override_session() -> Iterator[Session]:
        yield session

    def _override_user() -> User:
        return User(spotify_id="test-owner", display_name="Test Owner", refresh_token="")

    # process-wide cache を避けるため毎回新しい SpotifyAppClient を返す
    def _override_app_client() -> SpotifyAppClient:
        return SpotifyAppClient(test_settings)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_spotify_app_client] = _override_app_client
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def unauthed_client(session: Session, test_settings: Settings) -> Iterator[TestClient]:
    """`get_current_user` を override せず、cookie 無しで叩いた時の挙動を検証する。"""
    from app.core.db import get_session

    def _override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: test_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_search_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.get("/api/spotify/albums/search", params={"q": "anything"})
    assert res.status_code == 401


def test_search_returns_items(spotify_client: TestClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_SEARCH_URL_PATTERN,
        method="GET",
        json=_search_response([_album()]),
    )

    res = spotify_client.get("/api/spotify/albums/search", params={"q": "Kind of Blue"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body == {
        "items": [
            {
                "id": "spot-album-1",
                "name": "Kind of Blue",
                "release_date": "1959-08-17",
                "image_url": "https://i.scdn.co/image/koh.jpg",
                "artist_names": ["Miles Davis"],
                "primary_artist_id": "art-1",
            }
        ],
        "total": 0,
    }


def test_search_passes_artist_param(spotify_client: TestClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_SEARCH_URL_PATTERN,
        method="GET",
        json=_search_response([_album()]),
    )

    res = spotify_client.get(
        "/api/spotify/albums/search",
        params={"q": "Kind of Blue", "artist": "Miles Davis"},
    )
    assert res.status_code == 200
    spotify_req = next(r for r in httpx_mock.get_requests() if r.url.path == "/v1/search")
    q = spotify_req.url.params.get("q")
    assert q is not None and 'artist:"Miles Davis"' in q


def test_search_missing_q_is_validation_error(spotify_client: TestClient) -> None:
    res = spotify_client.get("/api/spotify/albums/search")
    assert res.status_code == 422


def test_search_translates_429(spotify_client: TestClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(url=_SEARCH_URL_PATTERN, method="GET", status_code=429)

    res = spotify_client.get("/api/spotify/albums/search", params={"q": "anything"})
    assert res.status_code == 429


def test_search_translates_500_to_502(spotify_client: TestClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(url=_SEARCH_URL_PATTERN, method="GET", status_code=500)

    res = spotify_client.get("/api/spotify/albums/search", params={"q": "anything"})
    assert res.status_code == 502


# ---- GET /api/spotify/artists/search ----


def _artist_search_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"artists": {"items": items}}


def _artist_item() -> dict[str, Any]:
    return {
        "id": "art-miles",
        "name": "Miles Davis",
        "images": [{"url": "https://i.scdn.co/image/miles.jpg"}],
    }


def test_artist_search_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.get("/api/spotify/artists/search", params={"q": "anything"})
    assert res.status_code == 401


def test_artist_search_returns_items(spotify_client: TestClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_SEARCH_URL_PATTERN,
        method="GET",
        json=_artist_search_response([_artist_item()]),
    )

    res = spotify_client.get("/api/spotify/artists/search", params={"q": "Miles"})
    assert res.status_code == 200, res.text
    assert res.json() == {
        "items": [
            {
                "spotify_id": "art-miles",
                "name": "Miles Davis",
                "image_url": "https://i.scdn.co/image/miles.jpg",
            }
        ],
        "total": 0,
    }


def test_artist_search_missing_q_is_validation_error(spotify_client: TestClient) -> None:
    res = spotify_client.get("/api/spotify/artists/search")
    assert res.status_code == 422


def test_artist_search_translates_429(spotify_client: TestClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(url=_SEARCH_URL_PATTERN, method="GET", status_code=429)

    res = spotify_client.get("/api/spotify/artists/search", params={"q": "Miles"})
    assert res.status_code == 429


def test_artist_search_skips_items_missing_id_or_name(
    spotify_client: TestClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(
        url=_SEARCH_URL_PATTERN,
        method="GET",
        json=_artist_search_response(
            [
                _artist_item(),
                {"id": "", "name": "no-id"},
                {"id": "art-2", "name": ""},
            ]
        ),
    )

    res = spotify_client.get("/api/spotify/artists/search", params={"q": "Miles"})
    assert res.status_code == 200
    ids = [a["spotify_id"] for a in res.json()["items"]]
    assert ids == ["art-miles"]
