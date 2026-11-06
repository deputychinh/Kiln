"""Presigned S3 GET URLs signed at a chosen instant, with botocore's own SigV4 (ADR 0008).

boto3 signs at the current second (`SigV4Auth.add_auth` reads `get_current_datetime()`), so a
preview URL changed on every response and browsers could never reuse a cached image. Pinning the
signing time to the start of a window keeps a URL the same for the whole window (KILN-27). The
signature itself is computed by botocore's `S3SigV4QueryAuth`; this module only pins its clock.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import quote, urlencode, urlsplit

from botocore.auth import SIGV4_TIMESTAMP, S3SigV4QueryAuth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

# S3 accepts presigned URLs valid for 1 second up to 7 days.
_EXPIRES_MIN_SECONDS = 1
_EXPIRES_MAX_SECONDS = 7 * 24 * 60 * 60
_NAIVE_TIME = "signed_at must carry a timezone"
_BAD_EXPIRY = "expires_seconds must be between 1 and 604800"
_BAD_ENDPOINT = "the storage endpoint must be an http(s) URL without credentials, query or fragment"


@dataclass(frozen=True, slots=True)
class SigningCredentials:
    """Where and as whom URLs are signed (from settings; the secret never leaves the API)."""

    endpoint: str
    region: str
    access_key: str
    secret_key: str = field(repr=False)

    def __post_init__(self) -> None:
        """Refuse an endpoint the URL builder below cannot express faithfully."""
        parts = urlsplit(self.endpoint)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.query
            or parts.fragment
        ):
            raise ValueError(_BAD_ENDPOINT)


class _PinnedTimeQueryAuth(S3SigV4QueryAuth):
    """botocore's S3 query signer with the signing time fixed instead of read from the clock."""

    def __init__(
        self, credentials: Credentials, region: str, expires: int, signed_at: datetime
    ) -> None:
        super().__init__(credentials, "s3", region, expires=expires)
        self._timestamp = signed_at.astimezone(UTC).strftime(SIGV4_TIMESTAMP)

    def _modify_request_before_signing(self, request: AWSRequest) -> None:
        # `add_auth` has just stamped the current time; every later step reads this value.
        request.context["timestamp"] = self._timestamp
        # The botocore stubs omit this hook; it is part of SigV4Auth since botocore 1.4.
        super()._modify_request_before_signing(request)  # type: ignore[misc]


def presign_get_url(  # noqa: PLR0913 - every part of the request is signed
    credentials: SigningCredentials,
    *,
    bucket: str,
    key: str,
    signed_at: datetime,
    expires_seconds: int,
    response_cache_control: str | None = None,
) -> str:
    """A path-style GET URL for `bucket/key`, valid `expires_seconds` from `signed_at`."""
    if signed_at.tzinfo is None:
        raise ValueError(_NAIVE_TIME)
    if not _EXPIRES_MIN_SECONDS <= expires_seconds <= _EXPIRES_MAX_SECONDS:
        raise ValueError(_BAD_EXPIRY)
    # The same path encoding boto3's S3 serializer uses for a key.
    url = f"{credentials.endpoint.rstrip('/')}/{quote(bucket, safe='')}/{quote(key, safe='/~')}"
    if response_cache_control is not None:
        url = f"{url}?{urlencode({'response-cache-control': response_cache_control})}"
    request = AWSRequest(method="GET", url=url)
    auth = _PinnedTimeQueryAuth(
        Credentials(credentials.access_key, credentials.secret_key),
        credentials.region,
        expires_seconds,
        signed_at,
    )
    auth.add_auth(request)
    return str(request.url)
