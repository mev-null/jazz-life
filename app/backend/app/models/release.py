from datetime import date

from sqlmodel import Field, SQLModel


class Release(SQLModel, table=True):
    """Spotify から日次同期される album メタ情報の catalog テーブル (ADR-007)。

    全 user 間で 1 album = 1 row として共有される。既読状態は
    `release_read_states` テーブルで per-user に持つ。
    """

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
