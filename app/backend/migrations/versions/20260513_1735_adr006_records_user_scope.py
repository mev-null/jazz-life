"""adr006 records user scope schema

ADR-006 §3.3 の手書き Migration。records を catalog + ownership に 2 層分離する。

手順:
1. `DELETE FROM vinyl_records` (本番未投入なので OK)
2. `vinyl_records` から ownership 系列を DROP
3. `vinyl_records.spotify_album_id` に partial UNIQUE INDEX を貼る
4. `user_collections` テーブル作成 (UNIQUE INDEX 含む)
5. `record_favorite_tracks` テーブル作成 (partial INDEX 含む)

Alembic autogenerate は partial UNIQUE INDEX の postgresql_where で安定しない
ため本 migration は手書き。

Revision ID: 9989037f7efe
Revises: 9061b123e963
Create Date: 2026-05-13 17:35:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "9989037f7efe"
down_revision: str | Sequence[str] | None = "9061b123e963"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. 本番未投入のため既存 records は破棄する。
    op.execute("DELETE FROM vinyl_records")

    # 2. vinyl_records を catalog 化: ownership 系列を DROP
    op.drop_column("vinyl_records", "status")
    op.drop_column("vinyl_records", "pressing_info")
    op.drop_column("vinyl_records", "purchase_date")
    op.drop_column("vinyl_records", "purchase_store")
    op.drop_column("vinyl_records", "purchase_price")
    op.drop_column("vinyl_records", "purchase_currency")
    op.drop_column("vinyl_records", "rating")
    op.drop_column("vinyl_records", "memo")
    op.drop_column("vinyl_records", "favorite_tracks")
    op.drop_column("vinyl_records", "display_order")

    # 3. Spotify dedup 用 partial UNIQUE INDEX (ADR-006 §2.2)
    op.execute(
        "CREATE UNIQUE INDEX uq_vinyl_records_spotify_album_id_not_null "
        "ON vinyl_records (spotify_album_id) WHERE spotify_album_id IS NOT NULL"
    )

    # 4. user_collections (ADR-006 §3.2)
    op.create_table(
        "user_collections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("vinyl_record_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            server_default="owned",
            nullable=False,
        ),
        sa.Column(
            "pressing_info",
            sqlmodel.sql.sqltypes.AutoString(length=200),
            nullable=True,
        ),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column(
            "purchase_store",
            sqlmodel.sql.sqltypes.AutoString(length=200),
            nullable=True,
        ),
        sa.Column("purchase_price", sa.Integer(), nullable=True),
        sa.Column(
            "purchase_currency",
            sqlmodel.sql.sqltypes.AutoString(length=3),
            server_default="JPY",
            nullable=False,
        ),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column(
            "memo",
            sqlmodel.sql.sqltypes.AutoString(length=2000),
            nullable=True,
        ),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["vinyl_record_id"], ["vinyl_records.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "vinyl_record_id",
            name="uq_user_collections_user_vinyl_record",
        ),
    )
    op.create_index(
        op.f("ix_user_collections_user_id"),
        "user_collections",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_collections_vinyl_record_id"),
        "user_collections",
        ["vinyl_record_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_collections_display_order"),
        "user_collections",
        ["display_order"],
        unique=False,
    )

    # 5. record_favorite_tracks (ADR-006 §2.8)
    op.create_table(
        "record_favorite_tracks",
        sa.Column("user_collection_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "spotify_track_id",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
        sa.Column(
            "track_name",
            sqlmodel.sql.sqltypes.AutoString(length=300),
            nullable=False,
        ),
        sa.Column(
            "note",
            sqlmodel.sql.sqltypes.AutoString(length=500),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_collection_id"], ["user_collections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_collection_id", "position"),
        sa.UniqueConstraint(
            "user_collection_id",
            "spotify_track_id",
            name="uq_record_favorite_tracks_collection_spotify",
        ),
    )
    op.execute(
        "CREATE INDEX ix_record_favorite_tracks_spotify_track_id "
        "ON record_favorite_tracks (spotify_track_id) "
        "WHERE spotify_track_id IS NOT NULL"
    )


def downgrade() -> None:
    """ADR-006: pre-deploy migration なので downgrade は実装しない。

    本番投入後は本 migration の DELETE FROM vinyl_records 前提が崩れるので、
    その場合は別途段階移行 plan を切る。
    """
    pass
