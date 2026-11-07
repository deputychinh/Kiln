"""Idempotency keys per user (KILN-12, ADR 0006 consequence).

Revision ID: 0007_idempotency_keys_per_user
Revises: 0006_identity
Create Date: 2026-11-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_idempotency_keys_per_user"
down_revision = "0006_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Key the table by (user, key); the keys of v0.1 had no owner and are dropped.

    Keys live 24 h, so dropping them costs at most one duplicate asset for a client that retries
    across this deploy.
    """
    op.execute("DELETE FROM idempotency_keys")
    op.add_column("idempotency_keys", sa.Column("user_id", sa.Uuid(), nullable=False))
    op.drop_constraint(op.f("pk_idempotency_keys"), "idempotency_keys", type_="primary")
    op.create_primary_key(op.f("pk_idempotency_keys"), "idempotency_keys", ["user_id", "key"])
    op.create_foreign_key(
        op.f("fk_idempotency_keys_user_id"),
        "idempotency_keys",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Global keys again (cleared, since two users may hold the same key)."""
    op.execute("DELETE FROM idempotency_keys")
    op.drop_constraint(op.f("fk_idempotency_keys_user_id"), "idempotency_keys", type_="foreignkey")
    op.drop_constraint(op.f("pk_idempotency_keys"), "idempotency_keys", type_="primary")
    op.drop_column("idempotency_keys", "user_id")
    op.create_primary_key(op.f("pk_idempotency_keys"), "idempotency_keys", ["key"])
