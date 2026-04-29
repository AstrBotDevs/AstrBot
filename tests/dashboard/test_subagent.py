"""Import smoke tests for the subagent dashboard route module.

Verifies that all public classes from ``subagent.py`` can be imported
without errors.
"""

# ---------------------------------------------------------------------------
# subagent.py -- SubAgentRoute
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.subagent import (
    SubAgentRoute,  # noqa: F401
)


def test_subagent_route_class():
    assert SubAgentRoute is not None
