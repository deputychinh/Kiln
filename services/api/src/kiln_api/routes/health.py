"""Liveness and readiness probes."""

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

from kiln_api.constants import API_VERSION
from kiln_api.enums import HealthStatus
from kiln_api.schemas.problems import problem_responses

router = APIRouter(tags=["health"])
logger = logging.getLogger("kiln_api")


class HealthResponse(BaseModel):
    """Probe result."""

    status: HealthStatus
    version: str


@router.get("/health")
def health() -> HealthResponse:
    """Report that the process is alive; never touches dependencies."""
    return HealthResponse(status=HealthStatus.OK, version=API_VERSION)


@router.get("/ready", responses=problem_responses(503))
def ready(request: Request) -> HealthResponse:
    """Report that the database and storage answer (503 problem details otherwise)."""
    container = request.app.state.container
    container.check_database()
    container.storage.ensure_bucket()
    return HealthResponse(status=HealthStatus.OK, version=API_VERSION)
