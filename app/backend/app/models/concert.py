import datetime as dt

from sqlmodel import DateTime, Field, SQLModel


class Venue(SQLModel, table=True):
    __tablename__ = "venues"

    id: str = Field(primary_key=True, max_length=64)
    name: str = Field(max_length=200)
    city: str = Field(max_length=100)


class Concert(SQLModel, table=True):
    __tablename__ = "concerts"

    id: str = Field(primary_key=True, max_length=128)
    venue_id: str = Field(
        foreign_key="venues.id",
        ondelete="RESTRICT",
        index=True,
        max_length=64,
    )
    date: dt.date = Field(index=True)
    title: str = Field(max_length=500)
    url: str | None = Field(default=None, max_length=500)
    stage_times: str | None = Field(default=None, max_length=200)
    status: str = Field(default="scheduled", max_length=20)
    # ADR-003 §2.1: "scraped" はスクレイピング由来、"manual" はユーザー手動追加
    # (過去公演 / 海外 / 閉鎖会場など)。
    source: str = Field(
        default="scraped",
        max_length=20,
        sa_column_kwargs={"server_default": "scraped"},
    )
    # 手動追加時に venue マスタに登録するほどでもない会場を自由記述で残す。
    # venue_id 自体の nullable 化は別 PR (ADR-003 PR-6) で扱う。
    venue_name_freetext: str | None = Field(default=None, max_length=200)
    first_seen_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    last_seen_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    is_read: bool = Field(default=False, index=True)
    read_at: dt.datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )


class ConcertArtist(SQLModel, table=True):
    __tablename__ = "concert_artists"

    concert_id: str = Field(
        foreign_key="concerts.id",
        ondelete="CASCADE",
        primary_key=True,
        max_length=128,
    )
    artist_id: str = Field(
        foreign_key="artists.spotify_id",
        ondelete="CASCADE",
        primary_key=True,
        max_length=64,
    )
