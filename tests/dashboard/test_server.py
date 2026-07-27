"""Import smoke test for astrbot.dashboard.server.

Verifies that the module can be imported and the main class
(AstrBotDashboard) is present with expected attributes and methods.
"""

import inspect

import pytest

from astrbot.dashboard.server import (
    AstrBotDashboard,
    AstrBotJSONProvider,
    _expand_env_placeholders,
    _parse_env_bool,
    _resolve_dashboard_value,
)


class TestAstrBotDashboardImports:
    """Smoke tests for the dashboard server module."""

    def test_astrbot_dashboard_class_exists(self):
        assert AstrBotDashboard is not None
        assert inspect.isclass(AstrBotDashboard)

    def test_astrbot_dashboard_has_init(self):
        sig = inspect.signature(AstrBotDashboard.__init__)
        params = list(sig.parameters.keys())
        for required_param in ("self", "core_lifecycle", "db", "shutdown_event"):
            assert required_param in params, (
                f"AstrBotDashboard.__init__ missing parameter: {required_param}"
            )

    def test_astrbot_dashboard_methods_exist(self):
        expected_methods = [
            "run",
            "auth_middleware",
            "check_port_in_use",
            "get_process_using_port",
            "srv_plug_route",
            "guarded_srv_plug_route",
            "shutdown_trigger",
        ]
        for method_name in expected_methods:
            assert hasattr(AstrBotDashboard, method_name), (
                f"AstrBotDashboard missing method: {method_name}"
            )

    def test_astrbot_dashboard_static_helpers(self):
        assert hasattr(AstrBotDashboard, "_resolve_dashboard_ssl_config")
        assert hasattr(AstrBotDashboard, "_unauthorized")
        assert hasattr(AstrBotDashboard, "_extract_raw_api_key")
        assert hasattr(AstrBotDashboard, "_get_required_open_api_scope")
        assert hasattr(AstrBotDashboard, "_build_bind")
        assert hasattr(AstrBotDashboard, "_print_access_urls")

    def test_astrbot_dashboard_class_attributes(self):
        assert hasattr(AstrBotDashboard, "ALLOWED_ENDPOINT_PREFIXES")
        assert hasattr(AstrBotDashboard, "RUNTIME_BYPASS_ENDPOINT_PREFIXES")
        assert hasattr(AstrBotDashboard, "RUNTIME_FAILED_RECOVERY_ENDPOINT_PREFIXES")

    def test_json_provider_exists(self):
        assert AstrBotJSONProvider is not None
        assert inspect.isclass(AstrBotJSONProvider)

    def test_module_level_functions_exist(self):
        assert callable(_parse_env_bool)
        assert callable(_expand_env_placeholders)
        assert callable(_resolve_dashboard_value)
