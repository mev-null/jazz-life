import concurrent.futures
import datetime as dt
import uuid
from collections.abc import Iterator
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

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
from app.models.record import VinylRecord
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
    now = dt.datetime.now(dt.UTC)
    session.add_all(
        [
            Artist(spotify_id=BILL_EVANS_ID, name="Bill Evans", added_at=now),
            Artist(spotify_id=AVISHAI_COHEN_ID, name="Avishai Cohen", added_at=now),
        ]
    )
    session.commit()


def _seed_user(session: Session, spotify_id: str = "test-owner") -> User:
    user = User(spotify_id=spotify_id, display_name=f"User {spotify_id}", refresh_token="")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _user_id(session: Session, spotify_id: str = "test-owner") -> UUID:
    user = session.exec(select(User).where(User.spotify_id == spotify_id)).first()
    assert user is not None
    return user.id


def _make_service(session: Session) -> RecordService:
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
def authed_records_client(session: Session, _test_settings: Settings) -> Iterator[TestClient]:
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
    def _override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: _test_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---- list / auth ----


def test_list_empty(authed_records_client: TestClient) -> None:
    res = authed_records_client.get("/api/records")
    assert res.status_code == 200
    assert res.json() == {"items": [], "total": 0}


def test_get_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.get("/api/records")
    assert res.status_code == 401


def test_post_requires_auth(unauthed_client: TestClient) -> None:
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
    assert body["favorite_tracks"] == []

    res2 = authed_records_client.get("/api/records")
    assert len(res2.json()["items"]) == 1


def test_create_auto_follows_artist(authed_records_client: TestClient, session: Session) -> None:
    user_id = _user_id(session)
    assert UserFollowRepository(session).list_artist_ids(user_id) == []
    authed_records_client.post("/api/records", json=_new_record_payload())
    follows = UserFollowRepository(session).list_artist_ids(user_id)
    assert follows == [BILL_EVANS_ID]


def test_display_order_increments(authed_records_client: TestClient) -> None:
    a = authed_records_client.post("/api/records", json=_new_record_payload(title="A")).json()
    b = authed_records_client.post("/api/records", json=_new_record_payload(title="B")).json()
    c = authed_records_client.post("/api/records", json=_new_record_payload(title="C")).json()
    assert (a["display_order"], b["display_order"], c["display_order"]) == (1, 2, 3)


# ---- update ----


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
    _seed_artists_for_records(session)
    res = unauthed_client.put(f"/api/records/{uuid.uuid4()}", json={"memo": "no auth"})
    assert res.status_code == 401


# ---- purchase_date default / wanted→owned auto-stamp ----


def test_create_owned_without_purchase_date_returns_today(
    authed_records_client: TestClient,
) -> None:
    res = authed_records_client.post("/api/records", json=_new_record_payload(status="owned"))
    assert res.status_code == 201, res.text
    today = dt.datetime.now(ZoneInfo("Asia/Tokyo")).date()
    body = res.json()
    assert body["purchase_date"] is not None
    returned = dt.date.fromisoformat(body["purchase_date"])
    assert abs((returned - today).days) <= 1


def test_create_wanted_forces_purchase_date_null(
    authed_records_client: TestClient,
) -> None:
    res = authed_records_client.post(
        "/api/records",
        json=_new_record_payload(status="wanted", purchase_date="2020-01-01"),
    )
    assert res.status_code == 201, res.text
    assert res.json()["purchase_date"] is None


def test_update_wanted_to_owned_stamps_today(
    authed_records_client: TestClient,
) -> None:
    created = authed_records_client.post(
        "/api/records", json=_new_record_payload(status="wanted")
    ).json()
    assert created["purchase_date"] is None

    res = authed_records_client.put(
        f"/api/records/{created['id']}",
        json={"status": "owned"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "owned"
    today = dt.datetime.now(ZoneInfo("Asia/Tokyo")).date()
    returned = dt.date.fromisoformat(body["purchase_date"])
    assert abs((returned - today).days) <= 1


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


def test_put_can_swap_artist_id_for_manual(authed_records_client: TestClient) -> None:
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


# ---- pagination ----


def test_list_returns_total(authed_records_client: TestClient) -> None:
    """`total` フィールドが返り、items 件数と一致する (全件取得時)。"""
    for i in range(3):
        authed_records_client.post("/api/records", json=_new_record_payload(title=f"R{i}"))
    body = authed_records_client.get("/api/records").json()
    assert body["total"] == 3
    assert len(body["items"]) == 3


def test_list_limit_offset_returns_slice(authed_records_client: TestClient) -> None:
    """`?limit=2&offset=1` で items は slice、total は全件数。"""
    for i in range(5):
        authed_records_client.post("/api/records", json=_new_record_payload(title=f"R{i}"))
    body = authed_records_client.get("/api/records?limit=2&offset=1").json()
    titles = [r["title"] for r in body["items"]]
    assert titles == ["R1", "R2"]
    assert body["total"] == 5


def test_list_invalid_limit_returns_422(authed_records_client: TestClient) -> None:
    """`?limit=0` は ge=1 制約違反で 422。"""
    res = authed_records_client.get("/api/records?limit=0")
    assert res.status_code == 422


# ---- status filter / sort (ADR-013) ----


def test_list_status_wanted_filters_and_counts(authed_records_client: TestClient) -> None:
    """`?status=wanted` は wanted のみ返し、total も絞り込み後の件数。"""
    authed_records_client.post(
        "/api/records", json=_new_record_payload(title="Owned", status="owned")
    )
    authed_records_client.post(
        "/api/records", json=_new_record_payload(title="Want1", status="wanted")
    )
    authed_records_client.post(
        "/api/records", json=_new_record_payload(title="Want2", status="wanted")
    )

    body = authed_records_client.get("/api/records?status=wanted").json()
    assert body["total"] == 2
    assert {r["title"] for r in body["items"]} == {"Want1", "Want2"}
    assert all(r["status"] == "wanted" for r in body["items"])


def test_list_sort_artist_orders_by_name_then_title(authed_records_client: TestClient) -> None:
    """`?sort=artist` は artist 名昇順 → 同一 artist 内は title 昇順。

    seed: Avishai Cohen (A) < Bill Evans (B)。
    """
    authed_records_client.post(
        "/api/records", json=_new_record_payload(artist_id=BILL_EVANS_ID, title="Zoo")
    )
    authed_records_client.post(
        "/api/records", json=_new_record_payload(artist_id=BILL_EVANS_ID, title="Aaa")
    )
    authed_records_client.post(
        "/api/records", json=_new_record_payload(artist_id=AVISHAI_COHEN_ID, title="Seven Seas")
    )

    titles = [
        r["title"] for r in authed_records_client.get("/api/records?sort=artist").json()["items"]
    ]
    # Avishai Cohen の Seven Seas が先頭、続いて Bill Evans の Aaa → Zoo
    assert titles == ["Seven Seas", "Aaa", "Zoo"]


def test_list_sort_added_orders_by_created_at_desc(authed_records_client: TestClient) -> None:
    """`?sort=added` は created_at 降順 (追加が新しい順)。"""
    for i in range(3):
        authed_records_client.post("/api/records", json=_new_record_payload(title=f"R{i}"))
    titles = [
        r["title"] for r in authed_records_client.get("/api/records?sort=added").json()["items"]
    ]
    assert titles == ["R2", "R1", "R0"]


def test_list_status_and_sort_combined(authed_records_client: TestClient) -> None:
    """`?status=wanted&sort=artist` は wanted のみを artist 名昇順で返す。"""
    authed_records_client.post(
        "/api/records",
        json=_new_record_payload(artist_id=BILL_EVANS_ID, title="Owned B", status="owned"),
    )
    authed_records_client.post(
        "/api/records",
        json=_new_record_payload(artist_id=BILL_EVANS_ID, title="Want B", status="wanted"),
    )
    authed_records_client.post(
        "/api/records",
        json=_new_record_payload(artist_id=AVISHAI_COHEN_ID, title="Want A", status="wanted"),
    )

    body = authed_records_client.get("/api/records?status=wanted&sort=artist").json()
    titles = [r["title"] for r in body["items"]]
    assert titles == ["Want A", "Want B"]


def test_list_invalid_status_returns_422(authed_records_client: TestClient) -> None:
    res = authed_records_client.get("/api/records?status=bogus")
    assert res.status_code == 422


def test_list_invalid_sort_returns_422(authed_records_client: TestClient) -> None:
    res = authed_records_client.get("/api/records?sort=bogus")
    assert res.status_code == 422


# ---- pin via permissive PUT ----


def test_put_is_pinned_sets_pin(authed_records_client: TestClient) -> None:
    created = authed_records_client.post("/api/records", json=_new_record_payload()).json()
    res = authed_records_client.put(f"/api/records/{created['id']}", json={"is_pinned": True})
    assert res.status_code == 200
    assert res.json()["is_pinned"] is True


def test_put_is_pinned_over_limit_returns_409(
    authed_records_client: TestClient,
) -> None:
    """8 件 pin 済の状態で 9 件目を pin しようとすると 409。"""
    created_ids = [
        authed_records_client.post("/api/records", json=_new_record_payload(title=f"R{i}")).json()[
            "id"
        ]
        for i in range(9)
    ]
    for cid in created_ids[:8]:
        res = authed_records_client.put(f"/api/records/{cid}", json={"is_pinned": True})
        assert res.status_code == 200, res.text

    res = authed_records_client.put(f"/api/records/{created_ids[8]}", json={"is_pinned": True})
    assert res.status_code == 409


def test_list_orders_pinned_first(authed_records_client: TestClient) -> None:
    """pinned レコードが先頭に並ぶ (`is_pinned DESC, display_order ASC`)。"""
    authed_records_client.post("/api/records", json=_new_record_payload(title="A"))
    b = authed_records_client.post("/api/records", json=_new_record_payload(title="B")).json()
    authed_records_client.post("/api/records", json=_new_record_payload(title="C"))

    authed_records_client.put(f"/api/records/{b['id']}", json={"is_pinned": True})

    titles = [r["title"] for r in authed_records_client.get("/api/records").json()["items"]]
    assert titles == ["B", "A", "C"]
    # a, c は元の display_order 順を保つ
    assert titles.index("A") < titles.index("C")


# ---- pin reorder ----


def test_reorder_pins_changes_list_order(authed_records_client: TestClient) -> None:
    ids = [
        authed_records_client.post("/api/records", json=_new_record_payload(title=f"R{i}")).json()[
            "id"
        ]
        for i in range(3)
    ]
    for rid in ids:
        authed_records_client.put(f"/api/records/{rid}", json={"is_pinned": True})

    # 逆順に並び替え
    res = authed_records_client.put(
        "/api/records/pins/order", json={"ids": [ids[2], ids[0], ids[1]]}
    )
    assert res.status_code == 204

    titles = [r["title"] for r in authed_records_client.get("/api/records").json()["items"]]
    assert titles == ["R2", "R0", "R1"]


def test_reorder_pins_mismatched_returns_409(
    authed_records_client: TestClient,
) -> None:
    a = authed_records_client.post("/api/records", json=_new_record_payload(title="A")).json()
    b = authed_records_client.post("/api/records", json=_new_record_payload(title="B")).json()
    authed_records_client.put(f"/api/records/{a['id']}", json={"is_pinned": True})
    authed_records_client.put(f"/api/records/{b['id']}", json={"is_pinned": True})

    # 1 件足りない
    res = authed_records_client.put("/api/records/pins/order", json={"ids": [a["id"]]})
    assert res.status_code == 409


def test_reorder_pins_requires_auth(unauthed_client: TestClient) -> None:
    res = unauthed_client.put("/api/records/pins/order", json={"ids": [str(uuid.uuid4())]})
    assert res.status_code == 401


# ---- conflict (duplicate Spotify album) ----


def test_post_same_spotify_album_twice_returns_409(
    authed_records_client: TestClient,
) -> None:
    """同じ user が同じ Spotify album を 2 回 POST → 1 回目 201、2 回目 409。"""
    payload = _new_record_payload(spotify_album_id="alb-x", source="spotify", title="X")
    res1 = authed_records_client.post("/api/records", json=payload)
    assert res1.status_code == 201
    res2 = authed_records_client.post("/api/records", json=payload)
    assert res2.status_code == 409


# ---- delete ----


def test_delete_returns_204_and_removes(authed_records_client: TestClient) -> None:
    created = authed_records_client.post("/api/records", json=_new_record_payload()).json()

    res = authed_records_client.delete(f"/api/records/{created['id']}")
    assert res.status_code == 204
    assert authed_records_client.get("/api/records").json()["items"] == []


def test_delete_requires_auth(unauthed_client: TestClient, session: Session) -> None:
    res = unauthed_client.delete(f"/api/records/{uuid.uuid4()}")
    assert res.status_code == 401


def test_delete_unknown_id_returns_404(authed_records_client: TestClient) -> None:
    res = authed_records_client.delete(f"/api/records/{uuid.uuid4()}")
    assert res.status_code == 404


def test_delete_does_not_touch_user_follows(
    authed_records_client: TestClient, session: Session
) -> None:
    created = authed_records_client.post("/api/records", json=_new_record_payload()).json()
    user_id = _user_id(session)
    assert UserFollowRepository(session).list_artist_ids(user_id) == [BILL_EVANS_ID]

    res = authed_records_client.delete(f"/api/records/{created['id']}")
    assert res.status_code == 204

    assert UserFollowRepository(session).list_artist_ids(user_id) == [BILL_EVANS_ID]


def test_delete_does_not_touch_catalog(authed_records_client: TestClient, session: Session) -> None:
    """user_collection 削除後も catalog (vinyl_records) 行は残る (ADR-006 §2.7)。"""
    created = authed_records_client.post("/api/records", json=_new_record_payload()).json()
    catalog_before = list(session.exec(select(VinylRecord)).all())
    assert len(catalog_before) == 1

    authed_records_client.delete(f"/api/records/{created['id']}")

    session.expire_all()
    catalog_after = list(session.exec(select(VinylRecord)).all())
    assert len(catalog_after) == 1


# ---- favorite_tracks via PUT body ----


def test_create_with_favorite_tracks(authed_records_client: TestClient) -> None:
    payload = _new_record_payload(
        favorite_tracks=[
            {"track_name": "So What", "spotify_track_id": "t1", "note": "great solo"},
            {"track_name": "Freddie Freeloader", "spotify_track_id": "t2"},
        ]
    )
    res = authed_records_client.post("/api/records", json=payload)
    assert res.status_code == 201, res.text
    body = res.json()
    assert [t["track_name"] for t in body["favorite_tracks"]] == [
        "So What",
        "Freddie Freeloader",
    ]


def test_put_replaces_favorite_tracks(authed_records_client: TestClient) -> None:
    created = authed_records_client.post(
        "/api/records",
        json=_new_record_payload(
            favorite_tracks=[{"track_name": "Old", "spotify_track_id": "t-old"}]
        ),
    ).json()

    res = authed_records_client.put(
        f"/api/records/{created['id']}",
        json={
            "favorite_tracks": [
                {"track_name": "New 1", "spotify_track_id": "t1"},
                {"track_name": "New 2", "spotify_track_id": "t2"},
            ]
        },
    )
    assert res.status_code == 200
    assert [t["track_name"] for t in res.json()["favorite_tracks"]] == [
        "New 1",
        "New 2",
    ]


def test_put_empty_favorite_tracks_clears(authed_records_client: TestClient) -> None:
    created = authed_records_client.post(
        "/api/records",
        json=_new_record_payload(favorite_tracks=[{"track_name": "T", "spotify_track_id": "t1"}]),
    ).json()

    res = authed_records_client.put(f"/api/records/{created['id']}", json={"favorite_tracks": []})
    assert res.status_code == 200
    assert res.json()["favorite_tracks"] == []


def test_put_duplicate_favorite_track_spotify_id_returns_409(
    authed_records_client: TestClient,
) -> None:
    created = authed_records_client.post("/api/records", json=_new_record_payload()).json()
    res = authed_records_client.put(
        f"/api/records/{created['id']}",
        json={
            "favorite_tracks": [
                {"track_name": "A", "spotify_track_id": "t1"},
                {"track_name": "B", "spotify_track_id": "t1"},
            ]
        },
    )
    assert res.status_code == 409


# ---- concurrency / display_order ----


def test_concurrent_create_assigns_unique_display_order(engine: Engine) -> None:
    """Parallel POSTs each get a distinct display_order via the advisory lock."""
    with Session(engine) as bootstrap:
        _seed_artists_for_records(bootstrap)
        user = _seed_user(bootstrap)
        user_id = user.id

    n_workers = 5

    def worker(i: int) -> int:
        with Session(engine) as session:
            service = _make_service(session)
            record = service.create(
                VinylRecordCreate(artist_id=BILL_EVANS_ID, title=f"R{i}"), user_id
            )
            return record.display_order

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as ex:
        orders = sorted(ex.map(worker, range(n_workers)))

    assert orders == list(range(1, n_workers + 1))


# ---- cross-user isolation ----


def test_list_for_user_isolates_collections(session: Session, _test_settings: Settings) -> None:
    """user A の record は user B の GET /api/records に出ない。"""
    _seed_artists_for_records(session)
    user_a = _seed_user(session, spotify_id="user-a")
    user_b = _seed_user(session, spotify_id="user-b")

    _make_service(session).create(
        VinylRecordCreate(artist_id=BILL_EVANS_ID, title="A only"), user_a.id
    )
    _make_service(session).create(
        VinylRecordCreate(artist_id=BILL_EVANS_ID, title="B only"), user_b.id
    )

    def _override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: _test_settings
    try:
        app.dependency_overrides[get_current_user] = lambda: user_a
        c = TestClient(app)
        titles_a = [r["title"] for r in c.get("/api/records").json()["items"]]
        app.dependency_overrides[get_current_user] = lambda: user_b
        c = TestClient(app)
        titles_b = [r["title"] for r in c.get("/api/records").json()["items"]]
    finally:
        app.dependency_overrides.clear()

    assert titles_a == ["A only"]
    assert titles_b == ["B only"]


def test_update_other_users_record_returns_404(session: Session, _test_settings: Settings) -> None:
    _seed_artists_for_records(session)
    user_a = _seed_user(session, spotify_id="user-a")
    user_b = _seed_user(session, spotify_id="user-b")

    b_record = _make_service(session).create(
        VinylRecordCreate(artist_id=BILL_EVANS_ID, title="B"), user_b.id
    )

    def _override_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_settings] = lambda: _test_settings
    app.dependency_overrides[get_current_user] = lambda: user_a
    try:
        c = TestClient(app)
        res = c.put(f"/api/records/{b_record.id}", json={"memo": "hack"})
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 404
