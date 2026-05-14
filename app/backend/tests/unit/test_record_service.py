import datetime as dt
import uuid
from uuid import UUID

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
    service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)
    b = service.create(VinylRecordCreate(artist_id=artist_id, title="B"), user_id)
    service.create(VinylRecordCreate(artist_id=artist_id, title="C"), user_id)

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
    record = service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)

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
    """9 件目の pin で `ConflictError` (`pin limit exceeded: max 8`)。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    records = [
        service.create(VinylRecordCreate(artist_id=artist_id, title=f"R{i}"), user_id)
        for i in range(9)
    ]

    for r in records[:8]:
        service.update_partial(r.id, VinylRecordUpdate(is_pinned=True), user_id)

    with pytest.raises(ConflictError, match="pin limit exceeded"):
        service.update_partial(records[8].id, VinylRecordUpdate(is_pinned=True), user_id)


def test_unpinning_frees_a_slot(session: Session) -> None:
    """8 件 pin → 1 件外す → 9 件目を新たに pin できる。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    records = [
        service.create(VinylRecordCreate(artist_id=artist_id, title=f"R{i}"), user_id)
        for i in range(9)
    ]
    for r in records[:8]:
        service.update_partial(r.id, VinylRecordUpdate(is_pinned=True), user_id)

    service.update_partial(records[0].id, VinylRecordUpdate(is_pinned=False), user_id)
    pinned9 = service.update_partial(records[8].id, VinylRecordUpdate(is_pinned=True), user_id)

    assert pinned9.is_pinned is True


def test_pin_assigns_incrementing_pin_order(session: Session) -> None:
    """新規 pin は `pin_order = max+1` で末尾に積まれる。"""
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    records = [
        service.create(VinylRecordCreate(artist_id=artist_id, title=f"R{i}"), user_id)
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
    record = service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_id)

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
        service.create(VinylRecordCreate(artist_id=artist_id, title=f"R{i}"), user_id)
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
    r0 = service.create(VinylRecordCreate(artist_id=artist_id, title="R0"), user_id)
    r1 = service.create(VinylRecordCreate(artist_id=artist_id, title="R1"), user_id)
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
    # 8 件 pin して上限まで
    records = [
        service.create(VinylRecordCreate(artist_id=artist_id, title=f"R{i}"), user_id)
        for i in range(8)
    ]
    for r in records:
        service.update_partial(r.id, VinylRecordUpdate(is_pinned=True), user_id)

    # 既に pin 済みを再度 True で送る → 上限チェックを通過すべき
    again = service.update_partial(records[0].id, VinylRecordUpdate(is_pinned=True), user_id)
    assert again.is_pinned is True


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
