import json
from pathlib import Path

from kiln_api.main import create_app

CONTRACT = Path(__file__).parents[2] / "openapi.json"


def test_the_committed_openapi_contract_matches_the_app() -> None:
    """Run `make openapi` after changing routes or schemas; the web types come from this file."""
    assert json.loads(CONTRACT.read_text()) == create_app().openapi()


def test_the_contract_lists_the_upload_endpoints() -> None:
    paths = json.loads(CONTRACT.read_text())["paths"]

    assert {
        "/api/v1/assets",
        "/api/v1/assets/{asset_id}",
        "/api/v1/assets/{asset_id}/versions",
        "/api/v1/asset-versions/{version_id}",
        "/api/v1/asset-versions/{version_id}/completions",
    } <= set(paths)


def test_error_responses_are_documented_as_problem_json_only() -> None:
    schema = json.loads(CONTRACT.read_text())
    completion = schema["paths"]["/api/v1/asset-versions/{version_id}/completions"]["post"]

    for status in ("404", "409", "413", "422", "503"):
        content = completion["responses"][status]["content"]
        assert set(content) == {"application/problem+json"}
        assert content["application/problem+json"]["schema"] == {
            "$ref": "#/components/schemas/Problem"
        }
    assert "Retry-After" in completion["responses"]["503"]["headers"]
    assert "Problem" in schema["components"]["schemas"]


def test_creations_document_the_location_header() -> None:
    paths = json.loads(CONTRACT.read_text())["paths"]

    for path in ("/api/v1/assets", "/api/v1/assets/{asset_id}/versions"):
        assert "Location" in paths[path]["post"]["responses"]["201"]["headers"]


def test_creations_document_idempotency_errors_and_the_replay_header() -> None:
    paths = json.loads(CONTRACT.read_text())["paths"]

    for path in ("/api/v1/assets", "/api/v1/assets/{asset_id}/versions"):
        responses = paths[path]["post"]["responses"]
        assert {"400", "409"} <= set(responses)
        assert "Idempotent-Replayed" in responses["201"]["headers"]
        parameters = {p["name"] for p in paths[path]["post"]["parameters"]}
        assert "Idempotency-Key" in parameters


def test_protected_operations_declare_both_security_schemes_and_401_403() -> None:
    schema = json.loads(CONTRACT.read_text())
    public = {("/api/v1/sessions", "post"), ("/api/v1/sessions/current", "delete")}

    assert set(schema["components"]["securitySchemes"]) == {"accessToken", "sessionCookie"}
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            if path.endswith(("/health", "/ready")) or (path, method) in public:
                assert "security" not in operation
                continue
            assert operation["security"] == [{"accessToken": []}, {"sessionCookie": []}]
            assert "401" in operation["responses"], (method, path)
            if (path, method) != ("/api/v1/me", "get"):  # any principal may read itself
                assert "403" in operation["responses"], (method, path)
            assert "WWW-Authenticate" in operation["responses"]["401"]["headers"]


def test_sign_in_documents_throttling_and_the_csrf_refusal() -> None:
    responses = json.loads(CONTRACT.read_text())["paths"]["/api/v1/sessions"]["post"]["responses"]

    assert {"201", "401", "403", "429"} <= set(responses)
    assert "Retry-After" in responses["429"]["headers"]
