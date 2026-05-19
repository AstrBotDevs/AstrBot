"""Import smoke tests for the log dashboard route module.

Verifies that all public classes and helper functions from ``log.py``
can be imported without errors.
"""

# ---------------------------------------------------------------------------
# log.py -- LogRoute and helper functions
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.log import (
    LogRoute,              # noqa: F401
    _format_log_sse,       # noqa: F401
    _coerce_log_timestamp,  # noqa: F401
)


def test_log_route_class():
    assert LogRoute is not None


def test_format_log_sse():
    log_entry = {"level": "INFO", "message": "hello"}
    ts = 1234567890.0
    result = _format_log_sse(log_entry, ts)
    assert result.startswith(f"id: {ts}\n")
    assert "hello" in result


def test_coerce_log_timestamp():
    assert _coerce_log_timestamp(1234567890) == 1234567890.0
    assert _coerce_log_timestamp("1234567890") == 1234567890.0
    assert _coerce_log_timestamp("invalid") is None
    assert _coerce_log_timestamp(None) is None
