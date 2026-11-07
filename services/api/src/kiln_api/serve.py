"""Start the API: `python -m kiln_api.serve` (`make api`, the e2e web server).

uvicorn believes `X-Forwarded-For` from 127.0.0.1 by default, so anything reaching the API through
loopback (a dev proxy, a reverse proxy on the same host, a curl on the box) could choose the client
IP that sign-in throttling counts. Here proxy headers are read only from `KILN_TRUSTED_PROXIES`
(KILN-12 review); with none set, the TCP peer is the client.
"""

import argparse
from collections.abc import Sequence
from typing import Any

import uvicorn

from kiln_api.config import Settings, get_settings

APP = "kiln_api.main:app"


def server_options(settings: Settings) -> dict[str, Any]:
    """The proxy options uvicorn gets for `settings`: off unless proxies are named."""
    trusted = settings.trusted_proxy_list
    if not trusted:
        return {"proxy_headers": False}
    return {"proxy_headers": True, "forwarded_allow_ips": trusted}


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover - runs a server
    """Parse `--host`, `--port` and `--reload`, then serve."""
    parser = argparse.ArgumentParser(prog="kiln-api-serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)
    uvicorn.run(
        APP, host=args.host, port=args.port, reload=args.reload, **server_options(get_settings())
    )


if __name__ == "__main__":  # pragma: no cover
    main()
