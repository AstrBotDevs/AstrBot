import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mcp.types import ReadResourceResult, TextResourceContents, Tool

from astrbot.core.agent.mcp_app_registry import McpAppRegistry, mcp_apps
from astrbot.core.agent.mcp_client import MCPTool
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.webchat.webchat_event import WebChatMessageEvent
from astrbot.dashboard.services.chat_service import (
    BotMessageAccumulator,
    ChatServiceError,
)
from astrbot.dashboard.services.mcp_app_service import read_chat_mcp_app


def _event(
    username="alice", session_id="session", run_id="run", checkpoint_id="checkpoint"
):
    """Build a real WebChat event with server-issued request identity.

    Args:
        username: Authenticated owner.
        session_id: Conversation identifier.
        run_id: Server-generated request identifier.
        checkpoint_id: Server-generated checkpoint identifier.

    Returns:
        A WebChat platform event with its original adapter payload.
    """
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.sender = MessageMember(username, username)
    message.message_id = run_id
    message.raw_message = (
        username,
        session_id,
        {"message_id": run_id, "llm_checkpoint_id": checkpoint_id},
    )
    return WebChatMessageEvent(
        "",
        message,
        PlatformMetadata(name="webchat", description="webchat", id="webchat"),
        f"webchat!{username}!{session_id}",
    )


@pytest.fixture
def app_context():
    mcp_apps.entries.clear()
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
            name="picker.photo",
            inputSchema={"type": "object"},
            _meta={"ui": {"resourceUri": uri}},
        ),
        client,
        "photos",
    )
    invocation = mcp_apps.capture(tool, _event(), "call", {"query": "forest"})
    ref = mcp_apps.issue(
        invocation, {"content": [], "structuredContent": {"ids": [1, 2]}}
    )
    mcp_apps.bind_message(
        ref, "alice", "session", "run", "checkpoint", "call", "message"
    )
    call = {
        "id": "call",
        "name": tool.name,
        "args": {"query": "forest"},
        "mcp_app": {"app_ref": ref},
    }
    record = SimpleNamespace(
        user_id="session",
        platform_id="webchat",
        llm_checkpoint_id="checkpoint",
        content={
            "type": "bot",
            "message": [{"type": "tool_call", "tool_calls": [call]}],
        },
    )
    service = SimpleNamespace(
        db=SimpleNamespace(
            get_platform_session_by_id=AsyncMock(
                return_value=SimpleNamespace(
                    creator="alice",
                    platform_id="webchat",
                    session_id="session",
                    is_group=False,
                )
            ),
            get_platform_message_history_by_id=AsyncMock(return_value=record),
        ),
        core_lifecycle=SimpleNamespace(
            provider_manager=SimpleNamespace(
                llm_tools=SimpleNamespace(func_list=[tool])
            )
        ),
    )
    yield service, tool, record, call
    mcp_apps.entries.clear()


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
        "expired",
        "reconnected",
        "checkpoint",
        "forged_ref",
        "restarted",
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
        service.core_lifecycle.provider_manager.llm_tools.func_list = []
    if mutation == "server":
        tool.mcp_server_name = "other"
    if mutation == "uri":
        tool.mcp_tool.meta = {"ui": {"resourceUri": "ui://other/app"}}
    if mutation == "disabled":
        tool.active = False
    if mutation == "disconnected":
        tool.mcp_client.active = False
    if mutation == "missing_call":
        call["id"] = "other"
    if mutation == "expired":
        mcp_apps.entries[call["mcp_app"]["app_ref"]].expires = 0
    if mutation == "reconnected":
        tool.mcp_client.session = SimpleNamespace(read_resource=AsyncMock())
    if mutation == "checkpoint":
        record.llm_checkpoint_id = "other"
    if mutation == "forged_ref":
        call["mcp_app"]["app_ref"] = "forged"
    if mutation == "restarted":
        mcp_apps.entries.clear()
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
    assert set(stored["mcp_app"]) == {"app_ref"}


@pytest.mark.asyncio
async def test_colliding_display_names_cannot_redirect_resource(app_context):
    service, tool, _, call = app_context
    other = MCPTool(
        Tool(
            name="picker/photo",
            inputSchema={},
            _meta={"ui": {"resourceUri": tool.ui_resource_uri}},
        ),
        SimpleNamespace(
            active=True, session=SimpleNamespace(read_resource=AsyncMock())
        ),
        "other-server",
    )
    assert other.name == tool.name
    service.core_lifecycle.provider_manager.llm_tools.func_list = [other, tool]
    call["args"] = {"forged": "history is not authority"}
    call["mcp_app"]["uri"] = "ui://forged"
    data = await read_chat_mcp_app(service, "alice", "session", "message", "call")
    assert data["arguments"] == {"query": "forest"}
    other.mcp_client.session.read_resource.assert_not_awaited()
    service.core_lifecycle.provider_manager.llm_tools.func_list = [other]
    with pytest.raises(ChatServiceError):
        await read_chat_mcp_app(service, "alice", "session", "message", "call")


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["owner", "conversation", "message"])
async def test_copied_reference_cannot_cross_persisted_boundaries(app_context, target):
    service, tool, record, _ = app_context
    username, session_id, message_id = "alice", "session", "message"
    session = service.db.get_platform_session_by_id.return_value
    if target == "owner":
        username = session.creator = "bob"
    if target == "conversation":
        session_id = session.session_id = record.user_id = "other"
    if target == "message":
        message_id = "copied-message"
    with pytest.raises(ChatServiceError):
        await read_chat_mcp_app(service, username, session_id, message_id, "call")
    tool.mcp_client.session.read_resource.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconnect_during_resource_read_is_rejected(app_context):
    service, tool, _, _ = app_context
    original = tool.mcp_client.session

    async def reconnect(uri):
        tool.mcp_client.session = SimpleNamespace(read_resource=AsyncMock())
        return original.read_resource.return_value

    original.read_resource.side_effect = reconnect
    with pytest.raises(ChatServiceError):
        await read_chat_mcp_app(service, "alice", "session", "message", "call")


@pytest.mark.asyncio
async def test_resource_bundle_cannot_include_extra_contents(app_context):
    service, tool, _, _ = app_context
    contents = tool.mcp_client.session.read_resource.return_value.contents
    contents.append(contents[0])
    with pytest.raises(ChatServiceError, match="exactly one"):
        await read_chat_mcp_app(service, "alice", "session", "message", "call")


def test_reference_must_be_bound_by_its_original_chat_run(app_context):
    _, tool, _, _ = app_context
    registry = McpAppRegistry()
    cap = registry.capture(tool, _event(), "call", {})
    ref = registry.issue(cap, {"content": []})
    registry.bind_message(
        ref, "alice", "session", "other-run", "checkpoint", "call", "message"
    )
    assert registry.entries[ref].message_id is None
    registry.bind_message(
        ref, "alice", "session", "run", "checkpoint", "call", "message"
    )
    registry.bind_message(
        ref, "alice", "session", "run", "checkpoint", "call", "copied"
    )
    assert registry.entries[ref].message_id == "message"


def test_non_webchat_and_changed_connection_do_not_issue_capabilities(app_context):
    _, tool, _, _ = app_context
    registry = McpAppRegistry()
    assert registry.capture(tool, SimpleNamespace(), "call", {}) is None
    cap = registry.capture(tool, _event(), "call", {})
    tool.mcp_client.session = object()
    assert registry.issue(cap, {}) is None


def test_capability_storage_is_bounded_and_results_are_independent(
    app_context, monkeypatch
):
    _, tool, _, _ = app_context
    monkeypatch.setattr("astrbot.core.agent.mcp_app_registry.MAX_APP_CAPABILITIES", 2)
    registry = McpAppRegistry()
    cap = registry.capture(tool, _event(), "call", {})
    first = registry.issue(cap, {"version": 1})
    second = registry.issue(cap, {"version": 2})
    assert registry.entries[first].result == {"version": 1}
    assert registry.entries[second].result == {"version": 2}
    registry.issue(cap, {"version": 3})
    assert first not in registry.entries and len(registry.entries) == 2
    assert registry.issue(cap, {"large": "x" * (1024 * 1024)}) is None
