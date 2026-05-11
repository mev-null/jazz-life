import uuid
from datetime import UTC, datetime

import uuid6
from sqlmodel import DateTime, Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid6.uuid7, primary_key=True)
    spotify_id: str = Field(index=True, unique=True, max_length=64)
    display_name: str = Field(max_length=200)
    image_url: str | None = Field(default=None, max_length=500)
    # Fernet 暗号化済みの refresh_token (base64)。base64 で長くなるため余裕を持たせる。
    refresh_token: str = Field(max_length=1024)
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
