"""`/api/releases` 系エンドポイントの統合テスト (ADR-007)。

- GET /api/releases: follow フィルタ + 期間窓 / ソート / 空状態 / cross-user 隔離
- POST /api/releases/sync: 未認証 401、認証済で Spotify を httpx_mock 偽装して 200
- PATCH /api/releases/{spotify_id}/read: 既読/未読 toggle、cross-user 隔離
- GET /api/releases/sync-status: row なし / 後に成功状態
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pytest_httpx import HTTPXMock
from sqlmodel import Session, select

from app.core.db import get_session, get_session_factory
from app.core.settings import Settings, get_settings
from app.main import app
from app.models.artist import Artist
from app.models.release import Release
from app.models.release_read_state import ReleaseReadState
from app.models.user import User
from app.models.user_follow import UserFollow
from app.routers.deps import get_current_user, get_spotify_app_client
from app.services.release_sync_runner import release_sync_runner
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


def _seed_follow(session: Session, user_id, artist_id: str, archived: bool = False) -> None:
    session.add(UserFollow(user_id=user_id, artist_id=artist_id, archived_flag=archived))
    session.commit()


@pytest.fixture
def _test_settings() -> Settings:
    return make_settings()


@pytest.fixture(autouse=True)
def _reset_sync_runner() -> Iterator[None]:
    """process-wide な release_sync_runner の in-memory 状態をテスト毎に初期化。"""
    release_sync_runner.reset()
    yield
    release_sync_runner.reset()


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

    @contextmanager
    def _override_session_scope() -> Iterator[Session]:
        # バックグラウンドジョブ用の session ファクトリ。テストでは新規に開かず、
        # テスト session をそのまま貸す (close はフィクスチャ側に任せる)。
        yield session

    def _override_user() -> User:
        return user

    def _override_spotify() -> SpotifyAppClient:
        return SpotifyAppClient(_test_settings)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_session_factory] = lambda: _override_session_scope
    app.dependency_overrides[get_settings] = lambda: _test_settings
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_spotify_app_client] = _override_spotify
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---- GET /api/releases ----


def test_get_releases_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.get("/api/releases")
    assert res.status_code == 401


def test_get_releases_empty(authed_client: TestClient) -> None:
    res = authed_client.get("/api/releases")
    assert res.status_code == 200
    assert res.json() == {"items": [], "total": 0}


def test_get_releases_returns_within_window_and_sorts_desc(
    authed_client: TestClient, session: Session
) -> None:
    today = date.today()
    _seed_artist(session, "art-1")
    user = session.exec(select(User).where(User.spotify_id == "test-owner")).one()
    _seed_follow(session, user.id, "art-1")
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

    res = authed_client.get("/api/releases")
    body = res.json()
    ids = [r["spotify_id"] for r in body["items"]]
    # r-old は窓外なので除外、新しい順 (release_date desc)
    assert ids == ["r-upcoming", "r-recent"]


def test_get_releases_accepts_custom_window(authed_client: TestClient, session: Session) -> None:
    _seed_artist(session, "art-1")
    user = session.exec(select(User).where(User.spotify_id == "test-owner")).one()
    _seed_follow(session, user.id, "art-1")
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

    res = authed_client.get("/api/releases", params={"from": "2024-01-01", "to": "2024-12-31"})
    assert res.status_code == 200
    assert [r["spotify_id"] for r in res.json()["items"]] == ["r-1"]


def test_get_releases_only_followed_artists(authed_client: TestClient, session: Session) -> None:
    """current user が follow している artist の release だけ返る (ADR-007 §2.4)。"""
    today = date.today()
    _seed_artist(session, "art-followed")
    _seed_artist(session, "art-not-followed")
    user = session.exec(select(User).where(User.spotify_id == "test-owner")).one()
    _seed_follow(session, user.id, "art-followed")
    # art-not-followed は follow しない

    session.add_all(
        [
            Release(
                spotify_id="r-followed",
                artist_id="art-followed",
                title="Followed Album",
                album_type="album",
                release_date=today,
            ),
            Release(
                spotify_id="r-not-followed",
                artist_id="art-not-followed",
                title="Not Followed Album",
                album_type="album",
                release_date=today,
            ),
        ]
    )
    session.commit()

    res = authed_client.get("/api/releases")
    ids = [r["spotify_id"] for r in res.json()["items"]]
    assert ids == ["r-followed"]


def test_get_releases_excludes_archived_follows(
    authed_client: TestClient, session: Session
) -> None:
    """archived な follow の artist の release は返らない。"""
    today = date.today()
    _seed_artist(session, "art-archived")
    user = session.exec(select(User).where(User.spotify_id == "test-owner")).one()
    _seed_follow(session, user.id, "art-archived", archived=True)

    session.add(
        Release(
            spotify_id="r-archived",
            artist_id="art-archived",
            title="X",
            album_type="album",
            release_date=today,
        )
    )
    session.commit()

    res = authed_client.get("/api/releases")
    assert res.json() == {"items": [], "total": 0}


def test_get_releases_isolated_between_users(session: Session, _test_settings: Settings) -> None:
    """user A が follow している artist の release は user B には見えない。"""
    today = date.today()
    user_a = User(spotify_id="user-a", display_name="A", refresh_token="")
    user_b = User(spotify_id="user-b", display_name="B", refresh_token="")
    session.add_all([user_a, user_b])
    session.commit()
    session.refresh(user_a)
    session.refresh(user_b)
    _seed_artist(session, "art-a")
    _seed_follow(session, user_a.id, "art-a")
    session.add(
        Release(
            spotify_id="r-a",
            artist_id="art-a",
            title="A only",
            album_type="album",
            release_date=today,
        )
    )
    session.commit()

    def _override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: _test_settings
    try:
        # user A 視点
        app.dependency_overrides[get_current_user] = lambda: user_a
        c = TestClient(app)
        a_ids = [r["spotify_id"] for r in c.get("/api/releases").json()["items"]]
        # user B 視点 (follow していない)
        app.dependency_overrides[get_current_user] = lambda: user_b
        c = TestClient(app)
        b_ids = [r["spotify_id"] for r in c.get("/api/releases").json()["items"]]
    finally:
        app.dependency_overrides.clear()

    assert a_ids == ["r-a"]
    assert b_ids == []


# ---- GET /api/releases/sync-status ----


def test_sync_status_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.get("/api/releases/sync-status")
    assert res.status_code == 401


def test_sync_status_returns_null_fields_when_never_synced(
    authed_client: TestClient,
) -> None:
    res = authed_client.get("/api/releases/sync-status")
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "spotify_releases"
    assert body["last_success_at"] is None
    assert body["last_attempt_at"] is None
    assert body["last_error"] is None
    assert body["is_running"] is False


# ---- POST /api/releases/sync ----


def test_post_sync_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.post("/api/releases/sync")
    assert res.status_code == 401


def test_post_sync_ingests_albums_for_followed_artists(
    authed_client: TestClient,
    session: Session,
    httpx_mock: HTTPXMock,
) -> None:
    """user_follows に登録された artist を対象に Spotify から albums を取り込み、
    sync_status を last_success_at 付きで更新する。
    """
    now = datetime.now(UTC)
    session.add_all(
        [
            Artist(spotify_id="art-A", name="A", source="manual", added_at=now),
            Artist(spotify_id="art-B", name="B", source="manual", added_at=now),
        ]
    )
    session.commit()

    user = session.exec(select(User).where(User.spotify_id == "test-owner")).one()
    session.add_all(
        [
            UserFollow(user_id=user.id, artist_id="art-A"),
            UserFollow(user_id=user.id, artist_id="art-B"),
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

    # sync はバックグラウンド実行 (202 即返し)。TestClient は background task を
    # レスポンス返却前に完走させるので、この後に DB / sync-status を検証できる。
    res = authed_client.post("/api/releases/sync")
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["status"] == "started"
    assert body["is_running"] is True

    session.expire_all()
    release_rows = list(session.exec(select(Release)).all())
    assert {r.spotify_id for r in release_rows} == {"alb-A1", "alb-B1"}

    status_res = authed_client.get("/api/releases/sync-status").json()
    assert status_res["last_success_at"] is not None
    assert status_res["last_error"] is None
    # ジョブ完走後なので is_running は False に戻っている。
    assert status_res["is_running"] is False
    # 直近ジョブの件数サマリが last_run に乗る。
    assert status_res["last_run"]["artists_total"] == 2
    assert status_res["last_run"]["artists_succeeded"] == 2
    assert status_res["last_run"]["albums_ingested"] == 2
    assert status_res["last_run"]["first_error"] is None


def test_post_sync_marks_error_when_all_artists_fail(
    authed_client: TestClient,
    session: Session,
    httpx_mock: HTTPXMock,
) -> None:
    """全 artist が Spotify 5xx を返したら sync_status.last_error が立ち、
    last_success_at は据え置き (None)。"""
    now = datetime.now(UTC)
    session.add(Artist(spotify_id="art-A", name="A", source="manual", added_at=now))
    session.commit()

    user = session.exec(select(User).where(User.spotify_id == "test-owner")).one()
    session.add(UserFollow(user_id=user.id, artist_id="art-A"))
    session.commit()
    httpx_mock.add_response(url=SPOTIFY_TOKEN_URL, method="POST", json=_token_response())
    httpx_mock.add_response(url=_ARTIST_ALBUMS_URL_PATTERN, method="GET", status_code=500)

    res = authed_client.post("/api/releases/sync")
    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "started"
    assert body["is_running"] is True

    status_res = authed_client.get("/api/releases/sync-status").json()
    assert status_res["last_success_at"] is None
    assert status_res["last_error"] is not None
    assert status_res["is_running"] is False


# ---- PATCH /api/releases/{spotify_id}/read ----


def test_set_read_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.patch("/api/releases/whatever/read", json={"is_read": True})
    assert res.status_code == 401


def test_set_read_unknown_id_returns_404(authed_client: TestClient) -> None:
    res = authed_client.patch("/api/releases/ghost/read", json={"is_read": True})
    assert res.status_code == 404


def test_set_read_true_then_false(authed_client: TestClient, session: Session) -> None:
    """is_read=true で release_read_states に行が入り read_at=now、false で行が消える。"""
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

    res = authed_client.patch("/api/releases/rel-1/read", json={"is_read": True})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_read"] is True
    assert body["read_at"] is not None

    res2 = authed_client.patch("/api/releases/rel-1/read", json={"is_read": False})
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["is_read"] is False
    assert body2["read_at"] is None


def test_set_read_isolated_between_users(session: Session, _test_settings: Settings) -> None:
    """user A が既読化した release を user B では未読のまま見える (ADR-007 §2.3)。"""
    now = datetime.now(UTC)
    user_a = User(spotify_id="user-a", display_name="A", refresh_token="")
    user_b = User(spotify_id="user-b", display_name="B", refresh_token="")
    session.add_all([user_a, user_b])
    session.commit()
    session.refresh(user_a)
    session.refresh(user_b)

    _seed_artist(session, "art-shared")
    _seed_follow(session, user_a.id, "art-shared")
    _seed_follow(session, user_b.id, "art-shared")
    session.add(
        Release(
            spotify_id="rel-shared",
            artist_id="art-shared",
            title="Shared",
            album_type="album",
            release_date=now.date(),
        )
    )
    session.commit()

    def _override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: _test_settings
    try:
        # user A が既読化
        app.dependency_overrides[get_current_user] = lambda: user_a
        c = TestClient(app)
        res_a = c.patch("/api/releases/rel-shared/read", json={"is_read": True})
        assert res_a.status_code == 200
        assert res_a.json()["is_read"] is True

        # user B が同じ release を GET → 未読のまま
        app.dependency_overrides[get_current_user] = lambda: user_b
        c = TestClient(app)
        res_b = c.get("/api/releases", params={"from": "2025-01-01", "to": "2030-12-31"})
        items = res_b.json()["items"]
        b_item = next(r for r in items if r["spotify_id"] == "rel-shared")
        assert b_item["is_read"] is False
        assert b_item["read_at"] is None
    finally:
        app.dependency_overrides.clear()

    # release_read_states 行は user A の 1 行だけ
    states = list(session.exec(select(ReleaseReadState)).all())
    assert len(states) == 1
    assert states[0].user_id == user_a.id
