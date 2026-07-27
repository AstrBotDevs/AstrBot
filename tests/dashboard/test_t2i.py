"""Import smoke tests for the T2I (text-to-image) route module.

Verifies that the ``T2iRoute`` class from ``t2i.py`` can be imported without
errors.
"""

# ---------------------------------------------------------------------------
# t2i.py — T2iRoute
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.t2i import (
    T2iRoute,  # noqa: F401
)


def test_t2i_route_class():
    assert T2iRoute is not None
