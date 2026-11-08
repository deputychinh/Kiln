"""The review history refuses TRUNCATE as well (KILN-51, ADR 0018).

Revision ID: 0013_review_events_no_truncate
Revises: 0012_review_events_cascade_only
Create Date: 2026-11-08
"""

from alembic import op

revision = "0013_review_events_no_truncate"
down_revision = "0012_review_events_cascade_only"
branch_labels = None
depends_on = None

# Copied, not imported, from db/schema.py: a migration must not change when the module does.
_NO_TRUNCATE = (
    "CREATE TRIGGER review_events_no_truncate BEFORE TRUNCATE ON review_events"
    " FOR EACH STATEMENT EXECUTE FUNCTION review_events_append_only()"
)


def upgrade() -> None:
    """Add a statement-level trigger: row triggers never see TRUNCATE.

    It reuses the append-only function, which refuses everything but the cascade delete.
    CREATE TRIGGER takes a brief SHARE ROW EXCLUSIVE lock (under the migration lock_timeout) and
    rewrites nothing.
    """
    op.execute(_NO_TRUNCATE)


def downgrade() -> None:
    """Back to 0012: TRUNCATE passes again."""
    op.execute("DROP TRIGGER review_events_no_truncate ON review_events")
