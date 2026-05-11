"""ユーザーが artist をフォロー・ピン留めしている関係を持つテーブル (ADR-003 §2.1)。

artists マスタから `followed` カラムを切り出し、ユーザー側責務に寄せたもの。
- フォロー / 解除はこのテーブルの存在で表現
- ピン留めは `pinned=true`、サービス層で 5 件上限をチェック
- 「所有か興味か」は `vinyl_records.status` の存在から派生判定するためここには持たない
- 4 週間アクセスなしの自然減衰用に `last_action_at` と `archived_flag` を保持
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import DateTime, Field, SQLModel


class UserFollow(SQLModel, table=True):
    __tablename__ = "user_follows"

    user_id: UUID = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        primary_key=True,
    )
    artist_id: str = Field(
        foreign_key="artists.spotify_id",
        ondelete="CASCADE",
        primary_key=True,
        max_length=64,
    )
    pinned: bool = Field(default=False, index=True)
    followed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    pinned_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )
    last_action_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    archived_flag: bool = Field(default=False, index=True)
