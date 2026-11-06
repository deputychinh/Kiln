"""The pinned-time signer must produce exactly what boto3 would at the same instant (KILN-27)."""

from datetime import UTC, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import boto3
import botocore.auth
import pytest
from botocore.config import Config

from kiln_api.signing import SigningCredentials, presign_get_url

CREDENTIALS = SigningCredentials(
    endpoint="http://127.0.0.1:8333",
    region="us-east-1",
    access_key="kiln",
    secret_key="kiln-local-secret",
)
SIGNED_AT = datetime(2026, 11, 6, 8, 30, tzinfo=UTC)
CACHE_CONTROL = "private, max-age=1500, immutable"


def _boto3_url(monkeypatch: pytest.MonkeyPatch, key: str, *, cache_control: str | None) -> str:
    """What boto3 signs for the same request with its clock frozen at `SIGNED_AT`."""
    monkeypatch.setattr(
        botocore.auth, "get_current_datetime", lambda: SIGNED_AT.replace(tzinfo=None)
    )
    client = boto3.client(
        "s3",
        endpoint_url=CREDENTIALS.endpoint,
        region_name=CREDENTIALS.region,
        aws_access_key_id=CREDENTIALS.access_key,
        aws_secret_access_key=CREDENTIALS.secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    params = {"Bucket": "kiln-assets", "Key": key}
    if cache_control:
        params["ResponseCacheControl"] = cache_control
    return client.generate_presigned_url("get_object", Params=params, ExpiresIn=1500)


@pytest.mark.parametrize(
    "key",
    [
        "thumbs/0190f1c2-0000-7000-8000-000000000001/0190f1c2-0000-7000-8000-0000000000a1.webp",
        "plain.webp",
        "with space/and+plus.webp",
        "unicode/ảnh-thử_ü.webp",
        "reserved/a~b!c*d'e(f)g;h:i@j&k=l$m,n.webp",
    ],
)
@pytest.mark.parametrize("cache_control", [CACHE_CONTROL, None])
def test_the_url_matches_boto3_signing_at_the_same_instant(
    monkeypatch: pytest.MonkeyPatch, key: str, cache_control: str | None
) -> None:
    ours = presign_get_url(
        CREDENTIALS,
        bucket="kiln-assets",
        key=key,
        signed_at=SIGNED_AT,
        expires_seconds=1500,
        response_cache_control=cache_control,
    )

    theirs = urlsplit(_boto3_url(monkeypatch, key, cache_control=cache_control))
    mine = urlsplit(ours)
    assert (mine.scheme, mine.netloc, mine.path) == (theirs.scheme, theirs.netloc, theirs.path)
    assert parse_qs(mine.query) == parse_qs(theirs.query)


def test_the_same_inputs_always_give_the_same_url() -> None:
    def sign() -> str:
        return presign_get_url(
            CREDENTIALS,
            bucket="kiln-assets",
            key="thumbs/a.webp",
            signed_at=SIGNED_AT,
            expires_seconds=1500,
        )

    assert sign() == sign()


def test_another_instant_or_key_gives_another_signature() -> None:
    def signature(key: str, at: datetime) -> str:
        url = presign_get_url(
            CREDENTIALS, bucket="kiln-assets", key=key, signed_at=at, expires_seconds=1500
        )
        return parse_qs(urlsplit(url).query)["X-Amz-Signature"][0]

    base = signature("thumbs/a.webp", SIGNED_AT)
    assert signature("thumbs/a.webp", SIGNED_AT + timedelta(minutes=10)) != base
    assert signature("thumbs/b.webp", SIGNED_AT) != base


@pytest.mark.parametrize(
    "endpoint",
    ["http://h:9000/prefix", "https://storage.example:443", "http://STORAGE.example:8333"],
)
def test_endpoints_boto3_accepts_sign_the_same_way(
    monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    credentials = SigningCredentials(
        endpoint=endpoint, region="eu-west-3", access_key="AK/+x", secret_key="s"
    )
    monkeypatch.setattr(
        botocore.auth, "get_current_datetime", lambda: SIGNED_AT.replace(tzinfo=None)
    )
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="eu-west-3",
        aws_access_key_id="AK/+x",
        aws_secret_access_key="s",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    theirs = client.generate_presigned_url(
        "get_object", Params={"Bucket": "kiln-assets", "Key": "a b/ü.webp"}, ExpiresIn=60
    )

    ours = presign_get_url(
        credentials, bucket="kiln-assets", key="a b/ü.webp", signed_at=SIGNED_AT, expires_seconds=60
    )

    assert urlsplit(ours)._replace(query="") == urlsplit(theirs)._replace(query="")
    assert parse_qs(urlsplit(ours).query) == parse_qs(urlsplit(theirs).query)


def test_a_signing_time_in_another_zone_is_the_same_instant() -> None:
    """23:55 at UTC-7 is the next UTC day: the date in the scope must follow UTC."""
    local = datetime(2026, 11, 6, 23, 55, tzinfo=timezone(timedelta(hours=-7)))

    def sign(at: datetime) -> str:
        return presign_get_url(
            CREDENTIALS, bucket="kiln-assets", key="a.webp", signed_at=at, expires_seconds=60
        )

    assert sign(local) == sign(local.astimezone(UTC))
    assert "20261107T065500Z" in sign(local)


@pytest.mark.parametrize("expires", [0, -5, 604_801])
def test_an_expiry_outside_what_s3_accepts_is_refused(expires: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 604800"):
        presign_get_url(
            CREDENTIALS,
            bucket="kiln-assets",
            key="a.webp",
            signed_at=SIGNED_AT,
            expires_seconds=expires,
        )


@pytest.mark.parametrize(
    "endpoint",
    ["ftp://h", "http://user:pass@h:8333", "http://h:8333?x=1", "http://h#f", "storage"],
)
def test_an_endpoint_the_signer_cannot_express_is_refused(endpoint: str) -> None:
    with pytest.raises(ValueError, match="endpoint"):
        SigningCredentials(endpoint=endpoint, region="us-east-1", access_key="k", secret_key="s")


def test_the_secret_never_shows_in_a_repr() -> None:
    assert "kiln-local-secret" not in repr(CREDENTIALS)


def test_a_naive_signing_time_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone"):
        presign_get_url(
            CREDENTIALS,
            bucket="kiln-assets",
            key="a.webp",
            signed_at=datetime(2026, 11, 6, 8, 30),  # noqa: DTZ001 - the case under test
            expires_seconds=60,
        )
