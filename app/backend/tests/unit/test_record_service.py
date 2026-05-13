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

    items_a = service.list_for_user(user_a)
    items_b = service.list_for_user(user_b)

    assert [r.title for r in items_a] == ["A"]
    assert [r.title for r in items_b] == ["B"]


def test_count_owned_by_artist_for_user_counts_only_owned(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_id = _seed_user(session)
    service = _service(session)
    service.create(VinylRecordCreate(artist_id=artist_id, title="A", status="owned"), user_id)
    service.create(VinylRecordCreate(artist_id=artist_id, title="B", status="wanted"), user_id)

    counts = service.count_owned_by_artist_for_user(user_id)
    assert counts == {artist_id: 1}


def test_count_owned_isolated_between_users(session: Session) -> None:
    artist_id = _seed_artist(session)
    user_a = _seed_user(session, spotify_id="user-a")
    user_b = _seed_user(session, spotify_id="user-b")
    service = _service(session)
    service.create(VinylRecordCreate(artist_id=artist_id, title="A"), user_a)

    counts_b = service.count_owned_by_artist_for_user(user_b)
    assert counts_b == {}


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
