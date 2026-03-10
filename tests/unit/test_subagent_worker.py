from __future__ import annotations

from astrbot.core.subagent.worker import SubagentWorker


def test_worker_error_backoff_grows_and_caps():
    worker = SubagentWorker(runtime=None, poll_interval=1.0)  # type: ignore[arg-type]

    assert worker._compute_error_backoff(1) == 1.0
    assert worker._compute_error_backoff(2) == 2.0
    assert worker._compute_error_backoff(3) == 4.0
    assert worker._compute_error_backoff(10) == 30.0
