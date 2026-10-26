import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mcp.types import ReadResourceResult, TextResourceContents, Tool

from astrbot.core.agent.mcp_client import MCPTool
from astrbot.dashboard.services.chat_service import (
    BotMessageAccumulator,
    ChatServiceError,
)
from astrbot.dashboard.services.mcp_app_service import read_chat_mcp_app


@pytest.fixture
def app_context():
    uri = "ui://picker/index.html"
    client = SimpleNamespace(
        active=True,
        session=SimpleNamespace(
            read_resource=AsyncMock(
                return_value=ReadResourceResult(
                    contents=[
                        TextResourceContents(
                            uri=uri,
                            mimeType="text/html;profile=mcp-app",
                            text="<h1>Picker</h1>",
                        )
                    ]
                )
            )
        ),
    )
    tool = MCPTool(
        Tool(
            name="picker",
            inputSchema={"type": "object"},
            _meta={"ui": {"resourceUri": uri}},
        ),
        client,
        "photos",
    )
    app = {
        "server": "photos",
        "uri": uri,
        "result": {"content": [], "structuredContent": {"ids": [1, 2]}},
    }
    call = {"id": "call", "name": "picker", "args": {"query": "forest"}, "mcp_app": app}
    record = SimpleNamespace(
        user_id="session",
        platform_id="webchat",
        content={
            "type": "bot",
            "message": [{"type": "tool_call", "tool_calls": [call]}],
        },
    )
    service = SimpleNamespace(
        db=SimpleNamespace(
            get_platform_session_by_id=AsyncMock(
                return_value=SimpleNamespace(creator="alice", platform_id="webchat")
            ),
            get_platform_message_history_by_id=AsyncMock(return_value=record),
        ),
        core_lifecycle=SimpleNamespace(
            provider_manager=SimpleNamespace(
                llm_tools=SimpleNamespace(func_list=[tool])
            )
        ),
    )
    return service, tool, record, call


@pytest.mark.asyncio
async def test_reads_declared_resource_and_preserves_structured_data(app_context):
    service, tool, _, _ = app_context
    data = await read_chat_mcp_app(service, "alice", "session", "message", "call")
    assert data["html"] == "<h1>Picker</h1>"
    assert data["arguments"] == {"query": "forest"}
    assert data["result"]["structuredContent"]["ids"] == [1, 2]
    tool.mcp_client.session.read_resource.assert_awaited_once_with(
        "ui://picker/index.html"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "owner",
        "session",
        "platform",
        "user_message",
        "tool",
        "server",
        "uri",
        "disabled",
        "disconnected",
        "missing_call",
    ],
)
async def test_rejects_unrelated_or_unavailable_apps(app_context, mutation):
    service, tool, record, call = app_context
    if mutation == "owner":
        service.db.get_platform_session_by_id.return_value.creator = "bob"
    if mutation == "session":
        record.user_id = "other"
    if mutation == "platform":
        record.platform_id = "other"
    if mutation == "user_message":
        record.content["type"] = "user"
    if mutation == "tool":
        call["name"] = "other"
    if mutation == "server":
        call["mcp_app"]["server"] = "other"
    if mutation == "uri":
        call["mcp_app"]["uri"] = "https://attacker.invalid/"
    if mutation == "disabled":
        tool.active = False
    if mutation == "disconnected":
        tool.mcp_client.active = False
    if mutation == "missing_call":
        call["id"] = "other"
    with pytest.raises(ChatServiceError):
        await read_chat_mcp_app(service, "alice", "session", "message", "call")
    tool.mcp_client.session.read_resource.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("mimeType", "text/html"),
        ("uri", "ui://other/app"),
        ("text", "x" * (1024 * 1024 + 1)),
    ],
    ids=["mime", "uri", "oversized"],
)
async def test_rejects_wrong_resource_type_identity_and_size(app_context, field, value):
    service, tool, _, _ = app_context
    content = tool.mcp_client.session.read_resource.return_value.contents[0]
    setattr(content, field, value)
    with pytest.raises(ChatServiceError):
        await read_chat_mcp_app(service, "alice", "session", "message", "call")


@pytest.mark.asyncio
async def test_read_failure_has_no_server_details(app_context):
    service, tool, _, _ = app_context
    tool.mcp_client.session.read_resource.side_effect = RuntimeError("secret-token")
    with pytest.raises(ChatServiceError, match="Could not read") as exc:
        await read_chat_mcp_app(service, "alice", "session", "message", "call")
    assert "secret-token" not in str(exc.value)


@pytest.mark.parametrize(
    "meta,expected",
    [
        ({}, None),
        ({"ui": {"resourceUri": "https://other"}}, None),
        ({"ui/resourceUri": "ui://legacy/app"}, "ui://legacy/app"),
        ({"ui": "bad"}, None),
    ],
)
def test_ui_metadata_validation(meta, expected):
    tool = MCPTool(Tool(name="picker", inputSchema={}, _meta=meta), None, "photos")
    assert tool.ui_resource_uri == expected


def test_history_keeps_app_data_outside_plain_tool_result(app_context):
    _, _, _, call = app_context
    accumulator = BotMessageAccumulator()
    accumulator._store_tool_call(json.dumps({"id": "call", "name": "picker"}))
    accumulator._store_tool_call_result(
        json.dumps({"id": "call", "result": "Visible text", "mcp_app": call["mcp_app"]})
    )
    stored = accumulator.parts[0]["tool_calls"][0]
    assert stored["result"] == "Visible text"
    assert stored["mcp_app"] == call["mcp_app"]
