"""adr007 release read states

ADR-007 §3.3 の手書き Migration。releases の per-user 既読状態と配信スコープを
分離する:

1. `DELETE FROM releases` (本番未投入なので OK、is_read 列付きのデータは破棄)
2. `releases` から `ix_releases_is_read` インデックス DROP
3. `releases` から `is_read` / `read_at` 列を DROP
4. `release_read_states` テーブル作成 (複合 PK + 2 FK + user_id INDEX)

Revision ID: 584c75938220
Revises: 9989037f7efe
Create Date: 2026-05-13 18:28:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "584c75938220"
down_revision: str | Sequence[str] | None = "9989037f7efe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. 本番未投入のため既存 releases は破棄する (is_read 列付きのデータごと)
    op.execute("DELETE FROM releases")

    # 2. is_read の INDEX を DROP してから列を DROP
    op.drop_index(op.f("ix_releases_is_read"), table_name="releases")
    op.drop_column("releases", "is_read")
    op.drop_column("releases", "read_at")

    # 3. release_read_states (ADR-007 §3.2)
    op.create_table(
        "release_read_states",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "release_spotify_id",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["release_spotify_id"], ["releases.spotify_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "release_spotify_id"),
    )
    op.create_index(
        op.f("ix_release_read_states_user_id"),
        "release_read_states",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """ADR-007: pre-deploy migration なので downgrade は実装しない。

    本番投入後は `DELETE FROM releases` 前提が崩れるので、その場合は別途
    段階移行 plan を切る。
    """
    pass
