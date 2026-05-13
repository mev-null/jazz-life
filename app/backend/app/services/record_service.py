import datetime as dt
import uuid
from uuid import UUID

from app.core.exceptions import NotFoundError
from app.core.repositories.artist_repository import ArtistRepository
from app.core.repositories.record_repository import RecordRepository
from app.core.repositories.user_follow_repository import UserFollowRepository
from app.models.record import VinylRecord
from app.schemas.record import VinylRecordCreate, VinylRecordUpdate


class RecordService:
    def __init__(
        self,
        repo: RecordRepository,
        artist_repo: ArtistRepository,
        follow_repo: UserFollowRepository,
    ) -> None:
        self.repo = repo
        self.artist_repo = artist_repo
        self.follow_repo = follow_repo

    def list_all(self) -> list[VinylRecord]:
        return self.repo.list_all()

    def count_owned_by_artist_for_user(self, user_id: UUID) -> dict[str, int]:
        """current user の所有レコード数を artist_id ごとに返す。

        repo 層の同名メソッドへの薄いラッパ。詳細はそちらの docstring を参照。
        """
        return self.repo.count_owned_by_artist_for_user(user_id)

    def create(self, data: VinylRecordCreate, user_id: UUID) -> VinylRecord:
        """Record を 1 件作成し、同じトランザクション扱いで該当 artist を
        ユーザのフォローに自動追加する (auto-follow on record create)。

        ADR-003 + Phase B-3 設計: 「seeds/artists.json は空に倒し、artist は
        ユーザが record を登録する経路で動的に生まれる」 設計の中核。
        record を持っている = そのアーティストに興味がある = フォロー扱い、
        とすることで release sync 対象が自然に正しい集合になる。
        """
        self._ensure_artist_exists(data.artist_id)
        # Serialize display_order assignment across concurrent POSTs. Released
        # with the transaction inside repo.add(...).
        self.repo.lock_for_display_order()
        next_order = self.repo.max_display_order() + 1
        now = dt.datetime.now(dt.UTC)
        record = VinylRecord(
            **data.model_dump(),
            display_order=next_order,
            created_at=now,
            updated_at=now,
        )
        saved = self.repo.add(record)
        # 既に follow 済みなら no-op (on_conflict_do_nothing)。
        self.follow_repo.upsert(user_id, saved.artist_id)
        return saved

    def delete(self, id: uuid.UUID) -> None:
        """1 件削除。存在しなければ NotFoundError。

        user_follows は意図的に触らない (record の生死と follow の独立性を
        保つ。最後の record を消しても follow は残る)。auto-unfollow が必要に
        なったらここに足す。
        """
        record = self.repo.get(id)
        if record is None:
            raise NotFoundError(f"vinyl_record id={id}")
        self.repo.delete(record)

    def update_partial(self, id: uuid.UUID, patch: VinylRecordUpdate) -> VinylRecord:
        record = self.repo.get(id)
        if record is None:
            raise NotFoundError(f"vinyl_record id={id}")
        patch_data = patch.model_dump(exclude_unset=True)
        new_artist_id = patch_data.get("artist_id")
        if new_artist_id is not None and new_artist_id != record.artist_id:
            self._ensure_artist_exists(new_artist_id)
        for key, value in patch_data.items():
            setattr(record, key, value)
        record.updated_at = dt.datetime.now(dt.UTC)
        return self.repo.save(record)

    def _ensure_artist_exists(self, artist_id: str) -> None:
        if self.artist_repo.get(artist_id) is None:
            raise NotFoundError(f"artist spotify_id={artist_id}")
