"""Comment threads, replies and region annotations on asset versions (`/api/v1`, KILN-10)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from kiln_api.authentication import Authenticated
from kiln_api.constants import (
    API_PREFIX,
    COMMENT_PAGE_LIMIT_DEFAULT,
    COMMENT_PAGE_LIMIT_MAX,
    COMMENT_PAGE_LIMIT_MIN,
    IDEMPOTENT_REPLAYED_HEADER,
)
from kiln_api.routes.assets import IdempotencyKey
from kiln_api.schemas.comments import (
    CommentOut,
    CommentPageOut,
    CommentRequest,
    ResolveRequest,
    StartThreadRequest,
    ThreadOut,
    ThreadPageOut,
)
from kiln_api.schemas.problems import CREATED_HEADERS, problem_responses
from kiln_api.services.comments import CommentService, Created

router = APIRouter(
    prefix=API_PREFIX, tags=["comments"], responses=problem_responses(401, 403, 404, 413, 422, 503)
)


def _service(request: Request) -> CommentService:
    service: CommentService = request.app.state.container.comments
    return service


Service = Annotated[CommentService, Depends(_service)]
Cursor = Annotated[str | None, Query(max_length=256)]
Limit = Annotated[int, Query(ge=COMMENT_PAGE_LIMIT_MIN, le=COMMENT_PAGE_LIMIT_MAX)]
_CREATED = {
    201: {"description": "Created.", "headers": CREATED_HEADERS},
    **problem_responses(400, 409),
}


def _created[T](response: Response, created: Created[T]) -> T:
    if created.replayed:
        response.headers[IDEMPOTENT_REPLAYED_HEADER] = "true"
    return created.item


@router.get("/asset-versions/{version_id}/comment-threads", responses=problem_responses(400))
def list_threads(
    version_id: UUID,
    principal: Authenticated,
    service: Service,
    cursor: Cursor = None,
    limit: Limit = COMMENT_PAGE_LIMIT_DEFAULT,
) -> ThreadPageOut:
    """A version's comment threads by number, each with its first comment; `limit` is 1 to 100."""
    page = service.list_threads(principal, version_id, cursor=cursor, limit=limit)
    return ThreadPageOut.of(page)


@router.post(
    "/asset-versions/{version_id}/comment-threads",
    status_code=status.HTTP_201_CREATED,
    responses=_CREATED,
)
def start_thread(  # noqa: PLR0913, PLR0917 - FastAPI injects each parameter
    version_id: UUID,
    body: StartThreadRequest,
    principal: Authenticated,
    service: Service,
    response: Response,
    key: IdempotencyKey,
) -> ThreadOut:
    """Start a thread on a version: on a region of its image (images only) or on all of it."""
    created = service.start_thread(
        principal,
        version_id,
        body=body.body,
        region=None if body.region is None else body.region.to_region(),
        idempotency_key=key,
    )
    view = _created(response, created)
    response.headers["Location"] = f"{API_PREFIX}/comment-threads/{view.thread.id}"
    return ThreadOut.of(view)


@router.get("/comment-threads/{thread_id}")
def get_thread(thread_id: UUID, principal: Authenticated, service: Service) -> ThreadOut:
    """One thread with its first comment."""
    return ThreadOut.of(service.get_thread(principal, thread_id))


@router.patch("/comment-threads/{thread_id}")
def resolve_thread(
    thread_id: UUID, body: ResolveRequest, principal: Authenticated, service: Service
) -> ThreadOut:
    """Resolve or reopen a thread; resolving again keeps the first resolution."""
    return ThreadOut.of(service.resolve(principal, thread_id, resolved=body.resolved))


@router.get("/comment-threads/{thread_id}/comments", responses=problem_responses(400))
def list_replies(
    thread_id: UUID,
    principal: Authenticated,
    service: Service,
    cursor: Cursor = None,
    limit: Limit = COMMENT_PAGE_LIMIT_DEFAULT,
) -> CommentPageOut:
    """A thread's replies oldest first (its first comment is on the thread); `limit` 1 to 100."""
    return CommentPageOut.of(service.list_replies(principal, thread_id, cursor=cursor, limit=limit))


@router.post(
    "/comment-threads/{thread_id}/comments",
    status_code=status.HTTP_201_CREATED,
    responses=_CREATED,
)
def reply(  # noqa: PLR0913, PLR0917 - FastAPI injects each parameter
    thread_id: UUID,
    body: CommentRequest,
    principal: Authenticated,
    service: Service,
    response: Response,
    key: IdempotencyKey,
) -> CommentOut:
    """Reply at the end of a thread."""
    created = service.reply(principal, thread_id, body=body.body, idempotency_key=key)
    view = _created(response, created)
    response.headers["Location"] = f"{API_PREFIX}/comments/{view.comment.id}"
    return CommentOut.of(view)


@router.get("/comments/{comment_id}")
def get_comment(comment_id: UUID, principal: Authenticated, service: Service) -> CommentOut:
    """One comment."""
    return CommentOut.of(service.get_comment(principal, comment_id))


@router.patch("/comments/{comment_id}", responses=problem_responses(409))
def edit_comment(
    comment_id: UUID, body: CommentRequest, principal: Authenticated, service: Service
) -> CommentOut:
    """Change the text of your own comment."""
    return CommentOut.of(service.edit(principal, comment_id, body=body.body))


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(comment_id: UUID, principal: Authenticated, service: Service) -> None:
    """Delete your own comment; it stays in its thread as deleted. Safe to repeat."""
    service.delete(principal, comment_id)
