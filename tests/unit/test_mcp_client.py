from __future__ import annotations

import importlib.util
import logging
import sys
import types
from pathlib import Path
from typing import Generic, TypeVar
from unittest.mock import AsyncMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_CLIENT_MODULE_PATH = REPO_ROOT / "astrbot/core/agent/mcp_client.py"


def load_mcp_client_module():
    package_names = [
        "astrbot",
        "astrbot.core",
        "astrbot.core.agent",
        "astrbot.core.utils",
    ]
    for name in package_names:
        if name not in sys.modules:
            module = types.ModuleType(name)
            module.__path__ = []
            sys.modules[name] = module

    astrbot_module = sys.modules["astrbot"]
    astrbot_module.logger = logging.getLogger("astrbot-test")

    log_pipe_module = types.ModuleType("astrbot.core.utils.log_pipe")
    log_pipe_module.LogPipe = type("LogPipe", (), {})
    sys.modules[log_pipe_module.__name__] = log_pipe_module

    run_context_module = types.ModuleType("astrbot.core.agent.run_context")
    run_context_module.TContext = TypeVar("TContext")

    class ContextWrapper(Generic[run_context_module.TContext]):
        pass

    run_context_module.ContextWrapper = ContextWrapper
    sys.modules[run_context_module.__name__] = run_context_module

    tool_module = types.ModuleType("astrbot.core.agent.tool")
    tool_module.FunctionTool = type("FunctionTool", (), {})
    sys.modules[tool_module.__name__] = tool_module

    anyio_module = types.ModuleType("anyio")
    anyio_module.ClosedResourceError = type("ClosedResourceError", (Exception,), {})
    sys.modules["anyio"] = anyio_module

    mcp_module = types.ModuleType("mcp")
    mcp_module.Tool = type("Tool", (), {})
    mcp_module.ClientSession = type("ClientSession", (), {})
    mcp_module.ListToolsResult = type("ListToolsResult", (), {})
    mcp_module.StdioServerParameters = type("StdioServerParameters", (), {})
    mcp_module.stdio_client = lambda *args, **kwargs: None
    mcp_module.types = types.SimpleNamespace(
        LoggingMessageNotificationParams=type(
            "LoggingMessageNotificationParams", (), {}
        ),
        CallToolResult=type("CallToolResult", (), {}),
    )
    sys.modules["mcp"] = mcp_module

    mcp_client_module = types.ModuleType("mcp.client")
    sys.modules[mcp_client_module.__name__] = mcp_client_module

    mcp_client_sse_module = types.ModuleType("mcp.client.sse")
    mcp_client_sse_module.sse_client = lambda *args, **kwargs: None
    sys.modules[mcp_client_sse_module.__name__] = mcp_client_sse_module

    mcp_client_streamable_http_module = types.ModuleType(
        "mcp.client.streamable_http"
    )
    mcp_client_streamable_http_module.streamablehttp_client = (
        lambda *args, **kwargs: None
    )
    sys.modules[mcp_client_streamable_http_module.__name__] = (
        mcp_client_streamable_http_module
    )

    spec = importlib.util.spec_from_file_location(
        "astrbot.core.agent.mcp_client", MCP_CLIENT_MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sanitize_mcp_arguments_removes_nested_empty_collections():
    mcp_client_module = load_mcp_client_module()

    sanitized = mcp_client_module._sanitize_mcp_arguments(
        {
            "query": "hello",
            "filters": {"tags": [], "scope": {}},
            "metadata": {"owner": "", "visibility": None},
        }
    )

    assert sanitized == {"query": "hello"}


@pytest.mark.asyncio
async def test_call_tool_with_reconnect_falls_back_to_empty_top_level_arguments():
    mcp_client_module = load_mcp_client_module()

    client = mcp_client_module.MCPClient()
    client.session = types.SimpleNamespace(call_tool=AsyncMock(return_value="ok"))

    result = await client.call_tool_with_reconnect(
        tool_name="search",
        arguments={"filters": {}, "query": ""},
        read_timeout_seconds=mcp_client_module.timedelta(seconds=1),
    )

    assert result == "ok"
    client.session.call_tool.assert_awaited_once_with(
        name="search",
        arguments={},
        read_timeout_seconds=mcp_client_module.timedelta(seconds=1),
    )
