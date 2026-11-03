from fastapi.testclient import TestClient


def test_health_reports_ok_with_the_version(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.0.0"}


def test_ready_is_also_served_under_the_versioned_prefix(client: TestClient) -> None:
    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_request_id_is_echoed_when_the_client_sends_one(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-Id": "abc-123"})

    assert response.headers["X-Request-Id"] == "abc-123"


def test_request_id_is_generated_when_missing(client: TestClient) -> None:
    response = client.get("/health")

    assert len(response.headers["X-Request-Id"]) == 36
