"""Index sessions by last activity for the idle purge (KILN-12 review V7).

Revision ID: 0008_sessions_last_seen_index
Revises: 0007_idempotency_keys_per_user
Create Date: 2026-11-08
"""

from alembic import op

revision = "0008_sessions_last_seen_index"
down_revision = "0007_idempotency_keys_per_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Built concurrently: sign-ins keep writing sessions meanwhile."""
    with op.get_context().autocommit_block():
        op.create_index(
            op.f("ix_sessions_last_seen_at"),
            "sessions",
            ["last_seen_at"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    """Drop the index without blocking sessions."""
    with op.get_context().autocommit_block():
        op.drop_index(
            op.f("ix_sessions_last_seen_at"),
            table_name="sessions",
            postgresql_concurrently=True,
            if_exists=True,
        )
