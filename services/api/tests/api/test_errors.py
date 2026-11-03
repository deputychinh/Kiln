from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from kiln_api.errors import NotFoundError, install_error_handlers


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


def test_other_http_errors_map_to_the_internal_code() -> None:
    response = TestClient(_app()).delete("/missing")

    assert response.status_code == 405
    assert response.json()["code"] == "INTERNAL"
