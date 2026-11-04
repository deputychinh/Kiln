import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import create_engine, text

from kiln_api.errors import NotFoundError, StorageUnavailableError
from kiln_api.problems import install_error_handlers


class _Body(BaseModel):
    name: str


def _app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/missing")
    def missing() -> None:
        raise NotFoundError("Asset 42 does not exist.")

    @app.post("/things")
    def create(body: _Body) -> _Body:
        return body

    return app


def test_domain_errors_become_problem_details_with_a_stable_code() -> None:
    response = TestClient(_app()).get("/missing")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "Asset 42 does not exist.",
        "instance": "/missing",
        "code": "NOT_FOUND",
    }


def test_unknown_routes_use_the_same_problem_shape() -> None:
    response = TestClient(_app()).get("/nowhere")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_validation_errors_list_the_failing_fields() -> None:
    response = TestClient(_app()).post("/things", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["errors"][0]["loc"] == ["body", "name"]


def test_a_wrong_method_has_its_own_code() -> None:
    response = TestClient(_app()).delete("/missing")

    assert response.status_code == 405
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"
    assert response.headers["Allow"] == "GET"


def test_a_statement_timeout_is_a_busy_database_with_retry_after(database_url: str) -> None:
    engine = create_engine(database_url, connect_args={"options": "-c statement_timeout=100"})
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/slow")
    def slow() -> None:
        with engine.connect() as connection:
            connection.execute(text("SELECT pg_sleep(1)"))

    response = TestClient(app).get("/slow")
    engine.dispose()

    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_BUSY"
    assert response.headers["Retry-After"] == "1"


def test_server_side_domain_errors_are_logged_with_their_cause(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/storage")
    def storage() -> None:
        raise StorageUnavailableError(cause_code="ReadTimeoutError")

    with caplog.at_level(logging.ERROR, logger="kiln_api"):
        response = TestClient(app).get("/storage")

    assert response.status_code == 503
    assert response.json()["code"] == "STORAGE_UNAVAILABLE"
    assert response.headers["Retry-After"] == "1"
    assert "STORAGE_UNAVAILABLE" in caplog.text
    assert "cause ReadTimeoutError" in caplog.text
    assert "ReadTimeoutError" not in response.text
