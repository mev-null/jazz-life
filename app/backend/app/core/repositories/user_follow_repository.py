from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session, col, func, select

from app.models.user_follow import UserFollow


class UserFollowRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_artist_ids(self, user_id: UUID) -> list[str]:
        """フォロー中アーティストの spotify_id 配列。archived_flag=true は除外。"""
        stmt = (
            select(UserFollow.artist_id)
            .where(col(UserFollow.user_id) == user_id)
            .where(col(UserFollow.archived_flag).is_(False))
        )
        return list(self.session.exec(stmt).all())

    def count_by_user(self, user_id: UUID) -> int:
        """seed 判定用に「ユーザが follow しているレコード数」を返す。

        archived_flag は問わない (一度 follow したら user_follows 行は残るので、
        0 件 = まだ一度も follow していない = seed 対象)。
        """
        stmt = (
            select(func.count()).select_from(UserFollow).where(col(UserFollow.user_id) == user_id)
        )
        return self.session.exec(stmt).one() or 0

    def bulk_insert(self, user_id: UUID, artist_ids: list[str]) -> int:
        """artist_id 配列を user_follows に投入する。既存 (user_id, artist_id) は無視。

        seed_user_follows_if_empty の実装用。同じ user で 2 度叩いても安全。
        """
        if not artist_ids:
            return 0
        payloads = [{"user_id": user_id, "artist_id": aid} for aid in artist_ids]
        stmt = (
            pg_insert(UserFollow)
            .values(payloads)
            .on_conflict_do_nothing(index_elements=["user_id", "artist_id"])
        )
        self.session.exec(stmt)  # type: ignore[call-overload]
        self.session.commit()
        return len(artist_ids)

    def upsert(self, user_id: UUID, artist_id: str) -> None:
        """1 件の (user_id, artist_id) を follow に追加 / 再有効化する。

        record 登録時の auto-follow 経路で使う。挙動:
        - 行が無ければ INSERT (archived_flag のデフォルトは False)
        - 既に archived な行があれば archived_flag=False に戻して再 follow
        - 既に active な行があれば no-op (上書きで害なし)

        「以前 unfollow したアーティストの record を再追加 → 自動的に re-follow」
        という UX を担保するため、`ON CONFLICT DO UPDATE` で archived_flag を
        必ず False に書き直す。
        """
        stmt = (
            pg_insert(UserFollow)
            .values(user_id=user_id, artist_id=artist_id, archived_flag=False)
            .on_conflict_do_update(
                index_elements=["user_id", "artist_id"],
                set_={"archived_flag": False},
            )
        )
        self.session.exec(stmt)  # type: ignore[call-overload]
        self.session.commit()

    def archive(self, user_id: UUID, artist_id: str) -> bool:
        """(user_id, artist_id) の follow を soft delete (`archived_flag=true`) する。

        該当行が無ければ False、archive 済の行を更新したら True を返す。
        既に archived の行に対しては True を返す (冪等性)。
        list_artist_ids が archived_flag=False のみ返すので、archive 後は sync
        対象から自然に外れる。
        """
        stmt = (
            select(UserFollow)
            .where(col(UserFollow.user_id) == user_id)
            .where(col(UserFollow.artist_id) == artist_id)
        )
        row = self.session.exec(stmt).first()
        if row is None:
            return False
        row.archived_flag = True
        self.session.add(row)
        self.session.commit()
        return True
