from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.settings import Settings, get_settings
from app.main import app
from app.models.user import User
from app.routers.deps import get_current_user
from tests.conftest import make_settings


def test_artists_empty(client: TestClient) -> None:
    res = client.get("/api/artists")
    assert res.status_code == 200
    assert res.json() == {"items": []}


def test_artists_seeded_returns_six(seeded_client: TestClient) -> None:
    res = seeded_client.get("/api/artists")
    assert res.status_code == 200
    body = res.json()
    assert len(body["items"]) == 6
    names = {item["name"] for item in body["items"]}
    assert "Bill Evans" in names
    assert "Avishai Cohen" in names


def test_artists_sorted_by_added_at_desc(seeded_client: TestClient) -> None:
    res = seeded_client.get("/api/artists")
    items = res.json()["items"]
    added_dates = [item["added_at"] for item in items]
    assert added_dates == sorted(added_dates, reverse=True)


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
    assert body["source"] == "spotify"
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
