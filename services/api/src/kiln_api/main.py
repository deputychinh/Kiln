"""Application factory: the composition root for HTTP."""

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from kiln_api.config import Settings, get_settings
from kiln_api.constants import API_PREFIX, API_TITLE, API_VERSION, REQUEST_ID_HEADER
from kiln_api.container import Container, build_container
from kiln_api.errors import StorageUnavailableError
from kiln_api.problems import install_error_handlers
from kiln_api.routes import assets, health

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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER],
        expose_headers=["Location", REQUEST_ID_HEADER],
    )

    @app.middleware("http")
    async def request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        value = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = value
        return response

    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(assets.router)
    return app


app = create_app()
