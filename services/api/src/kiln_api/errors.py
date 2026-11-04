"""Domain errors with stable codes; framework-free so the domain can raise them."""

from http import HTTPStatus
from uuid import UUID

from kiln_api.constants import (
    ASSET_NAME_MAX_LENGTH,
    FILE_NAME_MAX_LENGTH,
    MAX_UPLOAD_BYTES,
    MEDIA_TYPES,
)
from kiln_api.enums import ErrorCode, VersionStatus


class DomainError(Exception):
    """Base for every error the API raises on purpose; `detail` never holds personal data."""

    status = HTTPStatus.BAD_REQUEST
    code = ErrorCode.INTERNAL
    default_detail = "The request could not be processed."

    def __init__(self, detail: str | None = None) -> None:
        """Use the class's default detail unless a more specific one is given."""
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class NotFoundError(DomainError):
    """The resource does not exist or the caller may not see it."""

    status = HTTPStatus.NOT_FOUND
    code = ErrorCode.NOT_FOUND
    default_detail = "The resource does not exist."


class AssetNotFoundError(NotFoundError):
    """No asset with that id."""

    code = ErrorCode.ASSET_NOT_FOUND

    def __init__(self, asset_id: UUID) -> None:
        """Name the missing id."""
        super().__init__(f"Asset {asset_id} does not exist.")


class AssetVersionNotFoundError(NotFoundError):
    """No asset version with that id."""

    code = ErrorCode.ASSET_VERSION_NOT_FOUND

    def __init__(self, version_id: UUID) -> None:
        """Name the missing id."""
        super().__init__(f"Asset version {version_id} does not exist.")


class InvalidAssetNameError(DomainError):
    """The asset name is blank, too long or has control characters."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = ErrorCode.INVALID_ASSET_NAME
    default_detail = (
        f"An asset name needs 1 to {ASSET_NAME_MAX_LENGTH} characters,"
        " without hidden or control characters."
    )


class InvalidFileNameError(DomainError):
    """The file name is blank, too long or has control characters."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = ErrorCode.INVALID_FILE_NAME
    default_detail = (
        f"A file name needs 1 to {FILE_NAME_MAX_LENGTH} characters,"
        " without hidden or control characters, and cannot be only dots."
    )


class InvalidFileSizeError(DomainError):
    """The declared size is outside 1 byte to the upload limit."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = ErrorCode.INVALID_FILE_SIZE
    default_detail = f"A file must be between 1 byte and {MAX_UPLOAD_BYTES} bytes."


class UnsupportedMediaTypeError(DomainError):
    """The declared content type is not one Kiln can preview (a body field, hence 422)."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = ErrorCode.UNSUPPORTED_MEDIA_TYPE
    default_detail = f"Supported types: {', '.join(sorted(MEDIA_TYPES))}."


class AssetKindMismatchError(DomainError):
    """A version must be of the same kind as its asset."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = ErrorCode.ASSET_KIND_MISMATCH
    default_detail = "A new version must be the same kind of file as the asset."


class InvalidStatusTransitionError(DomainError):
    """The version life cycle does not allow this move."""

    status = HTTPStatus.CONFLICT
    code = ErrorCode.INVALID_STATUS_TRANSITION

    def __init__(self, current: VersionStatus, target: VersionStatus) -> None:
        """Name both states."""
        super().__init__(f"A version cannot move from {current} to {target}.")


class InvalidCursorError(DomainError):
    """The pagination cursor was not issued by this API."""

    code = ErrorCode.INVALID_CURSOR
    default_detail = "The cursor is not valid; start again without one."
