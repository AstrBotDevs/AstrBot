"""Import smoke tests for config and platform route modules.

Verifies that all public classes and key standalone functions from
``config.py`` and ``platform.py`` can be imported without errors.
"""

# ---------------------------------------------------------------------------
# config.py — ConfigRoute and standalone helpers
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.config import (
    ConfigRoute,          # noqa: F401
    save_config,          # noqa: F401
    validate_config,      # noqa: F401
    try_cast,             # noqa: F401
    _expect_type,         # noqa: F401
    _validate_template_list,  # noqa: F401
    _log_computer_config_changes,  # noqa: F401
)


def test_config_route_class():
    assert ConfigRoute is not None


def test_save_config_is_callable():
    assert callable(save_config)


def test_validate_config_is_callable():
    assert callable(validate_config)


def test_try_cast_is_callable():
    assert callable(try_cast)


def test_expect_type_is_callable():
    assert callable(_expect_type)


def test_validate_template_list_is_callable():
    assert callable(_validate_template_list)


def test_log_computer_config_changes_is_callable():
    assert callable(_log_computer_config_changes)


# ---------------------------------------------------------------------------
# platform.py — PlatformRoute
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.platform import (
    PlatformRoute,  # noqa: F401
)


def test_platform_route_class():
    assert PlatformRoute is not None
