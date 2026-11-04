"""Idempotency keys for creating assets and versions.

Revision ID: 0002_idempotency_keys
Revises: 0001_assets
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_idempotency_keys"
down_revision = "0001_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create `idempotency_keys`."""
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.LargeBinary(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("version_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(key) BETWEEN 1 AND 255", name=op.f("ck_idempotency_keys_key_length")
        ),
        sa.CheckConstraint(
            "octet_length(request_hash) = 32",
            name=op.f("ck_idempotency_keys_request_hash_length"),
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_idempotency_keys")),
    )
    op.create_index(op.f("ix_idempotency_keys_created_at"), "idempotency_keys", ["created_at"])


def downgrade() -> None:
    """Drop `idempotency_keys`."""
    op.drop_index(op.f("ix_idempotency_keys_created_at"), table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
