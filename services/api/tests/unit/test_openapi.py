import json

import pytest

from kiln_api.openapi import main


def test_openapi_export_lists_the_health_route(capsys: pytest.CaptureFixture[str]) -> None:
    main()

    schema = json.loads(capsys.readouterr().out)
    assert "/health" in schema["paths"]
    assert schema["info"]["title"] == "Kiln API"
