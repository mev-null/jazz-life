"""`DELETE /api/user-follows/{artist_id}` の統合テスト。

- 認証なしで叩いたら 401
- 該当 follow 行が無ければ 404
- 該当 follow 行があれば 204 + archived_flag=true、list_artist_ids から外れる
- 既に archived な行に再叩きしても 204 (冪等)
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.db import get_session
from app.core.repositories.artist_repository import ArtistRepository
from app.core.repositories.record_favorite_track_repository import (
    RecordFavoriteTrackRepository,
)
from app.core.repositories.record_repository import RecordRepository
from app.core.repositories.user_collection_repository import UserCollectionRepository
from app.core.repositories.user_follow_repository import UserFollowRepository
from app.core.settings import Settings, get_settings
from app.main import app
from app.models.artist import Artist
from app.models.user import User
from app.models.user_follow import UserFollow
from app.routers.deps import get_current_user
from app.schemas.record import VinylRecordCreate
from app.services.record_service import RecordService
from tests.conftest import make_settings


def _seed_user(session: Session) -> User:
    user = User(spotify_id="test-owner", display_name="Test Owner", refresh_token="")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _seed_artist(session: Session, spotify_id: str) -> None:
    session.add(Artist(spotify_id=spotify_id, name=spotify_id, added_at=datetime.now(UTC)))
    session.commit()


def _seed_follow(session: Session, user_id, artist_id: str, archived: bool = False) -> None:
    session.add(UserFollow(user_id=user_id, artist_id=artist_id, archived_flag=archived))
    session.commit()


def _make_record_service(session: Session) -> RecordService:
    return RecordService(
        record_repo=RecordRepository(session),
        collection_repo=UserCollectionRepository(session),
        favorite_track_repo=RecordFavoriteTrackRepository(session),
        artist_repo=ArtistRepository(session),
        follow_repo=UserFollowRepository(session),
    )


@pytest.fixture
def _test_settings() -> Settings:
    return make_settings()


@pytest.fixture
def authed_client(session: Session, _test_settings: Settings) -> Iterator[TestClient]:
    user = _seed_user(session)

    def _override_session() -> Iterator[Session]:
        yield session

    def _override_user() -> User:
        return user

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: _test_settings
    app.dependency_overrides[get_current_user] = _override_user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def unauthed_client(session: Session, _test_settings: Settings) -> Iterator[TestClient]:
    def _override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: _test_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_unfollow_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.delete("/api/user-follows/some-artist")
    assert res.status_code == 401


def test_unfollow_unknown_artist_returns_404(authed_client: TestClient) -> None:
    res = authed_client.delete("/api/user-follows/ghost-artist")
    assert res.status_code == 404


def test_unfollow_archives_existing_follow(authed_client: TestClient, session: Session) -> None:
    """既存 follow が archived_flag=true になり、list_artist_ids から外れる。"""
    from sqlmodel import select

    _seed_artist(session, "art-1")
    user = session.exec(select(User).where(User.spotify_id == "test-owner")).one()
    _seed_follow(session, user.id, "art-1")
    # 事前確認: list_artist_ids に出る
    assert UserFollowRepository(session).list_artist_ids(user.id) == ["art-1"]

    res = authed_client.delete("/api/user-follows/art-1")
    assert res.status_code == 204

    # 行は残るが archived_flag=true、list_artist_ids には出ない
    session.expire_all()
    follow_row = session.exec(select(UserFollow).where(UserFollow.user_id == user.id)).one()
    assert follow_row.archived_flag is True
    assert UserFollowRepository(session).list_artist_ids(user.id) == []


def test_unfollow_already_archived_is_idempotent(
    authed_client: TestClient, session: Session
) -> None:
    from sqlmodel import select

    _seed_artist(session, "art-arc")
    user = session.exec(select(User).where(User.spotify_id == "test-owner")).one()
    _seed_follow(session, user.id, "art-arc", archived=True)

    res = authed_client.delete("/api/user-follows/art-arc")
    assert res.status_code == 204


# ---- GET /api/user-follows/artists ----


def test_list_followed_artists_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.get("/api/user-follows/artists")
    assert res.status_code == 401


def test_list_followed_artists_returns_only_active_follows(
    authed_client: TestClient, session: Session
) -> None:
    """followed (archived=false) は出る、archived は出ない、未 follow は出ない。"""
    from sqlmodel import select

    user = session.exec(select(User).where(User.spotify_id == "test-owner")).one()
    _seed_artist(session, "art-active")
    _seed_artist(session, "art-archived")
    _seed_artist(session, "art-unfollowed")  # follow 行自体無い
    _seed_follow(session, user.id, "art-active", archived=False)
    _seed_follow(session, user.id, "art-archived", archived=True)

    res = authed_client.get("/api/user-follows/artists")
    assert res.status_code == 200
    ids = {item["spotify_id"] for item in res.json()["items"]}
    assert ids == {"art-active"}


# ---- POST /api/user-follows ----


def test_follow_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.post("/api/user-follows", json={"artist_id": "any"})
    assert res.status_code == 401


def test_follow_unknown_artist_returns_404(authed_client: TestClient) -> None:
    res = authed_client.post("/api/user-follows", json={"artist_id": "ghost"})
    assert res.status_code == 404


def test_follow_creates_new_row(authed_client: TestClient, session: Session) -> None:
    from sqlmodel import select

    _seed_artist(session, "art-new")
    user = session.exec(select(User).where(User.spotify_id == "test-owner")).one()

    res = authed_client.post("/api/user-follows", json={"artist_id": "art-new"})
    assert res.status_code == 201, res.text
    assert res.json()["spotify_id"] == "art-new"

    session.expire_all()
    follow_row = session.exec(
        select(UserFollow)
        .where(UserFollow.user_id == user.id)
        .where(UserFollow.artist_id == "art-new")
    ).one()
    assert follow_row.archived_flag is False


def test_follow_reactivates_archived(authed_client: TestClient, session: Session) -> None:
    """archived 行があるアーティストを再 follow すると archived_flag=false に戻る。"""
    from sqlmodel import select

    _seed_artist(session, "art-revive")
    user = session.exec(select(User).where(User.spotify_id == "test-owner")).one()
    _seed_follow(session, user.id, "art-revive", archived=True)

    res = authed_client.post("/api/user-follows", json={"artist_id": "art-revive"})
    assert res.status_code == 201

    session.expire_all()
    follow_row = session.exec(
        select(UserFollow)
        .where(UserFollow.user_id == user.id)
        .where(UserFollow.artist_id == "art-revive")
    ).one()
    assert follow_row.archived_flag is False
    assert UserFollowRepository(session).list_artist_ids(user.id) == ["art-revive"]


def test_follow_already_active_is_idempotent(authed_client: TestClient, session: Session) -> None:
    from sqlmodel import select

    _seed_artist(session, "art-dup")
    user = session.exec(select(User).where(User.spotify_id == "test-owner")).one()
    _seed_follow(session, user.id, "art-dup", archived=False)

    res = authed_client.post("/api/user-follows", json={"artist_id": "art-dup"})
    assert res.status_code == 201

    rows = session.exec(
        select(UserFollow)
        .where(UserFollow.user_id == user.id)
        .where(UserFollow.artist_id == "art-dup")
    ).all()
    assert len(rows) == 1
    assert rows[0].archived_flag is False


# ---- GET /api/user-follows/record-counts ----


def test_record_counts_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.get("/api/user-follows/record-counts")
    assert res.status_code == 401


def test_record_counts_empty_when_no_records(authed_client: TestClient) -> None:
    res = authed_client.get("/api/user-follows/record-counts")
    assert res.status_code == 200
    assert res.json() == {"items": [], "total": 0}


def test_record_counts_counts_only_owned_collections(
    authed_client: TestClient, session: Session
) -> None:
    """current user の status='owned' な user_collections を artist_id ごとに集計する。

    ADR-006 後の挙動:
    - status='wanted' は除外
    - 他 user の collection は cross-user で混ざらない (user_id ガード)
    - follow の archived 状態とは独立 (collection が user に直接 scope されているため)
    """
    from sqlmodel import select

    user = session.exec(select(User).where(User.spotify_id == "test-owner")).one()
    _seed_artist(session, "art-bill")
    _seed_artist(session, "art-avishai")

    service = _make_record_service(session)
    service.create(
        VinylRecordCreate(artist_id="art-bill", title="owned-1", status="owned"),
        user.id,
    )
    service.create(
        VinylRecordCreate(artist_id="art-bill", title="owned-2", status="owned"),
        user.id,
    )
    service.create(
        VinylRecordCreate(artist_id="art-avishai", title="wanted-1", status="wanted"),
        user.id,
    )

    res = authed_client.get("/api/user-follows/record-counts")

    assert res.status_code == 200
    items = {item["artist_id"]: item["count"] for item in res.json()["items"]}
    assert items == {"art-bill": 2}


def test_record_counts_isolated_between_users(session: Session, _test_settings: Settings) -> None:
    """user A の collection は user B の record-counts に現れない。"""
    from sqlmodel import select

    _seed_artist(session, "art-x")
    user_b = User(spotify_id="user-b", display_name="B", refresh_token="")
    session.add(user_b)
    session.commit()
    session.refresh(user_b)
    user_a = session.exec(select(User).where(User.spotify_id == "test-owner")).first()
    if user_a is None:
        user_a = User(spotify_id="test-owner", display_name="A", refresh_token="")
        session.add(user_a)
        session.commit()
        session.refresh(user_a)

    _make_record_service(session).create(
        VinylRecordCreate(artist_id="art-x", title="A only"), user_a.id
    )

    def _override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: _test_settings
    app.dependency_overrides[get_current_user] = lambda: user_b
    try:
        c = TestClient(app)
        res = c.get("/api/user-follows/record-counts")
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    assert res.json() == {"items": [], "total": 0}
