"""Maintenance: expired uploads as a failure reason, the run lease, abandoned-upload index.

Revision ID: 0004_maintenance
Revises: 0003_jobs_and_processing
Create Date: 2026-11-06
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_maintenance"
down_revision = "0003_jobs_and_processing"
branch_labels = None
depends_on = None

_OLD_REASONS = "'UPLOAD_CHANGED', 'UNREADABLE_IMAGE', 'IMAGE_TOO_LARGE', 'PROCESSING_GAVE_UP'"
_NEW_REASONS = f"{_OLD_REASONS}, 'UPLOAD_EXPIRED'"


def _reasons_check(reasons: str) -> None:
    op.drop_constraint(op.f("ck_asset_versions_failure_reason"), "asset_versions", type_="check")
    op.create_check_constraint(
        op.f("ck_asset_versions_failure_reason"),
        "asset_versions",
        f"failure_reason IS NULL OR failure_reason IN ({reasons})",
    )


def upgrade() -> None:
    """Allow UPLOAD_EXPIRED, add the lease table and the pending-upload index."""
    _reasons_check(_NEW_REASONS)
    op.create_table(
        "maintenance_runs",
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("task", name=op.f("pk_maintenance_runs")),
    )
    op.create_index(
        op.f("ix_asset_versions_created_at"),
        "asset_versions",
        ["created_at"],
        postgresql_where=sa.text("status = 'pending_upload'"),
    )


def downgrade() -> None:
    """Undo; expired versions go back to the generic reason so the old check holds."""
    op.drop_index(op.f("ix_asset_versions_created_at"), table_name="asset_versions")
    op.drop_table("maintenance_runs")
    op.execute(
        "UPDATE asset_versions SET failure_reason = 'PROCESSING_GAVE_UP'"
        " WHERE failure_reason = 'UPLOAD_EXPIRED'"
    )
    _reasons_check(_OLD_REASONS)
