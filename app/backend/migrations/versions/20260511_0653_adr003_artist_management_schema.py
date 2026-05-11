"""adr003 artist management schema

ADR-003 §3.2 の Migration スクリプト。アーティスト管理を 3 層構造に再編成する
スキーマ基盤を 1 revision に集約する:

- 新規テーブル user_follows / user_concert_attendances
- vinyl_records.status / concerts.source / concerts.venue_name_freetext 追加
- artists.followed 削除 (user_follows へ役割移譲)
- artists.source の値域を ("spotify" | "manual") から
  ("seeded" | "spotify_dynamic" | "manual") に切替

Revision ID: 9061b123e963
Revises: 0711c49b1ee7
Create Date: 2026-05-11 06:53:24.160126+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9061b123e963"
down_revision: str | Sequence[str] | None = "0711c49b1ee7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1) 新規テーブル
    op.create_table(
        "user_follows",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "artist_id",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("followed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_action_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_flag", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["artist_id"], ["artists.spotify_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "artist_id"),
    )
    op.create_index(
        op.f("ix_user_follows_archived_flag"),
        "user_follows",
        ["archived_flag"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_follows_pinned"),
        "user_follows",
        ["pinned"],
        unique=False,
    )
    op.create_table(
        "user_concert_attendances",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "concert_id",
            sqlmodel.sql.sqltypes.AutoString(length=128),
            nullable=False,
        ),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column(
            "memo",
            sqlmodel.sql.sqltypes.AutoString(length=2000),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["concert_id"], ["concerts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "concert_id"),
    )

    # 2) 既存テーブルにカラム追加 (NOT NULL は server_default で既存行を埋める)
    op.add_column(
        "vinyl_records",
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            server_default="owned",
            nullable=False,
        ),
    )
    op.add_column(
        "concerts",
        sa.Column(
            "source",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            server_default="scraped",
            nullable=False,
        ),
    )
    op.add_column(
        "concerts",
        sa.Column(
            "venue_name_freetext",
            sqlmodel.sql.sqltypes.AutoString(length=200),
            nullable=True,
        ),
    )

    # 3) artists.source の値域を新 Literal に揃える。
    # 既存 seed 行は `"spotify"` で入っているので `"seeded"` に書き換える。
    # 以降の初期投入は seed.py 側で `source="seeded"` を明示する。
    op.execute("UPDATE artists SET source = 'seeded' WHERE source = 'spotify'")

    # 4) 旧 followed=true を user_follows に転記。users が空のときは何もしない
    # (NOT NULL FK 違反回避)。本番では OAuth ログイン後にしか走らないので空
    # で問題ないが、開発環境を壊さないためのガード。
    op.execute(
        """
        INSERT INTO user_follows (user_id, artist_id, pinned, followed_at, last_action_at, archived_flag)
        SELECT
            (SELECT id FROM users ORDER BY created_at LIMIT 1) AS user_id,
            a.spotify_id,
            false AS pinned,
            a.added_at AS followed_at,
            a.added_at AS last_action_at,
            false AS archived_flag
        FROM artists AS a
        WHERE a.followed = true
          AND EXISTS (SELECT 1 FROM users)
        """
    )

    # 5) 旧カラム削除
    op.drop_column("artists", "followed")


def downgrade() -> None:
    """ADR-003 §3.2: 本番運用前なので downgrade はスキップ可。

    安全のため逆順 SQL は実装せず、誤って戻す経路を塞ぐ。必要になれば
    手書きで戻すか、対象 DB を作り直す方が確実。
    """
    pass
