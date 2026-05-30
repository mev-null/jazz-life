import datetime as dt
import uuid
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, select

from app.core.exceptions import ConflictError, NotFoundError
from app.core.repositories.artist_repository import ArtistRepository
from app.core.repositories.record_favorite_track_repository import (
    RecordFavoriteTrackRepository,
)
from app.core.repositories.record_repository import RecordRepository
from app.core.repositories.user_collection_repository import UserCollectionRepository
from app.core.repositories.user_follow_repository import UserFollowRepository
from app.models.artist import Artist
from app.models.record import VinylRecord
from app.models.record_favorite_track import RecordFavoriteTrack
from app.models.user import User
from app.models.user_collection import UserCollection
from app.schemas.record import (
    FavoriteTrack,
    VinylRecordCreate,
    VinylRecordUpdate,
)
from app.services.record_service import RecordService


def _seed_artist(session: Session, spotify_id: str = "test_artist") -> str:
    artist = Artist(
        spotify_id=spotify_id,
        name=f"Artist {spotify_id}",
        added_at=dt.datetime.now(dt.UTC),
    )
    session.add(artist)
    session.commit()
    return artist.spotify_id


def _seed_user(session: Session, spotify_id: str = "test-owner") -> UUID:
    user = User(spotify_id=spotify_id, display_name=f"User {spotify_id}", refresh_token="")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user.id


def _service(session: Session) -> RecordService:
    return RecordService(
        record_repo=RecordRepository(session),
        collection_repo=UserCollectionRepository(session),
        favorite_track_repo=RecordFavoriteTrackRepository(session),
        artist_repo=ArtistRepository(session),
        follow_repo=UserFollowRepository(session),
    )


# ---- create: display_order / id / auto-follow ----


def test_create_assigns_display_order_max_plus_one_per_user(session: Session) -> None:
    """display_order は user 単位で 1 から採番される (ADR-006 §2.6)。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    first = service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)
    second = service.create(VinylRecordCreate(artist_id=artist_id, title="B"), user_id)

    assert first.display_order == 1
    assert second.display_order == 2


def test_create_display_order_isolated_between_users(session: Session) -> None:
    """user A の display_order が user B に影響しない。"""
    artist_id = _seed_artist(session)
    user_a = _seed_user(session, spotify_id="user-a")
    user_b = _seed_user(session, spotify_id="user-b")
    service = _service(session)

    service.create(VinylRecordCreate(artist_id=artist_id, title="A1"), user_a)
    service.create(VinylRecordCreate(artist_id=artist_id, title="A2"), user_a)
    b_first = service.create(VinylRecordCreate(artist_id=artist_id, title="B1"), user_b)

    assert b_first.display_order == 1


def test_create_uses_uuid_v7_id_for_collection(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    record = service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)
    assert record.id.version == 7


def test_create_auto_follows_artist(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)

    follows = UserFollowRepository(session).list_artist_ids(user_id)
    assert follows == [artist_id]


def test_create_auto_follow_is_idempotent(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)
    service.create(VinylRecordCreate(artist_id=artist_id, title="B"), user_id)

    follows = UserFollowRepository(session).list_artist_ids(user_id)
    assert follows == [artist_id]


def test_create_with_unknown_artist_raises_not_found(session: Session) -> None:
    user_id = _seed_user(session)
    service = _service(session)
    with pytest.raises(NotFoundError, match="artist"):
        service.create(VinylRecordCreate(artist_id="ghost_artist", title="A"), user_id)


# ---- create: catalog dedup ----


def test_create_spotify_dedups_catalog_across_users(session: Session) -> None:
    """user A と user B が同じ spotify_album_id を POST → catalog 1 行、collections 2 行。"""
    artist_id = _seed_artist(session)
    user_a = _seed_user(session, spotify_id="user-a")
    user_b = _seed_user(session, spotify_id="user-b")
    service = _service(session)

    a = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            spotify_album_id="alb-1",
            source="spotify",
            title="Same Album",
        ),
        user_a,
    )
    b = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            spotify_album_id="alb-1",
            source="spotify",
            title="Same Album",
        ),
        user_b,
    )

    assert a.id != b.id  # collection.id は別
    assert a.spotify_album_id == b.spotify_album_id == "alb-1"
    # catalog 行は 1 つしかない
    catalog_rows = list(session.exec(select(VinylRecord)).all())
    assert len(catalog_rows) == 1


def test_create_manual_allows_duplicate_titles(session: Session) -> None:
    """source='manual' は spotify_album_id NULL なので catalog 重複可。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    service.create(VinylRecordCreate(artist_id=artist_id, title="Same Title"), user_id)
    service.create(VinylRecordCreate(artist_id=artist_id, title="Same Title"), user_id)

    catalog_rows = list(session.exec(select(VinylRecord)).all())
    assert len(catalog_rows) == 2


def test_create_same_spotify_album_twice_for_same_user_raises_conflict(
    session: Session,
) -> None:
    """UNIQUE(user_id, vinyl_record_id) で 409。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            spotify_album_id="alb-1",
            source="spotify",
            title="X",
        ),
        user_id,
    )
    with pytest.raises(ConflictError):
        service.create(
            VinylRecordCreate(
                artist_id=artist_id,
                spotify_album_id="alb-1",
                source="spotify",
                title="X",
            ),
            user_id,
        )


# ---- update_partial ----


def test_update_partial_only_changes_sent_fields(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            title="Original",
            memo="initial memo",
            original_release_date="1962",
        ),
        user_id,
    )
    original_created_at = record.created_at

    updated = service.update_partial(record.id, VinylRecordUpdate(memo="changed"), user_id)

    assert updated.memo == "changed"
    assert updated.title == "Original"
    assert updated.original_release_date == "1962"
    assert updated.created_at == original_created_at
    assert updated.updated_at >= original_created_at


def test_update_unknown_id_raises_not_found(session: Session) -> None:
    user_id = _seed_user(session)
    service = _service(session)
    with pytest.raises(NotFoundError):
        service.update_partial(uuid.uuid4(), VinylRecordUpdate(memo="x"), user_id)


def test_update_other_users_collection_raises_not_found(session: Session) -> None:
    """user B の collection を user A が更新しようとしても 404 (user_id ガード)。"""
    artist_id = _seed_artist(session)
    user_a = _seed_user(session, spotify_id="user-a")
    user_b = _seed_user(session, spotify_id="user-b")
    service = _service(session)
    b_record = service.create(VinylRecordCreate(artist_id=artist_id, title="B"), user_b)

    with pytest.raises(NotFoundError):
        service.update_partial(b_record.id, VinylRecordUpdate(memo="hack"), user_a)


def test_update_can_swap_artist_id_for_manual(session: Session) -> None:
    src = _seed_artist(session, "artist_src")
    dst = _seed_artist(session, "artist_dst")
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(VinylRecordCreate(artist_id=src, title="A"), user_id)

    updated = service.update_partial(record.id, VinylRecordUpdate(artist_id=dst), user_id)

    assert updated.artist_id == dst


def test_update_swap_to_unknown_artist_raises_not_found(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)

    with pytest.raises(NotFoundError, match="artist"):
        service.update_partial(record.id, VinylRecordUpdate(artist_id="ghost_artist"), user_id)


def test_update_spotify_catalog_silently_ignored(session: Session) -> None:
    """source='spotify' の catalog 行は他 user と共有しているので、title 等の
    catalog 編集は silently ignore する (ADR-006 §2.5)。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            spotify_album_id="alb-spot",
            source="spotify",
            title="Spotify Title",
        ),
        user_id,
    )

    updated = service.update_partial(record.id, VinylRecordUpdate(title="Hacked Title"), user_id)

    # title は元のまま、collection 系 (memo 等) は通る
    assert updated.title == "Spotify Title"


def test_update_promote_manual_to_spotify(session: Session) -> None:
    """manual record に spotify_album_id を埋めると catalog が promote される (§2.9)。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(VinylRecordCreate(artist_id=artist_id, title="Was Manual"), user_id)

    updated = service.update_partial(
        record.id,
        VinylRecordUpdate(spotify_album_id="alb-new", source="spotify"),
        user_id,
    )

    assert updated.spotify_album_id == "alb-new"
    assert updated.source == "spotify"


def test_update_promote_when_other_user_already_has_spotify_album(
    session: Session,
) -> None:
    """promote 先の Spotify album を他 user が既に catalog 化済み → collection を
    既存 catalog 行に付け替える (§2.9)。"""
    artist_id = _seed_artist(session)
    user_a = _seed_user(session, spotify_id="user-a")
    user_b = _seed_user(session, spotify_id="user-b")
    service = _service(session)

    # user A: 既に Spotify album を持っている
    a_record = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            spotify_album_id="alb-shared",
            source="spotify",
            title="Shared Album",
        ),
        user_a,
    )

    # user B: manual で同じアルバムを登録
    b_record = service.create(VinylRecordCreate(artist_id=artist_id, title="Was Manual"), user_b)

    # user B が後から「これ alb-shared だったわ」と promote
    updated_b = service.update_partial(
        b_record.id,
        VinylRecordUpdate(spotify_album_id="alb-shared", source="spotify"),
        user_b,
    )

    # 両者とも同じ catalog (alb-shared) を指す
    assert updated_b.spotify_album_id == "alb-shared"
    a_refreshed_collection = UserCollectionRepository(session).get(a_record.id)
    b_refreshed_collection = UserCollectionRepository(session).get(b_record.id)
    assert a_refreshed_collection is not None and b_refreshed_collection is not None
    assert a_refreshed_collection.vinyl_record_id == b_refreshed_collection.vinyl_record_id


# ---- purchase_date default / wanted→owned auto-stamp ----


def test_create_owned_without_purchase_date_defaults_to_today(session: Session) -> None:
    """owned + purchase_date 未指定 → サーバ側で今日 (JST) を打刻。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    record = service.create(
        VinylRecordCreate(artist_id=artist_id, title="A", status="owned"), user_id
    )

    today = dt.datetime.now(ZoneInfo("Asia/Tokyo")).date()
    assert record.purchase_date is not None
    # TZ 境界の flaky を避けるため ±1 日許容
    assert abs((record.purchase_date - today).days) <= 1


def test_create_owned_preserves_explicit_purchase_date(session: Session) -> None:
    """owned + 過去日を明示 → そのまま保存 (デフォルトに上書きされない)。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    record = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            title="A",
            status="owned",
            purchase_date=dt.date(2020, 1, 1),
        ),
        user_id,
    )

    assert record.purchase_date == dt.date(2020, 1, 1)


def test_create_wanted_forces_purchase_date_none(session: Session) -> None:
    """wanted は purchase_date を持たない。明示値が来ても None に強制。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    record = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            title="A",
            status="wanted",
            purchase_date=dt.date(2020, 1, 1),
        ),
        user_id,
    )

    assert record.purchase_date is None


def test_update_wanted_to_owned_auto_stamps_today(session: Session) -> None:
    """wanted → owned 遷移時、purchase_date が None なら今日 (JST) を打刻。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    wanted = service.create(
        VinylRecordCreate(artist_id=artist_id, title="A", status="wanted"), user_id
    )
    assert wanted.purchase_date is None

    updated = service.update_partial(wanted.id, VinylRecordUpdate(status="owned"), user_id)

    today = dt.datetime.now(ZoneInfo("Asia/Tokyo")).date()
    assert updated.status == "owned"
    assert updated.purchase_date is not None
    assert abs((updated.purchase_date - today).days) <= 1


def test_update_wanted_to_owned_respects_explicit_purchase_date(session: Session) -> None:
    """wanted → owned + 明示 purchase_date があれば、自動打刻より明示値を優先。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    wanted = service.create(
        VinylRecordCreate(artist_id=artist_id, title="A", status="wanted"), user_id
    )

    updated = service.update_partial(
        wanted.id,
        VinylRecordUpdate(status="owned", purchase_date=dt.date(2010, 1, 1)),
        user_id,
    )

    assert updated.purchase_date == dt.date(2010, 1, 1)


def test_update_owned_to_owned_does_not_touch_purchase_date(session: Session) -> None:
    """既に owned の行に status: owned を送っても purchase_date は変えない。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    owned = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            title="A",
            status="owned",
            purchase_date=dt.date(2015, 6, 1),
        ),
        user_id,
    )

    updated = service.update_partial(owned.id, VinylRecordUpdate(status="owned"), user_id)

    assert updated.purchase_date == dt.date(2015, 6, 1)


def test_update_partial_purchase_date_round_trips(session: Session) -> None:
    """通常の purchase_date 単体 patch (ADR-002 寛容 PUT) はそのまま反映される。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(
        VinylRecordCreate(artist_id=artist_id, title="A", status="owned"), user_id
    )

    updated = service.update_partial(
        record.id, VinylRecordUpdate(purchase_date=dt.date(1999, 12, 31)), user_id
    )

    assert updated.purchase_date == dt.date(1999, 12, 31)


# ---- delete ----


def test_delete_removes_collection_only(session: Session) -> None:
    """user_collection は消えるが catalog (vinyl_records) は残る (§2.7)。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)

    service.delete(record.id, user_id)

    assert UserCollectionRepository(session).get(record.id) is None
    # catalog 行は残っている
    catalog_rows = list(session.exec(select(VinylRecord)).all())
    assert len(catalog_rows) == 1


def test_delete_unknown_id_raises_not_found(session: Session) -> None:
    user_id = _seed_user(session)
    service = _service(session)
    with pytest.raises(NotFoundError, match="user_collection"):
        service.delete(uuid.uuid4(), user_id)


def test_delete_other_users_collection_raises_not_found(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_a = _seed_user(session, spotify_id="user-a")
    user_b = _seed_user(session, spotify_id="user-b")
    service = _service(session)
    b_record = service.create(VinylRecordCreate(artist_id=artist_id, title="B"), user_b)

    with pytest.raises(NotFoundError):
        service.delete(b_record.id, user_a)


def test_delete_leaves_user_follows_intact(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)
    assert UserFollowRepository(session).list_artist_ids(user_id) == [artist_id]

    service.delete(record.id, user_id)

    assert UserFollowRepository(session).list_artist_ids(user_id) == [artist_id]


def test_delete_cascades_to_favorite_tracks(session: Session) -> None:
    """user_collection 削除時、record_favorite_tracks も CASCADE で消える。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            title="A",
            favorite_tracks=[
                FavoriteTrack(track_name="Track 1", spotify_track_id="t1"),
                FavoriteTrack(track_name="Track 2", spotify_track_id="t2"),
            ],
        ),
        user_id,
    )
    assert len(RecordFavoriteTrackRepository(session).list_for_collection(record.id)) == 2

    service.delete(record.id, user_id)
    session.expire_all()
    favs = list(session.exec(select(RecordFavoriteTrack)).all())
    assert favs == []


# ---- favorite_tracks ----


def test_create_with_favorite_tracks_inserts_in_order(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    record = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            title="A",
            favorite_tracks=[
                FavoriteTrack(track_name="So What", spotify_track_id="t1", note="solo"),
                FavoriteTrack(track_name="Freddie", spotify_track_id="t2"),
            ],
        ),
        user_id,
    )

    assert [t.track_name for t in record.favorite_tracks] == ["So What", "Freddie"]
    assert record.favorite_tracks[0].note == "solo"
    assert record.favorite_tracks[1].note is None


def test_update_replaces_favorite_tracks(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            title="A",
            favorite_tracks=[FavoriteTrack(track_name="Old", spotify_track_id="t-old")],
        ),
        user_id,
    )

    updated = service.update_partial(
        record.id,
        VinylRecordUpdate(
            favorite_tracks=[
                FavoriteTrack(track_name="New 1", spotify_track_id="t1"),
                FavoriteTrack(track_name="New 2", spotify_track_id="t2"),
            ]
        ),
        user_id,
    )

    assert [t.track_name for t in updated.favorite_tracks] == ["New 1", "New 2"]


def test_update_with_empty_favorite_tracks_clears(session: Session) -> None:
    """`favorite_tracks=[]` を送ると全削除 (ADR-002 寛容 PUT)。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            title="A",
            favorite_tracks=[FavoriteTrack(track_name="T", spotify_track_id="t1")],
        ),
        user_id,
    )

    updated = service.update_partial(record.id, VinylRecordUpdate(favorite_tracks=[]), user_id)
    assert updated.favorite_tracks == []


def test_update_omits_favorite_tracks_keeps_existing(session: Session) -> None:
    """`favorite_tracks` フィールドを omit すると no-op (既存を維持)。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            title="A",
            favorite_tracks=[FavoriteTrack(track_name="T", spotify_track_id="t1")],
        ),
        user_id,
    )

    updated = service.update_partial(record.id, VinylRecordUpdate(memo="just memo"), user_id)
    assert [t.track_name for t in updated.favorite_tracks] == ["T"]


def test_set_favorite_tracks_duplicate_spotify_id_raises_conflict(
    session: Session,
) -> None:
    """同一 collection 内で同じ spotify_track_id を 2 回 INSERT → UNIQUE 違反 → 409。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)

    with pytest.raises(ConflictError, match="duplicate"):
        service.update_partial(
            record.id,
            VinylRecordUpdate(
                favorite_tracks=[
                    FavoriteTrack(track_name="A", spotify_track_id="t1"),
                    FavoriteTrack(track_name="B", spotify_track_id="t1"),
                ]
            ),
            user_id,
        )


def test_set_favorite_tracks_allows_multiple_manual_null_ids(session: Session) -> None:
    """`spotify_track_id` が NULL の manual 行は複数追加できる (partial UNIQUE)。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)

    updated = service.update_partial(
        record.id,
        VinylRecordUpdate(
            favorite_tracks=[
                FavoriteTrack(track_name="Manual 1"),
                FavoriteTrack(track_name="Manual 2"),
            ]
        ),
        user_id,
    )
    assert [t.track_name for t in updated.favorite_tracks] == ["Manual 1", "Manual 2"]


# ---- list_for_user / count ----


def test_list_for_user_returns_only_own_collections(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_a = _seed_user(session, spotify_id="user-a")
    user_b = _seed_user(session, spotify_id="user-b")
    service = _service(session)
    service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_a)
    service.create(VinylRecordCreate(artist_id=artist_id, title="B"), user_b)

    items_a, total_a = service.list_for_user(user_a)
    items_b, total_b = service.list_for_user(user_b)

    assert [r.title for r in items_a] == ["A"]
    assert [r.title for r in items_b] == ["B"]
    assert total_a == 1
    assert total_b == 1


def test_count_owned_by_artist_for_user_counts_only_owned(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    service.create(VinylRecordCreate(artist_id=artist_id, title="A", status="owned"), user_id)
    service.create(VinylRecordCreate(artist_id=artist_id, title="B", status="wanted"), user_id)

    counts = service.count_owned_by_artist_for_user(user_id)
    assert counts == {artist_id: 1}


def test_list_for_user_paginated_returns_slice_and_total(session: Session) -> None:
    """`limit/offset` 指定で items は slice、total は全件数を返す。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    for i in range(5):
        service.create(VinylRecordCreate(artist_id=artist_id, title=f"R{i}"), user_id)

    items, total = service.list_for_user(user_id, limit=2, offset=2)

    assert [r.title for r in items] == ["R2", "R3"]
    assert total == 5


def test_list_for_user_orders_pinned_first(session: Session) -> None:
    """`is_pinned DESC, display_order ASC` 順で並ぶ。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    # owned は作成時に auto-pin されるため、手動 pin の並び替えを検証するこの
    # テストでは wanted で作って初期状態を未 pin に固定する。
    service.create(VinylRecordCreate(artist_id=artist_id, title="A", status="wanted"), user_id)
    b = service.create(VinylRecordCreate(artist_id=artist_id, title="B", status="wanted"), user_id)
    service.create(VinylRecordCreate(artist_id=artist_id, title="C", status="wanted"), user_id)

    # B を pin する → 先頭に上がる
    service.update_partial(b.id, VinylRecordUpdate(is_pinned=True), user_id)

    items, _ = service.list_for_user(user_id)

    # B (pinned) → A, C (display_order 順)。a と c の relative order は保つ。
    assert [r.title for r in items] == ["B", "A", "C"]


def test_count_owned_isolated_between_users(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_a = _seed_user(session, spotify_id="user-a")
    user_b = _seed_user(session, spotify_id="user-b")
    service = _service(session)
    service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_a)

    counts_b = service.count_owned_by_artist_for_user(user_b)
    assert counts_b == {}


# ---- pin ----


def test_pin_sets_pinned_at_and_unpin_clears_it(session: Session) -> None:
    """is_pinned=True 化で pinned_at が now()、False で None に戻る。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    # wanted で作って未 pin から手動 pin する遷移を検証する。
    record = service.create(
        VinylRecordCreate(artist_id=artist_id, title="A", status="wanted"), user_id
    )

    pinned = service.update_partial(record.id, VinylRecordUpdate(is_pinned=True), user_id)
    assert pinned.is_pinned is True

    raw = UserCollectionRepository(session).get(record.id)
    assert raw is not None and raw.pinned_at is not None

    unpinned = service.update_partial(record.id, VinylRecordUpdate(is_pinned=False), user_id)
    assert unpinned.is_pinned is False
    session.expire_all()
    raw_after = UserCollectionRepository(session).get(record.id)
    assert raw_after is not None and raw_after.pinned_at is None


def test_pin_limit_exceeded_raises_conflict(session: Session) -> None:
    """7 件目の pin で `ConflictError` (`pin limit exceeded: max 6`)。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    # wanted で作って auto-pin を回避し、手動 pin の上限 enforce を検証する。
    records = [
        service.create(
            VinylRecordCreate(artist_id=artist_id, title=f"R{i}", status="wanted"), user_id
        )
        for i in range(7)
    ]

    for r in records[:6]:
        service.update_partial(r.id, VinylRecordUpdate(is_pinned=True), user_id)

    with pytest.raises(ConflictError, match="pin limit exceeded"):
        service.update_partial(records[6].id, VinylRecordUpdate(is_pinned=True), user_id)


def test_unpinning_frees_a_slot(session: Session) -> None:
    """6 件 pin → 1 件外す → 7 件目を新たに pin できる。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    records = [
        service.create(
            VinylRecordCreate(artist_id=artist_id, title=f"R{i}", status="wanted"), user_id
        )
        for i in range(7)
    ]
    for r in records[:6]:
        service.update_partial(r.id, VinylRecordUpdate(is_pinned=True), user_id)

    service.update_partial(records[0].id, VinylRecordUpdate(is_pinned=False), user_id)
    pinned7 = service.update_partial(records[6].id, VinylRecordUpdate(is_pinned=True), user_id)

    assert pinned7.is_pinned is True


def test_pin_assigns_incrementing_pin_order(session: Session) -> None:
    """新規 pin は `pin_order = max+1` で末尾に積まれる。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    records = [
        service.create(
            VinylRecordCreate(artist_id=artist_id, title=f"R{i}", status="wanted"), user_id
        )
        for i in range(3)
    ]

    pinned_orders: list[int | None] = []
    for r in records:
        updated = service.update_partial(r.id, VinylRecordUpdate(is_pinned=True), user_id)
        # _to_read には pin_order が無いので生 row で確認
        raw = UserCollectionRepository(session).get(updated.id)
        assert raw is not None
        pinned_orders.append(raw.pin_order)

    assert pinned_orders == [1, 2, 3]


def test_unpin_clears_pin_order(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    record = service.create(
        VinylRecordCreate(artist_id=artist_id, title="A", status="wanted"), user_id
    )

    service.update_partial(record.id, VinylRecordUpdate(is_pinned=True), user_id)
    service.update_partial(record.id, VinylRecordUpdate(is_pinned=False), user_id)

    session.expire_all()
    raw = UserCollectionRepository(session).get(record.id)
    assert raw is not None
    assert raw.pin_order is None


def test_reorder_pins_renumbers_1_to_n(session: Session) -> None:
    """`reorder_pins` で渡した順序通りに `pin_order` が 1..N で振り直される。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    records = [
        service.create(
            VinylRecordCreate(artist_id=artist_id, title=f"R{i}", status="wanted"), user_id
        )
        for i in range(3)
    ]
    for r in records:
        service.update_partial(r.id, VinylRecordUpdate(is_pinned=True), user_id)

    # 現在の順序: R0(1), R1(2), R2(3)。逆順に並び替える
    service.reorder_pins(user_id, [records[2].id, records[0].id, records[1].id])

    session.expire_all()
    raw_by_title = {r.title: UserCollectionRepository(session).get(r.id) for r in records}
    assert raw_by_title["R2"] is not None and raw_by_title["R2"].pin_order == 1
    assert raw_by_title["R0"] is not None and raw_by_title["R0"].pin_order == 2
    assert raw_by_title["R1"] is not None and raw_by_title["R1"].pin_order == 3

    # 並び順も order_by 経由で反映される
    items, _ = service.list_for_user(user_id)
    assert [r.title for r in items] == ["R2", "R0", "R1"]


def test_reorder_pins_mismatched_ids_raises(session: Session) -> None:
    """request の id 集合と現在 pin セットが不一致 → 409。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    r0 = service.create(
        VinylRecordCreate(artist_id=artist_id, title="R0", status="wanted"), user_id
    )
    r1 = service.create(
        VinylRecordCreate(artist_id=artist_id, title="R1", status="wanted"), user_id
    )
    service.update_partial(r0.id, VinylRecordUpdate(is_pinned=True), user_id)
    service.update_partial(r1.id, VinylRecordUpdate(is_pinned=True), user_id)

    # 1 件足りない
    with pytest.raises(ConflictError, match="pin reorder mismatch"):
        service.reorder_pins(user_id, [r0.id])
    # 余分な id
    with pytest.raises(ConflictError, match="pin reorder mismatch"):
        service.reorder_pins(user_id, [r0.id, r1.id, uuid.uuid4()])


def test_pin_already_pinned_is_noop(session: Session) -> None:
    """既に True の record を再度 True で送ってもカウントは増えない。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    # 6 件 pin して上限まで
    records = [
        service.create(
            VinylRecordCreate(artist_id=artist_id, title=f"R{i}", status="wanted"), user_id
        )
        for i in range(6)
    ]
    for r in records:
        service.update_partial(r.id, VinylRecordUpdate(is_pinned=True), user_id)

    # 既に pin 済みを再度 True で送る → 上限チェックを通過すべき
    again = service.update_partial(records[0].id, VinylRecordUpdate(is_pinned=True), user_id)
    assert again.is_pinned is True


# ---- auto-pin (owned 化の瞬間) ----


def test_create_owned_auto_pins_when_under_limit(session: Session) -> None:
    """owned で新規作成し pin 枠に空きがあれば auto-pin される。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    record = service.create(
        VinylRecordCreate(artist_id=artist_id, title="A", status="owned"), user_id
    )

    assert record.is_pinned is True
    raw = UserCollectionRepository(session).get(record.id)
    assert raw is not None and raw.pin_order == 1 and raw.pinned_at is not None


def test_create_wanted_does_not_auto_pin(session: Session) -> None:
    """wanted での作成は auto-pin されない (Home showcase は owned 用)。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)

    record = service.create(
        VinylRecordCreate(artist_id=artist_id, title="A", status="wanted"), user_id
    )

    assert record.is_pinned is False


def test_create_owned_does_not_pin_when_limit_reached(session: Session) -> None:
    """pin 枠 (6) が埋まっている状態の owned 新規作成は auto-pin されない。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    # 先に 6 件 owned を作って枠を埋める (全て auto-pin される)
    for i in range(6):
        service.create(
            VinylRecordCreate(artist_id=artist_id, title=f"R{i}", status="owned"), user_id
        )

    overflow = service.create(
        VinylRecordCreate(artist_id=artist_id, title="overflow", status="owned"), user_id
    )

    assert overflow.is_pinned is False


def test_update_wanted_to_owned_auto_pins_when_room(session: Session) -> None:
    """wanted→owned 遷移で枠に空きがあれば auto-pin される。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    wanted = service.create(
        VinylRecordCreate(artist_id=artist_id, title="A", status="wanted"), user_id
    )
    assert wanted.is_pinned is False

    updated = service.update_partial(wanted.id, VinylRecordUpdate(status="owned"), user_id)

    assert updated.is_pinned is True


def test_update_wanted_to_owned_does_not_pin_when_full(session: Session) -> None:
    """枠が埋まっている時の wanted→owned 遷移は auto-pin されない。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    for i in range(6):
        service.create(
            VinylRecordCreate(artist_id=artist_id, title=f"R{i}", status="owned"), user_id
        )
    wanted = service.create(
        VinylRecordCreate(artist_id=artist_id, title="W", status="wanted"), user_id
    )

    updated = service.update_partial(wanted.id, VinylRecordUpdate(status="owned"), user_id)

    assert updated.is_pinned is False


def test_update_wanted_to_owned_respects_explicit_is_pinned_false(session: Session) -> None:
    """同一リクエストで is_pinned=False を明示したら auto-pin は発動しない。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    wanted = service.create(
        VinylRecordCreate(artist_id=artist_id, title="A", status="wanted"), user_id
    )

    updated = service.update_partial(
        wanted.id, VinylRecordUpdate(status="owned", is_pinned=False), user_id
    )

    assert updated.is_pinned is False


# ---- catalog dedup / orphan ----


def test_delete_does_not_remove_shared_spotify_catalog(session: Session) -> None:
    """user A が削除しても user B が持っている同じ spotify catalog 行は消えない。"""
    artist_id = _seed_artist(session)
    user_a = _seed_user(session, spotify_id="user-a")
    user_b = _seed_user(session, spotify_id="user-b")
    service = _service(session)

    a = service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            spotify_album_id="alb-1",
            source="spotify",
            title="X",
        ),
        user_a,
    )
    service.create(
        VinylRecordCreate(
            artist_id=artist_id,
            spotify_album_id="alb-1",
            source="spotify",
            title="X",
        ),
        user_b,
    )

    service.delete(a.id, user_a)

    catalog_rows = list(session.exec(select(VinylRecord)).all())
    assert len(catalog_rows) == 1  # まだ user B が持っているので残る
    # user B の collection はまだ生きている
    b_collections = list(
        session.exec(select(UserCollection).where(UserCollection.user_id == user_b)).all()
    )
    assert len(b_collections) == 1
