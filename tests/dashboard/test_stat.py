"""Import smoke test for astrbot.dashboard.routes.stat.

Verifies that the module can be imported and the main class (StatRoute)
is present and has the expected method signatures.
"""

import inspect

import pytest

from astrbot.dashboard.routes.stat import StatRoute


class TestStatRouteImports:
    """Smoke tests for the stat route module."""

    def test_stat_route_class_exists(self):
        assert StatRoute is not None
        assert inspect.isclass(StatRoute)

    def test_stat_route_has_init(self):
        sig = inspect.signature(StatRoute.__init__)
        params = list(sig.parameters.keys())
        for required_param in ("self", "context", "db_helper", "core_lifecycle"):
            assert required_param in params, (
                f"StatRoute.__init__ missing parameter: {required_param}"
            )

    def test_stat_route_methods_exist(self):
        expected_methods = [
            "get_stat",
            "get_provider_token_stats",
            "get_version",
            "get_start_time",
            "restart_core",
            "test_ghproxy_connection",
            "get_changelog",
            "list_changelog_versions",
            "get_first_notice",
            "get_storage_status",
            "cleanup_storage",
        ]
        for method_name in expected_methods:
            assert hasattr(StatRoute, method_name), (
                f"StatRoute missing method: {method_name}"
            )

    def test_stat_route_has_static_helper(self):
        assert hasattr(StatRoute, "_ensure_aware_utc")
        method = getattr(StatRoute, "_ensure_aware_utc")
        assert callable(method)

    def test_stat_route_has_running_time_helper(self):
        assert hasattr(StatRoute, "_get_running_time_components")
        method = getattr(StatRoute, "_get_running_time_components")
        assert callable(method)

    def test_stat_route_has_default_cred_check(self):
        assert hasattr(StatRoute, "is_default_cred")
        method = getattr(StatRoute, "is_default_cred")
        assert callable(method)
