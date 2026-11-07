"""The API as `make api` starts it: proxy headers only from trusted proxies (KILN-12 review)."""

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager

import httpx2
import pytest
from sqlalchemy import Engine, text

from kiln_api.config import Settings
from kiln_api.serve import server_options

FORGED = "203.0.113.77"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@contextmanager
def _serve(database_url: str, *, trusted_proxies: str) -> Iterator[str]:
    port = _free_port()
    env = {
        **os.environ,
        "KILN_ENV": "test",
        "KILN_DATABASE_URL": database_url,
        "KILN_TRUSTED_PROXIES": trusted_proxies,
    }
    server = subprocess.Popen(  # noqa: S603 - fixed interpreter and module
        [sys.executable, "-m", "kiln_api.serve", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                if httpx2.get(f"{base}/health", timeout=1).status_code == 200:
                    break
            except httpx2.TransportError:
                pass
            if time.monotonic() > deadline or server.poll() is not None:
                pytest.fail("the API did not start")
            time.sleep(0.1)
        yield base
    finally:
        server.terminate()
        server.wait(timeout=10)


def _forged_failed_sign_in(base: str) -> None:
    response = httpx2.post(
        f"{base}/api/v1/sessions",
        json={"email": "nobody@kiln.test", "password": "wrong password!"},
        headers={
            "X-Kiln-Csrf": "1",
            "Origin": "http://127.0.0.1:5173",
            "X-Forwarded-For": FORGED,
        },
        timeout=10,
    )
    assert response.status_code == 401


def _recorded_ips(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return list(connection.execute(text("SELECT client_ip FROM sign_in_failures")).scalars())


def test_a_forged_forwarded_for_does_not_choose_the_throttled_address(
    database_url: str, engine: Engine
) -> None:
    with _serve(database_url, trusted_proxies="") as base:
        _forged_failed_sign_in(base)

    assert _recorded_ips(engine) == ["127.0.0.1"]


def test_a_trusted_proxy_reports_the_client_address(database_url: str, engine: Engine) -> None:
    with _serve(database_url, trusted_proxies="127.0.0.1") as base:
        _forged_failed_sign_in(base)  # here the caller *is* the trusted proxy

    assert _recorded_ips(engine) == [FORGED]


def test_proxy_headers_are_off_unless_proxies_are_named() -> None:
    assert server_options(Settings(trusted_proxies="")) == {"proxy_headers": False}
    assert server_options(Settings(trusted_proxies=" 10.0.0.2, 10.0.1.0/24 ")) == {
        "proxy_headers": True,
        "forwarded_allow_ips": ["10.0.0.2", "10.0.1.0/24"],
    }
