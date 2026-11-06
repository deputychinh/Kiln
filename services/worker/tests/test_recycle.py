import sys

import pytest

from kiln_worker.enums import RecycleReason
from kiln_worker.recycle import RecyclePolicy, peak_rss_bytes

MB = 1024 * 1024


def test_the_job_count_and_peak_memory_decide_when_to_recycle() -> None:
    memory = [100 * MB]
    policy = RecyclePolicy(max_jobs=3, max_rss_bytes=200 * MB, rss=lambda: memory[0])

    assert policy.reason(2) is None
    assert policy.reason(3) is RecycleReason.MAX_JOBS
    memory[0] = 200 * MB
    assert policy.reason(1) is None  # at the limit is fine
    memory[0] = 200 * MB + 1
    assert policy.reason(1) is RecycleReason.MAX_MEMORY


def test_peak_memory_is_reported_in_bytes_on_every_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Usage:
        ru_maxrss = 2048

    monkeypatch.setattr("resource.getrusage", lambda _: _Usage())
    monkeypatch.setattr(sys, "platform", "linux")
    assert peak_rss_bytes() == 2048 * 1024  # KiB on Linux
    monkeypatch.setattr(sys, "platform", "darwin")
    assert peak_rss_bytes() == 2048  # bytes on macOS


def test_the_real_peak_memory_is_plausible() -> None:
    assert 10 * MB < peak_rss_bytes() < 8 * 1024 * MB
