"""Print the OpenAPI schema; `make openapi` writes it to `services/api/openapi.json`."""

import json
import sys

from kiln_api.main import create_app


def main() -> None:
    """Write the schema as pretty JSON to stdout."""
    sys.stdout.write(json.dumps(create_app().openapi(), indent=2) + "\n")


if __name__ == "__main__":
    main()
