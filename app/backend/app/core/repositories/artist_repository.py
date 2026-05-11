from uuid import UUID

from sqlmodel import Session, col, func, select

from app.models.artist import Artist
from app.models.user_follow import UserFollow


class ArtistRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[Artist]:
        stmt = select(Artist).order_by(col(Artist.added_at).desc())
        return list(self.session.exec(stmt).all())

    def list_followed_by(self, user_id: UUID) -> list[Artist]:
        """指定ユーザが現在 follow 中 (archived_flag=false) の artists のみ返す。

        Artists 一覧画面用。auto-follow で record 登録時に user_follows へ追加
        されているはずの行のうち、unfollow されていないものに限定する。
        archived な行は除外するので「以前持っていた / 興味あった」アーティスト
        は出さない。
        """
        stmt = (
            select(Artist)
            .join(UserFollow, col(Artist.spotify_id) == col(UserFollow.artist_id))
            .where(col(UserFollow.user_id) == user_id)
            .where(col(UserFollow.archived_flag).is_(False))
            .order_by(col(Artist.added_at).desc())
        )
        return list(self.session.exec(stmt).all())

    def get(self, spotify_id: str) -> Artist | None:
        return self.session.get(Artist, spotify_id)

    def count(self) -> int:
        stmt = select(func.count()).select_from(Artist)
        return self.session.exec(stmt).one() or 0

    def update_image(self, spotify_id: str, image_url: str) -> Artist | None:
        artist = self.session.get(Artist, spotify_id)
        if artist is None:
            return None
        artist.image_url = image_url
        self.session.add(artist)
        self.session.commit()
        self.session.refresh(artist)
        return artist

    def bulk_insert(self, rows: list[Artist]) -> None:
        self.session.add_all(rows)
        self.session.commit()

    def add(self, artist: Artist) -> Artist:
        self.session.add(artist)
        self.session.commit()
        self.session.refresh(artist)
        return artist
