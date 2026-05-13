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
from app.core.repositories.user_follow_repository import UserFollowRepository
from app.core.settings import Settings, get_settings
from app.main import app
from app.models.artist import Artist
from app.models.user import User
from app.models.user_follow import UserFollow
from app.routers.deps import get_current_user
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


# ---- GET /api/user-follows/record-counts ----


def test_record_counts_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.get("/api/user-follows/record-counts")
    assert res.status_code == 401


def test_record_counts_empty_when_no_records(authed_client: TestClient) -> None:
    res = authed_client.get("/api/user-follows/record-counts")
    assert res.status_code == 200
    assert res.json() == {"items": []}


def test_record_counts_counts_only_owned_for_active_follows(
    authed_client: TestClient, session: Session
) -> None:
    """current user の所有 (status='owned') レコードを follow 中 artist ごとに集計する。

    検証する観点:
    - status='wanted' な record は数えない (want list 除外)
    - archived な follow の artist の record も数えない (followed_artists と整合)
    - そもそも follow していない artist の record は数えない (理屈上は auto-follow
      で発生しないはずだが、念のため JOIN 条件として担保)
    """
    from datetime import UTC, datetime

    from sqlmodel import select

    from app.models.record import VinylRecord

    now = datetime.now(UTC)
    user = session.exec(select(User).where(User.spotify_id == "test-owner")).one()

    _seed_artist(session, "art-bill")
    _seed_artist(session, "art-avishai")
    _seed_artist(session, "art-archived")
    _seed_artist(session, "art-unfollowed")
    _seed_follow(session, user.id, "art-bill", archived=False)
    _seed_follow(session, user.id, "art-avishai", archived=False)
    _seed_follow(session, user.id, "art-archived", archived=True)

    session.add_all(
        [
            VinylRecord(
                artist_id="art-bill",
                title="owned-1",
                source="manual",
                status="owned",
                display_order=1,
                created_at=now,
                updated_at=now,
            ),
            VinylRecord(
                artist_id="art-bill",
                title="owned-2",
                source="manual",
                status="owned",
                display_order=2,
                created_at=now,
                updated_at=now,
            ),
            VinylRecord(
                artist_id="art-avishai",
                title="wanted-1",
                source="manual",
                status="wanted",  # 数えない
                display_order=3,
                created_at=now,
                updated_at=now,
            ),
            VinylRecord(
                artist_id="art-archived",
                title="archived-owned",
                source="manual",
                status="owned",  # follow が archived なので数えない
                display_order=4,
                created_at=now,
                updated_at=now,
            ),
            VinylRecord(
                artist_id="art-unfollowed",
                title="unfollowed-owned",
                source="manual",
                status="owned",  # そもそも follow 行が無いので数えない
                display_order=5,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    session.commit()

    res = authed_client.get("/api/user-follows/record-counts")

    assert res.status_code == 200
    items = {item["artist_id"]: item["count"] for item in res.json()["items"]}
    assert items == {"art-bill": 2}
