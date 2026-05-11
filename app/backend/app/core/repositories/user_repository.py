import uuid
from datetime import UTC, datetime

from sqlmodel import Session, col, select

from app.models.user import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, id: uuid.UUID) -> User | None:
        return self.session.get(User, id)

    def get_by_spotify_id(self, spotify_id: str) -> User | None:
        stmt = select(User).where(col(User.spotify_id) == spotify_id)
        return self.session.exec(stmt).first()

    def upsert_from_spotify(
        self,
        spotify_id: str,
        display_name: str,
        image_url: str | None,
        encrypted_refresh_token: str,
    ) -> User:
        """Insert a new user row or update profile + refresh_token of an existing one.

        upsert を 1 トランザクションで完結させる。display_name / image_url は Spotify
        側で変わる可能性があるためログイン毎に更新する。refresh_token も都度更新
        (Spotify が rotate するケースに備える)。
        """
        now = datetime.now(UTC)
        existing = self.get_by_spotify_id(spotify_id)
        if existing is None:
            user = User(
                spotify_id=spotify_id,
                display_name=display_name,
                image_url=image_url,
                refresh_token=encrypted_refresh_token,
                created_at=now,
                updated_at=now,
            )
            self.session.add(user)
            self.session.commit()
            self.session.refresh(user)
            return user
        existing.display_name = display_name
        existing.image_url = image_url
        existing.refresh_token = encrypted_refresh_token
        existing.updated_at = now
        self.session.add(existing)
        self.session.commit()
        self.session.refresh(existing)
        return existing
