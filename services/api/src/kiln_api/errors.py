"""Domain errors with stable codes; framework-free so the domain can raise them."""

from http import HTTPStatus
from uuid import UUID

from kiln_api.constants import (
    ACCESS_TOKEN_MAX_PER_USER,
    ACCESS_TOKEN_NAME_MAX_LENGTH,
    ASSET_NAME_MAX_LENGTH,
    COMMENT_BODY_MAX_LENGTH,
    DISPLAY_NAME_MAX_LENGTH,
    FILE_NAME_MAX_LENGTH,
    MAX_UPLOAD_BYTES,
    MEDIA_TYPES,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    REVIEW_NOTE_MAX_LENGTH,
)
from kiln_api.enums import ErrorCode, ReviewAction, ReviewState, VersionStatus


class DomainError(Exception):
    """Base for every error the API raises on purpose; `detail` never holds personal data."""

    status = HTTPStatus.BAD_REQUEST
    code = ErrorCode.INTERNAL
    default_detail = "The request could not be processed."

    def __init__(self, detail: str | None = None, *, cause_code: str = "") -> None:
        """Use the class's default detail unless a more specific one is given.

        `cause_code` names the infrastructure failure (for logs only, never shown to clients).
        """
        self.detail = detail or self.default_detail
        self.cause_code = cause_code
        super().__init__(self.detail)

    @property
    def extensions(self) -> dict[str, object]:
        """Extension members of the problem details (RFC 9457 section 3.2); none by default."""
        return {}


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


class UploadNotFoundError(DomainError):
    """Completion was requested but storage has no object for the version."""

    status = HTTPStatus.CONFLICT
    code = ErrorCode.UPLOAD_NOT_FOUND
    default_detail = "No file has been uploaded for this version yet."


class UploadMismatchError(DomainError):
    """The stored object differs from what was declared."""

    status = HTTPStatus.CONFLICT
    code = ErrorCode.UPLOAD_MISMATCH
    default_detail = "The uploaded file does not match the declared size or content type."


class StorageUnavailableError(DomainError):
    """Object storage did not answer in time or failed."""

    status = HTTPStatus.SERVICE_UNAVAILABLE
    code = ErrorCode.STORAGE_UNAVAILABLE
    default_detail = "File storage is unavailable; try again shortly."

    def __init__(
        self,
        detail: str | None = None,
        *,
        cause_code: str = "",
        retry_after_seconds: int | None = None,
    ) -> None:
        """`retry_after_seconds` becomes the `Retry-After` header (an open circuit's cool-down)."""
        super().__init__(detail, cause_code=cause_code)
        self.retry_after_seconds = retry_after_seconds


class DatabaseUnavailableError(DomainError):
    """The database did not answer."""

    status = HTTPStatus.SERVICE_UNAVAILABLE
    code = ErrorCode.DATABASE_UNAVAILABLE
    default_detail = "The database is unavailable; try again shortly."


class InvalidIdempotencyKeyError(DomainError):
    """The `Idempotency-Key` header is not a valid key."""

    code = ErrorCode.INVALID_IDEMPOTENCY_KEY
    default_detail = (
        "Idempotency-Key must be a quoted string (or a token) of 1 to 255 printable ASCII"
        " characters, for example a UUID."
    )


class IdempotencyKeyReusedError(DomainError):
    """The key was already used for a different request."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = ErrorCode.IDEMPOTENCY_KEY_REUSED
    default_detail = "This Idempotency-Key was already used for a different request."


class IdempotencyKeyInUseError(DomainError):
    """A request with the same key is still being processed."""

    status = HTTPStatus.CONFLICT
    code = ErrorCode.IDEMPOTENCY_KEY_IN_USE
    default_detail = "A request with this Idempotency-Key is still in progress; retry unchanged."


class UnauthenticatedError(DomainError):
    """No valid session or token: missing, unknown, expired or revoked (never says which)."""

    status = HTTPStatus.UNAUTHORIZED
    code = ErrorCode.UNAUTHENTICATED
    default_detail = "Sign in, or send a valid personal access token."


class InvalidCredentialsError(DomainError):
    """Unknown email or wrong password; one answer for both, so accounts cannot be probed."""

    status = HTTPStatus.UNAUTHORIZED
    code = ErrorCode.INVALID_CREDENTIALS
    default_detail = "The email or password is not correct."


class SignInThrottledError(DomainError):
    """Too many failed sign-ins for this account or from this address."""

    status = HTTPStatus.TOO_MANY_REQUESTS
    code = ErrorCode.SIGN_IN_THROTTLED
    default_detail = "Too many failed attempts. Wait a few minutes, then try again."

    def __init__(self, retry_after_seconds: int) -> None:
        """`retry_after_seconds` becomes the `Retry-After` header."""
        super().__init__()
        self.retry_after_seconds = retry_after_seconds


class CsrfCheckFailedError(DomainError):
    """A cookie-authenticated write without the CSRF header or from an origin not allowed."""

    status = HTTPStatus.FORBIDDEN
    code = ErrorCode.CSRF_CHECK_FAILED
    default_detail = "The request did not come from the Kiln app."


class InsufficientScopeError(DomainError):
    """The token lacks the scope this action needs."""

    status = HTTPStatus.FORBIDDEN
    code = ErrorCode.INSUFFICIENT_SCOPE
    default_detail = "This token does not have the scope this action needs."


class SessionRequiredError(DomainError):
    """Managing tokens needs a signed-in browser session, not a token."""

    status = HTTPStatus.FORBIDDEN
    code = ErrorCode.SESSION_REQUIRED
    default_detail = "Manage access tokens from a signed-in browser session."


class AccessTokenNotFoundError(NotFoundError):
    """No token with that id belongs to the caller."""

    code = ErrorCode.ACCESS_TOKEN_NOT_FOUND
    default_detail = "The access token does not exist."


class AccessTokenLimitError(DomainError):
    """A user may hold a bounded number of active tokens."""

    status = HTTPStatus.CONFLICT
    code = ErrorCode.ACCESS_TOKEN_LIMIT
    default_detail = (
        f"You already have {ACCESS_TOKEN_MAX_PER_USER} active tokens; revoke one first."
    )


class InvalidTokenNameError(DomainError):
    """A token name is blank, too long or has hidden characters."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = ErrorCode.INVALID_TOKEN_NAME
    default_detail = (
        f"A token name needs 1 to {ACCESS_TOKEN_NAME_MAX_LENGTH} characters,"
        " without hidden or control characters."
    )


class InvalidEmailError(DomainError):
    """Not an email address Kiln accepts."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = ErrorCode.INVALID_EMAIL
    default_detail = "Enter an email address such as name@studio.com."


class InvalidDisplayNameError(DomainError):
    """A display name is blank, too long or has hidden characters."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = ErrorCode.INVALID_DISPLAY_NAME
    default_detail = (
        f"A name needs 1 to {DISPLAY_NAME_MAX_LENGTH} characters,"
        " without hidden or control characters."
    )


class WeakPasswordError(DomainError):
    """A new password is refused: outside the allowed length, or one of the subclasses below.

    No detail ever repeats the password.
    """

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = ErrorCode.WEAK_PASSWORD
    default_detail = f"A password needs {PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters."


class CommonPasswordError(WeakPasswordError):
    """The password is on the bundled list of common and breached passwords (KILN-39)."""

    code = ErrorCode.COMMON_PASSWORD
    default_detail = (
        "This password is on a list of common or breached passwords that attackers try first."
        " Choose another one, for example a few unrelated words."
    )


class GuessablePasswordError(WeakPasswordError):
    """Without the context words (ADR 0019), the password is too short or common (KILN-39)."""

    code = ErrorCode.GUESSABLE_PASSWORD
    default_detail = (
        "This password leans on the email address, the person's name or the word Kiln, which"
        f" attackers try first: it needs {PASSWORD_MIN_LENGTH} characters besides them."
        " Choose another one."
    )


class EmailTakenError(DomainError):
    """A user with that email exists (only the operator's CLI can see this)."""

    status = HTTPStatus.CONFLICT
    code = ErrorCode.EMAIL_TAKEN
    default_detail = "A user with this email already exists."


class CommentThreadNotFoundError(NotFoundError):
    """No comment thread with that id."""

    code = ErrorCode.COMMENT_THREAD_NOT_FOUND

    def __init__(self, thread_id: UUID) -> None:
        """Name the missing id."""
        super().__init__(f"Comment thread {thread_id} does not exist.")


class CommentNotFoundError(NotFoundError):
    """No comment with that id."""

    code = ErrorCode.COMMENT_NOT_FOUND

    def __init__(self, comment_id: UUID) -> None:
        """Name the missing id."""
        super().__init__(f"Comment {comment_id} does not exist.")


class InvalidCommentBodyError(DomainError):
    """A comment is blank, too long or hides characters."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = ErrorCode.INVALID_COMMENT_BODY
    default_detail = (
        f"A comment needs 1 to {COMMENT_BODY_MAX_LENGTH} characters,"
        " without hidden or control characters (line breaks are fine)."
    )


class InvalidRegionError(DomainError):
    """A region lies outside the image or has the wrong size for its shape."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = ErrorCode.INVALID_REGION
    default_detail = (
        "A region needs x and y from 0 to 1; a rectangle a width and height of at least 0.01"
        " that stay inside the image; a point no size."
    )


class RegionNotSupportedError(DomainError):
    """Regions mark images; a 3D model takes plain comments only."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = ErrorCode.REGION_NOT_SUPPORTED
    default_detail = "Regions can be marked on images only; comment on a model without one."


class NotCommentAuthorError(DomainError):
    """Only a comment's author may edit or delete it."""

    status = HTTPStatus.FORBIDDEN
    code = ErrorCode.NOT_COMMENT_AUTHOR
    default_detail = "Only the author of a comment can change or delete it."


class CommentDeletedError(DomainError):
    """A deleted comment cannot be edited."""

    status = HTTPStatus.CONFLICT
    code = ErrorCode.COMMENT_DELETED
    default_detail = "This comment was deleted."


class ReviewEventNotFoundError(NotFoundError):
    """No review event with that id (KILN-11)."""

    code = ErrorCode.REVIEW_EVENT_NOT_FOUND

    def __init__(self, event_id: UUID) -> None:
        """Name the missing id."""
        super().__init__(f"Review event {event_id} does not exist.")


class InvalidReviewNoteError(DomainError):
    """A review note is too long or hides characters."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = ErrorCode.INVALID_REVIEW_NOTE
    default_detail = (
        f"A review note is optional and holds up to {REVIEW_NOTE_MAX_LENGTH} characters,"
        " without hidden or control characters (line breaks are fine)."
    )


class InvalidReviewTransitionError(DomainError):
    """The action does not apply to the version's review state (the transition table)."""

    status = HTTPStatus.CONFLICT
    code = ErrorCode.INVALID_REVIEW_TRANSITION

    def __init__(self, state: ReviewState, action: ReviewAction) -> None:
        """Name the state and the refused action."""
        self.state = state
        super().__init__(f"A version that is {state.value} cannot take {action.value}.")

    @property
    def extensions(self) -> dict[str, object]:
        """The state the version is in."""
        return {"current_state": self.state.value}


class ReviewStateConflictError(DomainError):
    """Someone changed the version's review state since the caller read it (compare-and-set)."""

    status = HTTPStatus.CONFLICT
    code = ErrorCode.REVIEW_STATE_CONFLICT

    def __init__(self, current: ReviewState, revision: int) -> None:
        """Name the state and revision the version is at now."""
        self.current = current
        self.revision = revision
        super().__init__(
            f"The version is {current.value} now; someone changed it since you looked."
            " Read it again before deciding."
        )

    @property
    def extensions(self) -> dict[str, object]:
        """The state and revision the version is at now, so the client can show and resend them."""
        return {"current_state": self.current.value, "current_revision": self.revision}


class VersionNotReadyError(DomainError):
    """Only a ready version (one that was processed and can be looked at) is approved or refused."""

    status = HTTPStatus.CONFLICT
    code = ErrorCode.VERSION_NOT_READY
    default_detail = "Only a ready version can be approved or sent back for changes."
