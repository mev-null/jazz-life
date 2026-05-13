import uuid
from datetime import datetime

from sqlmodel import DateTime, Field, SQLModel


class ReleaseReadState(SQLModel, table=True):
    """User ごとの release 既読状態 (ADR-007)。

    行があれば既読、無ければ未読。`read_at` は既読化の時刻。
    `(user_id, release_spotify_id)` 複合 PK、両 FK は ON DELETE CASCADE。
    """

    __tablename__ = "release_read_states"

    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        primary_key=True,
        index=True,
    )
    release_spotify_id: str = Field(
        foreign_key="releases.spotify_id",
        ondelete="CASCADE",
        primary_key=True,
        max_length=64,
    )
    read_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
