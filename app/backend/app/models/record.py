import uuid
from datetime import UTC, datetime

import uuid6
from sqlalchemy import Index, text
from sqlmodel import DateTime, Field, SQLModel


class VinylRecord(SQLModel, table=True):
    """Album メタ情報の catalog テーブル (ADR-006)。

    `source='spotify'` 行は `spotify_album_id` を持ち、partial UNIQUE INDEX で
    全 user 間 dedup される (1 album = 1 row)。`source='manual'` 行は
    `spotify_album_id` NULL で重複可。所有関係は user_collections 側で持つ。
    """

    __tablename__ = "vinyl_records"
    __table_args__ = (
        Index(
            "uq_vinyl_records_spotify_album_id_not_null",
            "spotify_album_id",
            unique=True,
            postgresql_where=text("spotify_album_id IS NOT NULL"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid6.uuid7, primary_key=True)
    artist_id: str = Field(
        foreign_key="artists.spotify_id",
        ondelete="RESTRICT",
        index=True,
        max_length=64,
    )
    spotify_album_id: str | None = Field(default=None, max_length=64)
    source: str = Field(default="manual", max_length=20)
    title: str = Field(max_length=300)
    image_url: str | None = Field(default=None, max_length=500)
    original_release_date: str | None = Field(default=None, max_length=10)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
