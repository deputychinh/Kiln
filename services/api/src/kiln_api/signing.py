"""AWS Signature Version 4 query-string signing for path-style S3 GET URLs.

boto3 always signs at the current second, so a preview URL changed on every response and
browsers could never reuse a cached image. Signing at a chosen instant (the start of a time
window) gives the same URL for the whole window (KILN-27). The algorithm follows
https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-query-string-auth.html and is
cross-checked against botocore in `tests/unit/test_signing.py`.
"""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

_ALGORITHM = "AWS4-HMAC-SHA256"
_SERVICE = "s3"
_UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD"
_NAIVE_TIME = "signed_at must carry a timezone"


@dataclass(frozen=True, slots=True)
class SigningCredentials:
    """Where and as whom URLs are signed (from settings; the secret never leaves the API)."""

    endpoint: str
    region: str
    access_key: str
    secret_key: str


def _encode(value: str, *, keep_slash: bool = False) -> str:
    """RFC 3986 percent-encoding as SigV4 requires (unreserved characters stay)."""
    return quote(value, safe="-_.~/" if keep_slash else "-_.~")


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def presign_get_url(  # noqa: PLR0913 - every field of the request is signed
    credentials: SigningCredentials,
    *,
    bucket: str,
    key: str,
    signed_at: datetime,
    expires_seconds: int,
    response_cache_control: str | None = None,
) -> str:
    """A GET URL for `bucket/key`, valid `expires_seconds` from `signed_at` (timezone-aware)."""
    if signed_at.tzinfo is None:
        raise ValueError(_NAIVE_TIME)
    amz_date = signed_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    scope = f"{day}/{credentials.region}/{_SERVICE}/aws4_request"
    endpoint = urlsplit(credentials.endpoint)
    path = _encode(f"/{bucket}/{key}", keep_slash=True)

    params = {
        "X-Amz-Algorithm": _ALGORITHM,
        "X-Amz-Credential": f"{credentials.access_key}/{scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires_seconds),
        "X-Amz-SignedHeaders": "host",
    }
    if response_cache_control is not None:
        params["response-cache-control"] = response_cache_control
    query = "&".join(f"{_encode(name)}={_encode(value)}" for name, value in sorted(params.items()))

    canonical_request = "\n".join(
        ["GET", path, query, f"host:{endpoint.netloc}", "", "host", _UNSIGNED_PAYLOAD]
    )
    string_to_sign = "\n".join(
        [_ALGORITHM, amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest()]
    )
    signing_key = _hmac(
        _hmac(
            _hmac(_hmac(f"AWS4{credentials.secret_key}".encode(), day), credentials.region),
            _SERVICE,
        ),
        "aws4_request",
    )
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return f"{endpoint.scheme}://{endpoint.netloc}{path}?{query}&X-Amz-Signature={signature}"
