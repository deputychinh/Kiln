"""Request and response bodies for assets and versions."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from kiln_api.constants import (
    MAX_CONTENT_TYPE_FIELD_LENGTH,
    MAX_FILE_NAME_FIELD_LENGTH,
    MAX_NAME_FIELD_LENGTH,
)
from kiln_api.domain.assets import Asset, AssetVersion, UploadSpec
from kiln_api.enums import AssetKind, VersionStatus
from kiln_api.services.assets import AssetDetail, PendingUpload


class UploadDeclaration(BaseModel):
    """What the client is about to upload."""

    model_config = ConfigDict(extra="forbid")

    file_name: str = Field(max_length=MAX_FILE_NAME_FIELD_LENGTH)
    content_type: str = Field(max_length=MAX_CONTENT_TYPE_FIELD_LENGTH)
    size_bytes: StrictInt

    def to_spec(self) -> UploadSpec:
        """Convert to the domain value."""
        return UploadSpec(
            file_name=self.file_name, content_type=self.content_type, size_bytes=self.size_bytes
        )


class CreateAssetRequest(UploadDeclaration):
    """A new asset and its first file."""

    name: str = Field(max_length=MAX_NAME_FIELD_LENGTH)


class AssetOut(BaseModel):
    """An asset."""

    id: UUID
    name: str
    kind: AssetKind
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, asset: Asset) -> "AssetOut":
        """Build from the domain object."""
        return cls(
            id=asset.id,
            name=asset.name,
            kind=asset.kind,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )


class VersionOut(BaseModel):
    """One version; the storage key stays internal."""

    id: UUID
    asset_id: UUID
    number: int
    status: VersionStatus
    file_name: str
    content_type: str
    size_bytes: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, version: AssetVersion) -> "VersionOut":
        """Build from the domain object."""
        return cls(
            id=version.id,
            asset_id=version.asset_id,
            number=version.number,
            status=version.status,
            file_name=version.file_name,
            content_type=version.content_type,
            size_bytes=version.size_bytes,
            created_at=version.created_at,
            updated_at=version.updated_at,
        )


class UploadOut(BaseModel):
    """POST the file as multipart form data: every field, then `file`, to `url`."""

    url: str
    fields: dict[str, str]
    expires_at: datetime


class PendingUploadOut(BaseModel):
    """A created asset or version waiting for its file."""

    asset: AssetOut
    version: VersionOut
    upload: UploadOut

    @classmethod
    def of(cls, pending: PendingUpload) -> "PendingUploadOut":
        """Build from the service result."""
        return cls(
            asset=AssetOut.of(pending.asset),
            version=VersionOut.of(pending.version),
            upload=UploadOut(
                url=pending.upload.url,
                fields=pending.upload.fields,
                expires_at=pending.upload.expires_at,
            ),
        )


class AssetDetailOut(AssetOut):
    """An asset with its versions by number."""

    versions: list[VersionOut]

    @classmethod
    def of_detail(cls, detail: AssetDetail) -> "AssetDetailOut":
        """Build from the service result."""
        return cls(
            **AssetOut.of(detail.asset).model_dump(),
            versions=[VersionOut.of(version) for version in detail.versions],
        )


class AssetPageOut(BaseModel):
    """A newest-first page; pass `next_cursor` back to get the next one."""

    items: list[AssetOut]
    next_cursor: str | None
