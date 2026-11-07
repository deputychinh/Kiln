"""Identity (KILN-12): users, sessions, access tokens, sign-in failures; asset owners.

Revision ID: 0006_identity
Revises: 0005_model_previews
Create Date: 2026-11-08
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_identity"
down_revision = "0005_model_previews"
branch_labels = None
depends_on = None


def _timestamps(*names: str) -> list[sa.Column[datetime]]:
    return [sa.Column(name, sa.DateTime(timezone=True), nullable=False) for name in names]


def upgrade() -> None:
    """Add the identity tables; owners stay NULL on assets made before sign-in."""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        *_timestamps("created_at", "updated_at"),
        sa.CheckConstraint(
            "char_length(email) BETWEEN 3 AND 254", name=op.f("ck_users_email_length")
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lower_case")),
        sa.CheckConstraint(
            "char_length(display_name) BETWEEN 1 AND 80", name=op.f("ck_users_display_name_length")
        ),
        sa.CheckConstraint(
            "password_hash LIKE '$argon2id$%'", name=op.f("ck_users_password_hash_argon2id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "sessions",
        sa.Column("id_hash", sa.LargeBinary(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        *_timestamps("created_at", "last_seen_at", "expires_at"),
        sa.CheckConstraint("octet_length(id_hash) = 32", name=op.f("ck_sessions_id_hash_length")),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_sessions_expires_after_creation")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id_hash", name=op.f("pk_sessions")),
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])
    op.create_index(op.f("ix_sessions_expires_at"), "sessions", ["expires_at"])
    op.create_table(
        "access_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.Text()), nullable=False),
        *_timestamps("created_at", "expires_at"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name=op.f("ck_access_tokens_token_hash_length")
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 80", name=op.f("ck_access_tokens_name_length")
        ),
        sa.CheckConstraint(
            "cardinality(scopes) >= 1 AND scopes <@ ARRAY['read', 'write']::text[]",
            name=op.f("ck_access_tokens_scopes"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_access_tokens_expires_after_creation")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_access_tokens_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_access_tokens_token_hash")),
    )
    op.create_index(
        op.f("ix_access_tokens_user_id_created_at"), "access_tokens", ["user_id", "created_at"]
    )
    op.create_table(
        "sign_in_failures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_key", sa.LargeBinary(), nullable=False),
        sa.Column("client_ip", sa.Text(), nullable=False),
        *_timestamps("created_at"),
        sa.CheckConstraint(
            "octet_length(account_key) = 32", name=op.f("ck_sign_in_failures_account_key_length")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sign_in_failures")),
    )
    op.create_index(
        op.f("ix_sign_in_failures_account_key_created_at"),
        "sign_in_failures",
        ["account_key", "created_at"],
    )
    op.create_index(
        op.f("ix_sign_in_failures_client_ip_created_at"),
        "sign_in_failures",
        ["client_ip", "created_at"],
    )
    op.create_index(op.f("ix_sign_in_failures_created_at"), "sign_in_failures", ["created_at"])
    # Nullable columns with no default: a metadata-only change, no table rewrite (expand step).
    op.add_column("assets", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f("fk_assets_owner_id"), "assets", "users", ["owner_id"], ["id"])
    op.add_column("asset_versions", sa.Column("uploaded_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_asset_versions_uploaded_by"), "asset_versions", "users", ["uploaded_by"], ["id"]
    )


def downgrade() -> None:
    """Back to anonymous v0.1: owners and identity tables gone."""
    op.drop_constraint(op.f("fk_asset_versions_uploaded_by"), "asset_versions", type_="foreignkey")
    op.drop_column("asset_versions", "uploaded_by")
    op.drop_constraint(op.f("fk_assets_owner_id"), "assets", type_="foreignkey")
    op.drop_column("assets", "owner_id")
    op.drop_table("sign_in_failures")
    op.drop_table("access_tokens")
    op.drop_table("sessions")
    op.drop_table("users")
