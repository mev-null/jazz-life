from sqlmodel import Session, col, func, select

from app.models.artist import Artist


class ArtistRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[Artist]:
        stmt = select(Artist).order_by(col(Artist.added_at).desc())
        return list(self.session.exec(stmt).all())

    def get(self, spotify_id: str) -> Artist | None:
        return self.session.get(Artist, spotify_id)

    def count(self) -> int:
        stmt = select(func.count()).select_from(Artist)
        return self.session.exec(stmt).one() or 0

    def bulk_insert(self, rows: list[Artist]) -> None:
        self.session.add_all(rows)
        self.session.commit()
