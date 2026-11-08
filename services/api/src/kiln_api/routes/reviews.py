"""Review states of asset versions and their history (`/api/v1`, KILN-11)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from kiln_api.authentication import Authenticated
from kiln_api.constants import (
    API_PREFIX,
    IDEMPOTENT_REPLAYED_HEADER,
    REVIEW_PAGE_LIMIT_DEFAULT,
    REVIEW_PAGE_LIMIT_MAX,
    REVIEW_PAGE_LIMIT_MIN,
)
from kiln_api.routes.assets import IdempotencyKey
from kiln_api.schemas.problems import CREATED_HEADERS, problem_responses
from kiln_api.schemas.reviews import ReviewEventOut, ReviewEventPageOut, ReviewTransitionRequest
from kiln_api.services.reviews import ReviewService

router = APIRouter(
    prefix=API_PREFIX, tags=["reviews"], responses=problem_responses(401, 403, 404, 413, 422, 503)
)


def _service(request: Request) -> ReviewService:
    service: ReviewService = request.app.state.container.reviews
    return service


Service = Annotated[ReviewService, Depends(_service)]
Cursor = Annotated[str | None, Query(max_length=256)]
Limit = Annotated[int, Query(ge=REVIEW_PAGE_LIMIT_MIN, le=REVIEW_PAGE_LIMIT_MAX)]


@router.post(
    "/asset-versions/{version_id}/review-transitions",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Created.", "headers": CREATED_HEADERS},
        **problem_responses(400, 409),
    },
)
def transition(  # noqa: PLR0913, PLR0917 - FastAPI injects each parameter
    version_id: UUID,
    body: ReviewTransitionRequest,
    principal: Authenticated,
    service: Service,
    response: Response,
    key: IdempotencyKey,
) -> ReviewEventOut:
    """Approve, request changes on or reopen a version; the answer is the new history event.

    Compare-and-set: nothing changes unless the version is still in `expected_state` (409
    `REVIEW_STATE_CONFLICT` with `current_state`). The state machine is in `domain/reviews.py`.
    """
    created = service.transition(
        principal,
        version_id,
        action=body.action,
        expected_state=body.expected_state,
        note=body.note,
        idempotency_key=key,
    )
    if created.replayed:
        response.headers[IDEMPOTENT_REPLAYED_HEADER] = "true"
    response.headers["Location"] = f"{API_PREFIX}/review-events/{created.item.event.id}"
    return ReviewEventOut.of(created.item)


@router.get("/asset-versions/{version_id}/review-history", responses=problem_responses(400))
def history(
    version_id: UUID,
    principal: Authenticated,
    service: Service,
    cursor: Cursor = None,
    limit: Limit = REVIEW_PAGE_LIMIT_DEFAULT,
) -> ReviewEventPageOut:
    """A version's review events, newest first; `limit` is 1 to 100."""
    return ReviewEventPageOut.of(service.history(principal, version_id, cursor=cursor, limit=limit))


@router.get("/review-events/{event_id}")
def get_event(event_id: UUID, principal: Authenticated, service: Service) -> ReviewEventOut:
    """One review event."""
    return ReviewEventOut.of(service.get_event(principal, event_id))
