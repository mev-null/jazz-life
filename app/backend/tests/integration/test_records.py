import concurrent.futures
import datetime as dt
import uuid
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.core.db import get_session
from app.core.repositories.artist_repository import ArtistRepository
from app.core.repositories.record_repository import RecordRepository
from app.core.repositories.user_follow_repository import UserFollowRepository
from app.core.settings import Settings, get_settings
from app.main import app
from app.models.artist import Artist
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.record import VinylRecordCreate
from app.services.record_service import RecordService
from tests.conftest import make_settings

BILL_EVANS_ID = "test-bill-evans-id"
AVISHAI_COHEN_ID = "test-avishai-cohen-id"


def _new_record_payload(**overrides) -> dict:
    base = {
        "artist_id": BILL_EVANS_ID,
        "title": "Waltz for Debby",
        "original_release_date": "1962",
        "pressing_info": "original",
        "memo": "",
    }
    base.update(overrides)
    return base


def _seed_artists_for_records(session: Session) -> None:
    """records テストが使う 2 アーティストを直接投入する。

    Phase B-3 で seeds/artists.json を空にしたため、`seeded_client` は
    artists を作らない。records 側で必要な fixture artist は SQL で投入する。
    """
    now = dt.datetime.now(dt.UTC)
    session.add_all(
        [
            Artist(spotify_id=BILL_EVANS_ID, name="Bill Evans", added_at=now),
            Artist(spotify_id=AVISHAI_COHEN_ID, name="Avishai Cohen", added_at=now),
        ]
    )
    session.commit()


def _seed_user(session: Session) -> User:
    """records POST が auth 必須になったので user_id を持つテストユーザを 1 件作る。"""
    user = User(spotify_id="test-owner", display_name="Test Owner", refresh_token="")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def _test_settings() -> Settings:
    return make_settings()


@pytest.fixture
def authed_records_client(session: Session, _test_settings: Settings) -> Iterator[TestClient]:
    """records 全エンドポイント用の auth 済 TestClient。

    - get_current_user override で固定 user を返す
    - 必要な artist を直接 INSERT する (records が FK 参照するため)
    - GET / POST / PUT / DELETE すべて auth ガードあり (本 PR で GET も塞いだ)
    """
    _seed_artists_for_records(session)
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
    """records に cookie 無しでアクセスして 401 を確認するための client。"""

    def _override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: _test_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_empty(authed_records_client: TestClient) -> None:
    res = authed_records_client.get("/api/records")
    assert res.status_code == 200
    assert res.json() == {"items": []}


def test_get_requires_auth(unauthed_client: TestClient) -> None:
    """GET /api/records は auth 必須 (records が user-scope されるまでの入口ガード)。"""
    res = unauthed_client.get("/api/records")
    assert res.status_code == 401


def test_post_requires_auth(unauthed_client: TestClient) -> None:
    """records POST は auth 必須 (auto-follow に user_id が要るため)。"""
    res = unauthed_client.post("/api/records", json=_new_record_payload())
    assert res.status_code == 401


def test_create_then_list(authed_records_client: TestClient) -> None:
    res = authed_records_client.post("/api/records", json=_new_record_payload())
    assert res.status_code == 201, res.text
    body = res.json()
    parsed = uuid.UUID(body["id"])
    assert parsed.version == 7
    assert body["display_order"] == 1
    assert body["title"] == "Waltz for Debby"
    assert body["source"] == "manual"
    assert body["purchase_currency"] == "JPY"

    res2 = authed_records_client.get("/api/records")
    assert len(res2.json()["items"]) == 1


def test_create_auto_follows_artist(authed_records_client: TestClient, session: Session) -> None:
    """POST /api/records が user_follows に (current_user.id, artist_id) を追加する。"""
    user_id_before = UserFollowRepository(session).list_artist_ids(_seed_user_id(session))
    assert user_id_before == []
    authed_records_client.post("/api/records", json=_new_record_payload())
    follows = UserFollowRepository(session).list_artist_ids(_seed_user_id(session))
    assert follows == [BILL_EVANS_ID]


def _seed_user_id(session: Session) -> UUID:
    """テストユーザの id を取り出すヘルパ。fixture 内で作ったユーザを再取得する。"""
    from sqlmodel import select

    user = session.exec(select(User).where(User.spotify_id == "test-owner")).first()
    assert user is not None
    return user.id


def test_display_order_increments(authed_records_client: TestClient) -> None:
    a = authed_records_client.post("/api/records", json=_new_record_payload(title="A")).json()
    b = authed_records_client.post("/api/records", json=_new_record_payload(title="B")).json()
    c = authed_records_client.post("/api/records", json=_new_record_payload(title="C")).json()
    assert (a["display_order"], b["display_order"], c["display_order"]) == (1, 2, 3)


def test_partial_update_preserves_unsent_fields(
    authed_records_client: TestClient,
) -> None:
    created = authed_records_client.post(
        "/api/records",
        json=_new_record_payload(title="Original", memo="initial memo"),
    ).json()

    res = authed_records_client.put(
        f"/api/records/{created['id']}",
        json={"memo": "updated memo only"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["memo"] == "updated memo only"
    assert body["title"] == "Original"
    assert body["original_release_date"] == "1962"
    assert body["display_order"] == 1


def test_put_unknown_id_returns_404(authed_records_client: TestClient) -> None:
    res = authed_records_client.put(
        f"/api/records/{uuid.uuid4()}",
        json={"memo": "noop"},
    )
    assert res.status_code == 404


def test_put_requires_auth(unauthed_client: TestClient, session: Session) -> None:
    """update_record も create / delete と同様に auth ガード必須。

    record 行は authed client を使わず直接 INSERT する (両 fixture を同テストで
    使うと dependency_overrides が積み重なって auth ガードが効かなくなる)。
    """
    from app.models.record import VinylRecord

    _seed_artists_for_records(session)
    now = dt.datetime.now(dt.UTC)
    record = VinylRecord(
        artist_id=BILL_EVANS_ID,
        title="x",
        source="manual",
        status="owned",
        display_order=1,
        created_at=now,
        updated_at=now,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    res = unauthed_client.put(f"/api/records/{record.id}", json={"memo": "no auth"})
    assert res.status_code == 401


def test_invalid_release_date_returns_422(authed_records_client: TestClient) -> None:
    res = authed_records_client.post(
        "/api/records",
        json=_new_record_payload(original_release_date="not-a-date"),
    )
    assert res.status_code == 422


def test_invalid_currency_returns_422(authed_records_client: TestClient) -> None:
    res = authed_records_client.post(
        "/api/records",
        json=_new_record_payload(purchase_currency="yen"),
    )
    assert res.status_code == 422


@pytest.mark.parametrize("date_str", ["1962", "1962-06", "1962-06-25"])
def test_release_date_accepts_year_yearmonth_yearmonthday(
    authed_records_client: TestClient, date_str: str
) -> None:
    res = authed_records_client.post(
        "/api/records",
        json=_new_record_payload(title=f"R-{date_str}", original_release_date=date_str),
    )
    assert res.status_code == 201, res.text
    assert res.json()["original_release_date"] == date_str


def test_post_unknown_artist_returns_404(authed_records_client: TestClient) -> None:
    res = authed_records_client.post(
        "/api/records",
        json=_new_record_payload(artist_id="ghost_artist_id"),
    )
    assert res.status_code == 404
    assert "artist" in res.json()["detail"]


def test_put_can_swap_artist_id(authed_records_client: TestClient) -> None:
    created = authed_records_client.post(
        "/api/records",
        json=_new_record_payload(artist_id=BILL_EVANS_ID),
    ).json()

    res = authed_records_client.put(
        f"/api/records/{created['id']}",
        json={"artist_id": AVISHAI_COHEN_ID},
    )
    assert res.status_code == 200, res.text
    assert res.json()["artist_id"] == AVISHAI_COHEN_ID


def test_put_to_unknown_artist_returns_404(authed_records_client: TestClient) -> None:
    created = authed_records_client.post("/api/records", json=_new_record_payload()).json()

    res = authed_records_client.put(
        f"/api/records/{created['id']}",
        json={"artist_id": "ghost_artist_id"},
    )
    assert res.status_code == 404


# ---- DELETE /api/records/{id} ----


def test_delete_returns_204_and_removes(authed_records_client: TestClient) -> None:
    created = authed_records_client.post("/api/records", json=_new_record_payload()).json()

    res = authed_records_client.delete(f"/api/records/{created['id']}")
    assert res.status_code == 204
    # GET 一覧から消えていること
    assert authed_records_client.get("/api/records").json()["items"] == []


def test_delete_requires_auth(unauthed_client: TestClient, session: Session) -> None:
    """delete も POST と同様に auth ガード。

    record は authed client を使わず直接 INSERT する (両 fixture を同テストで
    使うと dependency_overrides が積み重なって auth ガードが効かなくなる)。
    """
    from app.models.record import VinylRecord

    _seed_artists_for_records(session)
    now = dt.datetime.now(dt.UTC)
    record = VinylRecord(
        artist_id=BILL_EVANS_ID,
        title="x",
        source="manual",
        status="owned",
        display_order=1,
        created_at=now,
        updated_at=now,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    res = unauthed_client.delete(f"/api/records/{record.id}")
    assert res.status_code == 401


def test_delete_unknown_id_returns_404(authed_records_client: TestClient) -> None:
    res = authed_records_client.delete(f"/api/records/{uuid.uuid4()}")
    assert res.status_code == 404


def test_delete_does_not_touch_user_follows(
    authed_records_client: TestClient, session: Session
) -> None:
    """delete で record は消えるが user_follows 行は残る。"""
    created = authed_records_client.post("/api/records", json=_new_record_payload()).json()
    user_id = _seed_user_id(session)
    assert UserFollowRepository(session).list_artist_ids(user_id) == [BILL_EVANS_ID]

    res = authed_records_client.delete(f"/api/records/{created['id']}")
    assert res.status_code == 204

    # follow は残る
    assert UserFollowRepository(session).list_artist_ids(user_id) == [BILL_EVANS_ID]


def test_concurrent_create_assigns_unique_display_order(engine: Engine) -> None:
    """Parallel POSTs each get a distinct display_order via the advisory lock."""
    with Session(engine) as bootstrap:
        _seed_artists_for_records(bootstrap)
        user = _seed_user(bootstrap)
        user_id = user.id

    n_workers = 5

    def worker(i: int) -> int:
        with Session(engine) as session:
            service = RecordService(
                RecordRepository(session),
                ArtistRepository(session),
                UserFollowRepository(session),
            )
            record = service.create(
                VinylRecordCreate(artist_id=BILL_EVANS_ID, title=f"R{i}"), user_id
            )
            return record.display_order

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as ex:
        orders = sorted(ex.map(worker, range(n_workers)))

    assert orders == list(range(1, n_workers + 1))
