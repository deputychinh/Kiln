"""The review history's triggers fire in replica mode too (KILN-51 review, ADR 0020).

Revision ID: 0014_review_events_always
Revises: 0013_review_events_no_truncate
Create Date: 2026-11-08
"""

from alembic import op

revision = "0014_review_events_always"
down_revision = "0013_review_events_no_truncate"
branch_labels = None
depends_on = None

# Copied, not imported, from db/schema.py: a migration must not change when the module does.
_TRIGGERS = ("review_events_append_only", "review_events_no_truncate")


def upgrade() -> None:
    """ENABLE ALWAYS: `SET session_replication_role = replica` no longer skips them.

    A catalogue change only: a brief SHARE ROW EXCLUSIVE lock under the migration lock_timeout,
    no rewrite.
    """
    for name in _TRIGGERS:
        op.execute(f"ALTER TABLE review_events ENABLE ALWAYS TRIGGER {name}")


def downgrade() -> None:
    """Back to the default (fires only when session_replication_role is origin or local)."""
    for name in _TRIGGERS:
        op.execute(f"ALTER TABLE review_events ENABLE TRIGGER {name}")
