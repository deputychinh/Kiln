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
