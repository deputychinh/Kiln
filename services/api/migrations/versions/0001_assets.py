"""Assets and asset versions.

Revision ID: 0001_assets
Revises:
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_assets"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create `assets` and `asset_versions` with their invariants."""
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 120", name=op.f("ck_assets_name_length")
        ),
        sa.CheckConstraint("kind IN ('image', 'model')", name=op.f("ck_assets_kind")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assets")),
    )
    op.create_index(op.f("ix_assets_created_at_id"), "assets", ["created_at", "id"])
    op.create_table(
        "asset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("number >= 1", name=op.f("ck_asset_versions_number_positive")),
        sa.CheckConstraint(
            "status IN ('pending_upload', 'processing', 'ready', 'failed')",
            name=op.f("ck_asset_versions_status"),
        ),
        sa.CheckConstraint(
            "char_length(file_name) BETWEEN 1 AND 255",
            name=op.f("ck_asset_versions_file_name_length"),
        ),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 524288000", name=op.f("ck_asset_versions_size_range")
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name=op.f("fk_asset_versions_asset_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_asset_versions")),
        sa.UniqueConstraint("asset_id", "number", name=op.f("uq_asset_versions_asset_id_number")),
        sa.UniqueConstraint("object_key", name=op.f("uq_asset_versions_object_key")),
    )


def downgrade() -> None:
    """Drop both tables."""
    op.drop_table("asset_versions")
    op.drop_index(op.f("ix_assets_created_at_id"), table_name=op.f("assets"))
    op.drop_table("assets")
