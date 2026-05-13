import uuid
from datetime import UTC, date, datetime

import uuid6
from sqlmodel import DateTime, Field, SQLModel, UniqueConstraint


class UserCollection(SQLModel, table=True):
    """User の所有関係 (ownership) テーブル (ADR-006)。

    1 ユーザが 1 catalog 行を 2 度持つことは UNIQUE INDEX で禁止。
    `display_order` は user 単位の advisory lock で直列化採番する。
    """

    __tablename__ = "user_collections"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "vinyl_record_id",
            name="uq_user_collections_user_vinyl_record",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid6.uuid7, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        index=True,
    )
    vinyl_record_id: uuid.UUID = Field(
        foreign_key="vinyl_records.id",
        ondelete="CASCADE",
        index=True,
    )
    status: str = Field(
        default="owned",
        max_length=20,
        sa_column_kwargs={"server_default": "owned"},
    )
    pressing_info: str | None = Field(default=None, max_length=200)
    purchase_date: date | None = Field(default=None)
    purchase_store: str | None = Field(default=None, max_length=200)
    purchase_price: int | None = Field(default=None)
    purchase_currency: str = Field(
        default="JPY",
        max_length=3,
        sa_column_kwargs={"server_default": "JPY"},
    )
    rating: int | None = Field(default=None)
    memo: str | None = Field(default=None, max_length=2000)
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
