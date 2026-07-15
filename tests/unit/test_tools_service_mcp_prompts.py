import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.mcp_client import MCPPromptPaginationNotSupportedError
from astrbot.dashboard.services import tools_service as tools_service_module
from astrbot.dashboard.services.tools_service import ToolsService, ToolsServiceError


def _make_service(*, runtimes=None):
    tool_mgr = SimpleNamespace(
        mcp_server_runtime_view=runtimes or {},
    )
    lifecycle = SimpleNamespace(provider_manager=SimpleNamespace(llm_tools=tool_mgr))
    return ToolsService(lifecycle)


def _make_client(*, supports_prompts=True):
    return SimpleNamespace(
        supports_prompts=supports_prompts,
        list_prompts=AsyncMock(),
        get_prompt=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_mcp_prompt_catalog_requires_connected_server():
    service = _make_service()

    with pytest.raises(ToolsServiceError, match="demo is not connected"):
        await service.list_mcp_prompts("demo")


@pytest.mark.asyncio
async def test_mcp_prompt_catalog_requires_advertised_capability():
    client = _make_client(supports_prompts=False)
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    with pytest.raises(ToolsServiceError, match="does not advertise prompts"):
        await service.list_mcp_prompts("demo")

    client.list_prompts.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_mcp_prompts_serializes_explicit_metadata_and_opaque_cursor():
    client = _make_client()
    client.list_prompts.return_value = SimpleNamespace(
        prompts=[
            SimpleNamespace(
                name="review",
                title="Review code",
                description="Review a change",
                arguments=[
                    SimpleNamespace(
                        name="language",
                        description="Programming language",
                        required=True,
                        unexpected="not exposed",
                    ),
                    SimpleNamespace(
                        name="focus",
                        description=None,
                        required=None,
                    ),
                ],
                icons=[{"src": "https://example.invalid/icon.png"}],
                _meta={"secret": "not exposed"},
                meta={"secret": "not exposed"},
                unexpected="not exposed",
            ),
            SimpleNamespace(
                name="summarize",
                description=None,
                arguments=None,
            ),
        ],
        nextCursor="",
        _meta={"secret": "not exposed"},
        meta={"secret": "not exposed"},
    )
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    result = await service.list_mcp_prompts("demo", "")

    assert result == {
        "prompts": [
            {
                "name": "review",
                "title": "Review code",
                "description": "Review a change",
                "arguments": [
                    {
                        "name": "language",
                        "description": "Programming language",
                        "required": True,
                    },
                    {
                        "name": "focus",
                        "description": None,
                        "required": False,
                    },
                ],
            },
            {
                "name": "summarize",
                "title": None,
                "description": None,
                "arguments": [],
            },
        ],
        "next_cursor": "",
    }
    client.list_prompts.assert_awaited_once_with("")
    client.get_prompt.assert_not_awaited()


@pytest.mark.asyncio
async def test_mcp_prompt_errors_do_not_expose_server_payloads(monkeypatch):
    client = _make_client()
    client.list_prompts.side_effect = ValueError("SECRET_PROMPT_PAYLOAD")
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )
    log_error = MagicMock()
    monkeypatch.setattr(tools_service_module.logger, "error", log_error)

    with pytest.raises(
        ToolsServiceError,
        match="^Failed to list prompts for MCP server demo$",
    ) as exc_info:
        await service.list_mcp_prompts("demo")

    assert "SECRET_PROMPT_PAYLOAD" not in str(exc_info.value)
    assert "SECRET_PROMPT_PAYLOAD" not in str(log_error.call_args)


@pytest.mark.asyncio
async def test_mcp_prompt_pagination_compatibility_error_remains_actionable():
    client = _make_client()
    client.list_prompts.side_effect = MCPPromptPaginationNotSupportedError(
        "The installed MCP SDK does not support prompt pagination."
    )
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    with pytest.raises(ToolsServiceError, match="does not support prompt pagination"):
        await service.list_mcp_prompts("demo", "next-page")


@pytest.mark.asyncio
async def test_mcp_prompt_catalog_propagates_cancellation(monkeypatch):
    client = _make_client()
    client.list_prompts.side_effect = asyncio.CancelledError()
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )
    log_error = MagicMock()
    monkeypatch.setattr(tools_service_module.logger, "error", log_error)

    with pytest.raises(asyncio.CancelledError):
        await service.list_mcp_prompts("demo")

    log_error.assert_not_called()
