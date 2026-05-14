"""add_pin_to_user_collections

UserCollection に Home プレビュー編集用の `is_pinned` / `pinned_at` を追加する。

Revision ID: 3f2971c32f64
Revises: 584c75938220
Create Date: 2026-05-14 03:37:26.908923+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3f2971c32f64"
down_revision: str | Sequence[str] | None = "584c75938220"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_collections",
        sa.Column(
            "is_pinned",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "user_collections",
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_collections", "pinned_at")
    op.drop_column("user_collections", "is_pinned")
