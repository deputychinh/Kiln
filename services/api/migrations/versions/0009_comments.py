"""Comment threads, comments and region annotations (KILN-10).

Revision ID: 0009_comments
Revises: 0008_sessions_last_seen_index
Create Date: 2026-11-08
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0009_comments"
down_revision = "0008_sessions_last_seen_index"
branch_labels = None
depends_on = None


def _timestamps(*names: str, nullable: bool = False) -> list[sa.Column[datetime]]:
    return [sa.Column(name, sa.DateTime(timezone=True), nullable=nullable) for name in names]


def upgrade() -> None:
    """New, empty tables plus one nullable column: nothing on a live table is rewritten or scanned.

    The foreign keys of the new tables lock `asset_versions` and `users` only briefly (SHARE ROW
    EXCLUSIVE, under the 5 s `lock_timeout` of env.py) and validate against empty tables, so
    `NOT VALID` buys nothing here; the indexes are built on empty tables, so not concurrently.
    """
    op.add_column("idempotency_keys", sa.Column("resource_id", sa.Uuid(), nullable=True))
    op.create_table(
        "comment_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("region_shape", sa.Text(), nullable=True),
        sa.Column("region_x", sa.Double(), nullable=True),
        sa.Column("region_y", sa.Double(), nullable=True),
        sa.Column("region_width", sa.Double(), nullable=True),
        sa.Column("region_height", sa.Double(), nullable=True),
        *_timestamps("resolved_at", nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        *_timestamps("created_at", "updated_at"),
        sa.CheckConstraint("number >= 1", name=op.f("ck_comment_threads_number_positive")),
        sa.CheckConstraint(
            "region_shape IS NULL OR region_shape IN ('rect', 'point')",
            name=op.f("ck_comment_threads_region_shape"),
        ),
        sa.CheckConstraint(
            "(region_shape IS NULL AND region_x IS NULL AND region_y IS NULL"
            " AND region_width IS NULL AND region_height IS NULL)"
            " OR (region_shape IS NOT NULL AND region_x IS NOT NULL AND region_y IS NOT NULL"
            " AND region_x BETWEEN 0 AND 1"
            " AND region_y BETWEEN 0 AND 1)",
            name=op.f("ck_comment_threads_region_position"),
        ),
        sa.CheckConstraint(
            "region_shape IS DISTINCT FROM 'point'"
            " OR (region_width IS NULL AND region_height IS NULL)",
            name=op.f("ck_comment_threads_point_has_no_size"),
        ),
        sa.CheckConstraint(
            "region_shape IS DISTINCT FROM 'rect'"
            " OR (region_width IS NOT NULL AND region_height IS NOT NULL"
            " AND region_width > 0 AND region_height > 0"
            " AND region_x + region_width <= 1 AND region_y + region_height <= 1)",
            name=op.f("ck_comment_threads_rect_inside_image"),
        ),
        sa.CheckConstraint(
            "(resolved_at IS NULL) = (resolved_by IS NULL)",
            name=op.f("ck_comment_threads_resolved_by_when_resolved"),
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["asset_versions.id"],
            name=op.f("fk_comment_threads_version_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_comment_threads_author_id")
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"], ["users.id"], name=op.f("fk_comment_threads_resolved_by")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comment_threads")),
        sa.UniqueConstraint(
            "version_id", "number", name=op.f("uq_comment_threads_version_id_number")
        ),
    )
    op.create_table(
        "comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_root", sa.Boolean(), nullable=False),
        *_timestamps("created_at"),
        *_timestamps("edited_at", "deleted_at", nullable=True),
        sa.CheckConstraint(
            "(deleted_at IS NULL AND char_length(body) BETWEEN 1 AND 2000)"
            " OR (deleted_at IS NOT NULL AND body = '')",
            name=op.f("ck_comments_body_unless_deleted"),
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["comment_threads.id"],
            name=op.f("fk_comments_thread_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name=op.f("fk_comments_author_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comments")),
    )
    op.create_index(
        op.f("ix_comments_thread_id_created_at_id"),
        "comments",
        ["thread_id", "created_at", "id"],
    )
    op.create_index(
        "uq_comments_thread_id_root",
        "comments",
        ["thread_id"],
        unique=True,
        postgresql_where=sa.text("is_root"),
    )


def downgrade() -> None:
    """Drop the comments (their text is lost) and the idempotency column."""
    op.drop_table("comments")
    op.drop_table("comment_threads")
    op.drop_column("idempotency_keys", "resource_id")
