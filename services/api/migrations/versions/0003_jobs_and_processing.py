"""Jobs, the recorded ETag, failure reasons and the asset cover.

Revision ID: 0003_jobs_and_processing
Revises: 0002_idempotency_keys
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_jobs_and_processing"
down_revision = "0002_idempotency_keys"
branch_labels = None
depends_on = None

_REASONS = "'UPLOAD_CHANGED', 'UNREADABLE_IMAGE', 'IMAGE_TOO_LARGE', 'PROCESSING_GAVE_UP'"


def upgrade() -> None:
    """Add processing columns and the jobs table."""
    op.add_column("asset_versions", sa.Column("etag", sa.Text(), nullable=True))
    op.add_column("asset_versions", sa.Column("failure_reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_asset_versions_failure_reason"),
        "asset_versions",
        f"failure_reason IS NULL OR failure_reason IN ({_REASONS})",
    )
    op.create_check_constraint(
        op.f("ck_asset_versions_failure_reason_when_failed"),
        "asset_versions",
        "(status = 'failed') = (failure_reason IS NOT NULL)",
    )
    op.add_column("assets", sa.Column("cover_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_assets_cover_version_id"),
        "assets",
        "asset_versions",
        ["cover_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('thumbnail')", name=op.f("ck_jobs_kind")),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'dead')", name=op.f("ck_jobs_status")
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_jobs_attempts_non_negative")),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["asset_versions.id"],
            name=op.f("fk_jobs_version_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("version_id", "kind", name=op.f("uq_jobs_version_id_kind")),
    )
    op.create_index(
        op.f("ix_jobs_run_after"),
        "jobs",
        ["run_after"],
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        op.f("ix_jobs_leased_until"),
        "jobs",
        ["leased_until"],
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    """Remove the jobs table and processing columns."""
    op.drop_index(op.f("ix_jobs_leased_until"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_run_after"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_constraint(op.f("fk_assets_cover_version_id"), "assets", type_="foreignkey")
    op.drop_column("assets", "cover_version_id")
    op.drop_constraint(
        op.f("ck_asset_versions_failure_reason_when_failed"), "asset_versions", type_="check"
    )
    op.drop_constraint(op.f("ck_asset_versions_failure_reason"), "asset_versions", type_="check")
    op.drop_column("asset_versions", "failure_reason")
    op.drop_column("asset_versions", "etag")
