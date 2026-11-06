from fakes import FakeStorage
from fastapi.testclient import TestClient

from kiln_api.constants import API_VERSION


def test_health_reports_ok_with_the_version(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": API_VERSION}


def test_ready_checks_database_and_storage_and_creates_the_bucket(
    client: TestClient, storage: FakeStorage
) -> None:
    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert storage.bucket_ready


def test_a_storage_outage_makes_ready_fail_while_health_stays_up(
    client: TestClient, storage: FakeStorage
) -> None:
    storage.available = False

    ready = client.get("/ready")
    health = client.get("/health")

    assert ready.status_code == 503
    assert ready.json()["code"] == "STORAGE_UNAVAILABLE"
    assert health.status_code == 200


def test_request_id_is_echoed_when_the_client_sends_one(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-Id": "abc-123"})

    assert response.headers["X-Request-Id"] == "abc-123"


def test_request_id_is_generated_when_missing(client: TestClient) -> None:
    response = client.get("/health")

    assert len(response.headers["X-Request-Id"]) == 36


def test_ready_only_probes_and_never_creates_the_bucket(
    client: TestClient, storage: FakeStorage
) -> None:
    calls_at_start_up = storage.ensure_calls

    client.get("/ready")
    client.get("/ready")

    assert calls_at_start_up == 1
    assert storage.ensure_calls == 1
