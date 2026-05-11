"""Import smoke tests for auth and API key route modules.

Verifies that all public classes and key constants from ``auth.py``
and ``api_key.py`` can be imported without errors.
"""

# ---------------------------------------------------------------------------
# auth.py — AuthRoute
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.auth import (
    AuthRoute,  # noqa: F401
)


def test_auth_route_class():
    assert AuthRoute is not None


# ---------------------------------------------------------------------------
# api_key.py — ApiKeyRoute and key constants
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.api_key import (
    ALL_OPEN_API_SCOPES,  # noqa: F401
    ApiKeyRoute,          # noqa: F401
)


def test_api_key_route_class():
    assert ApiKeyRoute is not None


def test_all_open_api_scopes():
    assert "chat" in ALL_OPEN_API_SCOPES
    assert "config" in ALL_OPEN_API_SCOPES
    assert "file" in ALL_OPEN_API_SCOPES
    assert "im" in ALL_OPEN_API_SCOPES
