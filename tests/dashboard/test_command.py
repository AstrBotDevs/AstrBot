"""Import smoke tests for the command dashboard route module.

Verifies that all public classes from ``command.py`` can be imported
without errors.
"""

# ---------------------------------------------------------------------------
# command.py -- CommandRoute and module-level helper
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.command import (
    CommandRoute,       # noqa: F401
    _get_command_payload,  # noqa: F401
)


def test_command_route_class():
    assert CommandRoute is not None


def test_get_command_payload_is_async_function():
    import inspect
    assert inspect.iscoroutinefunction(_get_command_payload)
