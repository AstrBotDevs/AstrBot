import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

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
        read_resource=AsyncMock(),
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


@pytest.mark.asyncio
async def test_mcp_prompt_preview_requires_connected_server():
    service = _make_service()

    with pytest.raises(ToolsServiceError, match="demo is not connected"):
        await service.preview_mcp_prompt("demo", "review")


@pytest.mark.asyncio
async def test_mcp_prompt_preview_requires_advertised_capability():
    client = _make_client(supports_prompts=False)
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    with pytest.raises(ToolsServiceError, match="does not advertise prompts"):
        await service.preview_mcp_prompt("demo", "review")

    client.get_prompt.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [None, {}, {"language": "Python", "focus": ""}])
async def test_mcp_prompt_preview_forwards_arguments_exactly(arguments):
    client = _make_client()
    client.get_prompt.return_value = SimpleNamespace(messages=[])
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    result = await service.preview_mcp_prompt("demo", "review", arguments)

    assert result == {
        "messages": [],
        "total_messages": 0,
        "messages_truncated": False,
        "text_truncated": False,
    }
    client.get_prompt.assert_awaited_once_with("review", arguments)
    client.list_prompts.assert_not_awaited()
    client.read_resource.assert_not_awaited()


@pytest.mark.asyncio
async def test_mcp_prompt_preview_serializes_explicit_content_allowlist():
    image_data = base64.b64encode(b"f").decode()
    audio_data = base64.b64encode(b"fo").decode()
    blob_data = base64.b64encode(b"foo").decode()
    client = _make_client()
    client.get_prompt.return_value = SimpleNamespace(
        description="not exposed",
        messages=[
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(
                    type="text",
                    text="Review this",
                    annotations={"audience": ["assistant"]},
                    _meta={"secret": "not exposed"},
                    meta={"secret": "not exposed"},
                    unexpected="not exposed",
                ),
            ),
            SimpleNamespace(
                role="assistant",
                content=SimpleNamespace(
                    type="image",
                    data=image_data,
                    mimeType="image/png",
                    annotations={"priority": 1},
                    _meta={"secret": "not exposed"},
                ),
            ),
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(
                    type="audio",
                    data=audio_data,
                    mimeType="audio/wav",
                    meta={"secret": "not exposed"},
                ),
            ),
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(
                    type="resource",
                    resource=SimpleNamespace(
                        uri="file:///guide.md",
                        mimeType="text/markdown",
                        text="Guide text",
                        _meta={"secret": "not exposed"},
                    ),
                ),
            ),
            SimpleNamespace(
                role="assistant",
                content=SimpleNamespace(
                    type="resource",
                    resource=SimpleNamespace(
                        uri="file:///image.png",
                        mimeType="image/png",
                        blob=blob_data,
                        meta={"secret": "not exposed"},
                    ),
                ),
            ),
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(
                    type="resource_link",
                    uri="file:///details.md",
                    name="details",
                    title="not exposed",
                    description="not exposed",
                    mimeType="text/markdown",
                    size=42,
                    icons=[{"src": "https://example.invalid/icon.png"}],
                    annotations={"audience": ["user"]},
                    _meta={"secret": "not exposed"},
                    unexpected="not exposed",
                ),
            ),
        ],
        _meta={"secret": "not exposed"},
        meta={"secret": "not exposed"},
        unexpected="not exposed",
    )
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    result = await service.preview_mcp_prompt(
        "demo",
        "review",
        {"language": "Python"},
    )

    assert result == {
        "messages": [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": "Review this",
                    "size": len(b"Review this"),
                    "truncated": False,
                },
            },
            {
                "role": "assistant",
                "content": {
                    "type": "image",
                    "mime_type": "image/png",
                    "size": 1,
                },
            },
            {
                "role": "user",
                "content": {
                    "type": "audio",
                    "mime_type": "audio/wav",
                    "size": 2,
                },
            },
            {
                "role": "user",
                "content": {
                    "type": "resource",
                    "resource": {
                        "type": "text",
                        "uri": "file:///guide.md",
                        "mime_type": "text/markdown",
                        "text": "Guide text",
                        "size": len(b"Guide text"),
                        "truncated": False,
                    },
                },
            },
            {
                "role": "assistant",
                "content": {
                    "type": "resource",
                    "resource": {
                        "type": "blob",
                        "uri": "file:///image.png",
                        "mime_type": "image/png",
                        "size": 3,
                    },
                },
            },
            {
                "role": "user",
                "content": {
                    "type": "resource_link",
                    "uri": "file:///details.md",
                    "name": "details",
                    "mime_type": "text/markdown",
                    "size": 42,
                },
            },
        ],
        "total_messages": 6,
        "messages_truncated": False,
        "text_truncated": False,
    }
    client.get_prompt.assert_awaited_once_with(
        "review",
        {"language": "Python"},
    )
    client.read_resource.assert_not_awaited()


@pytest.mark.asyncio
async def test_mcp_prompt_preview_accepts_empty_binary_content():
    client = _make_client()
    client.get_prompt.return_value = SimpleNamespace(
        messages=[
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(
                    type="image",
                    data="",
                    mimeType="image/png",
                ),
            )
        ]
    )
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    result = await service.preview_mcp_prompt("demo", "review")

    assert result["messages"][0]["content"] == {
        "type": "image",
        "mime_type": "image/png",
        "size": 0,
    }


@pytest.mark.asyncio
async def test_mcp_prompt_preview_bounds_combined_utf8_text():
    first_text = "a" * (256 * 1024 - 1)
    client = _make_client()
    client.get_prompt.return_value = SimpleNamespace(
        messages=[
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(type="text", text=first_text),
            ),
            SimpleNamespace(
                role="assistant",
                content=SimpleNamespace(
                    type="resource",
                    resource=SimpleNamespace(
                        uri="file:///second.txt",
                        mimeType="text/plain",
                        text="é",
                    ),
                ),
            ),
        ]
    )
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    result = await service.preview_mcp_prompt("demo", "review")

    first, second = result["messages"]
    assert first["content"] == {
        "type": "text",
        "text": first_text,
        "size": 256 * 1024 - 1,
        "truncated": False,
    }
    assert second["content"]["resource"] == {
        "type": "text",
        "uri": "file:///second.txt",
        "mime_type": "text/plain",
        "text": "",
        "size": 2,
        "truncated": True,
    }
    assert result["text_truncated"] is True


@pytest.mark.asyncio
async def test_mcp_prompt_preview_bounds_message_count():
    client = _make_client()
    client.get_prompt.return_value = SimpleNamespace(
        messages=[
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(type="text", text=str(index)),
            )
            for index in range(101)
        ]
    )
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    result = await service.preview_mcp_prompt("demo", "review")

    assert len(result["messages"]) == 100
    assert result["messages"][0]["content"]["text"] == "0"
    assert result["messages"][-1]["content"]["text"] == "99"
    assert result["total_messages"] == 101
    assert result["messages_truncated"] is True
    assert result["text_truncated"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "error"),
    [
        (
            SimpleNamespace(
                role="system",
                content=SimpleNamespace(type="text", text="secret"),
            ),
            "unsupported prompt message role",
        ),
        (
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(
                    type="future-content",
                    payload="SECRET_PROMPT_PAYLOAD",
                ),
            ),
            "unsupported prompt content type",
        ),
        (
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(
                    type="resource",
                    resource=SimpleNamespace(
                        uri="file:///invalid",
                        text="text",
                        blob="SECRET_PROMPT_PAYLOAD",
                    ),
                ),
            ),
            "invalid embedded resource",
        ),
        (
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(
                    type="image",
                    data="!",
                    mimeType="image/png",
                ),
            ),
            "invalid prompt binary content",
        ),
        (
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(
                    type="resource",
                    resource=SimpleNamespace(
                        uri="file:///invalid.bin",
                        mimeType="application/octet-stream",
                        blob="A===",
                    ),
                ),
            ),
            "invalid prompt binary content",
        ),
        (
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(
                    type="resource",
                    resource=SimpleNamespace(
                        uri="file:///invalid.txt",
                        mimeType={"secret": "SECRET_PROMPT_PAYLOAD"},
                        text="text",
                    ),
                ),
            ),
            "invalid embedded resource",
        ),
        (
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(
                    type="resource_link",
                    uri="file:///invalid.txt",
                    name="invalid",
                    mimeType="text/plain",
                    size=-1,
                ),
            ),
            "invalid resource link content",
        ),
    ],
)
async def test_mcp_prompt_preview_fails_closed_for_invalid_shapes(message, error):
    client = _make_client()
    client.get_prompt.return_value = SimpleNamespace(messages=[message])
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    with pytest.raises(ToolsServiceError, match=error) as exc_info:
        await service.preview_mcp_prompt("demo", "review")

    assert "SECRET_PROMPT_PAYLOAD" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_mcp_prompt_preview_bounds_combined_metadata():
    client = _make_client()
    client.get_prompt.return_value = SimpleNamespace(
        messages=[
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(
                    type="resource_link",
                    uri="é" * (32 * 1024),
                    name="",
                    mimeType=None,
                    size=None,
                ),
            ),
            SimpleNamespace(
                role="assistant",
                content=SimpleNamespace(
                    type="image",
                    data="",
                    mimeType="x",
                ),
            ),
        ]
    )
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )

    with pytest.raises(ToolsServiceError, match="oversized prompt metadata"):
        await service.preview_mcp_prompt("demo", "review")


@pytest.mark.asyncio
async def test_mcp_prompt_preview_maps_invalid_params_without_leaking(monkeypatch):
    client = _make_client()
    client.get_prompt.side_effect = McpError(
        ErrorData(
            code=-32602,
            message="SECRET_PROMPT_PAYLOAD",
            data={"secret": "SECRET_ARGUMENT"},
        )
    )
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )
    log_error = MagicMock()
    monkeypatch.setattr(tools_service_module.logger, "error", log_error)

    with pytest.raises(
        ToolsServiceError,
        match="rejected the prompt name or arguments",
    ) as exc_info:
        await service.preview_mcp_prompt("demo", "review", {"secret": "value"})

    assert "SECRET" not in str(exc_info.value)
    log_error.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_prompt_preview_sanitizes_server_errors(monkeypatch):
    client = _make_client()
    client.get_prompt.side_effect = ValueError("SECRET_PROMPT_PAYLOAD")
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )
    log_error = MagicMock()
    monkeypatch.setattr(tools_service_module.logger, "error", log_error)

    with pytest.raises(
        ToolsServiceError,
        match="^Failed to preview prompt for MCP server demo$",
    ) as exc_info:
        await service.preview_mcp_prompt("demo", "review")

    assert "SECRET_PROMPT_PAYLOAD" not in str(exc_info.value)
    assert "SECRET_PROMPT_PAYLOAD" not in str(log_error.call_args)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [asyncio.CancelledError(), MemoryError()])
async def test_mcp_prompt_preview_propagates_control_flow_errors(
    error,
    monkeypatch,
):
    client = _make_client()
    client.get_prompt.side_effect = error
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )
    log_error = MagicMock()
    monkeypatch.setattr(tools_service_module.logger, "error", log_error)

    with pytest.raises(type(error)):
        await service.preview_mcp_prompt("demo", "review")

    log_error.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_prompt_preview_propagates_serializer_memory_error(monkeypatch):
    client = _make_client()
    client.get_prompt.return_value = SimpleNamespace(
        messages=[
            SimpleNamespace(
                role="user",
                content=SimpleNamespace(type="text", text="review"),
            )
        ]
    )
    service = _make_service(
        runtimes={"demo": SimpleNamespace(client=client)},
    )
    log_error = MagicMock()
    monkeypatch.setattr(tools_service_module.logger, "error", log_error)
    monkeypatch.setattr(
        tools_service_module,
        "_serialize_mcp_prompt_content",
        MagicMock(side_effect=MemoryError()),
    )

    with pytest.raises(MemoryError):
        await service.preview_mcp_prompt("demo", "review")

    log_error.assert_not_called()
