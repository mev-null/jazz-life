"""add_pin_order_to_user_collections

ピン済みレコード同士の並び順 (drag & drop で書き換える) を保持する
`pin_order` カラムを追加する。非 pin 行は NULL。

Revision ID: bce2b8b6d3e1
Revises: 3f2971c32f64
Create Date: 2026-05-14 04:03:34.939184+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bce2b8b6d3e1"
down_revision: str | Sequence[str] | None = "3f2971c32f64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_collections",
        sa.Column("pin_order", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_collections", "pin_order")
