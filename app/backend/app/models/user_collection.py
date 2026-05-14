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
    # Home プレビューに何を見せるかをユーザが編集する手段。上限 8 件は
    # `record_service` が enforce。`pin_order` は pinned 内での並び順 (drag &
    # drop で書き換える)。`pinned_at` は将来分析用に残してある (Home の表示順
    # 自体は pin_order ASC で決まる)。
    is_pinned: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "false"},
    )
    pin_order: int | None = Field(default=None)
    pinned_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )
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
