"""Import smoke tests for plugin and tools route modules.

Verifies that all public classes, standalone functions, and exceptions
from ``plugin.py`` and ``tools.py`` can be imported without errors.
"""

# ---------------------------------------------------------------------------
# plugin.py — PluginRoute, RegistrySource and helpers
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.plugin import (
    PluginRoute,          # noqa: F401
    RegistrySource,       # noqa: F401
    PLUGIN_UPDATE_CONCURRENCY,  # noqa: F401
    PLUGIN_ROUTE_DEFINITIONS,   # noqa: F401
)


def test_plugin_route_class():
    assert PluginRoute is not None


def test_registry_source_dataclass():
    from dataclasses import fields

    assert fields(RegistrySource)


def test_plugin_update_concurrency_value():
    assert isinstance(PLUGIN_UPDATE_CONCURRENCY, int)


def test_plugin_route_definitions_is_list():
    assert isinstance(PLUGIN_ROUTE_DEFINITIONS, tuple)


# ---------------------------------------------------------------------------
# tools.py — ToolsRoute, EmptyMcpServersError, _extract_mcp_server_config
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.tools import (
    EmptyMcpServersError,    # noqa: F401
    ToolsRoute,              # noqa: F401
    DEFAULT_MCP_CONFIG,      # noqa: F401
    _extract_mcp_server_config,  # noqa: F401
)


def test_tools_route_class():
    assert ToolsRoute is not None


def test_empty_mcp_servers_error():
    assert issubclass(EmptyMcpServersError, ValueError)


def test_default_mcp_config():
    assert DEFAULT_MCP_CONFIG == {"mcpServers": {}}


def test_extract_mcp_server_config_is_callable():
    assert callable(_extract_mcp_server_config)
