# ruff: noqa: ASYNC110

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import mcp
import pytest

from astrbot.core.agent.mcp_client import MCPClient
from astrbot.core.agent.mcp_elicitation_registry import (
    pending_mcp_elicitation,
    submit_pending_mcp_elicitation_reply,
    try_capture_pending_mcp_elicitation,
)
from astrbot.core.agent.mcp_subcapability_bridge import MCPClientSubCapabilityBridge
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.provider.func_tool_manager import FunctionToolManager


class _DummyAsyncContext:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _RecordingClientSession:
    constructor_calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        self.__class__.constructor_calls.append(
            {
                "args": args,
                "kwargs": kwargs,
            }
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def initialize(self):
        return None

    def get_server_capabilities(self):
        return None


class _SamplingAwareSession:
    def __init__(self, bridge, params):
        self.bridge = bridge
        self.params = params
        self.calls: list[dict] = []

    async def call_tool(self, *, name, arguments, read_timeout_seconds):
        self.calls.append(
            {
                "name": name,
                "arguments": arguments,
                "read_timeout_seconds": read_timeout_seconds,
            }
        )
        sampling_result = await self.bridge.handle_sampling(None, self.params)
        assert isinstance(sampling_result, mcp.types.CreateMessageResult)
        return mcp.types.CallToolResult(
            content=[
                mcp.types.TextContent(
                    type="text",
                    text=sampling_result.content.text,
                )
            ]
        )


class _DummyProvider:
    def __init__(self, model: str = "gpt-4o-mini"):
        self._model = model

    def get_model(self) -> str:
        return self._model

    def meta(self):
        return SimpleNamespace(model=self._model, id="provider-1")


class _DummyPluginContext:
    def __init__(
        self,
        *,
        completion_text: str,
        release_event: asyncio.Event | None = None,
        entered_event: asyncio.Event | None = None,
    ):
        self.provider = _DummyProvider()
        self.completion_text = completion_text
        self.release_event = release_event
        self.entered_event = entered_event
        self.requests: list[dict] = []

    async def get_current_chat_provider_id(self, umo: str) -> str:
        assert umo
        return "provider-1"

    def get_using_provider(self, umo: str | None = None):
        return self.provider

    async def llm_generate(self, **kwargs):
        self.requests.append(kwargs)
        if self.entered_event is not None:
            self.entered_event.set()
        if self.release_event is not None:
            await self.release_event.wait()
        return LLMResponse(role="assistant", completion_text=self.completion_text)


class _DummyEvent:
    def __init__(
        self,
        *,
        umo: str = "test:umo",
        sender_id: str = "user-1",
        message_text: str = "",
        outline: str = "",
        platform_name: str = "test",
    ) -> None:
        self.unified_msg_origin = umo
        self._sender_id = sender_id
        self._message_text = message_text
        self._outline = outline or message_text
        self._platform_name = platform_name
        self.sent_messages: list[str] = []
        self.sent_payloads: list[dict] = []

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_message_str(self) -> str:
        return self._message_text

    def get_message_outline(self) -> str:
        return self._outline

    def get_platform_name(self) -> str:
        return self._platform_name

    async def send(self, message_chain) -> None:
        self.sent_messages.append(
            message_chain.get_plain_text(with_other_comps_mark=True)
        )
        if (
            getattr(message_chain, "type", None) == "elicitation"
            and message_chain.chain
        ):
            first = message_chain.chain[0]
            payload = getattr(first, "data", None)
            if isinstance(payload, dict):
                self.sent_payloads.append(payload)


def _build_run_context(
    plugin_context: _DummyPluginContext,
    *,
    umo: str = "test:umo",
    event: _DummyEvent | None = None,
):
    event = event or _DummyEvent(umo=umo)
    agent_context = SimpleNamespace(
        context=plugin_context,
        event=event,
    )
    return ContextWrapper(context=agent_context)


def _build_sampling_params(*, tools=None, content=None):
    if content is None:
        content = mcp.types.TextContent(type="text", text="hello from server")
    return mcp.types.CreateMessageRequestParams(
        messages=[
            mcp.types.SamplingMessage(
                role="user",
                content=content,
            )
        ],
        maxTokens=64,
        tools=tools,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enabled", "expected_sampling_enabled"),
    [
        pytest.param(False, False, id="sampling-disabled"),
        pytest.param(True, True, id="sampling-enabled"),
    ],
)
async def test_mcp_client_capability_advertisement_depends_on_config(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    expected_sampling_enabled: bool,
):
    _RecordingClientSession.constructor_calls.clear()

    async def _fake_quick_test(_config):
        return True, ""

    monkeypatch.setattr(
        "astrbot.core.agent.mcp_client._quick_test_mcp_connection",
        _fake_quick_test,
    )
    monkeypatch.setattr(
        "astrbot.core.agent.mcp_client.sse_client",
        lambda **_kwargs: _DummyAsyncContext(("read", "write")),
    )
    monkeypatch.setattr(
        "astrbot.core.agent.mcp_client.mcp.ClientSession",
        _RecordingClientSession,
    )

    client = MCPClient()
    await client.connect_to_server(
        {
            "url": "https://example.com/mcp",
            "transport": "sse",
            "client_capabilities": {
                "sampling": {
                    "enabled": enabled,
                }
            },
        },
        "demo",
    )

    kwargs = _RecordingClientSession.constructor_calls[0]["kwargs"]
    sampling_callback = kwargs.get("sampling_callback")
    sampling_capabilities = kwargs.get("sampling_capabilities")

    if expected_sampling_enabled:
        assert callable(sampling_callback)
        assert sampling_capabilities is not None
    else:
        assert sampling_callback is None
        assert sampling_capabilities is None

    await client.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enabled", "expected_roots_enabled"),
    [
        pytest.param(False, False, id="roots-disabled"),
        pytest.param(True, True, id="roots-enabled"),
    ],
)
async def test_mcp_client_roots_capability_advertisement_depends_on_config(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    expected_roots_enabled: bool,
):
    _RecordingClientSession.constructor_calls.clear()

    async def _fake_quick_test(_config):
        return True, ""

    monkeypatch.setattr(
        "astrbot.core.agent.mcp_client._quick_test_mcp_connection",
        _fake_quick_test,
    )
    monkeypatch.setattr(
        "astrbot.core.agent.mcp_client.sse_client",
        lambda **_kwargs: _DummyAsyncContext(("read", "write")),
    )
    monkeypatch.setattr(
        "astrbot.core.agent.mcp_client.mcp.ClientSession",
        _RecordingClientSession,
    )

    client = MCPClient()
    await client.connect_to_server(
        {
            "url": "https://example.com/mcp",
            "transport": "sse",
            "client_capabilities": {
                "roots": {
                    "enabled": enabled,
                }
            },
        },
        "demo",
    )

    kwargs = _RecordingClientSession.constructor_calls[0]["kwargs"]
    roots_callback = kwargs.get("list_roots_callback")

    if expected_roots_enabled:
        assert callable(roots_callback)
    else:
        assert roots_callback is None

    await client.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enabled", "expected_elicitation_enabled"),
    [
        pytest.param(False, False, id="elicitation-disabled"),
        pytest.param(True, True, id="elicitation-enabled"),
    ],
)
async def test_mcp_client_elicitation_capability_advertisement_depends_on_config(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    expected_elicitation_enabled: bool,
):
    _RecordingClientSession.constructor_calls.clear()

    async def _fake_quick_test(_config):
        return True, ""

    monkeypatch.setattr(
        "astrbot.core.agent.mcp_client._quick_test_mcp_connection",
        _fake_quick_test,
    )
    monkeypatch.setattr(
        "astrbot.core.agent.mcp_client.sse_client",
        lambda **_kwargs: _DummyAsyncContext(("read", "write")),
    )
    monkeypatch.setattr(
        "astrbot.core.agent.mcp_client.mcp.ClientSession",
        _RecordingClientSession,
    )

    client = MCPClient()
    await client.connect_to_server(
        {
            "url": "https://example.com/mcp",
            "transport": "sse",
            "client_capabilities": {
                "elicitation": {
                    "enabled": enabled,
                    "timeout_seconds": 120,
                }
            },
        },
        "demo",
    )

    kwargs = _RecordingClientSession.constructor_calls[0]["kwargs"]
    elicitation_callback = kwargs.get("elicitation_callback")

    if expected_elicitation_enabled:
        assert callable(elicitation_callback)
    else:
        assert elicitation_callback is None

    await client.cleanup()


def test_load_and_save_mcp_config_normalizes_client_capabilities(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "astrbot.core.provider.func_tool_manager.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    tool_mgr = FunctionToolManager()

    config = {
        "mcpServers": {
            "disabled-default": {
                "command": "uv",
                "args": ["run", "demo.py"],
            },
            "enabled-sampling": {
                "command": "uv",
                "args": ["run", "demo.py"],
                "client_capabilities": {
                    "elicitation": {
                        "enabled": True,
                        "timeout_seconds": 180,
                    },
                    "sampling": {
                        "enabled": True,
                    },
                    "roots": {
                        "enabled": True,
                        "paths": ["data", "temp"],
                    },
                },
            },
        }
    }

    assert tool_mgr.save_mcp_config(config) is True

    saved_raw = json.loads((tmp_path / "mcp_server.json").read_text(encoding="utf-8"))
    assert (
        saved_raw["mcpServers"]["disabled-default"]["client_capabilities"][
            "elicitation"
        ]["enabled"]
        is False
    )
    assert (
        saved_raw["mcpServers"]["disabled-default"]["client_capabilities"][
            "elicitation"
        ]["timeout_seconds"]
        == 300
    )
    assert (
        saved_raw["mcpServers"]["disabled-default"]["client_capabilities"]["sampling"][
            "enabled"
        ]
        is False
    )
    assert (
        saved_raw["mcpServers"]["disabled-default"]["client_capabilities"]["roots"][
            "enabled"
        ]
        is False
    )
    assert (
        saved_raw["mcpServers"]["disabled-default"]["client_capabilities"]["roots"][
            "paths"
        ]
        == []
    )
    assert (
        saved_raw["mcpServers"]["enabled-sampling"]["client_capabilities"][
            "elicitation"
        ]["enabled"]
        is True
    )
    assert (
        saved_raw["mcpServers"]["enabled-sampling"]["client_capabilities"][
            "elicitation"
        ]["timeout_seconds"]
        == 180
    )
    assert (
        saved_raw["mcpServers"]["enabled-sampling"]["client_capabilities"]["sampling"][
            "enabled"
        ]
        is True
    )
    assert (
        saved_raw["mcpServers"]["enabled-sampling"]["client_capabilities"]["roots"][
            "enabled"
        ]
        is True
    )
    assert saved_raw["mcpServers"]["enabled-sampling"]["client_capabilities"]["roots"][
        "paths"
    ] == ["data", "temp"]

    loaded = tool_mgr.load_mcp_config()
    assert (
        loaded["mcpServers"]["disabled-default"]["client_capabilities"]["elicitation"][
            "enabled"
        ]
        is False
    )
    assert (
        loaded["mcpServers"]["disabled-default"]["client_capabilities"]["elicitation"][
            "timeout_seconds"
        ]
        == 300
    )
    assert (
        loaded["mcpServers"]["disabled-default"]["client_capabilities"]["sampling"][
            "enabled"
        ]
        is False
    )
    assert (
        loaded["mcpServers"]["disabled-default"]["client_capabilities"]["roots"][
            "enabled"
        ]
        is False
    )
    assert (
        loaded["mcpServers"]["enabled-sampling"]["client_capabilities"]["elicitation"][
            "enabled"
        ]
        is True
    )
    assert (
        loaded["mcpServers"]["enabled-sampling"]["client_capabilities"]["elicitation"][
            "timeout_seconds"
        ]
        == 180
    )
    assert (
        loaded["mcpServers"]["enabled-sampling"]["client_capabilities"]["sampling"][
            "enabled"
        ]
        is True
    )
    assert (
        loaded["mcpServers"]["enabled-sampling"]["client_capabilities"]["roots"][
            "enabled"
        ]
        is True
    )
    assert loaded["mcpServers"]["enabled-sampling"]["client_capabilities"]["roots"][
        "paths"
    ] == ["data", "temp"]


@pytest.mark.asyncio
async def test_roots_request_returns_default_roots_for_enabled_server(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    data_dir = tmp_path / "data"
    temp_dir = data_dir / "temp"
    data_dir.mkdir()
    temp_dir.mkdir()

    monkeypatch.setattr(
        "astrbot.core.agent.mcp_subcapability_bridge.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.agent.mcp_subcapability_bridge.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )

    bridge = MCPClientSubCapabilityBridge("demo")
    bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "roots": {
                    "enabled": True,
                }
            }
        }
    )

    result = await bridge.handle_list_roots(None)

    assert isinstance(result, mcp.types.ListRootsResult)
    assert [root.name for root in result.roots] == ["data", "temp"]
    assert str(result.roots[0].uri) == data_dir.resolve().as_uri()
    assert str(result.roots[1].uri) == temp_dir.resolve().as_uri()


@pytest.mark.asyncio
async def test_roots_request_uses_explicit_paths_and_skips_missing_entries(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    root_dir = tmp_path / "astrbot-root"
    root_dir.mkdir()
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    nested_dir = root_dir / "workspace"
    nested_dir.mkdir()

    monkeypatch.setattr(
        "astrbot.core.agent.mcp_subcapability_bridge.get_astrbot_root",
        lambda: str(root_dir),
    )

    bridge = MCPClientSubCapabilityBridge("demo")
    bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "roots": {
                    "enabled": True,
                    "paths": [
                        str(explicit_dir),
                        "workspace",
                        "missing-dir",
                    ],
                }
            }
        }
    )

    result = await bridge.handle_list_roots(None)

    assert isinstance(result, mcp.types.ListRootsResult)
    assert [
        Path(str(root.uri).removeprefix("file:///")).name for root in result.roots
    ] == [
        "explicit",
        "workspace",
    ]


@pytest.mark.asyncio
async def test_roots_request_is_rejected_when_disabled():
    bridge = MCPClientSubCapabilityBridge("demo")

    result = await bridge.handle_list_roots(None)

    assert isinstance(result, mcp.types.ErrorData)
    assert result.code == mcp.types.INVALID_REQUEST
    assert "Roots are not enabled" in result.message


@pytest.mark.asyncio
async def test_sampling_request_uses_bound_astrbot_context():
    bridge = MCPClientSubCapabilityBridge("demo")
    bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "sampling": {
                    "enabled": True,
                }
            }
        }
    )
    plugin_context = _DummyPluginContext(completion_text="reply from astrbot")
    run_context = _build_run_context(plugin_context)
    params = _build_sampling_params()

    async with bridge.interactive_call(run_context):
        result = await bridge.handle_sampling(None, params)

    assert isinstance(result, mcp.types.CreateMessageResult)
    assert result.content.text == "reply from astrbot"
    assert result.model == "gpt-4o-mini"
    assert plugin_context.requests[0]["contexts"] == [
        {
            "role": "user",
            "content": "hello from server",
        }
    ]
    assert plugin_context.requests[0]["max_tokens"] == 64


@pytest.mark.asyncio
async def test_sampling_request_without_bound_context_is_rejected():
    bridge = MCPClientSubCapabilityBridge("demo")
    bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "sampling": {
                    "enabled": True,
                }
            }
        }
    )

    result = await bridge.handle_sampling(None, _build_sampling_params())

    assert isinstance(result, mcp.types.ErrorData)
    assert result.code == mcp.types.INVALID_REQUEST
    assert "active AstrBot MCP interaction" in result.message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        pytest.param(
            _build_sampling_params(
                tools=[
                    mcp.types.Tool(
                        name="demo_tool",
                        description="demo",
                        inputSchema={"type": "object", "properties": {}},
                    )
                ]
            ),
            id="tool-assisted-sampling",
        ),
        pytest.param(
            _build_sampling_params(
                content=mcp.types.ImageContent(
                    type="image",
                    data="ZmFrZQ==",
                    mimeType="image/png",
                )
            ),
            id="image-input",
        ),
    ],
)
async def test_sampling_request_rejects_unsupported_inputs(params):
    bridge = MCPClientSubCapabilityBridge("demo")
    bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "sampling": {
                    "enabled": True,
                }
            }
        }
    )
    plugin_context = _DummyPluginContext(completion_text="reply")
    run_context = _build_run_context(plugin_context)

    async with bridge.interactive_call(run_context):
        result = await bridge.handle_sampling(None, params)

    assert isinstance(result, mcp.types.ErrorData)
    assert result.code == mcp.types.INVALID_REQUEST


@pytest.mark.asyncio
async def test_sampling_enabled_interactive_calls_are_serialized():
    bridge = MCPClientSubCapabilityBridge("demo")
    bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "sampling": {
                    "enabled": True,
                }
            }
        }
    )

    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    first_plugin_context = _DummyPluginContext(
        completion_text="first reply",
        release_event=release_first,
        entered_event=first_entered,
    )
    second_plugin_context = _DummyPluginContext(completion_text="second reply")
    order: list[str] = []
    params = _build_sampling_params()

    async def _first_call():
        async with bridge.interactive_call(_build_run_context(first_plugin_context)):
            order.append("enter-1")
            result = await bridge.handle_sampling(None, params)
            order.append("exit-1")
            return result

    async def _second_call():
        await first_entered.wait()
        async with bridge.interactive_call(_build_run_context(second_plugin_context)):
            order.append("enter-2")
            result = await bridge.handle_sampling(None, params)
            order.append("exit-2")
            return result

    first_task = asyncio.create_task(_first_call())
    await first_entered.wait()
    second_task = asyncio.create_task(_second_call())

    await asyncio.sleep(0)
    assert order == ["enter-1"]

    release_first.set()
    first_result = await first_task
    second_result = await second_task

    assert isinstance(first_result, mcp.types.CreateMessageResult)
    assert isinstance(second_result, mcp.types.CreateMessageResult)
    assert first_result.content.text == "first reply"
    assert second_result.content.text == "second reply"
    assert order == ["enter-1", "exit-1", "enter-2", "exit-2"]


@pytest.mark.asyncio
async def test_mcp_client_call_tool_with_reconnect_preserves_sampling_runtime_context():
    client = MCPClient()
    client.subcapability_bridge.set_server_name("demo")
    client.subcapability_bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "sampling": {
                    "enabled": True,
                }
            }
        }
    )
    client.session = _SamplingAwareSession(
        client.subcapability_bridge,
        _build_sampling_params(),
    )

    plugin_context = _DummyPluginContext(completion_text="reply from astrbot")
    run_context = _build_run_context(plugin_context)

    result = await client.call_tool_with_reconnect(
        tool_name="draft-brief",
        arguments={"topic": "MCP 最小实现"},
        read_timeout_seconds=timedelta(seconds=60),
        run_context=run_context,
    )

    assert isinstance(result, mcp.types.CallToolResult)
    assert result.content[0].text == "reply from astrbot"
    assert len(client.session.calls) == 1
    assert client.session.calls[0]["name"] == "draft-brief"
    assert client.session.calls[0]["arguments"] == {"topic": "MCP 最小实现"}
    assert plugin_context.requests[0]["contexts"] == [
        {
            "role": "user",
            "content": "hello from server",
        }
    ]


@pytest.mark.asyncio
async def test_pending_mcp_elicitation_captures_only_matching_sender():
    async with pending_mcp_elicitation("umo:1", "user-1") as future:
        wrong_sender_event = _DummyEvent(
            umo="umo:1",
            sender_id="user-2",
            message_text="ignored",
        )
        assert try_capture_pending_mcp_elicitation(wrong_sender_event) is False
        assert future.done() is False

        matching_event = _DummyEvent(
            umo="umo:1",
            sender_id="user-1",
            message_text="accepted",
        )
        assert try_capture_pending_mcp_elicitation(matching_event) is True
        resolved_event = await future
        assert resolved_event.message_text == "accepted"
        assert resolved_event.message_outline == "accepted"


@pytest.mark.asyncio
async def test_pending_mcp_elicitation_accepts_direct_submission():
    async with pending_mcp_elicitation("umo:1", "user-1") as future:
        assert (
            submit_pending_mcp_elicitation_reply(
                "umo:1",
                "user-1",
                '{"topic":"MCP 最小实现"}',
                reply_outline="topic: MCP 最小实现",
            )
            is True
        )
        resolved_reply = await future

    assert resolved_reply.message_text == '{"topic":"MCP 最小实现"}'
    assert resolved_reply.message_outline == "topic: MCP 最小实现"


@pytest.mark.asyncio
async def test_elicitation_form_request_uses_next_matching_reply():
    bridge = MCPClientSubCapabilityBridge("demo")
    bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "elicitation": {
                    "enabled": True,
                    "timeout_seconds": 30,
                }
            }
        }
    )
    event = _DummyEvent(umo="test:umo", sender_id="user-1")
    run_context = _build_run_context(
        _DummyPluginContext(completion_text="unused"),
        event=event,
    )
    params = mcp.types.ElicitRequestFormParams(
        message="Please provide the topic.",
        requestedSchema={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Brief topic name",
                }
            },
            "required": ["topic"],
        },
    )

    async def _resolve_reply():
        while not event.sent_messages:
            await asyncio.sleep(0)
        assert "topic" in event.sent_messages[0]
        reply_event = _DummyEvent(
            umo="test:umo",
            sender_id="user-1",
            message_text="MCP 最小实现",
        )
        while not try_capture_pending_mcp_elicitation(reply_event):
            await asyncio.sleep(0)

    async with bridge.interactive_call(run_context):
        result_task = asyncio.create_task(bridge.handle_elicitation(None, params))
        await _resolve_reply()
        result = await result_task

    assert isinstance(result, mcp.types.ElicitResult)
    assert result.action == "accept"
    assert result.content == {"topic": "MCP 最小实现"}


@pytest.mark.asyncio
async def test_elicitation_form_request_reprompts_after_invalid_reply():
    bridge = MCPClientSubCapabilityBridge("demo")
    bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "elicitation": {
                    "enabled": True,
                    "timeout_seconds": 30,
                }
            }
        }
    )
    event = _DummyEvent(umo="test:umo", sender_id="user-1")
    run_context = _build_run_context(
        _DummyPluginContext(completion_text="unused"),
        event=event,
    )
    params = mcp.types.ElicitRequestFormParams(
        message="How many sections do you need?",
        requestedSchema={
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                }
            },
            "required": ["count"],
        },
    )

    async def _resolve_replies():
        while len(event.sent_messages) < 1:
            await asyncio.sleep(0)
        first_reply = _DummyEvent(
            umo="test:umo",
            sender_id="user-1",
            message_text="not-a-number",
        )
        while not try_capture_pending_mcp_elicitation(first_reply):
            await asyncio.sleep(0)

        while len(event.sent_messages) < 2:
            await asyncio.sleep(0)
        assert "could not use that reply" in event.sent_messages[1].lower()
        second_reply = _DummyEvent(
            umo="test:umo",
            sender_id="user-1",
            message_text="2",
        )
        while not try_capture_pending_mcp_elicitation(second_reply):
            await asyncio.sleep(0)

    async with bridge.interactive_call(run_context):
        result_task = asyncio.create_task(bridge.handle_elicitation(None, params))
        await _resolve_replies()
        result = await result_task

    assert isinstance(result, mcp.types.ElicitResult)
    assert result.action == "accept"
    assert result.content == {"count": 2}


@pytest.mark.asyncio
async def test_elicitation_form_request_accepts_natural_language_key_value_patterns():
    bridge = MCPClientSubCapabilityBridge("demo")
    bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "elicitation": {
                    "enabled": True,
                    "timeout_seconds": 30,
                }
            }
        }
    )
    event = _DummyEvent(umo="test:umo", sender_id="user-1")
    run_context = _build_run_context(
        _DummyPluginContext(completion_text="unused"),
        event=event,
    )
    params = mcp.types.ElicitRequestFormParams(
        message="Collect plan details.",
        requestedSchema={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "audience": {"type": "string"},
            },
            "required": ["topic", "audience"],
        },
    )

    async def _resolve_reply():
        while not event.sent_messages:
            await asyncio.sleep(0)
        reply_event = _DummyEvent(
            umo="test:umo",
            sender_id="user-1",
            message_text="topic 是 MCP 最小实现，audience 为 新手",
        )
        while not try_capture_pending_mcp_elicitation(reply_event):
            await asyncio.sleep(0)

    async with bridge.interactive_call(run_context):
        result_task = asyncio.create_task(bridge.handle_elicitation(None, params))
        await _resolve_reply()
        result = await result_task

    assert isinstance(result, mcp.types.ElicitResult)
    assert result.action == "accept"
    assert result.content == {
        "topic": "MCP 最小实现",
        "audience": "新手",
    }


@pytest.mark.asyncio
async def test_elicitation_form_request_uses_llm_fallback_for_bot_reply():
    bridge = MCPClientSubCapabilityBridge("demo")
    bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "elicitation": {
                    "enabled": True,
                    "timeout_seconds": 30,
                }
            }
        }
    )
    plugin_context = _DummyPluginContext(
        completion_text='```json\n{"topic":"MCP 最小实现","audience":"新手"}\n```'
    )
    event = _DummyEvent(umo="test:umo", sender_id="user-1")
    run_context = _build_run_context(
        plugin_context,
        event=event,
    )
    params = mcp.types.ElicitRequestFormParams(
        message="Collect plan details.",
        requestedSchema={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "audience": {"type": "string"},
            },
            "required": ["topic", "audience"],
        },
    )

    async def _resolve_reply():
        while not event.sent_messages:
            await asyncio.sleep(0)
        reply_event = _DummyEvent(
            umo="test:umo",
            sender_id="user-1",
            message_text="面向新手，写一个关于 MCP 最小实现 的简要说明。",
        )
        while not try_capture_pending_mcp_elicitation(reply_event):
            await asyncio.sleep(0)

    async with bridge.interactive_call(run_context):
        result_task = asyncio.create_task(bridge.handle_elicitation(None, params))
        await _resolve_reply()
        result = await result_task

    assert isinstance(result, mcp.types.ElicitResult)
    assert result.action == "accept"
    assert result.content == {
        "topic": "MCP 最小实现",
        "audience": "新手",
    }
    assert len(plugin_context.requests) == 1
    assert plugin_context.requests[0]["chat_provider_id"] == "provider-1"
    assert "Return only a JSON object." in plugin_context.requests[0]["system_prompt"]


@pytest.mark.asyncio
async def test_elicitation_form_request_retries_when_llm_fallback_returns_invalid_json():
    bridge = MCPClientSubCapabilityBridge("demo")
    bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "elicitation": {
                    "enabled": True,
                    "timeout_seconds": 30,
                }
            }
        }
    )
    plugin_context = _DummyPluginContext(completion_text="not-json")
    event = _DummyEvent(umo="test:umo", sender_id="user-1")
    run_context = _build_run_context(
        plugin_context,
        event=event,
    )
    params = mcp.types.ElicitRequestFormParams(
        message="Collect plan details.",
        requestedSchema={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "audience": {"type": "string"},
            },
            "required": ["topic", "audience"],
        },
    )

    async def _resolve_replies():
        while not event.sent_messages:
            await asyncio.sleep(0)
        first_reply = _DummyEvent(
            umo="test:umo",
            sender_id="user-1",
            message_text="帮我给新手准备一个关于 MCP 最小实现 的说明。",
        )
        while not try_capture_pending_mcp_elicitation(first_reply):
            await asyncio.sleep(0)

        while len(event.sent_messages) < 2:
            await asyncio.sleep(0)
        assert "could not use that reply" in event.sent_messages[1].lower()

        second_reply = _DummyEvent(
            umo="test:umo",
            sender_id="user-1",
            message_text='{"topic":"MCP 最小实现","audience":"新手"}',
        )
        while not try_capture_pending_mcp_elicitation(second_reply):
            await asyncio.sleep(0)

    async with bridge.interactive_call(run_context):
        result_task = asyncio.create_task(bridge.handle_elicitation(None, params))
        await _resolve_replies()
        result = await result_task

    assert isinstance(result, mcp.types.ElicitResult)
    assert result.action == "accept"
    assert result.content == {
        "topic": "MCP 最小实现",
        "audience": "新手",
    }
    assert len(plugin_context.requests) == 1


@pytest.mark.asyncio
async def test_webchat_elicitation_message_uses_structured_payload():
    bridge = MCPClientSubCapabilityBridge("demo")
    bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "elicitation": {
                    "enabled": True,
                    "timeout_seconds": 30,
                }
            }
        }
    )
    event = _DummyEvent(
        umo="test:umo",
        sender_id="user-1",
        platform_name="webchat",
    )
    run_context = _build_run_context(
        _DummyPluginContext(completion_text="unused"),
        event=event,
    )
    params = mcp.types.ElicitRequestFormParams(
        message="Choose a tone.",
        requestedSchema={
            "type": "object",
            "properties": {
                "tone": {
                    "type": "string",
                    "enum": ["formal", "casual"],
                }
            },
            "required": ["tone"],
        },
    )

    async def _resolve_reply():
        while not event.sent_payloads:
            await asyncio.sleep(0)
        assert event.sent_payloads[0]["fields"][0]["enum"] == ["formal", "casual"]
        submit_pending_mcp_elicitation_reply(
            "test:umo",
            "user-1",
            "formal",
            reply_outline="tone: formal",
        )

    async with bridge.interactive_call(run_context):
        result_task = asyncio.create_task(bridge.handle_elicitation(None, params))
        await _resolve_reply()
        result = await result_task

    assert isinstance(result, mcp.types.ElicitResult)
    assert result.action == "accept"
    assert result.content == {"tone": "formal"}


@pytest.mark.asyncio
async def test_elicitation_url_request_waits_for_confirmation():
    bridge = MCPClientSubCapabilityBridge("demo")
    bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "elicitation": {
                    "enabled": True,
                    "timeout_seconds": 30,
                }
            }
        }
    )
    event = _DummyEvent(umo="test:umo", sender_id="user-1")
    run_context = _build_run_context(
        _DummyPluginContext(completion_text="unused"),
        event=event,
    )
    params = mcp.types.ElicitRequestURLParams(
        message="Authorize the test server.",
        url="https://example.com/auth",
        elicitationId="elic-1",
    )

    async def _resolve_reply():
        while not event.sent_messages:
            await asyncio.sleep(0)
        assert "https://example.com/auth" in event.sent_messages[0]
        reply_event = _DummyEvent(
            umo="test:umo",
            sender_id="user-1",
            message_text="done",
        )
        while not try_capture_pending_mcp_elicitation(reply_event):
            await asyncio.sleep(0)

    async with bridge.interactive_call(run_context):
        result_task = asyncio.create_task(bridge.handle_elicitation(None, params))
        await _resolve_reply()
        result = await result_task

    assert isinstance(result, mcp.types.ElicitResult)
    assert result.action == "accept"
    assert result.content is None


@pytest.mark.asyncio
async def test_elicitation_request_times_out_to_cancel(monkeypatch: pytest.MonkeyPatch):
    bridge = MCPClientSubCapabilityBridge("demo")
    bridge.configure_from_server_config(
        {
            "client_capabilities": {
                "elicitation": {
                    "enabled": True,
                    "timeout_seconds": 30,
                }
            }
        }
    )
    event = _DummyEvent(umo="test:umo", sender_id="user-1")
    run_context = _build_run_context(
        _DummyPluginContext(completion_text="unused"),
        event=event,
    )
    params = mcp.types.ElicitRequestFormParams(
        message="Please provide topic.",
        requestedSchema={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
            },
        },
    )

    async def _fake_wait_for_reply(*, event, sender_id, deadline):
        del event, sender_id, deadline
        return None

    monkeypatch.setattr(bridge, "_wait_for_elicitation_reply", _fake_wait_for_reply)

    async with bridge.interactive_call(run_context):
        result = await bridge.handle_elicitation(None, params)

    assert isinstance(result, mcp.types.ElicitResult)
    assert result.action == "cancel"
