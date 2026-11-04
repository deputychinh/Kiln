import subprocess
import sys


def test_the_domain_imports_no_web_framework() -> None:
    code = (
        "import sys, kiln_api.domain.assets, kiln_api.domain.cursor, kiln_api.errors;"
        "print(sorted(m for m in ('fastapi', 'starlette', 'sqlalchemy') if m in sys.modules))"
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter and code
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "[]"
