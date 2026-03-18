# ruff: noqa: E402
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from astrbot.core.sdk_bridge import capability_bridge as capability_bridge_module
from astrbot_sdk.context import CancelToken
from astrbot_sdk.context import Context as RuntimeContext
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.llm.agents import AgentSpec
from astrbot_sdk.llm.entities import LLMToolSpec, ProviderMeta, ProviderRequest
from astrbot_sdk.llm.providers import (
    EmbeddingProvider,
    RerankProvider,
    STTProvider,
    TTSProvider,
)
from astrbot_sdk.runtime.capability_dispatcher import CapabilityDispatcher
from astrbot_sdk.runtime.loader import LoadedLLMTool
from astrbot_sdk.testing import MockContext


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mock_context_p0_5_provider_queries_and_tool_manager() -> None:
    ctx = MockContext(plugin_id="sdk_demo_agent_tools")
    ctx.router.set_provider_catalog(
        "chat",
        [
            ProviderMeta(
                id="chat-provider-1",
                model="gpt-test",
                type="mock",
                provider_type="chat_completion",
            ).to_payload()
        ],
        active_id="chat-provider-1",
    )
    ctx.router.set_plugin_llm_tools(
        "sdk_demo_agent_tools",
        [
            LLMToolSpec(
                name="sdk_static_note",
                description="static tool",
                parameters_schema={"type": "object", "properties": {}},
                active=True,
            ).to_payload()
        ],
    )
    ctx.router.set_plugin_agents(
        "sdk_demo_agent_tools",
        [
            AgentSpec(
                name="sdk_demo_note_agent",
                description="demo agent",
                tool_names=["sdk_static_note"],
                runner_class="demo.Agent",
            ).to_payload()
        ],
    )

    current = await ctx.get_using_provider()
    assert current is not None
    assert current.id == "chat-provider-1"
    assert await ctx.get_current_chat_provider_id() == "chat-provider-1"
    assert [item.id for item in await ctx.get_all_providers()] == ["chat-provider-1"]

    manager = ctx.get_llm_tool_manager()
    assert [item.name for item in await manager.list_registered()] == [
        "sdk_static_note"
    ]
    assert [item.name for item in await manager.list_active()] == ["sdk_static_note"]
    assert await ctx.deactivate_llm_tool("sdk_static_note") is True
    assert await manager.list_active() == []
    assert await ctx.activate_llm_tool("sdk_static_note") is True

    added = await ctx.add_llm_tools(
        LLMToolSpec(
            name="sdk_dynamic_note",
            description="dynamic tool",
            parameters_schema={"type": "object", "properties": {}},
            active=True,
        )
    )
    assert added == ["sdk_dynamic_note"]
    assert sorted(item.name for item in await manager.list_registered()) == [
        "sdk_dynamic_note",
        "sdk_static_note",
    ]

    response = await ctx.tool_loop_agent(
        ProviderRequest(prompt="hello", tool_names=["sdk_static_note"])
    )
    assert response.text == "Mock tool loop: hello tools=sdk_static_note"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mock_context_p1_1_provider_client_and_specialized_proxies() -> None:
    ctx = MockContext(plugin_id="sdk_demo_agent_tools")
    ctx.router.set_provider_catalog(
        "tts",
        [
                {
                    "id": "tts-provider-1",
                    "model": "tts-model",
                    "type": "mock",
                    "provider_type": "text_to_speech",
                }
            ],
        active_id="tts-provider-1",
    )
    ctx.router.set_provider_catalog(
        "stt",
        [
            {
                "id": "stt-provider-1",
                "model": "stt-model",
                "type": "mock",
                "provider_type": "speech_to_text",
            }
        ],
        active_id="stt-provider-1",
    )
    ctx.router.set_provider_catalog(
        "embedding",
        [
            {
                "id": "embedding-provider-1",
                "model": "embedding-model",
                "type": "mock",
                "provider_type": "embedding",
            }
        ],
    )
    ctx.router.set_provider_catalog(
        "rerank",
        [
            {
                "id": "rerank-provider-1",
                "model": "rerank-model",
                "type": "mock",
                "provider_type": "rerank",
            }
        ],
    )

    assert [item.id for item in await ctx.providers.list_tts()] == ["tts-provider-1"]
    assert [item.id for item in await ctx.providers.list_stt()] == ["stt-provider-1"]
    assert [item.id for item in await ctx.providers.list_embedding()] == [
        "embedding-provider-1"
    ]
    assert [item.id for item in await ctx.providers.list_rerank()] == [
        "rerank-provider-1"
    ]
    assert [item.id for item in await ctx.get_all_rerank_providers()] == [
        "rerank-provider-1"
    ]

    tts = await ctx.providers.get("tts-provider-1")
    stt = await ctx.providers.get("stt-provider-1")
    embedding = await ctx.providers.get("embedding-provider-1")
    rerank = await ctx.providers.get("rerank-provider-1")

    assert isinstance(tts, TTSProvider)
    assert isinstance(stt, STTProvider)
    assert isinstance(embedding, EmbeddingProvider)
    assert isinstance(rerank, RerankProvider)
    assert await ctx.providers.get("missing-provider") is None
    assert await ctx.providers.get("mock-chat-provider") is None

    assert await stt.get_text("https://example.com/audio.wav") == (
        "Mock transcript: https://example.com/audio.wav"
    )
    assert await tts.get_audio("hello sdk") == "mock://tts/tts-provider-1/hello sdk"
    assert tts.support_stream() is True

    single_chunks = [chunk async for chunk in tts.get_audio_stream("hello stream")]
    assert len(single_chunks) == 1
    assert single_chunks[0].text == "hello stream"
    assert single_chunks[0].audio == b"mock-audio:hello stream"

    async def text_source():
        yield "hello"
        yield "sdk"

    streamed_chunks = [chunk async for chunk in tts.get_audio_stream(text_source())]
    assert [chunk.text for chunk in streamed_chunks] == ["hello", "sdk"]
    assert [chunk.audio for chunk in streamed_chunks] == [
        b"mock-audio:hello",
        b"mock-audio:sdk",
    ]

    assert await embedding.get_embedding("AstrBot") == [0.0, 0.0, 0.0]
    assert await embedding.get_embeddings(["AstrBot", "SDK"]) == [
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
    ]
    assert await embedding.get_dim() == 3

    reranked = await rerank.rerank(
        "hello sdk",
        ["hello world", "sdk helper", "other"],
        top_n=2,
    )
    assert [(item.document, item.score) for item in reranked] == [
        ("hello world", 1.0),
        ("sdk helper", 1.0),
    ]

    using_tts = await ctx.providers.get_using_tts()
    using_stt = await ctx.providers.get_using_stt()
    assert isinstance(using_tts, TTSProvider)
    assert isinstance(using_stt, STTProvider)
    assert (await ctx.get_using_tts_provider()) is not None
    assert (await ctx.get_using_stt_provider()) is not None


# Note: test_loader_discovers_p0_5_demo_tools_and_agents removed
# as it depends on missing demo plugin directory


class _SlowSession:
    async def invoke_capability(
        self, _capability: str, _payload: dict, *, request_id: str
    ):
        await asyncio.sleep(0.05)
        return {"request_id": request_id}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_tool_bridge_wraps_timeout_as_failed_tool_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = object.__new__(capability_bridge_module.CoreCapabilityBridge)
    bridge._plugin_bridge = SimpleNamespace(
        _records={"sdk_demo_agent_tools": SimpleNamespace(session=_SlowSession())},
        _get_dispatch_token=lambda _event: "dispatch-token",
    )
    monkeypatch.setattr(
        capability_bridge_module.EventConverter,
        "core_to_sdk",
        lambda *_args, **_kwargs: {"session_id": "local-session", "text": "hello"},
    )

    handler = bridge._make_sdk_tool_handler(
        plugin_id="sdk_demo_agent_tools",
        tool_spec=LLMToolSpec(
            name="sdk_static_note",
            description="static tool",
            parameters_schema={"type": "object", "properties": {}},
            handler_ref="sdk_static_note",
            active=True,
        ),
        tool_call_timeout=0.01,
    )

    output = await handler(object(), query="slow")
    assert isinstance(output, str)
    payload = json.loads(output)
    assert payload["tool_name"] == "sdk_static_note"
    assert payload["success"] is False
    assert "timeout" in payload["content"].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_registered_llm_tool_rejects_non_mapping_tool_args() -> None:
    async def required_tool(required_text: str) -> str:
        return required_text

    dispatcher = CapabilityDispatcher(
        plugin_id="sdk_demo_agent_tools",
        peer=object(),
        capabilities=[],
        llm_tools=[
            LoadedLLMTool(
                spec=LLMToolSpec(
                    name="required_tool",
                    description="requires a string argument",
                    parameters_schema={"type": "object", "properties": {}},
                    active=True,
                ),
                callable=required_tool,
                owner=object(),
                plugin_id="sdk_demo_agent_tools",
            )
        ],
    )

    message = SimpleNamespace(
        id="tool-call-1",
        capability="internal.llm_tool.execute",
        input={
            "plugin_id": "sdk_demo_agent_tools",
            "tool_name": "required_tool",
            "tool_args": "not-a-dict",
            "event": "invalid-event-payload",
        },
    )

    with pytest.raises(TypeError, match="missing required argument 'required_text'"):
        await dispatcher.invoke(message, CancelToken())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_registered_llm_tool_injects_pep604_optional_event_and_context() -> None:
    async def optional_tool(
        event: MessageEvent | None = None,
        ctx: RuntimeContext | None = None,
    ) -> str:
        assert event is not None
        assert ctx is not None
        return f"{ctx.plugin_id}:{event.session_id}"

    dispatcher = CapabilityDispatcher(
        plugin_id="sdk_demo_agent_tools",
        peer=object(),
        capabilities=[],
        llm_tools=[
            LoadedLLMTool(
                spec=LLMToolSpec(
                    name="optional_tool",
                    description="uses optional event/context injections",
                    parameters_schema={"type": "object", "properties": {}},
                    active=True,
                ),
                callable=optional_tool,
                owner=object(),
                plugin_id="sdk_demo_agent_tools",
            )
        ],
    )

    message = SimpleNamespace(
        id="tool-call-2",
        capability="internal.llm_tool.execute",
        input={
            "plugin_id": "sdk_demo_agent_tools",
            "tool_name": "optional_tool",
            "tool_args": {},
            "event": {"session_id": "session-42", "text": "hello"},
        },
    )

    output = await dispatcher.invoke(message, CancelToken())
    assert output == {
        "content": "sdk_demo_agent_tools:session-42",
        "success": True,
    }


@pytest.mark.unit
def test_provider_to_payload_normalizes_core_provider_type_enum() -> None:
    from astrbot.core.provider.entities import ProviderMeta as CoreProviderMeta
    from astrbot.core.provider.entities import ProviderType as CoreProviderType

    provider = SimpleNamespace(
        meta=lambda: CoreProviderMeta(
            id="provider-1",
            model="gpt-test",
            type="openai",
            provider_type=CoreProviderType.CHAT_COMPLETION,
        )
    )

    payload = capability_bridge_module.CoreCapabilityBridge._provider_to_payload(
        provider
    )
    assert payload is not None
    assert payload["provider_type"] == "chat_completion"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_tool_loop_run_accepts_dict_contexts_from_sdk_payload() -> None:
    bridge = object.__new__(capability_bridge_module.CoreCapabilityBridge)
    captured: dict[str, object] = {}

    class _FakeStarContext:
        async def tool_loop_agent(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                completion_text="done",
                usage=None,
                tools_call_ids=[],
                role="assistant",
                reasoning_content="",
                reasoning_signature=None,
                to_openai_tool_calls=lambda: [],
            )

    bridge._star_context = _FakeStarContext()
    bridge._resolve_plugin_id = lambda _request_id: "sdk_demo_agent_tools"
    bridge._resolve_event_request_context = lambda _request_id, _payload: (
        SimpleNamespace(event="fake-event")
    )
    bridge._resolve_current_chat_provider_id = lambda _request_context: "provider-1"
    bridge._build_sdk_toolset = lambda **_kwargs: None

    payload = {
        "prompt": "hello",
        "contexts": [{"role": "user", "content": "from-sdk"}],
    }
    output = await bridge._agent_tool_loop_run("request-1", payload, None)

    assert output["text"] == "done"
    assert captured["contexts"] == payload["contexts"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_platform_send_by_session_supports_proactive_send_without_dispatch_token() -> (
    None
):
    sent: dict[str, object] = {}

    async def fake_send_message(session: str, chain) -> None:
        sent["session"] = session
        sent["chain"] = chain

    bridge = object.__new__(capability_bridge_module.CoreCapabilityBridge)
    bridge._star_context = SimpleNamespace(send_message=fake_send_message)
    bridge._plugin_bridge = SimpleNamespace(
        resolve_request_session=lambda _request_id: None,
        before_platform_send=lambda _dispatch_token: None,
        mark_platform_send=lambda _dispatch_token: "should-not-be-used",
        get_request_context_by_token=lambda _dispatch_token: None,
    )

    output = await bridge._platform_send_by_session(
        "request-1",
        {
            "session": "demo:private:user-1",
            "chain": [{"type": "text", "data": {"text": "hello proactive"}}],
        },
        None,
    )

    assert sent["session"] == "demo:private:user-1"
    assert sent["chain"].get_plain_text() == "hello proactive"
    assert output["message_id"].startswith("sdk_proactive_")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_platform_get_group_and_members_are_current_event_only() -> None:
    class _FakeEvent:
        unified_msg_origin = "demo:group:room-7"

        async def get_group(self):
            member = SimpleNamespace(user_id="user-1", nickname="Alice", role="admin")
            return SimpleNamespace(
                group_id="room-7",
                group_name="Room 7",
                group_avatar="",
                group_owner="owner-1",
                group_admins=["owner-1", "user-1"],
                members=[member],
            )

    request_context = SimpleNamespace(
        event=_FakeEvent(),
        cancelled=False,
        dispatch_token="dispatch-1",
    )
    bridge = object.__new__(capability_bridge_module.CoreCapabilityBridge)
    bridge._plugin_bridge = SimpleNamespace(
        resolve_request_session=lambda _request_id: request_context,
        get_request_context_by_token=lambda _dispatch_token: request_context,
    )

    group = await bridge._platform_get_group(
        "request-1",
        {"session": "demo:group:room-7"},
        None,
    )
    members = await bridge._platform_get_members(
        "request-1",
        {"session": "demo:group:room-7"},
        None,
    )

    assert group["group"]["group_id"] == "room-7"
    assert members["members"] == [
        {"user_id": "user-1", "nickname": "Alice", "role": "admin"}
    ]

    with pytest.raises(AstrBotError, match="current event session"):
        await bridge._platform_get_members(
            "request-1",
            {"session": "demo:group:another-room"},
            None,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_platform_list_instances_uses_platform_manager_metadata() -> None:
    class _FakeMeta:
        def __init__(self, platform_id: str, name: str, display_name: str) -> None:
            self.id = platform_id
            self.name = name
            self.adapter_display_name = display_name

    class _FakePlatform:
        def __init__(self, platform_id: str, name: str, display_name: str) -> None:
            self._meta = _FakeMeta(platform_id, name, display_name)
            self.status = SimpleNamespace(value="running")

        def meta(self):
            return self._meta

    bridge = object.__new__(capability_bridge_module.CoreCapabilityBridge)
    bridge._star_context = SimpleNamespace(
        platform_manager=SimpleNamespace(
            get_insts=lambda: [
                _FakePlatform("qq-main", "qq_official", "QQ"),
                _FakePlatform("webchat", "webchat", "WebChat"),
            ]
        )
    )

    output = await bridge._platform_list_instances("request-1", {}, None)
    assert output == {
        "platforms": [
            {
                "id": "qq-main",
                "name": "QQ",
                "type": "qq_official",
                "status": "running",
            },
            {
                "id": "webchat",
                "name": "WebChat",
                "type": "webchat",
                "status": "running",
            },
        ]
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_registry_command_register_validates_and_forwards_to_bridge() -> None:
    captured: dict[str, object] = {}
    bridge = object.__new__(capability_bridge_module.CoreCapabilityBridge)
    bridge._resolve_plugin_id = lambda _request_id: "sdk-demo"
    bridge._plugin_bridge = SimpleNamespace(
        register_dynamic_command_route=lambda **kwargs: captured.update(kwargs)
    )

    await bridge._registry_command_register(
        "request-1",
        {
            "source_event_type": "astrbot_loaded",
            "command_name": "hello",
            "handler_full_name": "sdk-demo:demo.handler",
            "desc": "demo",
            "priority": 3,
            "use_regex": True,
        },
        None,
    )
    assert captured == {
        "plugin_id": "sdk-demo",
        "command_name": "hello",
        "handler_full_name": "sdk-demo:demo.handler",
        "desc": "demo",
        "priority": 3,
        "use_regex": True,
    }

    with pytest.raises(AstrBotError, match="astrbot_loaded/platform_loaded"):
        await bridge._registry_command_register(
            "request-2",
            {
                "source_event_type": "message",
                "command_name": "hello",
                "handler_full_name": "sdk-demo:demo.handler",
            },
            None,
        )

    with pytest.raises(AstrBotError, match="ignore_prefix=True"):
        await bridge._registry_command_register(
            "request-3",
            {
                "source_event_type": "platform_loaded",
                "command_name": "hello",
                "handler_full_name": "sdk-demo:demo.handler",
                "ignore_prefix": True,
            },
            None,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_plugin_and_service_capabilities_reuse_existing_sp_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeSp:
        def __init__(self) -> None:
            self.store = {
                ("umo", "demo:group:room-7", "session_plugin_config"): {
                    "demo:group:room-7": {"disabled_plugins": ["sdk-disabled"]}
                },
                ("umo", "demo:group:room-7", "session_service_config"): {
                    "llm_enabled": False,
                    "tts_enabled": True,
                },
            }

        async def get_async(self, scope, scope_id, key, default=None):
            return self.store.get((scope, scope_id, key), default)

        async def put_async(self, scope, scope_id, key, value):
            self.store[(scope, scope_id, key)] = value

    fake_sp = _FakeSp()
    monkeypatch.setattr(capability_bridge_module, "_get_runtime_sp", lambda: fake_sp)

    bridge = object.__new__(capability_bridge_module.CoreCapabilityBridge)
    bridge._star_context = SimpleNamespace(
        get_all_stars=lambda: [SimpleNamespace(name="sdk-reserved", reserved=True)]
    )

    enabled = await bridge._session_plugin_is_enabled(
        "request-1",
        {"session": "demo:group:room-7", "plugin_name": "sdk-disabled"},
        None,
    )
    filtered = await bridge._session_plugin_filter_handlers(
        "request-1",
        {
            "session": "demo:group:room-7",
            "handlers": [
                {
                    "plugin_name": "sdk-disabled",
                    "handler_full_name": "sdk-disabled:main.on_message",
                    "trigger_type": "message",
                    "event_types": [],
                    "enabled": True,
                    "group_path": [],
                },
                {
                    "plugin_name": "sdk-reserved",
                    "handler_full_name": "sdk-reserved:main.on_message",
                    "trigger_type": "message",
                    "event_types": [],
                    "enabled": True,
                    "group_path": [],
                },
            ],
        },
        None,
    )
    llm_enabled = await bridge._session_service_is_llm_enabled(
        "request-1",
        {"session": "demo:group:room-7"},
        None,
    )
    tts_enabled = await bridge._session_service_is_tts_enabled(
        "request-1",
        {"session": "demo:group:room-7"},
        None,
    )

    await bridge._session_service_set_llm_status(
        "request-1",
        {"session": "demo:group:room-7", "enabled": True},
        None,
    )
    await bridge._session_service_set_tts_status(
        "request-1",
        {"session": "demo:group:room-7", "enabled": False},
        None,
    )

    assert enabled == {"enabled": False}
    assert [item["plugin_name"] for item in filtered["handlers"]] == ["sdk-reserved"]
    assert llm_enabled == {"enabled": False}
    assert tts_enabled == {"enabled": True}
    assert fake_sp.store[("umo", "demo:group:room-7", "session_service_config")] == {
        "llm_enabled": True,
        "tts_enabled": False,
    }
