"""Assets, versions and upload completion (`/api/v1`)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from kiln_api.constants import (
    API_PREFIX,
    IDEMPOTENCY_KEY_HEADER,
    IDEMPOTENT_REPLAYED_HEADER,
    PAGE_LIMIT_DEFAULT,
    PAGE_LIMIT_MAX,
    PAGE_LIMIT_MIN,
)
from kiln_api.domain.idempotency import parse_idempotency_key
from kiln_api.errors import InvalidIdempotencyKeyError
from kiln_api.schemas.assets import (
    AssetDetailOut,
    AssetOut,
    AssetPageOut,
    CreateAssetRequest,
    PendingUploadOut,
    UploadDeclaration,
    VersionOut,
)
from kiln_api.schemas.problems import CREATED_HEADERS, problem_responses
from kiln_api.services.assets import AssetService, PendingUpload

router = APIRouter(prefix=API_PREFIX, tags=["assets"], responses=problem_responses(413, 422, 503))


def _service(request: Request) -> AssetService:
    service: AssetService = request.app.state.container.assets
    return service


Service = Annotated[AssetService, Depends(_service)]


def _idempotency_key(
    request: Request,
    header: Annotated[
        str | None,
        Header(
            alias=IDEMPOTENCY_KEY_HEADER,
            description=(
                "Optional sf-string of 1 to 255 printable ASCII characters, e.g. a quoted UUID."
                " A repeat within 24 hours replays the first result with `Idempotent-Replayed:"
                " true`; another body or endpoint gives 422; send the header once."
            ),
        ),
    ] = None,
) -> str | None:
    if len(request.headers.getlist(IDEMPOTENCY_KEY_HEADER)) > 1:
        raise InvalidIdempotencyKeyError  # several lines form an sf-list, not one key
    return None if header is None else parse_idempotency_key(header)


IdempotencyKey = Annotated[str | None, Depends(_idempotency_key)]


def _created(response: Response, pending: PendingUpload, location: str) -> PendingUploadOut:
    response.headers["Location"] = location
    if pending.replayed:
        response.headers[IDEMPOTENT_REPLAYED_HEADER] = "true"
    return PendingUploadOut.of(pending)


@router.post(
    "/assets",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Created.", "headers": CREATED_HEADERS},
        **problem_responses(400, 409),
    },
)
def create_asset(
    body: CreateAssetRequest, service: Service, response: Response, key: IdempotencyKey
) -> PendingUploadOut:
    """Create an asset with version 1 and return the signed upload form."""
    pending = service.create(body.name, body.to_spec(), idempotency_key=key)
    return _created(response, pending, f"{API_PREFIX}/assets/{pending.asset.id}")


@router.get("/assets", responses=problem_responses(400))
def list_assets(
    service: Service,
    cursor: Annotated[str | None, Query(max_length=256)] = None,
    limit: Annotated[int, Query(ge=PAGE_LIMIT_MIN, le=PAGE_LIMIT_MAX)] = PAGE_LIMIT_DEFAULT,
) -> AssetPageOut:
    """List assets newest first; `limit` is 1 to 100."""
    page = service.list(cursor=cursor, limit=limit)
    return AssetPageOut(items=[AssetOut.of(a) for a in page.items], next_cursor=page.next_cursor)


@router.get("/assets/{asset_id}", responses=problem_responses(404))
def get_asset(asset_id: UUID, service: Service) -> AssetDetailOut:
    """Return an asset with its first 500 versions by number."""
    return AssetDetailOut.of_detail(service.get(asset_id))


@router.post(
    "/assets/{asset_id}/versions",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Created.", "headers": CREATED_HEADERS},
        **problem_responses(400, 404, 409),
    },
)
def add_version(
    asset_id: UUID,
    body: UploadDeclaration,
    service: Service,
    response: Response,
    key: IdempotencyKey,
) -> PendingUploadOut:
    """Add the next version of an asset and return its signed upload form."""
    pending = service.add_version(asset_id, body.to_spec(), idempotency_key=key)
    return _created(response, pending, f"{API_PREFIX}/asset-versions/{pending.version.id}")


@router.get("/asset-versions/{version_id}", responses=problem_responses(404))
def get_version(version_id: UUID, service: Service) -> VersionOut:
    """Return one version."""
    return VersionOut.of(service.get_version(version_id))


@router.post("/asset-versions/{version_id}/completions", responses=problem_responses(404, 409))
def complete_upload(version_id: UUID, service: Service) -> VersionOut:
    """Confirm the file arrived intact and start processing; safe to repeat."""
    return VersionOut.of(service.complete_upload(version_id))
