"""Import smoke tests for the cron route module.

Verifies that the ``CronRoute`` class from ``cron.py`` can be imported without
errors.
"""

# ---------------------------------------------------------------------------
# cron.py — CronRoute
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.cron import (
    CronRoute,  # noqa: F401
)


def test_cron_route_class():
    assert CronRoute is not None
