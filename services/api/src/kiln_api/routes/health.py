"""Liveness and readiness probes."""

from fastapi import APIRouter
from pydantic import BaseModel

from kiln_api.constants import API_VERSION
from kiln_api.enums import HealthStatus

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Probe result."""

    status: HealthStatus
    version: str


@router.get("/health")
def health() -> HealthResponse:
    """Report that the process is alive."""
    return HealthResponse(status=HealthStatus.OK, version=API_VERSION)


@router.get("/ready")
def ready() -> HealthResponse:
    """Report that dependencies are reachable (database and storage join in v0.1)."""
    return HealthResponse(status=HealthStatus.OK, version=API_VERSION)
