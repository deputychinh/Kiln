"""Review events may be deleted only by the cascade of their deleted version (KILN-11 review).

Revision ID: 0012_review_events_cascade_only
Revises: 0011_review_states
Create Date: 2026-11-08
"""

from alembic import op

revision = "0012_review_events_cascade_only"
down_revision = "0011_review_states"
branch_labels = None
depends_on = None

# Copied, not imported, from db/schema.py: a migration must not change when the module does.
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
_DEPTH_ONLY = """
CREATE OR REPLACE FUNCTION review_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'review_events is append-only' USING ERRCODE = 'restrict_violation';
END
$$
"""


def upgrade() -> None:
    """Replace the function body in place: no table is touched, the trigger keeps pointing at it.

    A delete nested in another trigger used to pass on depth alone; now it also needs the event's
    version to be gone, which is true only inside the cascade of deleting that version.
    """
    op.execute(_CASCADE_ONLY)


def downgrade() -> None:
    """Back to the depth-only rule of 0011."""
    op.execute(_DEPTH_ONLY)
