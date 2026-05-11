import uuid
from datetime import UTC, date, datetime

import uuid6
from sqlmodel import DateTime, Field, SQLModel


class VinylRecord(SQLModel, table=True):
    __tablename__ = "vinyl_records"

    id: uuid.UUID = Field(default_factory=uuid6.uuid7, primary_key=True)
    artist_id: str = Field(
        foreign_key="artists.spotify_id",
        ondelete="RESTRICT",
        index=True,
        max_length=64,
    )
    spotify_album_id: str | None = Field(default=None, max_length=64, index=True)
    source: str = Field(default="manual", max_length=20)
    # ADR-003 §2.1: "owned" は Home マトリクスに表示、"wanted" は want list 専用。
    # 既存行への ALTER 用に server_default を明示する (autogenerate が拾えるように)。
    status: str = Field(
        default="owned",
        max_length=20,
        sa_column_kwargs={"server_default": "owned"},
    )
    title: str = Field(max_length=300)
    image_url: str | None = Field(default=None, max_length=500)
    original_release_date: str | None = Field(default=None, max_length=10)
    pressing_info: str | None = Field(default=None, max_length=200)
    purchase_date: date | None = Field(default=None)
    purchase_store: str | None = Field(default=None, max_length=200)
    purchase_price: int | None = Field(default=None)
    purchase_currency: str = Field(default="JPY", max_length=3)
    rating: int | None = Field(default=None)
    memo: str | None = Field(default=None, max_length=2000)
    favorite_tracks: str | None = Field(default=None, max_length=2000)
    display_order: int = Field(index=True)
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
