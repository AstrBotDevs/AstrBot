"""Import smoke test for astrbot.dashboard.routes.plugin.

Verifies that the module can be imported and the main class (PluginRoute)
is present and has the expected method signatures.
"""

import inspect

import pytest

from astrbot.dashboard.routes.plugin import (
    PLUGIN_ROUTE_DEFINITIONS,
    PluginRoute,
    RegistrySource,
)


class TestPluginRouteImports:
    """Smoke tests for the plugin route module."""

    def test_plugin_route_class_exists(self):
        assert PluginRoute is not None
        assert inspect.isclass(PluginRoute)

    def test_plugin_route_definitions_exist(self):
        assert isinstance(PLUGIN_ROUTE_DEFINITIONS, tuple)
        assert len(PLUGIN_ROUTE_DEFINITIONS) > 0

    def test_registry_source_dataclass_exists(self):
        assert RegistrySource is not None
        assert hasattr(RegistrySource, "urls")
        assert hasattr(RegistrySource, "cache_file")
        assert hasattr(RegistrySource, "md5_url")

    def test_plugin_route_methods_exist(self):
        expected_handlers = {
            name for _, _, name, _ in PLUGIN_ROUTE_DEFINITIONS
        }
        for handler_name in expected_handlers:
            assert hasattr(PluginRoute, handler_name), (
                f"PluginRoute missing handler: {handler_name}"
            )

    def test_plugin_route_has_init(self):
        sig = inspect.signature(PluginRoute.__init__)
        params = list(sig.parameters.keys())
        for required_param in ("self", "context", "core_lifecycle", "plugin_manager"):
            assert required_param in params, (
                f"PluginRoute.__init__ missing parameter: {required_param}"
            )
