"""Import smoke tests for the tools route module.

Verifies that the ``ToolsRoute`` class, ``EmptyMcpServersError``, and
``_extract_mcp_server_config`` from ``tools.py`` can be imported without
errors, and checks key method signatures.
"""

import inspect

from astrbot.dashboard.routes.tools import (
    EmptyMcpServersError,
    ToolsRoute,
    _extract_mcp_server_config,
)
from astrbot.dashboard.routes.route import Route


def test_tools_route_class():
    assert ToolsRoute is not None
    assert issubclass(ToolsRoute, Route)


def test_empty_mcp_servers_error():
    assert EmptyMcpServersError is not None
    assert issubclass(EmptyMcpServersError, ValueError)


def test_extract_mcp_server_config_is_function():
    assert callable(_extract_mcp_server_config)


def test_tools_route_init_signature():
    sig = inspect.signature(ToolsRoute.__init__)
    params = list(sig.parameters.keys())
    assert "self" in params
    assert "context" in params
    assert "core_lifecycle" in params


def test_tools_route_get_mcp_servers_signature():
    sig = inspect.signature(ToolsRoute.get_mcp_servers)
    params = list(sig.parameters.keys())
    assert "self" in params


def test_tools_route_add_mcp_server_signature():
    sig = inspect.signature(ToolsRoute.add_mcp_server)
    params = list(sig.parameters.keys())
    assert "self" in params


def test_tools_route_get_tool_list_signature():
    sig = inspect.signature(ToolsRoute.get_tool_list)
    params = list(sig.parameters.keys())
    assert "self" in params


def test_tools_route_toggle_tool_signature():
    sig = inspect.signature(ToolsRoute.toggle_tool)
    params = list(sig.parameters.keys())
    assert "self" in params
