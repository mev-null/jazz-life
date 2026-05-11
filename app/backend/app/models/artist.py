from datetime import UTC, datetime

from sqlmodel import DateTime, Field, SQLModel


class Artist(SQLModel, table=True):
    __tablename__ = "artists"

    spotify_id: str = Field(primary_key=True, max_length=64)
    name: str = Field(max_length=200, index=True)
    image_url: str | None = Field(default=None, max_length=500)
    # ADR-003: artists マスタは「フォローしているか」を持たず、user_follows に責務を委譲。
    # source は "seeded" (初期投入) / "spotify_dynamic" (Spotify 検索由来で動的追加)
    # / "manual" (将来の手入力) の 3 値を取る。
    source: str = Field(default="seeded", max_length=20)
    added_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )


class ArtistAlias(SQLModel, table=True):
    __tablename__ = "artist_aliases"

    id: int | None = Field(default=None, primary_key=True)
    artist_id: str = Field(
        foreign_key="artists.spotify_id",
        ondelete="CASCADE",
        index=True,
        max_length=64,
    )
    alias_name: str = Field(max_length=200, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
