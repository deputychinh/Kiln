"""Tables; invariants are enforced here as well as in the domain."""

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)

from kiln_api.constants import (
    ACCESS_TOKEN_NAME_MAX_LENGTH,
    ASSET_NAME_MAX_LENGTH,
    COMMENT_BODY_MAX_LENGTH,
    DISPLAY_NAME_MAX_LENGTH,
    EMAIL_MAX_LENGTH,
    FILE_NAME_MAX_LENGTH,
    IDEMPOTENCY_KEY_MAX_LENGTH,
    MAX_UPLOAD_BYTES,
)
from kiln_api.enums import (
    AssetKind,
    FailureReason,
    JobKind,
    JobStatus,
    RegionShape,
    Scope,
    VersionStatus,
)

metadata = MetaData(
    naming_convention={
        "pk": "pk_%(table_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    }
)


def _one_of(column: str, values: list[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


users = Table(
    "users",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("email", Text, nullable=False),  # normalised (trimmed, lower case)
    Column("display_name", Text, nullable=False),
    Column("password_hash", Text, nullable=False),  # Argon2id PHC string
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("email"),
    CheckConstraint(f"char_length(email) BETWEEN 3 AND {EMAIL_MAX_LENGTH}", name="email_length"),
    CheckConstraint("email = lower(email)", name="email_lower_case"),
    CheckConstraint(
        f"char_length(display_name) BETWEEN 1 AND {DISPLAY_NAME_MAX_LENGTH}",
        name="display_name_length",
    ),
    CheckConstraint("password_hash LIKE '$argon2id$%'", name="password_hash_argon2id"),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id_hash", LargeBinary, primary_key=True),  # SHA-256 of the cookie value
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("octet_length(id_hash) = 32", name="id_hash_length"),
    CheckConstraint("expires_at > created_at", name="expires_after_creation"),
    Index(None, "user_id"),
    Index(None, "expires_at"),
    Index(None, "last_seen_at"),  # the idle purge at each sign-in (KILN-12 review V7)
)

access_tokens = Table(
    "access_tokens",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("name", Text, nullable=False),
    Column("prefix", Text, nullable=False),
    Column("token_hash", LargeBinary, nullable=False),  # SHA-256 of the token
    Column("scopes", ARRAY(Text), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("last_used_at", DateTime(timezone=True), nullable=True),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("token_hash"),
    CheckConstraint("octet_length(token_hash) = 32", name="token_hash_length"),
    CheckConstraint(
        f"char_length(name) BETWEEN 1 AND {ACCESS_TOKEN_NAME_MAX_LENGTH}", name="name_length"
    ),
    CheckConstraint(
        "cardinality(scopes) >= 1 AND scopes <@ ARRAY["
        + ", ".join(f"'{scope.value}'" for scope in Scope)
        + "]::text[]",
        name="scopes",
    ),
    CheckConstraint("expires_at > created_at", name="expires_after_creation"),
    Index(None, "user_id", "created_at"),
)

# Failed sign-ins in the throttling window; the account is a hash, never the typed email.
sign_in_failures = Table(
    "sign_in_failures",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("account_key", LargeBinary, nullable=False),
    Column("client_ip", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("octet_length(account_key) = 32", name="account_key_length"),
    Index(None, "account_key", "created_at"),
    Index(None, "client_ip", "created_at"),
    Index(None, "created_at"),
)


assets = Table(
    "assets",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column(
        "cover_version_id",
        Uuid,
        ForeignKey("asset_versions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    ),
    # Who created the asset (KILN-12); NULL only for assets made before sign-in existed.
    Column("owner_id", Uuid, ForeignKey("users.id"), nullable=True),
    CheckConstraint(f"char_length(name) BETWEEN 1 AND {ASSET_NAME_MAX_LENGTH}", name="name_length"),
    CheckConstraint(_one_of("kind", [k.value for k in AssetKind]), name="kind"),
    Index(None, "created_at", "id"),
)

asset_versions = Table(
    "asset_versions",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("asset_id", Uuid, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
    Column("number", Integer, nullable=False),
    Column("status", Text, nullable=False),
    Column("file_name", Text, nullable=False),
    Column("content_type", Text, nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("object_key", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("etag", Text, nullable=True),
    Column("failure_reason", Text, nullable=True),
    Column("uploaded_by", Uuid, ForeignKey("users.id"), nullable=True),  # KILN-12, as owner_id
    UniqueConstraint("asset_id", "number"),
    UniqueConstraint("object_key"),
    CheckConstraint("number >= 1", name="number_positive"),
    CheckConstraint(_one_of("status", [s.value for s in VersionStatus]), name="status"),
    CheckConstraint(
        f"char_length(file_name) BETWEEN 1 AND {FILE_NAME_MAX_LENGTH}", name="file_name_length"
    ),
    CheckConstraint(f"size_bytes BETWEEN 1 AND {MAX_UPLOAD_BYTES}", name="size_range"),
    CheckConstraint(
        "failure_reason IS NULL OR " + _one_of("failure_reason", [r.value for r in FailureReason]),
        name="failure_reason",
    ),
    CheckConstraint(
        "(status = 'failed') = (failure_reason IS NOT NULL)", name="failure_reason_when_failed"
    ),
    # Maintenance finds abandoned uploads oldest first (KILN-22).
    Index(None, "created_at", postgresql_where=text("status = 'pending_upload'")),
)


idempotency_keys = Table(
    "idempotency_keys",
    metadata,
    # Keys are scoped per user (KILN-12): one user's key never replays another's response.
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("key", Text, primary_key=True),
    Column("operation", Text, nullable=False),
    Column("request_hash", LargeBinary, nullable=False),
    Column("asset_id", Uuid, nullable=True),
    Column("version_id", Uuid, nullable=True),
    # What a comment request created: a thread or a reply (KILN-10).
    Column("resource_id", Uuid, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        f"char_length(key) BETWEEN 1 AND {IDEMPOTENCY_KEY_MAX_LENGTH}", name="key_length"
    ),
    CheckConstraint("octet_length(request_hash) = 32", name="request_hash_length"),
    Index(None, "created_at"),
)


# --- comments and region annotations (KILN-10) --------------------------------------------------
_IN_IMAGE = "BETWEEN 0 AND 1"

comment_threads = Table(
    "comment_threads",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("version_id", Uuid, ForeignKey("asset_versions.id", ondelete="CASCADE"), nullable=False),
    Column("number", Integer, nullable=False),  # per version, from 1, under an advisory lock
    Column("author_id", Uuid, ForeignKey("users.id"), nullable=False),
    # A region normalised to the image (0 to 1, origin top left); all NULL for a plain comment.
    Column("region_shape", Text, nullable=True),
    Column("region_x", Double, nullable=True),
    Column("region_y", Double, nullable=True),
    Column("region_width", Double, nullable=True),
    Column("region_height", Double, nullable=True),
    Column("resolved_at", DateTime(timezone=True), nullable=True),
    Column("resolved_by", Uuid, ForeignKey("users.id"), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("version_id", "number"),
    CheckConstraint("number >= 1", name="number_positive"),
    CheckConstraint(
        "region_shape IS NULL OR " + _one_of("region_shape", [s.value for s in RegionShape]),
        name="region_shape",
    ),
    CheckConstraint(
        "(region_shape IS NULL AND region_x IS NULL AND region_y IS NULL"
        " AND region_width IS NULL AND region_height IS NULL)"
        " OR (region_shape IS NOT NULL AND region_x IS NOT NULL AND region_y IS NOT NULL"
        f" AND region_x {_IN_IMAGE} AND region_y {_IN_IMAGE})",
        name="region_position",
    ),
    CheckConstraint(
        "region_shape IS DISTINCT FROM 'point' OR (region_width IS NULL AND region_height IS NULL)",
        name="point_has_no_size",
    ),
    CheckConstraint(
        "region_shape IS DISTINCT FROM 'rect'"
        " OR (region_width IS NOT NULL AND region_height IS NOT NULL"
        " AND region_width > 0 AND region_height > 0"
        " AND region_x + region_width <= 1 AND region_y + region_height <= 1)",
        name="rect_inside_image",
    ),
    CheckConstraint(
        "(resolved_at IS NULL) = (resolved_by IS NULL)", name="resolved_by_when_resolved"
    ),
)

comments = Table(
    "comments",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("thread_id", Uuid, ForeignKey("comment_threads.id", ondelete="CASCADE"), nullable=False),
    Column("author_id", Uuid, ForeignKey("users.id"), nullable=False),
    Column("body", Text, nullable=False),  # empty once deleted (soft delete keeps the place)
    Column("is_root", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("edited_at", DateTime(timezone=True), nullable=True),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    CheckConstraint(
        f"(deleted_at IS NULL AND char_length(body) BETWEEN 1 AND {COMMENT_BODY_MAX_LENGTH})"
        " OR (deleted_at IS NOT NULL AND body = '')",
        name="body_unless_deleted",
    ),
    Index(None, "thread_id", "created_at", "id"),
    # One root per thread; also how a thread page finds its first comments.
    Index(
        "uq_comments_thread_id_root",
        "thread_id",
        unique=True,
        postgresql_where=text("is_root"),
    ),
)


jobs = Table(
    "jobs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("kind", Text, nullable=False),
    Column("version_id", Uuid, ForeignKey("asset_versions.id", ondelete="CASCADE"), nullable=False),
    Column("status", Text, nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("run_after", DateTime(timezone=True), nullable=False),
    Column("leased_until", DateTime(timezone=True), nullable=True),
    Column("last_error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("version_id", "kind"),
    CheckConstraint(_one_of("kind", [k.value for k in JobKind]), name="kind"),
    CheckConstraint(_one_of("status", [s.value for s in JobStatus]), name="status"),
    CheckConstraint("attempts >= 0", name="attempts_non_negative"),
    Index(None, "run_after", postgresql_where=text("status = 'queued'")),
    Index(None, "leased_until", postgresql_where=text("status = 'running'")),
)


maintenance_runs = Table(
    "maintenance_runs",
    metadata,
    Column("task", Text, primary_key=True),
    Column("last_started_at", DateTime(timezone=True), nullable=False),
)
