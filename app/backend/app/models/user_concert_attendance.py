"""ユーザーの公演体験 (行きたい / 行った) を表すテーブル (ADR-003 §2.1)。

vinyl_records と違い、シンプルセット (status + rating + memo) のみ。
公演体験は自由記述に語らせる方針。
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import DateTime, Field, SQLModel


class UserConcertAttendance(SQLModel, table=True):
    __tablename__ = "user_concert_attendances"

    user_id: UUID = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        primary_key=True,
    )
    concert_id: str = Field(
        foreign_key="concerts.id",
        ondelete="CASCADE",
        primary_key=True,
        max_length=128,
    )
    # "wanted" (行きたい) / "attended" (行った)
    status: str = Field(max_length=20)
    rating: int | None = Field(default=None)
    memo: str | None = Field(default=None, max_length=2000)
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
