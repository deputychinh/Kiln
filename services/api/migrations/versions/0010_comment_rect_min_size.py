"""Rectangles are at least 1 % of the image on each side (KILN-10 review).

Revision ID: 0010_comment_rect_min_size
Revises: 0009_comments
Create Date: 2026-11-08
"""

from alembic import op

revision = "0010_comment_rect_min_size"
down_revision = "0009_comments"
branch_labels = None
depends_on = None

_NAME = "ck_comment_threads_rect_min_size"


def upgrade() -> None:
    """Add the check NOT VALID (a brief lock, no scan), then validate it in its own transaction.

    Validation scans without blocking writers; a row that breaks the rule fails it loudly.
    """
    op.execute(
        f"ALTER TABLE comment_threads ADD CONSTRAINT {_NAME} CHECK ("
        "region_shape IS DISTINCT FROM 'rect'"
        " OR (region_width >= 0.01 AND region_height >= 0.01)) NOT VALID"
    )
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE comment_threads VALIDATE CONSTRAINT {_NAME}")


def downgrade() -> None:
    """Drop the rule."""
    op.execute(f"ALTER TABLE comment_threads DROP CONSTRAINT {_NAME}")
