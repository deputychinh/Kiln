"""Model previews: two failure reasons, and previews for models made ready before them.

Revision ID: 0005_model_previews
Revises: 0004_maintenance
Create Date: 2026-11-06
"""

from alembic import op

revision = "0005_model_previews"
down_revision = "0004_maintenance"
branch_labels = None
depends_on = None

_OLD = (
    "UPLOAD_CHANGED",
    "UNREADABLE_IMAGE",
    "IMAGE_TOO_LARGE",
    "PROCESSING_GAVE_UP",
    "UPLOAD_EXPIRED",
)
_OLD_REASONS = ", ".join(f"'{reason}'" for reason in _OLD)
_NEW_REASONS = f"{_OLD_REASONS}, 'UNREADABLE_MODEL', 'MODEL_TOO_LARGE'"


def _reasons_check(reasons: str) -> None:
    op.drop_constraint(op.f("ck_asset_versions_failure_reason"), "asset_versions", type_="check")
    op.create_check_constraint(
        op.f("ck_asset_versions_failure_reason"),
        "asset_versions",
        f"failure_reason IS NULL OR failure_reason IN ({reasons})",
    )


def upgrade() -> None:
    """Allow the model reasons; send ready models without a preview back to processing."""
    _reasons_check(_NEW_REASONS)
    # Until now the worker marked models ready without rendering anything (KILN-4).
    op.execute(
        "UPDATE asset_versions SET status = 'processing', updated_at = now()"
        " WHERE status = 'ready' AND asset_id IN (SELECT id FROM assets WHERE kind = 'model')"
    )
    op.execute(
        "UPDATE jobs SET status = 'queued', attempts = 0, run_after = now(),"
        " leased_until = NULL, last_error = NULL, updated_at = now()"
        " WHERE kind = 'thumbnail' AND version_id IN ("
        "SELECT v.id FROM asset_versions v JOIN assets a ON a.id = v.asset_id"
        " WHERE a.kind = 'model' AND v.status = 'processing')"
    )


def downgrade() -> None:
    """Undo the reasons (failed models fall back to the generic reason); previews stay."""
    op.execute(
        "UPDATE asset_versions SET failure_reason = 'PROCESSING_GAVE_UP'"
        " WHERE failure_reason IN ('UNREADABLE_MODEL', 'MODEL_TOO_LARGE')"
    )
    _reasons_check(_OLD_REASONS)
