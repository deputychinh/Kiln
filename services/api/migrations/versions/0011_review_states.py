"""Review states of asset versions and their append-only history (KILN-11).

Revision ID: 0011_review_states
Revises: 0010_comment_rect_min_size
Create Date: 2026-11-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_review_states"
down_revision = "0010_comment_rect_min_size"
branch_labels = None
depends_on = None

_STATES = "('in_review', 'approved', 'changes_requested')"
_VERSION_CHECKS = {
    "ck_asset_versions_review_state": f"review_state IN {_STATES}",
    "ck_asset_versions_review_revision_non_negative": "review_revision >= 0",
}
# Copied, not imported, from db/schema.py: a migration must not change when the module does.
_APPEND_ONLY_FUNCTION = """
CREATE FUNCTION review_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'review_events is append-only' USING ERRCODE = 'restrict_violation';
END
$$
"""
_APPEND_ONLY_TRIGGER = (
    "CREATE TRIGGER review_events_append_only BEFORE UPDATE OR DELETE ON review_events"
    " FOR EACH ROW EXECUTE FUNCTION review_events_append_only()"
)
_EVENT_FOREIGN_KEYS = {
    "fk_review_events_version_id": (
        "FOREIGN KEY (version_id) REFERENCES asset_versions (id) ON DELETE CASCADE"
    ),
    "fk_review_events_actor_id": "FOREIGN KEY (actor_id) REFERENCES users (id)",
}


def upgrade() -> None:
    """Safe on a live `asset_versions`; the plan is in docs/stories/KILN-11.md (Data).

    1. Backfill: none needed. `ADD COLUMN … NOT NULL DEFAULT <constant>` is metadata-only since
       PostgreSQL 11: existing rows read the default from the catalogue, nothing is rewritten, so
       every existing version is `in_review` at revision 0 at once (set-based, zero batches).
       Only a brief ACCESS EXCLUSIVE lock, bounded by env.py's 5 s `lock_timeout`.
    2. Checks are added NOT VALID (no scan under the lock), then validated after commit, which
       scans under SHARE UPDATE EXCLUSIVE and lets readers and writers go on.
    3. `review_events` is new and empty: its unique index is built plainly. Its foreign keys are
       still added NOT VALID then validated, so the lock they take on `asset_versions` and `users`
       is never held during a scan.
    """
    op.add_column(
        "asset_versions",
        sa.Column("review_state", sa.Text(), nullable=False, server_default="in_review"),
    )
    op.add_column(
        "asset_versions",
        sa.Column("review_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    for name, check in _VERSION_CHECKS.items():
        op.execute(f"ALTER TABLE asset_versions ADD CONSTRAINT {name} CHECK ({check}) NOT VALID")
    op.create_table(
        "review_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=False),
        sa.Column("to_state", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence >= 1", name=op.f("ck_review_events_sequence_positive")),
        sa.CheckConstraint(
            "action IN ('approve', 'request_changes', 'reopen')",
            name=op.f("ck_review_events_action"),
        ),
        sa.CheckConstraint(f"from_state IN {_STATES}", name=op.f("ck_review_events_from_state")),
        sa.CheckConstraint(f"to_state IN {_STATES}", name=op.f("ck_review_events_to_state")),
        sa.CheckConstraint(
            "(action = 'approve' AND from_state = 'in_review' AND to_state = 'approved')"
            " OR (action = 'request_changes' AND from_state = 'in_review'"
            " AND to_state = 'changes_requested')"
            " OR (action = 'reopen' AND from_state IN ('approved', 'changes_requested')"
            " AND to_state = 'in_review')",
            name=op.f("ck_review_events_transition"),
        ),
        sa.CheckConstraint(
            "note IS NULL OR char_length(note) BETWEEN 1 AND 1000",
            name=op.f("ck_review_events_note_length"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_events")),
        sa.UniqueConstraint(
            "version_id", "sequence", name=op.f("uq_review_events_version_id_sequence")
        ),
    )
    for name, definition in _EVENT_FOREIGN_KEYS.items():
        op.execute(f"ALTER TABLE review_events ADD CONSTRAINT {name} {definition} NOT VALID")
    op.execute(_APPEND_ONLY_FUNCTION)
    op.execute(_APPEND_ONLY_TRIGGER)
    with op.get_context().autocommit_block():
        for name in _VERSION_CHECKS:
            op.execute(f"ALTER TABLE asset_versions VALIDATE CONSTRAINT {name}")
        for name in _EVENT_FOREIGN_KEYS:
            op.execute(f"ALTER TABLE review_events VALIDATE CONSTRAINT {name}")


def downgrade() -> None:
    """Drop the history (it is lost) and the review columns."""
    op.drop_table("review_events")
    op.execute("DROP FUNCTION IF EXISTS review_events_append_only()")
    for name in _VERSION_CHECKS:
        op.execute(f"ALTER TABLE asset_versions DROP CONSTRAINT {name}")
    op.drop_column("asset_versions", "review_revision")
    op.drop_column("asset_versions", "review_state")
