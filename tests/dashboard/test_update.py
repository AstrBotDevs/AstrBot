"""Import smoke tests for the update dashboard route module.

Verifies that all public classes and key constants from ``update.py``
can be imported without errors.
"""

# ---------------------------------------------------------------------------
# update.py -- UpdateRoute and CLEAR_SITE_DATA_HEADERS
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.update import (
    CLEAR_SITE_DATA_HEADERS,  # noqa: F401
    UpdateRoute,              # noqa: F401
)


def test_update_route_class():
    assert UpdateRoute is not None


def test_clear_site_data_headers():
    assert isinstance(CLEAR_SITE_DATA_HEADERS, dict)
    assert CLEAR_SITE_DATA_HEADERS.get("Clear-Site-Data") == '"cache"'
