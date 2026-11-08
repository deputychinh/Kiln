"""An event whose version is gone may be deleted directly (KILN-51 review round 2, ADR 0022).

Revision ID: 0015_review_events_orphans
Revises: 0014_review_events_always
Create Date: 2026-11-08
"""

from alembic import op

revision = "0015_review_events_orphans"
down_revision = "0014_review_events_always"
branch_labels = None
depends_on = None

# Copied, not imported, from db/schema.py: a migration must not change when the module does.
_ORPHANS_DELETABLE = """
CREATE OR REPLACE FUNCTION review_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE'
        AND NOT EXISTS (SELECT 1 FROM asset_versions WHERE id = OLD.version_id) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'review_events is append-only' USING ERRCODE = 'restrict_violation';
END
$$
"""
# The body of migration 0012.
_CASCADE_ONLY = """
CREATE OR REPLACE FUNCTION review_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1
        AND NOT EXISTS (SELECT 1 FROM asset_versions WHERE id = OLD.version_id) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'review_events is append-only' USING ERRCODE = 'restrict_violation';
END
$$
"""


def upgrade() -> None:
    """Drop the nesting condition: the version being gone is what makes a delete safe.

    Replica mode skips the foreign key's cascade, so deleting a version there leaves its events
    behind; they could then never be deleted and would block deleting their actor. Replacing the
    function body touches no table; both triggers keep pointing at it.
    """
    op.execute(_ORPHANS_DELETABLE)


def downgrade() -> None:
    """Back to 0012: only a delete nested in the cascade passes."""
    op.execute(_CASCADE_ONLY)
