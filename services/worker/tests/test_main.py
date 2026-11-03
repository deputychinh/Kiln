import logging

import pytest

from kiln_worker.__main__ import main
from kiln_worker.config import WorkerSettings


def test_worker_starts_and_exits_cleanly_without_job_kinds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="kiln_worker"):
        code = main(WorkerSettings(log_level="INFO"))

    assert code == 0
    assert "no job kinds registered" in caplog.text
