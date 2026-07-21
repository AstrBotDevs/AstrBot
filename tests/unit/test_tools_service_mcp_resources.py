import base64
from enum import Enum
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.mcp_client import MCPResourcePaginationNotSupportedError
from astrbot.dashboard.services import tools_service as tools_service_module
from astrbot.dashboard.services.tools_service import ToolsService, ToolsServiceError


def _make_service(*, runtimes=None, config=None):
    tool_mgr = SimpleNamespace(
        mcp_server_runtime_view=runtimes or {},
        load_mcp_config=MagicMock(
            return_value=config or {"mcpServers": {"demo": {"active": True}}}
        ),
    )
    lifecycle = SimpleNamespace(provider_manager=SimpleNamespace(llm_tools=tool_mgr))
    return ToolsService(lifecycle)


def _make_client(*, supports_resources=True):
    return SimpleNamespace(
        supports_resources=supports_resources,
        tools=[],
        server_errlogs=[],
        list_resources=AsyncMock(),
        list_resource_templates=AsyncMock(),
        read_resource=AsyncMock(),
    )


class _AudienceRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"


@pytest.mark.asyncio
async def test_mcp_resource_operations_require_connected_server():
    service = _make_service()

    with pytest.raises(ToolsServiceError, match="demo is not connected"):
        await service.list_mcp_resources("demo")


@pytest.mark.asyncio
async def test_mcp_resource_operations_require_advertised_capability():
    client = _make_client(supports_resources=False)
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    with pytest.raises(ToolsServiceError, match="does not advertise resources"):
        await service.read_mcp_resource("demo", "file:///guide.md")

    client.read_resource.assert_not_awaited()


def test_mcp_server_list_reports_resource_capability():
    resource_client = _make_client()
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=resource_client)},
        config={
            "mcpServers": {
                "demo": {"active": True},
                "offline": {"active": True, "supports_resources": True},
            }
        },
    )

    servers = service.get_mcp_servers()

    assert servers[0]["supports_resources"] is True
    assert servers[1]["supports_resources"] is False


@pytest.mark.asyncio
async def test_list_mcp_resources_serializes_explicit_dto_and_cursor():
    client = _make_client()
    client.list_resources.return_value = SimpleNamespace(
        resources=[
            SimpleNamespace(
                uri="file:///guide.md",
                name="guide",
                title="Guide",
                description="Project guide",
                mimeType="text/markdown",
                size=42,
                annotations=SimpleNamespace(
                    audience=[_AudienceRole.USER, _AudienceRole.ASSISTANT],
                    priority=0.75,
                ),
                unexpected="not exposed",
            )
        ],
        nextCursor="page-2",
    )
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    result = await service.list_mcp_resources("demo", "page-1")

    assert result == {
        "resources": [
            {
                "uri": "file:///guide.md",
                "name": "guide",
                "title": "Guide",
                "description": "Project guide",
                "mime_type": "text/markdown",
                "size": 42,
                "annotations": {
                    "audience": ["user", "assistant"],
                    "priority": 0.75,
                },
            }
        ],
        "next_cursor": "page-2",
    }
    client.list_resources.assert_awaited_once_with("page-1")


@pytest.mark.asyncio
async def test_list_mcp_resource_templates_serializes_explicit_dto_and_cursor():
    client = _make_client()
    client.list_resource_templates.return_value = SimpleNamespace(
        resourceTemplates=[
            SimpleNamespace(
                uriTemplate="file:///docs/{name}",
                name="document",
                description="A document",
                mimeType="text/plain",
                annotations=None,
            )
        ],
        nextCursor=None,
    )
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    result = await service.list_mcp_resource_templates("demo", "page-1")

    assert result == {
        "resource_templates": [
            {
                "uri_template": "file:///docs/{name}",
                "name": "document",
                "title": None,
                "description": "A document",
                "mime_type": "text/plain",
                "annotations": None,
            }
        ],
        "next_cursor": None,
    }
    client.list_resource_templates.assert_awaited_once_with("page-1")


@pytest.mark.asyncio
async def test_read_mcp_resource_truncates_text_and_omits_blob_data():
    text = "é" * (128 * 1024 + 1)
    blob = base64.b64encode(b"binary-content").decode()
    client = _make_client()
    client.read_resource.return_value = SimpleNamespace(
        contents=[
            SimpleNamespace(
                uri="file:///large.txt",
                mimeType="text/plain",
                text=text,
            ),
            SimpleNamespace(
                uri="file:///image.png",
                mimeType="image/png",
                blob=blob,
                meta={"secret": "not exposed"},
            ),
        ]
    )
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    result = await service.read_mcp_resource("demo", "file:///large.txt")

    text_content, blob_content = result["contents"]
    assert text_content == {
        "type": "text",
        "uri": "file:///large.txt",
        "mime_type": "text/plain",
        "text": "é" * (128 * 1024),
        "size": 256 * 1024 + 2,
        "truncated": True,
    }
    assert blob_content == {
        "type": "blob",
        "uri": "file:///image.png",
        "mime_type": "image/png",
        "size": len(b"binary-content"),
    }
    assert "blob" not in blob_content
    assert "meta" not in blob_content
    client.read_resource.assert_awaited_once_with("file:///large.txt")


@pytest.mark.asyncio
async def test_read_mcp_resource_bounds_combined_text_preview():
    client = _make_client()
    client.read_resource.return_value = SimpleNamespace(
        contents=[
            SimpleNamespace(
                uri="file:///first.txt",
                mimeType="text/plain",
                text="a" * (200 * 1024),
            ),
            SimpleNamespace(
                uri="file:///second.txt",
                mimeType="text/plain",
                text="b" * (100 * 1024),
            ),
        ]
    )
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    result = await service.read_mcp_resource("demo", "file:///bundle")

    first, second = result["contents"]
    assert len(first["text"].encode("utf-8")) == 200 * 1024
    assert first["truncated"] is False
    assert len(second["text"].encode("utf-8")) == 56 * 1024
    assert second["size"] == 100 * 1024
    assert second["truncated"] is True


@pytest.mark.asyncio
async def test_mcp_resource_errors_do_not_expose_server_payloads(monkeypatch):
    client = _make_client()
    client.read_resource.side_effect = ValueError("SECRET_RESOURCE_PAYLOAD")
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )
    log_error = MagicMock()
    monkeypatch.setattr(tools_service_module.logger, "error", log_error)

    with pytest.raises(
        ToolsServiceError,
        match="^Failed to read resource for MCP server demo$",
    ) as exc_info:
        await service.read_mcp_resource("demo", "file:///secret")

    assert "SECRET_RESOURCE_PAYLOAD" not in str(exc_info.value)
    assert "SECRET_RESOURCE_PAYLOAD" not in str(log_error.call_args)


@pytest.mark.asyncio
async def test_mcp_resource_pagination_compatibility_error_remains_actionable():
    client = _make_client()
    client.list_resources.side_effect = MCPResourcePaginationNotSupportedError(
        "The installed MCP SDK does not support resource pagination."
    )
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    with pytest.raises(ToolsServiceError, match="does not support resource pagination"):
        await service.list_mcp_resources("demo", "next-page")
