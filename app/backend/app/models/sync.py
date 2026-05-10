from datetime import datetime

from sqlmodel import DateTime, Field, SQLModel, Text


class SyncStatus(SQLModel, table=True):
    __tablename__ = "sync_status"

    source: str = Field(primary_key=True, max_length=64)
    last_success_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )
    last_attempt_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )
    last_error: str | None = Field(default=None, sa_type=Text)
