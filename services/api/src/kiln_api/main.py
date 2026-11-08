"""Application factory: the composition root for HTTP."""

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from kiln_api.config import Settings, get_settings
from kiln_api.constants import (
    API_PREFIX,
    API_TITLE,
    API_VERSION,
    CSRF_HEADER,
    IDEMPOTENCY_KEY_HEADER,
    REQUEST_ID_HEADER,
)
from kiln_api.container import Container, build_container
from kiln_api.errors import StorageUnavailableError
from kiln_api.problems import (
    BodySizeLimit,
    install_error_handlers,
    install_problem_schema,
    unexpected_problem,
)
from kiln_api.routes import assets, comments, health, identity, reviews

logger = logging.getLogger("kiln_api")


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    """Build the app; tests pass their own settings and container."""
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container or build_container(resolved)
        try:
            app.state.container.storage.ensure_bucket()
        except StorageUnavailableError:
            logger.warning("storage unavailable at start-up; /ready reports 503 until it answers")
        yield
        app.state.container.engine.dispose()

    app = FastAPI(title=API_TITLE, version=API_VERSION, lifespan=lifespan)
    app.state.settings = resolved
    # Starlette runs the last-added middleware first. Order from the outside in: CORS, request id
    # (with the one catch-all for unexpected errors), body limit; so 413 and 500 problems still
    # carry CORS headers and X-Request-Id.
    app.add_middleware(BodySizeLimit)

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        value = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = value
        try:
            response = await call_next(request)
        except Exception as error:
            response = unexpected_problem(request, error)
        response.headers[REQUEST_ID_HEADER] = value
        # API answers are private to the caller (KILN-12); previews carry their own caching.
        if request.url.path.startswith(API_PREFIX):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", CSRF_HEADER, IDEMPOTENCY_KEY_HEADER, REQUEST_ID_HEADER],
        expose_headers=["Location", "Retry-After", REQUEST_ID_HEADER],
    )
    install_error_handlers(app)
    install_problem_schema(app)
    app.include_router(health.router)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(identity.router)
    app.include_router(assets.router)
    app.include_router(comments.router)
    app.include_router(reviews.router)
    return app


app = create_app()
