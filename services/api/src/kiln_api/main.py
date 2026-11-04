"""Application factory: the composition root for HTTP."""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from kiln_api.config import Settings, get_settings
from kiln_api.constants import API_PREFIX, API_TITLE, API_VERSION, REQUEST_ID_HEADER
from kiln_api.problems import install_error_handlers
from kiln_api.routes import health


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; tests pass their own settings."""
    resolved = settings or get_settings()
    app = FastAPI(title=API_TITLE, version=API_VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
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
    return app


app = create_app()
