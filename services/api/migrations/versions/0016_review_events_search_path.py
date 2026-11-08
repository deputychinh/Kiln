"""Pin the append-only function's search_path and qualify its tables (KILN-51 round 3, ADR 0023).

Revision ID: 0016_review_events_search_path
Revises: 0015_review_events_orphans
Create Date: 2026-11-08
"""

from alembic import op

revision = "0016_review_events_search_path"
down_revision = "0015_review_events_orphans"
branch_labels = None
depends_on = None

# Copied, not imported, from db/schema.py: a migration must not change when the module does.
# `pg_temp` is named last on purpose: when it is left out, PostgreSQL searches it FIRST for
# tables, so `SET search_path = pg_catalog, public` alone would still let a temporary table
# shadow `asset_versions`. The reference is also schema-qualified, which no search_path changes.
_PINNED = """
CREATE OR REPLACE FUNCTION public.review_events_append_only() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    IF TG_OP = 'DELETE'
        AND NOT EXISTS (SELECT 1 FROM public.asset_versions WHERE id = OLD.version_id) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'review_events is append-only' USING ERRCODE = 'restrict_violation';
END
$$
"""
# The body of migration 0015: unqualified, no search_path.
_UNPINNED = """
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


def upgrade() -> None:
    """Replace the function in place (no table touched; both triggers keep pointing at it).

    Since 0015 a delete passes when its version is gone, so the existence check is the guard: a
    role with only DML rights could create `TEMP TABLE asset_versions` and make it say "gone"
    for a live version. Qualified and pinned, the check always reads `public.asset_versions`.
    """
    op.execute(_PINNED)


def downgrade() -> None:
    """Back to 0015 (and its hole); CREATE OR REPLACE also drops the SET clause."""
    op.execute(_UNPINNED)
