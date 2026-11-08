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
from kiln_api.enums import AssetKind, FailureReason, ReviewState, VersionStatus
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
    thumbnail_url: str | None = Field(
        default=None, description="Preview of the newest ready version (signed, 15 minutes)."
    )
    owner_id: UUID | None = Field(
        default=None, description="The user who created the asset; null for assets before sign-in."
    )
    review_state: ReviewState = Field(
        description="The review state of the newest version: a new version is back in review."
    )

    @classmethod
    def of(
        cls,
        asset: Asset,
        thumbnail_url: str | None = None,
        review_state: ReviewState = ReviewState.IN_REVIEW,
    ) -> "AssetOut":
        """Build from the domain object (a new asset or version is in review)."""
        return cls(
            id=asset.id,
            name=asset.name,
            kind=asset.kind,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
            thumbnail_url=thumbnail_url,
            owner_id=asset.owner_id,
            review_state=review_state,
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
    failure_reason: FailureReason | None = Field(
        default=None, description="Why processing failed; set only when status is failed."
    )
    thumbnail_url: str | None = Field(
        default=None, description="Preview once the version is ready (signed, 15 minutes)."
    )
    download_url: str | None = Field(
        default=None,
        description="The original file once the version is ready (signed like the preview).",
    )
    uploaded_by: UUID | None = Field(
        default=None, description="The user who uploaded it; null for versions before sign-in."
    )
    review_state: ReviewState = Field(description="Where the version stands in review (KILN-11).")
    review_revision: int = Field(
        description="How many review transitions it has had; the sequence of its newest event."
    )

    @classmethod
    def of(
        cls,
        version: AssetVersion,
        thumbnail_url: str | None = None,
        download_url: str | None = None,
    ) -> "VersionOut":
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
            failure_reason=version.failure_reason,
            thumbnail_url=thumbnail_url,
            download_url=download_url,
            uploaded_by=version.uploaded_by,
            review_state=version.review_state,
            review_revision=version.review_revision,
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
    upload: UploadOut | None = Field(
        description=(
            "Signed form for the file. A first creation always has one; a replay has null"
            " once the version left pending_upload."
        )
    )

    @classmethod
    def of(cls, pending: PendingUpload) -> "PendingUploadOut":
        """Build from the service result."""
        return cls(
            asset=AssetOut.of(pending.asset),
            version=VersionOut.of(pending.version),
            upload=None
            if pending.upload is None
            else UploadOut(
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
            **AssetOut.of(detail.asset, detail.thumbnail_url, detail.review_state).model_dump(),
            versions=[
                VersionOut.of(view.version, view.thumbnail_url, view.download_url)
                for view in detail.versions
            ],
        )


class AssetPageOut(BaseModel):
    """A newest-first page; pass `next_cursor` back to get the next one."""

    items: list[AssetOut]
    next_cursor: str | None
