"""Import smoke tests for the auth dashboard route module.

Verifies that all public classes from ``auth.py`` can be imported
without errors.
"""

# ---------------------------------------------------------------------------
# auth.py -- AuthRoute
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.auth import (
    AuthRoute,  # noqa: F401
)


def test_auth_route_class():
    assert AuthRoute is not None
