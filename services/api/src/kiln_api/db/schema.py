"""Tables; invariants are enforced here as well as in the domain."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)

from kiln_api.constants import ASSET_NAME_MAX_LENGTH, FILE_NAME_MAX_LENGTH, MAX_UPLOAD_BYTES
from kiln_api.enums import AssetKind, VersionStatus

metadata = MetaData(
    naming_convention={
        "pk": "pk_%(table_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "ix": "ix_%(table_name)s_%(column_0_name)s_%(column_1_name)s",
    }
)


def _one_of(column: str, values: list[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


assets = Table(
    "assets",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
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
    UniqueConstraint("asset_id", "number"),
    UniqueConstraint("object_key"),
    CheckConstraint("number >= 1", name="number_positive"),
    CheckConstraint(_one_of("status", [s.value for s in VersionStatus]), name="status"),
    CheckConstraint(
        f"char_length(file_name) BETWEEN 1 AND {FILE_NAME_MAX_LENGTH}", name="file_name_length"
    ),
    CheckConstraint(f"size_bytes BETWEEN 1 AND {MAX_UPLOAD_BYTES}", name="size_range"),
)
