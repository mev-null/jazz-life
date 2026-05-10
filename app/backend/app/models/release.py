from datetime import date, datetime

from sqlmodel import DateTime, Field, SQLModel


class Release(SQLModel, table=True):
    __tablename__ = "releases"

    spotify_id: str = Field(primary_key=True, max_length=64)
    artist_id: str = Field(
        foreign_key="artists.spotify_id",
        ondelete="CASCADE",
        index=True,
        max_length=64,
    )
    title: str = Field(max_length=300)
    album_type: str = Field(max_length=20)
    release_date: date = Field(index=True)
    image_url: str | None = Field(default=None, max_length=500)
    is_read: bool = Field(default=False, index=True)
    read_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )
