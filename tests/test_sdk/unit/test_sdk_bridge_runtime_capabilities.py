# ruff: noqa: E402
from __future__ import annotations

import asyncio
import json
import sys
import types
from asyncio import Queue
from functools import partial
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call

import pytest


def _install_optional_dependency_stubs() -> None:
    def install(name: str, attrs: dict[str, object]) -> None:
        if name in sys.modules:
            return
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module

    install(
        "faiss",
        {
            "read_index": lambda *args, **kwargs: None,
            "write_index": lambda *args, **kwargs: None,
            "IndexFlatL2": type("IndexFlatL2", (), {}),
            "IndexIDMap": type("IndexIDMap", (), {}),
            "normalize_L2": lambda *args, **kwargs: None,
        },
    )
    install("pypdf", {"PdfReader": type("PdfReader", (), {})})
    install(
        "jieba",
        {
            "cut": lambda text, *args, **kwargs: text.split(),
            "lcut": lambda text, *args, **kwargs: text.split(),
        },
    )
    install("rank_bm25", {"BM25Okapi": type("BM25Okapi", (), {})})
    install(
        "aiocqhttp",
        {
            "CQHttp": type("CQHttp", (), {}),
            "Event": type("Event", (), {}),
        },
    )
    install(
        "aiocqhttp.exceptions",
        {"ActionFailed": type("ActionFailed", (Exception,), {})},
    )


_install_optional_dependency_stubs()

from astrbot_sdk import MessageSession
from astrbot_sdk.clients.registry import HandlerMetadata
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.protocol.descriptors import (
    CommandTrigger,
    EventTrigger,
    HandlerDescriptor,
    MessageTrigger,
    ParamSpec,
    PlatformFilterSpec,
    ScheduleTrigger,
)
from astrbot_sdk.schedule import ScheduleContext
from astrbot_sdk.testing import MockContext

from astrbot.core.cron.manager import CronJobManager
from astrbot.core.db.po import CronJob
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party import (
    ThirdPartyAgentSubStage,
)
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import ProviderRequest as CoreProviderRequest
from astrbot.core.sdk_bridge.event_payload import (
    build_inbound_event_snapshot,
    sanitize_sdk_extras,
)
from astrbot.core.sdk_bridge.plugin_bridge import SdkPluginBridge
from astrbot.core.star.context import Context as StarContext


@pytest.mark.unit
def test_message_event_extensions_and_local_stop_control() -> None:
    event = MessageEvent.from_payload(
        {
            "text": "hello",
            "session_id": "test-platform:private:user-1",
            "platform": "test-platform",
            "platform_id": "test-platform-id",
            "message_type": "private",
            "self_id": "bot-1",
            "sender_name": "Tester",
            "is_admin": True,
        }
    )

    assert event.unified_msg_origin == "test-platform:private:user-1"
    assert event.get_session_id() == "test-platform:private:user-1"
    assert event.get_platform_id() == "test-platform-id"
    assert event.get_message_type() == "private"
    assert event.is_private_chat() is True
    assert event.is_admin() is True

    event.stop_event()
    assert event.is_stopped() is True
    event.continue_event()
    assert event.is_stopped() is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mock_context_system_tools_and_memory_stats() -> None:
    ctx = MockContext(plugin_id="sdk-demo")

    data_dir = await ctx.get_data_dir()
    assert isinstance(data_dir, Path)
    assert data_dir.name == "sdk-demo"

    image_result = await ctx.text_to_image("hello sdk")
    assert image_result == "mock://text_to_image/hello sdk"

    html_result = await ctx.html_render("card.html", {"title": "AstrBot"})
    assert html_result == "mock://html_render/card.html"

    await ctx.memory.save("profile", {"name": "AstrBot"})
    await ctx.memory.save_with_ttl("temp", {"value": "cached"}, 60)
    stats = await ctx.memory.stats()

    assert stats["total_items"] == 2
    assert stats["plugin_id"] == "sdk-demo"
    assert stats["ttl_entries"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mock_context_metadata_save_plugin_config_round_trip() -> None:
    ctx = MockContext(plugin_id="sdk-demo")

    saved = await ctx.metadata.save_plugin_config({"chat_scope_mode": "global_default"})

    assert saved == {"chat_scope_mode": "global_default"}
    assert await ctx.metadata.get_plugin_config() == {
        "chat_scope_mode": "global_default"
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_platform_client_accepts_message_session() -> None:
    ctx = MockContext(plugin_id="sdk-demo")
    session = MessageSession(
        platform_id="test-platform",
        message_type="private",
        session_id="user-42",
    )

    await ctx.platform.send(session, "hello session")

    assert len(ctx.sent_messages) == 1
    assert ctx.sent_messages[0].session_id == "test-platform:private:user-42"
    assert ctx.sent_messages[0].text == "hello session"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mock_context_platform_and_session_managers() -> None:
    ctx = MockContext(plugin_id="sdk-demo")
    session = "test-platform:group:room-7"
    ctx.router.set_session_plugin_config(
        session,
        disabled_plugins=["sdk-disabled"],
    )
    ctx.router.set_session_service_config(
        session,
        llm_enabled=False,
        tts_enabled=False,
    )
    ctx.router.upsert_plugin(
        metadata={
            "name": "sdk-disabled",
            "display_name": "sdk-disabled",
            "reserved": False,
        },
        config={},
    )
    ctx.router.upsert_plugin(
        metadata={
            "name": "sdk-reserved",
            "display_name": "sdk-reserved",
            "reserved": True,
        },
        config={},
    )

    await ctx.platform.send_by_session(session, "hello proactive")
    group = await MessageEvent.from_payload(
        {
            "text": "hello",
            "session_id": session,
            "platform": "test-platform",
            "platform_id": "test-platform",
            "message_type": "group",
        },
        context=ctx,
    ).get_group()
    members = await ctx.platform.get_members(session)
    handlers = await ctx.session_plugins.filter_handlers_by_session(
        session,
        [
            HandlerMetadata(
                plugin_name="sdk-disabled",
                handler_full_name="sdk-disabled:main.on_message",
                trigger_type="message",
                description="disabled handler",
                event_types=[],
                enabled=True,
                group_path=[],
                priority=1,
                kind="handler",
                require_admin=False,
            ),
            HandlerMetadata(
                plugin_name="sdk-reserved",
                handler_full_name="sdk-reserved:main.on_message",
                trigger_type="message",
                description="reserved handler",
                event_types=[],
                enabled=True,
                group_path=[],
                priority=5,
                kind="hook",
                require_admin=True,
            ),
        ],
    )

    assert ctx.sent_messages[-1].session_id == session
    assert ctx.sent_messages[-1].chain == [
        {"type": "text", "data": {"text": "hello proactive"}}
    ]
    assert group is not None
    assert group["group_id"] == "room-7"
    assert len(members) == 2
    assert (
        await ctx.session_plugins.is_plugin_enabled_for_session(session, "sdk-disabled")
        is False
    )
    assert [item.plugin_name for item in handlers] == ["sdk-reserved"]
    assert handlers[0].description == "reserved handler"
    assert handlers[0].priority == 5
    assert handlers[0].kind == "hook"
    assert handlers[0].require_admin is True
    assert await ctx.session_services.is_llm_enabled_for_session(session) is False
    assert await ctx.session_services.should_process_llm_request(session) is False
    await ctx.session_services.set_llm_status_for_session(session, True)
    assert await ctx.session_services.is_llm_enabled_for_session(session) is True
    assert await ctx.session_services.is_tts_enabled_for_session(session) is False
    assert await ctx.session_services.should_process_tts_request(session) is False
    await ctx.session_services.set_tts_status_for_session(session, True)
    assert await ctx.session_services.is_tts_enabled_for_session(session) is True

    current = await ctx.conversations.get_current_conversation(
        session,
        create_if_not_exists=True,
    )
    assert current is not None
    assert current.session == session


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mock_context_platform_capabilities_respect_support_platforms() -> None:
    ctx = MockContext(
        plugin_id="sdk-demo",
        plugin_metadata={"support_platforms": ["telegram"]},
    )
    ctx.router.set_platform_instances(
        [
            {
                "id": "telegram-main",
                "name": "Telegram",
                "type": "telegram",
                "status": "running",
            },
            {
                "id": "qq-main",
                "name": "QQ",
                "type": "qq",
                "status": "running",
            },
        ]
    )

    platforms = await ctx.list_platforms()

    assert [platform.id for platform in platforms] == ["telegram-main"]
    assert await ctx.get_platform("qq") is None

    with pytest.raises(AstrBotError, match="does not support platform 'qq'"):
        await ctx.platform.send_by_session(
            "qq-main:private:user-1",
            "hello unsupported",
        )


@pytest.mark.unit
def test_message_session_round_trip() -> None:
    session = MessageSession.from_str("demo-platform:group:room-7")

    assert session.platform_id == "demo-platform"
    assert session.message_type == "group"
    assert session.session_id == "room-7"
    assert str(session) == "demo-platform:group:room-7"


@pytest.mark.unit
def test_message_session_normalizes_legacy_message_type_aliases() -> None:
    private_session = MessageSession.from_str("demo-platform:FriendMessage:user-1")
    group_session = MessageSession(
        platform_id="demo-platform",
        message_type="GroupMessage",
        session_id="room-7",
    )
    other_session = MessageSession(
        platform_id="demo-platform",
        message_type="channel",
        session_id="thread-3",
    )

    assert private_session.message_type == "private"
    assert str(private_session) == "demo-platform:private:user-1"
    assert group_session.message_type == "group"
    assert str(group_session) == "demo-platform:group:room-7"
    assert other_session.message_type == "other"
    assert str(other_session) == "demo-platform:other:thread-3"


class _EventConverterProbe:
    def __init__(self) -> None:
        self.is_wake = False
        self.is_at_or_wake_command = False
        self.unified_msg_origin = "demo-platform:private:user-1"
        self._extras = {
            "serializable": {"value": 1},
            "callback": partial(str.upper, "demo"),
        }

    def get_message_type(self):
        return types.SimpleNamespace(value="private")

    def get_platform_id(self) -> str:
        return "demo-platform-id"

    def get_message_str(self) -> str:
        return "demo text"

    def get_sender_id(self) -> str:
        return "user-1"

    def get_group_id(self) -> str | None:
        return None

    def get_platform_name(self) -> str:
        return "demo-platform"

    def get_self_id(self) -> str:
        return "bot-1"

    def get_sender_name(self) -> str:
        return "Tester"

    def is_admin(self) -> bool:
        return False

    def get_message_outline(self) -> str:
        return "demo outline"

    def get_extra(self, key: str | None = None, default=None):
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    def get_messages(self):
        return [Plain("demo", convert=False)]


@pytest.mark.unit
def test_build_inbound_event_payload_sanitizes_non_serializable_extras() -> None:
    event = _EventConverterProbe()
    payload = build_inbound_event_snapshot(event).to_payload(
        dispatch_token="dispatch-1",
        plugin_id="sdk-demo",
        request_id="req-1",
        host_extras=sanitize_sdk_extras(event.get_extra()),
        sdk_local_extras={},
    )

    assert payload["extras"] == {"serializable": {"value": 1}}
    assert "callback" not in payload["extras"]


@pytest.mark.unit
def test_respond_stage_sdk_outline_supports_list_and_message_chain() -> None:
    chain_list = [Plain("hello", convert=False), Plain(" world", convert=False)]

    assert RespondStage._message_outline_for_sdk_event(chain_list) == "hello  world"
    assert (
        RespondStage._message_outline_for_sdk_event(MessageChain(chain_list))
        == "hello  world"
    )
    assert RespondStage._message_outline_for_sdk_event(None) == ""


@pytest.mark.unit
def test_result_decorate_stage_sdk_outline_supports_list_and_message_chain() -> None:
    chain_list = [Plain("hello", convert=False), Plain(" world", convert=False)]

    assert (
        ResultDecorateStage._message_outline_for_sdk_event(chain_list) == "hello  world"
    )
    assert (
        ResultDecorateStage._message_outline_for_sdk_event(MessageChain(chain_list))
        == "hello  world"
    )
    assert ResultDecorateStage._message_outline_for_sdk_event(None) == ""


class _OverlayFakeStarContext:
    def __init__(self) -> None:
        self.registered_web_apis = []
        self.cron_manager = object()

    def get_all_stars(self) -> list[object]:
        return []


class _ConcreteAstrMessageEvent(AstrMessageEvent):
    async def send(self, message):
        await super().send(message)


def _make_real_astr_event() -> AstrMessageEvent:
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "bot-1"
    message.session_id = "session-1"
    message.message_id = "message-1"
    message.sender = MessageMember(user_id="user-1", nickname="Tester")
    message.message = [Plain("hello", convert=False)]
    message.message_str = "hello"
    message.raw_message = None
    return _ConcreteAstrMessageEvent(
        message_str="hello",
        message_obj=message,
        platform_meta=PlatformMetadata(
            name="demo-platform",
            description="Demo",
            id="demo-platform",
        ),
        session_id="session-1",
    )


def _bind_real_event_to_overlay(
    bridge: SdkPluginBridge,
    *,
    dispatch_token: str = "dispatch-real",
    request_id: str = "req-1",
) -> tuple[AstrMessageEvent, object]:
    event = _make_real_astr_event()
    bridge._bind_dispatch_token(event, dispatch_token)
    bridge._request_overlays[dispatch_token] = bridge._ensure_request_overlay(
        dispatch_token,
        should_call_llm=True,
    )
    bridge._request_contexts[dispatch_token] = types.SimpleNamespace(
        plugin_id="sdk-demo",
        request_id=request_id,
        dispatch_token=dispatch_token,
        dispatch_state=types.SimpleNamespace(event=event),
        cancelled=False,
    )
    bridge._track_request_scope(
        dispatch_token=dispatch_token,
        request_id=request_id,
        plugin_id="sdk-demo",
    )
    overlay = bridge.get_request_overlay_by_token(dispatch_token)
    assert overlay is not None
    return event, overlay


class _CountingResult(MessageEventResult):
    def __init__(self) -> None:
        super().__init__(chain=[Plain("counted", convert=False)])
        self.stop_calls = 0
        self.continue_calls = 0

    def stop_event(self) -> _CountingResult:
        self.stop_calls += 1
        return super().stop_event()

    def continue_event(self) -> _CountingResult:
        self.continue_calls += 1
        return super().continue_event()


class _ScheduleDispatchStarContext(_OverlayFakeStarContext):
    def __init__(self) -> None:
        super().__init__()
        self.sent_messages: list[tuple[str, MessageChain]] = []

    async def send_message(self, session: str, message_chain: MessageChain) -> None:
        self.sent_messages.append((session, message_chain))


class _OverlayFakeEvent:
    def __init__(self) -> None:
        self.call_llm = False
        self._result = MessageEventResult(chain=[Plain("legacy", convert=False)])
        self._sdk_dispatch_token = "dispatch-1"

    def get_result(self) -> MessageEventResult | None:
        return self._result


class _TypedHookFakeEvent:
    def __init__(self) -> None:
        self.call_llm = False
        self.is_wake = False
        self.is_at_or_wake_command = False
        self.unified_msg_origin = "demo-platform:private:user-1"
        self._sdk_dispatch_token = "dispatch-typed"
        self._result = MessageEventResult(chain=[Plain("legacy", convert=False)])
        self._extras: dict[str, object] = {}

    def get_message_type(self):
        return types.SimpleNamespace(value="private")

    def get_platform_id(self) -> str:
        return "demo-platform"

    def get_message_str(self) -> str:
        return "hello"

    def get_sender_id(self) -> str:
        return "user-1"

    def get_group_id(self) -> str | None:
        return None

    def get_platform_name(self) -> str:
        return "demo-platform"

    def get_self_id(self) -> str:
        return "bot-1"

    def get_sender_name(self) -> str:
        return "Tester"

    def is_admin(self) -> bool:
        return False

    def get_message_outline(self) -> str:
        return "hello"

    def get_extra(self, key: str | None = None, default=None):
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    def get_messages(self):
        return [Plain("hello", convert=False)]

    def get_result(self) -> MessageEventResult | None:
        return self._result


class _TypedHookSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def invoke_handler(
        self,
        handler_id: str,
        event_payload: dict[str, object],
        *,
        request_id: str,
        args: dict[str, object],
    ) -> dict[str, object]:
        del request_id, args
        self.calls.append((handler_id, event_payload))
        return {
            "provider_request": {
                **dict(event_payload["provider_request"]),
                "system_prompt": "decorated memory prompt",
                "contexts": [
                    {"role": "system", "content": "memory: user likes tea"},
                ],
            },
            "event_result": {
                "type": "chain",
                "chain": [{"type": "text", "data": {"text": "decorated result"}}],
            },
        }


class _RequestScopedHookSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def invoke_handler(
        self,
        handler_id: str,
        event_payload: dict[str, object],
        *,
        request_id: str,
        args: dict[str, object],
    ) -> dict[str, object]:
        del request_id, args
        self.calls.append((handler_id, event_payload))
        if handler_id.endswith("capture_reply"):
            return {"sdk_local_extras": {"last_reply": "reply text"}}
        return {"sdk_local_extras": {}}


class _ChainedExtrasHookSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], str]] = []

    async def invoke_handler(
        self,
        handler_id: str,
        event_payload: dict[str, object],
        *,
        request_id: str,
        args: dict[str, object],
    ) -> dict[str, object]:
        del args
        self.calls.append((handler_id, event_payload, request_id))
        if handler_id.endswith("first"):
            return {"sdk_local_extras": {"stage": "first", "shared": "one"}}
        if handler_id.endswith("second"):
            return {"sdk_local_extras": {"stage": "second", "shared": "two"}}
        return {}


class _FailThenRecoverHookSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], str]] = []

    async def invoke_handler(
        self,
        handler_id: str,
        event_payload: dict[str, object],
        *,
        request_id: str,
        args: dict[str, object],
    ) -> dict[str, object]:
        del args
        self.calls.append((handler_id, event_payload, request_id))
        if handler_id.endswith("first"):
            raise RuntimeError("first handler failed")
        return {"sdk_local_extras": {"last_reply": "recovered"}}


class _SystemEventSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def invoke_handler(
        self,
        handler_id: str,
        event_payload: dict[str, object],
        *,
        request_id: str,
        args: dict[str, object],
    ) -> dict[str, object]:
        del request_id, args
        self.calls.append((handler_id, event_payload))
        return {}


class _OrderedSystemEventSession:
    def __init__(
        self,
        call_order: list[str],
        *,
        fail_on: set[str] | None = None,
    ) -> None:
        self.call_order = call_order
        self.fail_on = fail_on or set()

    async def invoke_handler(
        self,
        handler_id: str,
        event_payload: dict[str, object],
        *,
        request_id: str,
        args: dict[str, object],
    ) -> dict[str, object]:
        del event_payload, request_id, args
        self.call_order.append(handler_id)
        if handler_id in self.fail_on:
            raise RuntimeError(f"{handler_id} failed")
        return {}


class _RequestScopeSession:
    def __init__(self) -> None:
        self.request_ids: list[str] = []

    async def invoke_handler(
        self,
        handler_id: str,
        event_payload: dict[str, object],
        *,
        request_id: str,
        args: dict[str, object],
    ) -> dict[str, object]:
        del handler_id, event_payload, args
        self.request_ids.append(request_id)
        return {}


class _CancelableSession:
    def __init__(self, *, peer: object | None = None) -> None:
        self.peer = peer
        self.cancel = AsyncMock()
        self.stop = AsyncMock()


class _TemporaryClient:
    def __init__(self) -> None:
        self.cleaned = False

    async def cleanup(self) -> None:
        self.cleaned = True


class _ScheduleDispatchSession:
    def __init__(self, bridge: SdkPluginBridge) -> None:
        self.bridge = bridge
        self.request_ids: list[str] = []
        self.event_capability_results: list[dict[str, object]] = []

    async def invoke_handler(
        self,
        handler_id: str,
        event_payload: dict[str, object],
        *,
        request_id: str,
        args: dict[str, object],
    ) -> dict[str, object]:
        del handler_id, event_payload, args
        self.request_ids.append(request_id)
        request_context = self.bridge.resolve_request_session(request_id)
        assert request_context is not None
        assert request_context.has_event is False
        send_result = await self.bridge.capability_bridge.execute(
            "platform.send",
            {
                "session": "demo-platform:private:user-1",
                "text": "scheduled hello",
            },
            stream=False,
            cancel_token=None,
            request_id=request_id,
        )
        assert str(send_result["message_id"]).startswith("sdk_")
        event_result = await self.bridge.capability_bridge.execute(
            "system.event.send_typing",
            {},
            stream=False,
            cancel_token=None,
            request_id=request_id,
        )
        self.event_capability_results.append(event_result)
        return {}


class _CaptureSystemBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def dispatch_system_event(
        self,
        event_type: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        self.calls.append((event_type, dict(payload or {})))


class _FakePlatform:
    def __init__(self) -> None:
        self.sent: list[tuple[object, MessageChain]] = []

    class _Meta:
        id = "demo"
        name = "Demo Platform"

    def meta(self):
        return self._Meta()

    async def send_by_session(self, session, message_chain: MessageChain) -> None:
        self.sent.append((session, message_chain))


class _ThirdPartyDispatchBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], object | None]] = []

    async def dispatch_message_event(
        self,
        event_type: str,
        event,
        payload: dict[str, object] | None = None,
        *,
        provider_request=None,
        **_: object,
    ) -> None:
        del event
        self.calls.append((event_type, dict(payload or {}), provider_request))


class _ThirdPartyFakeEvent:
    def __init__(self) -> None:
        self.message_str = "hello runner"
        self.unified_msg_origin = "demo:private:user-1"
        self.message_obj = types.SimpleNamespace(message=[])
        self.extra: dict[str, object] = {}

    def set_extra(self, key: str, value: object) -> None:
        self.extra[key] = value


class _DecoratingResultFakeBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get_effective_result(
        self, event: _DecoratingResultFakeEvent
    ) -> MessageEventResult | None:
        return event.get_result()

    async def dispatch_message_event(
        self,
        event_type: str,
        event: _DecoratingResultFakeEvent,
        payload: dict[str, str],
        **_: object,
    ) -> None:
        self.calls.append((event_type, payload))


class _DecoratingResultFakeEvent:
    def __init__(self) -> None:
        self.plugins_name: list[str] = []
        self._stopped = False
        self._result = MessageEventResult(
            chain=[Plain("legacy", convert=False)],
            result_content_type=ResultContentType.STREAMING_FINISH,
        )

    def get_result(self) -> MessageEventResult | None:
        return self._result

    def is_stopped(self) -> bool:
        return self._stopped


@pytest.mark.unit
@pytest.mark.asyncio
async def test_result_decorate_stage_dispatches_sdk_outline_for_legacy_chain_list() -> (
    None
):
    stage = ResultDecorateStage()
    bridge = _DecoratingResultFakeBridge()
    event = _DecoratingResultFakeEvent()

    stage.sdk_plugin_bridge = bridge
    stage.content_safe_check_reply = False
    stage.content_safe_check_stage = None

    async for _ in stage.process(event):
        pass

    assert bridge.calls == [
        (
            "decorating_result",
            {
                "message_outline": "legacy",
                "result_content_type": "streaming_finish",
            },
        ),
    ]


@pytest.mark.unit
def test_sdk_request_overlay_controls_llm_result_and_whitelist() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    event = _OverlayFakeEvent()
    request_id = "req-1"

    bridge._request_id_to_token[request_id] = "dispatch-1"
    bridge._request_overlays["dispatch-1"] = bridge._ensure_request_overlay(
        "dispatch-1",
        should_call_llm=False,
    )

    assert bridge.get_effective_should_call_llm(event) is False
    assert bridge.request_llm_for_request(request_id) is True
    assert bridge.get_effective_should_call_llm(event) is True

    payload = {
        "type": "chain",
        "chain": [{"type": "plain", "data": {"text": "overlay"}}],
    }
    assert bridge.set_result_for_request(request_id, payload) is True
    effective_result = bridge.get_effective_result(event)
    assert effective_result is not None
    assert effective_result.chain.get_plain_text() == "overlay"

    effective_result.chain.chain.append(Plain("cached", convert=False))
    result_payload = bridge.get_result_payload_for_request(request_id)
    assert result_payload is not None
    assert result_payload["chain"][1]["data"]["text"] == "cached"

    assert (
        bridge.set_handler_whitelist_for_request(request_id, {"sdk-a", "sdk-b"}) is True
    )
    assert bridge.get_handler_whitelist_for_request(request_id) == {
        "sdk-a",
        "sdk-b",
    }

    assert bridge.clear_result_for_request(request_id) is True
    assert bridge.get_effective_result(event) is None


@pytest.mark.unit
def test_sdk_request_overlay_payload_reads_return_deep_copies() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    request_id = "req-1"

    bridge._request_id_to_token[request_id] = "dispatch-1"
    bridge._request_overlays["dispatch-1"] = bridge._ensure_request_overlay(
        "dispatch-1",
        should_call_llm=False,
    )
    assert bridge.set_result_for_request(
        request_id,
        {
            "type": "chain",
            "chain": [{"type": "text", "data": {"text": "overlay"}}],
        },
    )

    first = bridge.get_result_payload_for_request(request_id)
    assert first is not None
    first["chain"][0]["data"]["text"] = "mutated"

    second = bridge.get_result_payload_for_request(request_id)
    assert second is not None
    assert second["chain"][0]["data"]["text"] == "overlay"


@pytest.mark.unit
def test_astr_message_event_binding_updates_overlay_and_preserves_result_after_close() -> (
    None
):
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    dispatch_token = "dispatch-real"
    event, overlay = _bind_real_event_to_overlay(
        bridge,
        dispatch_token=dispatch_token,
        request_id="req-1",
    )

    event.set_result(MessageEventResult().message("binding result"))
    assert event.get_result() is not None
    assert event.get_result().get_plain_text() == "binding result"

    assert overlay.result_payload is not None
    assert overlay.result_payload["chain"][0]["data"]["text"] == "binding result"

    event.stop_event()
    assert event.is_stopped() is True
    assert overlay.result_stopped is True
    assert overlay.should_call_llm is False

    event.continue_event()
    assert event.is_stopped() is False
    assert overlay.result_stopped is False
    assert overlay.should_call_llm is False

    bridge.close_request_overlay_for_event(event)

    assert not hasattr(event, "_sdk_result_binding")
    assert event.get_result() is not None
    assert event.get_result().get_plain_text() == "binding result"


@pytest.mark.unit
def test_stop_and_continue_do_not_reserialize_existing_result_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    event, overlay = _bind_real_event_to_overlay(bridge)
    serialize_calls = 0
    original = bridge._legacy_result_to_sdk_payload

    def _counting_serializer(result: MessageEventResult | None):
        nonlocal serialize_calls
        serialize_calls += 1
        return original(result)

    monkeypatch.setattr(bridge, "_legacy_result_to_sdk_payload", _counting_serializer)

    event.set_result(MessageEventResult().message("binding result"))
    assert serialize_calls == 1
    assert overlay.result_payload is not None

    event.stop_event()
    event.continue_event()

    assert serialize_calls == 1
    assert overlay.result_payload is not None
    assert overlay.result_payload["chain"][0]["data"]["text"] == "binding result"
    assert overlay.result_stopped is False
    assert overlay.should_call_llm is False


@pytest.mark.unit
def test_get_effective_result_for_token_is_idempotent_when_stop_state_aligned() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    dispatch_token = "dispatch-real"
    bridge._request_overlays[dispatch_token] = bridge._ensure_request_overlay(
        dispatch_token,
        should_call_llm=True,
    )
    overlay = bridge.get_request_overlay_by_token(dispatch_token)
    assert overlay is not None

    result = _CountingResult()
    result.continue_event()
    result.stop_calls = 0
    result.continue_calls = 0
    overlay.result_object = result
    overlay.result_is_set = True
    overlay.result_stopped = False

    first = bridge._get_effective_result_for_token(dispatch_token)
    second = bridge._get_effective_result_for_token(dispatch_token)
    assert first is result
    assert second is result
    assert result.stop_calls == 0
    assert result.continue_calls == 0

    result.result_type = result.result_type.STOP
    overlay.result_stopped = True
    third = bridge._get_effective_result_for_token(dispatch_token)
    fourth = bridge._get_effective_result_for_token(dispatch_token)
    assert third is result
    assert fourth is result
    assert result.stop_calls == 0
    assert result.continue_calls == 0


@pytest.mark.unit
def test_get_effective_result_for_token_lazily_creates_stopped_result_once() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    dispatch_token = "dispatch-real"
    bridge._request_overlays[dispatch_token] = bridge._ensure_request_overlay(
        dispatch_token,
        should_call_llm=True,
    )
    overlay = bridge.get_request_overlay_by_token(dispatch_token)
    assert overlay is not None
    overlay.result_is_set = True
    overlay.result_stopped = True

    first = bridge._get_effective_result_for_token(dispatch_token)
    second = bridge._get_effective_result_for_token(dispatch_token)

    assert first is not None
    assert first.is_stopped() is True
    assert second is first


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_bridge_keeps_request_scope_after_event_hook_returns() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    session = _RequestScopeSession()
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-demo",
            load_order=0,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.observe",
                        trigger=EventTrigger(event_type="after_message_sent"),
                    ),
                    declaration_order=0,
                )
            ],
            session=session,
        )
    }

    event = _TypedHookFakeEvent()
    bridge._request_overlays["dispatch-typed"] = bridge._ensure_request_overlay(
        "dispatch-typed",
        should_call_llm=False,
    )

    await bridge.dispatch_message_event(
        "after_message_sent",
        event,
        {"message_outline": "reply text"},
    )

    parent_request_id = session.request_ids[0]

    llm_state = await bridge.capability_bridge.execute(
        "system.event.llm.request",
        {"_request_scope_id": parent_request_id},
        stream=False,
        cancel_token=None,
        request_id="child-llm-request",
    )
    assert llm_state == {"should_call_llm": True, "requested_llm": True}

    result_payload = {
        "type": "chain",
        "chain": [{"type": "text", "data": {"text": "reply text"}}],
    }
    set_result = await bridge.capability_bridge.execute(
        "system.event.result.set",
        {
            "_request_scope_id": parent_request_id,
            "result": result_payload,
        },
        stream=False,
        cancel_token=None,
        request_id="child-result-set",
    )
    assert set_result == {"result": result_payload}

    whitelist = await bridge.capability_bridge.execute(
        "system.event.handler_whitelist.set",
        {
            "_request_scope_id": parent_request_id,
            "plugin_names": ["sdk-demo"],
        },
        stream=False,
        cancel_token=None,
        request_id="child-whitelist-set",
    )
    assert whitelist == {"plugin_names": ["sdk-demo"]}

    bridge.close_request_overlay_for_event(event)
    assert bridge.get_request_overlay_by_request_id(parent_request_id) is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_schedule_handler_tracks_request_scope_for_proactive_send() -> None:
    star_context = _ScheduleDispatchStarContext()
    bridge = SdkPluginBridge(star_context)
    session = _ScheduleDispatchSession(bridge)
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-demo",
            load_order=0,
            session=session,
        )
    }

    await bridge._invoke_schedule_handler(
        plugin_id="sdk-demo",
        handler_id="sdk-demo:main.tick",
        trigger=ScheduleTrigger(interval_seconds=60),
    )

    assert len(star_context.sent_messages) == 1
    assert star_context.sent_messages[0][0] == "demo-platform:private:user-1"
    assert star_context.sent_messages[0][1].get_plain_text() == "scheduled hello"
    assert session.event_capability_results == [{"supported": False}]
    request_context = bridge.resolve_request_session(session.request_ids[0])
    assert request_context is not None
    assert request_context.has_event is False
    bridge._close_request_overlay(request_context.dispatch_token)
    assert bridge.resolve_request_session(session.request_ids[0]) is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_schedule_runner_ignores_scheduler_payload_kwargs() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    captured: list[dict[str, object]] = []

    async def _capture_invoke_schedule_handler(**kwargs: object) -> None:
        captured.append(dict(kwargs))

    bridge._invoke_schedule_handler = _capture_invoke_schedule_handler  # type: ignore[method-assign]
    runner = bridge._build_schedule_runner(
        plugin_id="sdk-demo",
        handler_id="sdk-demo:main.tick",
        trigger=ScheduleTrigger(interval_seconds=60),
    )

    await runner(interval_seconds=60)

    assert captured == [
        {
            "plugin_id": "sdk-demo",
            "handler_id": "sdk-demo:main.tick",
            "trigger": ScheduleTrigger(interval_seconds=60),
        }
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cron_manager_replays_interval_payload_to_sdk_schedule_runner() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    captured: list[dict[str, object]] = []

    async def _capture_invoke_schedule_handler(**kwargs: object) -> None:
        captured.append(dict(kwargs))

    bridge._invoke_schedule_handler = _capture_invoke_schedule_handler  # type: ignore[method-assign]
    cron_manager = CronJobManager(MagicMock())
    cron_manager._basic_handlers["sdk-schedule-job"] = bridge._build_schedule_runner(
        plugin_id="sdk-demo",
        handler_id="sdk-demo:main.tick",
        trigger=ScheduleTrigger(interval_seconds=60),
    )
    job = CronJob(
        job_id="sdk-schedule-job",
        name="sdk schedule",
        job_type="basic",
        payload={"interval_seconds": 60},
        enabled=True,
        persistent=False,
        run_once=False,
    )

    await cron_manager._run_basic_job(job)

    assert captured == [
        {
            "plugin_id": "sdk-demo",
            "handler_id": "sdk-demo:main.tick",
            "trigger": ScheduleTrigger(interval_seconds=60),
        }
    ]


@pytest.mark.unit
def test_build_schedule_payload_exposes_interval_metadata() -> None:
    payload = SdkPluginBridge._build_schedule_payload(
        plugin_id="sdk-demo",
        handler_id="sdk-demo:main.tick",
        trigger=ScheduleTrigger(interval_seconds=60, timezone="Asia/Shanghai"),
        job=types.SimpleNamespace(
            job_id="job-interval",
            name="MoodLog interval dispatcher",
            description="Run periodic maintenance",
            job_type="basic",
            timezone="Asia/Shanghai",
        ),
    )

    assert payload["event_type"] == "schedule"
    assert payload["text"] == ""
    assert payload["schedule"] == {
        "schedule_id": "sdk-demo:sdk-demo:main.tick",
        "job_id": "job-interval",
        "plugin_id": "sdk-demo",
        "handler_id": "sdk-demo:main.tick",
        "name": "MoodLog interval dispatcher",
        "description": "Run periodic maintenance",
        "job_type": "basic",
        "trigger_kind": "interval",
        "cron": None,
        "interval_seconds": 60,
        "timezone": "Asia/Shanghai",
        "scheduled_at": payload["schedule"]["scheduled_at"],
    }
    assert isinstance(payload["schedule"]["scheduled_at"], str)
    schedule = ScheduleContext.from_payload(payload)
    assert schedule.job_id == "job-interval"
    assert schedule.name == "MoodLog interval dispatcher"
    assert schedule.description == "Run periodic maintenance"
    assert schedule.job_type == "basic"
    assert schedule.timezone == "Asia/Shanghai"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_register_schedule_handlers_passes_trigger_config_to_cron_manager() -> (
    None
):
    cron_manager = types.SimpleNamespace(
        add_basic_job=AsyncMock(
            side_effect=[
                types.SimpleNamespace(
                    job_id="job-interval",
                    name="Interval maintenance",
                    description="Run periodic maintenance",
                    job_type="basic",
                    timezone="Asia/Shanghai",
                ),
                types.SimpleNamespace(
                    job_id="job-cron",
                    name="Morning mood sweep",
                    description="Run morning maintenance",
                    job_type="basic",
                    timezone=None,
                ),
            ]
        )
    )
    star_context = _OverlayFakeStarContext()
    star_context.cron_manager = cron_manager
    bridge = SdkPluginBridge(star_context)
    record = types.SimpleNamespace(
        plugin_id="sdk-demo",
        handlers=[
            types.SimpleNamespace(
                handler_id="sdk-demo:main.interval",
                descriptor=HandlerDescriptor(
                    id="sdk-demo:main.interval",
                    trigger=ScheduleTrigger(
                        interval_seconds=60,
                        name="Interval maintenance",
                        timezone="Asia/Shanghai",
                    ),
                    description="Run periodic maintenance",
                ),
            ),
            types.SimpleNamespace(
                handler_id="sdk-demo:main.cron",
                descriptor=HandlerDescriptor(
                    id="sdk-demo:main.cron",
                    trigger=ScheduleTrigger(
                        cron="0 9 * * *",
                        name="Morning mood sweep",
                    ),
                    description="Run morning maintenance",
                ),
            ),
        ],
    )

    await bridge._register_schedule_handlers(record)

    assert cron_manager.add_basic_job.await_count == 2
    first_call = cron_manager.add_basic_job.await_args_list[0].kwargs
    second_call = cron_manager.add_basic_job.await_args_list[1].kwargs
    assert first_call["name"] == "Interval maintenance"
    assert first_call["interval_seconds"] == 60
    assert first_call["cron_expression"] is None
    assert first_call["description"] == "Run periodic maintenance"
    assert first_call["timezone"] == "Asia/Shanghai"
    assert callable(first_call["handler"])
    assert second_call["name"] == "Morning mood sweep"
    assert second_call["cron_expression"] == "0 9 * * *"
    assert second_call["interval_seconds"] is None
    assert second_call["description"] == "Run morning maintenance"
    assert second_call["timezone"] is None
    assert callable(second_call["handler"])
    assert bridge._schedule_job_ids["sdk-demo"] == {"job-interval", "job-cron"}


@pytest.mark.unit
def test_unregister_http_api_empty_methods_remove_entire_route() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    bridge.register_http_api(
        plugin_id="sdk-demo",
        route="/health",
        methods=["GET", "POST"],
        handler_capability="http.health",
        description="health endpoint",
    )

    bridge.unregister_http_api(
        plugin_id="sdk-demo",
        route="/health",
        methods=["POST"],
    )
    assert bridge.list_http_apis("sdk-demo") == [
        {
            "route": "/health",
            "methods": ["GET"],
            "handler_capability": "http.health",
            "description": "health endpoint",
        }
    ]

    bridge.unregister_http_api(
        plugin_id="sdk-demo",
        route="/health",
        methods=[],
    )
    assert bridge.list_http_apis("sdk-demo") == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_dispatch_message_event_round_trips_typed_payloads() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    session = _TypedHookSession()
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-demo",
            load_order=0,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.on_llm_request",
                        trigger=EventTrigger(event_type="llm_request"),
                    ),
                    declaration_order=0,
                )
            ],
            session=session,
        )
    }

    event = _TypedHookFakeEvent()
    bridge._request_overlays["dispatch-typed"] = bridge._ensure_request_overlay(
        "dispatch-typed",
        should_call_llm=True,
    )
    request = CoreProviderRequest(
        prompt="hello",
        session_id=event.unified_msg_origin,
        contexts=[],
        system_prompt="original",
    )
    result = event.get_result()
    assert result is not None

    await bridge.dispatch_message_event(
        "llm_request",
        event,
        {"prompt": request.prompt, "provider_id": "demo-provider"},
        provider_request=request,
        event_result=result,
    )

    assert len(session.calls) == 1
    sent_payload = session.calls[0][1]
    assert sent_payload["provider_request"]["system_prompt"] == "original"
    assert request.system_prompt == "decorated memory prompt"
    assert request.contexts == [{"role": "system", "content": "memory: user likes tea"}]

    effective_result = bridge.get_effective_result(event)
    assert effective_result is not None
    assert effective_result.chain.get_plain_text() == "decorated result"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_persists_request_scoped_extras_and_sent_payloads() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    session = _RequestScopedHookSession()
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-demo",
            load_order=0,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.capture_reply",
                        trigger=EventTrigger(event_type="agent_done"),
                    ),
                    declaration_order=0,
                ),
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.persist_reply",
                        trigger=EventTrigger(event_type="after_message_sent"),
                    ),
                    declaration_order=1,
                ),
            ],
            session=session,
        )
    }

    event = _TypedHookFakeEvent()
    event._extras = {"host": "value"}
    bridge._request_overlays["dispatch-typed"] = bridge._ensure_request_overlay(
        "dispatch-typed",
        should_call_llm=True,
    )

    await bridge.dispatch_message_event(
        "agent_done", event, {"completion_text": "reply text"}
    )
    await bridge.dispatch_message_event(
        "after_message_sent",
        event,
        {
            "message_outline": "reply text",
            "sent_message_outline": "reply text",
            "sent_messages": [
                {"type": "text", "data": {"text": "reply text"}},
            ],
        },
    )

    assert len(session.calls) == 2
    first_payload = session.calls[0][1]
    second_payload = session.calls[1][1]
    assert first_payload["sdk_local_extras"] == {}
    assert second_payload["extras"] == {"host": "value", "last_reply": "reply text"}
    assert second_payload["sdk_local_extras"] == {"last_reply": "reply text"}
    assert second_payload["text"] == "hello"
    assert second_payload["message_outline"] == "reply text"
    assert second_payload["sent_message_outline"] == "reply text"
    assert second_payload["sent_messages"] == [
        {"type": "text", "data": {"text": "reply text"}}
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_chains_sdk_local_extras_across_matching_handlers() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    session = _ChainedExtrasHookSession()
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-demo",
            load_order=0,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.first",
                        trigger=EventTrigger(event_type="after_message_sent"),
                    ),
                    declaration_order=0,
                ),
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.second",
                        trigger=EventTrigger(event_type="after_message_sent"),
                    ),
                    declaration_order=1,
                ),
            ],
            session=session,
        )
    }

    event = _TypedHookFakeEvent()
    event._extras = {"host": "value"}
    bridge._request_overlays["dispatch-typed"] = bridge._ensure_request_overlay(
        "dispatch-typed",
        should_call_llm=False,
    )

    await bridge.dispatch_message_event(
        "after_message_sent",
        event,
        {"message_outline": "reply text"},
    )

    assert [call[0] for call in session.calls] == [
        "sdk-demo:main.first",
        "sdk-demo:main.second",
    ]
    second_payload = session.calls[1][1]
    assert second_payload["host_extras"] == {"host": "value"}
    assert second_payload["sdk_local_extras"] == {"stage": "first", "shared": "one"}
    assert second_payload["extras"] == {
        "host": "value",
        "stage": "first",
        "shared": "one",
    }
    overlay = bridge.get_request_overlay_by_token("dispatch-typed")
    assert overlay is not None
    assert overlay.sdk_local_extras == {"stage": "second", "shared": "two"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_dispatch_message_event_isolates_handler_exceptions() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    session = _FailThenRecoverHookSession()
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-demo",
            load_order=0,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.first",
                        trigger=EventTrigger(event_type="agent_done"),
                    ),
                    declaration_order=0,
                ),
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.second",
                        trigger=EventTrigger(event_type="agent_done"),
                    ),
                    declaration_order=1,
                ),
            ],
            session=session,
        )
    }

    event = _TypedHookFakeEvent()
    bridge._request_overlays["dispatch-typed"] = bridge._ensure_request_overlay(
        "dispatch-typed",
        should_call_llm=True,
    )

    await bridge.dispatch_message_event(
        "agent_done",
        event,
        {"completion_text": "reply text"},
    )

    assert [call[0] for call in session.calls] == [
        "sdk-demo:main.first",
        "sdk-demo:main.second",
    ]
    overlay = bridge.get_request_overlay_by_token("dispatch-typed")
    assert overlay is not None
    assert overlay.sdk_local_extras == {"last_reply": "recovered"}
    first_request_id = session.calls[0][2]
    second_request_id = session.calls[1][2]
    assert bridge.get_request_overlay_by_request_id(first_request_id) is not None
    assert bridge.get_request_overlay_by_request_id(second_request_id) is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_close_request_overlay_cleans_all_request_scopes() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    session = _ChainedExtrasHookSession()
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-demo",
            load_order=0,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.first",
                        trigger=EventTrigger(event_type="after_message_sent"),
                    ),
                    declaration_order=0,
                ),
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.second",
                        trigger=EventTrigger(event_type="after_message_sent"),
                    ),
                    declaration_order=1,
                ),
            ],
            session=session,
        )
    }

    event = _TypedHookFakeEvent()
    bridge._request_overlays["dispatch-typed"] = bridge._ensure_request_overlay(
        "dispatch-typed",
        should_call_llm=False,
    )

    await bridge.dispatch_message_event(
        "after_message_sent",
        event,
        {"message_outline": "reply text"},
    )

    request_ids = [call[2] for call in session.calls]
    assert len(request_ids) == 2
    for request_id in request_ids:
        assert bridge.get_request_overlay_by_request_id(request_id) is not None
        assert bridge.resolve_request_session(request_id) is not None

    bridge.close_request_overlay_for_event(event)

    for request_id in request_ids:
        assert bridge.get_request_overlay_by_request_id(request_id) is None
        assert bridge.resolve_request_session(request_id) is None
        assert request_id not in bridge._request_plugin_ids
    assert bridge.get_request_context_by_token("dispatch-typed") is None


@pytest.mark.unit
def test_sdk_bridge_persist_sdk_local_extras_handles_invalid_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    overlay = bridge._ensure_request_overlay("dispatch-typed", should_call_llm=False)
    overlay.sdk_local_extras = {"keep": "existing"}
    warning_spy = MagicMock()
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.logger.warning", warning_spy
    )

    bridge._persist_sdk_local_extras_from_handler(
        overlay,
        "invalid",
        plugin_id="sdk-demo",
        handler_id="sdk-demo:main.invalid",
    )
    assert overlay.sdk_local_extras == {"keep": "existing"}

    bridge._persist_sdk_local_extras_from_handler(
        overlay,
        {
            "valid": "value",
            "invalid": object(),
            "nested": [1, object(), {"safe": "ok", "drop": object()}],
        },
        plugin_id="sdk-demo",
        handler_id="sdk-demo:main.normalize",
    )
    assert overlay.sdk_local_extras == {
        "valid": "value",
        "nested": [1, {"safe": "ok"}],
    }
    warning_messages = [call.args[0] for call in warning_spy.call_args_list]
    assert any(
        "reason=%s recommended_fix=%s" in message for message in warning_messages
    )
    assert any(
        call.args[1:5] == ("sdk-demo", "sdk-demo:main.normalize", "invalid", "object")
        for call in warning_spy.call_args_list
    )

    bridge._persist_sdk_local_extras_from_handler(
        overlay,
        None,
        plugin_id="sdk-demo",
        handler_id="sdk-demo:main.clear",
    )
    assert overlay.sdk_local_extras == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_cancel_plugin_requests_cancels_active_worker_tasks() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    session = _CancelableSession(peer=object())
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            plugin_id="sdk-demo",
            session=session,
        )
    }
    overlay = bridge._ensure_request_overlay("dispatch-typed", should_call_llm=True)
    cleanup_task = overlay.cleanup_task
    request_task = asyncio.create_task(asyncio.sleep(60))
    bridge._plugin_requests = {
        "sdk-demo": {
            "req-1": types.SimpleNamespace(
                request_id="req-1",
                dispatch_token="dispatch-typed",
                task=request_task,
                logical_cancelled=False,
            )
        }
    }
    bridge._request_contexts["dispatch-typed"] = types.SimpleNamespace(
        plugin_id="sdk-demo",
        request_id="req-1",
        dispatch_token="dispatch-typed",
        dispatch_state=None,
        cancelled=False,
    )
    bridge._track_request_scope(
        dispatch_token="dispatch-typed",
        request_id="req-1",
        plugin_id="sdk-demo",
    )

    await bridge._cancel_plugin_requests("sdk-demo")
    await asyncio.sleep(0)

    session.cancel.assert_awaited_once_with("req-1")
    assert request_task.cancelled() is True
    assert bridge._plugin_requests == {}
    assert bridge.get_request_overlay_by_token("dispatch-typed") is None
    assert bridge.get_request_context_by_token("dispatch-typed") is None
    if cleanup_task is not None:
        assert cleanup_task.cancelled() is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_cancel_plugin_requests_marks_logical_cancel_without_worker() -> (
    None
):
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    session = _CancelableSession(peer=None)
    inflight = types.SimpleNamespace(
        request_id="req-1",
        dispatch_token="dispatch-typed",
        task=types.SimpleNamespace(done=lambda: False, cancel=MagicMock()),
        logical_cancelled=False,
    )
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            plugin_id="sdk-demo",
            session=session,
        )
    }
    bridge._plugin_requests = {"sdk-demo": {"req-1": inflight}}

    await bridge._cancel_plugin_requests("sdk-demo")

    session.cancel.assert_not_awaited()
    inflight.task.cancel.assert_not_called()
    assert inflight.logical_cancelled is True
    assert bridge._plugin_requests == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_handle_worker_closed_retries_once() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    plugin = types.SimpleNamespace(name="sdk-demo")
    record = types.SimpleNamespace(
        plugin_id="sdk-demo",
        plugin=plugin,
        load_order=3,
        session=object(),
        state="enabled",
        restart_attempted=False,
    )
    bridge._records = {"sdk-demo": record}
    bridge._cancel_plugin_requests = AsyncMock()  # type: ignore[method-assign]
    bridge._close_temporary_mcp_sessions = AsyncMock()  # type: ignore[method-assign]
    bridge._shutdown_local_mcp_servers = AsyncMock()  # type: ignore[method-assign]
    bridge._load_or_reload_plugin = AsyncMock()  # type: ignore[method-assign]

    await bridge._handle_worker_closed("sdk-demo")

    bridge._cancel_plugin_requests.assert_awaited_once_with("sdk-demo")
    bridge._close_temporary_mcp_sessions.assert_awaited_once_with("sdk-demo")
    bridge._shutdown_local_mcp_servers.assert_awaited_once_with(record)
    bridge._load_or_reload_plugin.assert_awaited_once_with(
        plugin,
        load_order=3,
        reset_restart_budget=False,
    )
    assert record.restart_attempted is True
    assert record.session is None


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["reloading", "disabled"])
async def test_sdk_bridge_handle_worker_closed_skips_retry_for_non_running_states(
    state: str,
) -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    record = types.SimpleNamespace(
        plugin_id="sdk-demo",
        plugin=types.SimpleNamespace(name="sdk-demo"),
        load_order=0,
        session=object(),
        state=state,
        restart_attempted=False,
    )
    bridge._records = {"sdk-demo": record}
    bridge._cancel_plugin_requests = AsyncMock()  # type: ignore[method-assign]
    bridge._close_temporary_mcp_sessions = AsyncMock()  # type: ignore[method-assign]
    bridge._shutdown_local_mcp_servers = AsyncMock()  # type: ignore[method-assign]
    bridge._load_or_reload_plugin = AsyncMock()  # type: ignore[method-assign]

    await bridge._handle_worker_closed("sdk-demo")

    bridge._load_or_reload_plugin.assert_not_awaited()
    assert record.session is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_handle_worker_closed_marks_record_failed_after_retry() -> (
    None
):
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    record = types.SimpleNamespace(
        plugin_id="sdk-demo",
        plugin=types.SimpleNamespace(name="sdk-demo"),
        load_order=0,
        session=object(),
        state="enabled",
        restart_attempted=True,
    )
    bridge._records = {"sdk-demo": record}
    bridge._http_routes = {"sdk-demo": [types.SimpleNamespace(route="/health")]}
    bridge._session_waiters = {"sdk-demo": {"waiter"}}
    bridge._cancel_plugin_requests = AsyncMock()  # type: ignore[method-assign]
    bridge._close_temporary_mcp_sessions = AsyncMock()  # type: ignore[method-assign]
    bridge._shutdown_local_mcp_servers = AsyncMock()  # type: ignore[method-assign]
    bridge._unregister_schedule_jobs = AsyncMock()  # type: ignore[method-assign]
    bridge._load_or_reload_plugin = AsyncMock()  # type: ignore[method-assign]

    await bridge._handle_worker_closed("sdk-demo")

    bridge._load_or_reload_plugin.assert_not_awaited()
    bridge._unregister_schedule_jobs.assert_awaited_once_with("sdk-demo")
    assert record.state == "failed"
    assert "sdk-demo" not in bridge._http_routes
    assert "sdk-demo" not in bridge._session_waiters


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_handle_worker_closed_clears_registered_skills_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    record = types.SimpleNamespace(
        plugin_id="sdk-demo",
        plugin=types.SimpleNamespace(name="sdk-demo"),
        load_order=0,
        session=object(),
        state="enabled",
        restart_attempted=True,
        skills={
            "sdk-demo.browser-helper": types.SimpleNamespace(
                to_registry_payload=lambda: {
                    "name": "sdk-demo.browser-helper",
                    "description": "demo skill",
                    "path": "/tmp/browser-helper/SKILL.md",
                    "skill_dir": "/tmp/browser-helper",
                }
            )
        },
    )
    bridge._records = {"sdk-demo": record}
    bridge._cancel_plugin_requests = AsyncMock()  # type: ignore[method-assign]
    bridge._close_temporary_mcp_sessions = AsyncMock()  # type: ignore[method-assign]
    bridge._shutdown_local_mcp_servers = AsyncMock()  # type: ignore[method-assign]
    bridge._unregister_schedule_jobs = AsyncMock()  # type: ignore[method-assign]
    published: list[str] = []
    monkeypatch.setattr(
        bridge,
        "_publish_plugin_skills",
        lambda plugin_id: published.append(plugin_id),
    )
    synced: list[str] = []

    async def _fake_sync_skills_to_active_sandboxes() -> None:
        synced.append("called")

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )

    await bridge._handle_worker_closed("sdk-demo")

    assert record.state == "failed"
    assert record.skills == {}
    assert published == ["sdk-demo"]
    assert synced == ["called"]


@pytest.mark.unit
def test_sdk_bridge_http_route_conflict_and_resolution() -> None:
    star_context = _OverlayFakeStarContext()
    star_context.registered_web_apis = [
        ("/legacy", object(), ["GET"], "legacy route"),
    ]
    bridge = SdkPluginBridge(star_context)

    with pytest.raises(AstrBotError, match="legacy plugin route"):
        bridge.register_http_api(
            plugin_id="sdk-demo",
            route="/legacy",
            methods=["GET"],
            handler_capability="http.legacy",
            description="legacy conflict",
        )

    bridge.register_http_api(
        plugin_id="sdk-a",
        route="health",
        methods=["POST", "GET"],
        handler_capability="http.health",
        description="sdk health",
    )
    with pytest.raises(AstrBotError, match="SDK plugin route"):
        bridge.register_http_api(
            plugin_id="sdk-b",
            route="/health",
            methods=["GET"],
            handler_capability="http.other",
            description="sdk conflict",
        )

    record_a = types.SimpleNamespace(plugin_id="sdk-a", load_order=1)
    bridge._records = {
        "sdk-a": record_a,
        "sdk-b": types.SimpleNamespace(plugin_id="sdk-b", load_order=2),
    }

    resolved = bridge._resolve_http_route("health", "get")
    assert resolved is not None
    resolved_record, resolved_route = resolved
    assert resolved_record is record_a
    assert resolved_route.route == "/health"
    assert resolved_route.methods == ("GET", "POST")
    assert bridge._resolve_http_route("/health", "DELETE") is None


@pytest.mark.unit
def test_register_http_api_logs_internal_and_public_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.astrbot_config",
        {"dashboard": {"host": "0.0.0.0", "port": 6185, "ssl": {"enable": False}}},
    )
    info_spy = MagicMock()
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.logger.info",
        info_spy,
    )

    bridge.register_http_api(
        plugin_id="sdk-demo",
        route="/sdk-demo/api/stats",
        methods=["GET"],
        handler_capability="sdk-demo.http_stats",
        description="stats endpoint",
    )

    assert any(
        call.args
        == (
            "SDK HTTP route registered: plugin=%s route=%s methods=%s handler=%s",
            "sdk-demo",
            "/sdk-demo/api/stats",
            "GET",
            "sdk-demo.http_stats",
        )
        for call in info_spy.call_args_list
    )


@pytest.mark.unit
def test_dashboard_public_base_url_prefers_dashboard_env_over_bind_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.astrbot_config",
        {"dashboard": {"host": "0.0.0.0", "port": 6185, "ssl": {"enable": False}}},
    )
    monkeypatch.setenv("ASTRBOT_DASHBOARD_HOST", "127.0.0.1")
    monkeypatch.setenv("ASTRBOT_DASHBOARD_PORT", "7443")
    monkeypatch.setenv("ASTRBOT_DASHBOARD_SSL_ENABLE", "true")

    assert bridge._dashboard_public_base_url() == "https://127.0.0.1:7443"


@pytest.mark.unit
def test_plugin_entry_route_prefers_plugin_root() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    bridge.register_http_api(
        plugin_id="sdk-demo",
        route="/sdk-demo/api/stats",
        methods=["GET"],
        handler_capability="sdk-demo.stats",
        description="stats endpoint",
    )
    bridge.register_http_api(
        plugin_id="sdk-demo",
        route="/sdk-demo",
        methods=["GET"],
        handler_capability="sdk-demo.overview",
        description="overview",
    )

    assert bridge._plugin_entry_route("sdk-demo") == "/sdk-demo"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_turn_off_plugin_disables_and_tears_down() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    bridge._persist_state_overrides = lambda: None
    record = types.SimpleNamespace(
        plugin_id="sdk-demo",
        state="enabled",
        failure_reason="boom",
    )
    bridge._records = {"sdk-demo": record}
    bridge._cancel_plugin_requests = AsyncMock()  # type: ignore[method-assign]
    bridge._teardown_plugin = AsyncMock()  # type: ignore[method-assign]

    await bridge.turn_off_plugin("sdk-demo")

    bridge._cancel_plugin_requests.assert_awaited_once_with("sdk-demo")
    bridge._teardown_plugin.assert_awaited_once_with("sdk-demo")
    assert record.state == "disabled"
    assert record.failure_reason == ""
    assert bridge._state_overrides["sdk-demo"]["disabled"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_turn_on_plugin_reloads_and_clears_disabled_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    bridge._persist_state_overrides = lambda: None
    bridge._state_overrides = {"sdk-demo": {"disabled": True}}
    plugin = types.SimpleNamespace(name="sdk-demo")
    discovered = types.SimpleNamespace(plugins=[plugin], issues=[])
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.discover_plugins",
        lambda _plugins_dir: discovered,
    )
    planned: list[list[object]] = []
    bridge.env_manager.plan = lambda plugins: planned.append(list(plugins))  # type: ignore[method-assign]
    bridge._load_or_reload_plugin = AsyncMock()  # type: ignore[method-assign]

    await bridge.turn_on_plugin("sdk-demo")

    assert planned == [[plugin]]
    bridge._load_or_reload_plugin.assert_awaited_once_with(
        plugin,
        load_order=0,
        reset_restart_budget=True,
    )
    assert bridge._state_overrides == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_stop_cleans_runtime_state() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    bridge._started = True
    overlay = bridge._ensure_request_overlay("dispatch-typed", should_call_llm=True)
    if overlay.cleanup_task is not None:
        overlay.cleanup_task.cancel()
    cleanup_task = asyncio.create_task(asyncio.sleep(60))
    overlay.cleanup_task = cleanup_task
    bridge._request_contexts["dispatch-typed"] = types.SimpleNamespace(cancelled=False)
    bridge._request_id_to_token["req-1"] = "dispatch-typed"
    bridge._request_plugin_ids["req-1"] = "sdk-demo"
    bridge._plugin_requests = {
        "sdk-demo": {
            "req-1": types.SimpleNamespace(
                request_id="req-1",
                dispatch_token="dispatch-typed",
                task=types.SimpleNamespace(done=lambda: True),
                logical_cancelled=False,
            )
        }
    }
    session = _CancelableSession(peer=None)
    record = types.SimpleNamespace(
        plugin_id="sdk-demo",
        session=session,
        local_mcp_servers={},
    )
    bridge._records = {"sdk-demo": record}
    bridge._http_routes = {"sdk-demo": [types.SimpleNamespace(route="/health")]}
    bridge._session_waiters = {"sdk-demo": {"waiter"}}
    bridge._schedule_job_ids = {"sdk-demo": {"job-1"}}
    bridge._temporary_mcp_sessions = {
        "temp-1": types.SimpleNamespace(
            plugin_id="sdk-demo",
            client=_TemporaryClient(),
        )
    }

    await bridge.stop()
    await asyncio.sleep(0)

    session.stop.assert_awaited_once()
    assert bridge._records == {}
    assert bridge._request_contexts == {}
    assert bridge._request_id_to_token == {}
    assert bridge._request_plugin_ids == {}
    assert bridge._request_overlays == {}
    assert bridge._plugin_requests == {}
    assert bridge._http_routes == {}
    assert bridge._session_waiters == {}
    assert bridge._schedule_job_ids == {}
    assert bridge._temporary_mcp_sessions == {}
    assert cleanup_task.cancelled() is True
    assert bridge._started is False
    assert bridge._stopping is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_reload_all_reloads_discovered_plugins_and_tears_down_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    plugin_a = types.SimpleNamespace(name="sdk-a")
    plugin_b = types.SimpleNamespace(name="sdk-b")
    issue = types.SimpleNamespace(
        plugin_id="broken",
        to_payload=lambda: {
            "plugin_id": "broken",
            "phase": "discovery",
            "message": "broken plugin",
        },
    )
    discovered = types.SimpleNamespace(plugins=[plugin_a, plugin_b], issues=[issue])
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.discover_plugins",
        lambda _plugins_dir: discovered,
    )
    pruned: list[set[str]] = []
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.SkillManager",
        lambda: types.SimpleNamespace(
            prune_sdk_plugin_skills=lambda known: pruned.append(set(known))
        ),
    )
    planned: list[list[object]] = []
    bridge.env_manager.plan = lambda plugins: planned.append(list(plugins))  # type: ignore[method-assign]
    bridge._teardown_plugin = AsyncMock()  # type: ignore[method-assign]
    bridge._load_or_reload_plugin = AsyncMock()  # type: ignore[method-assign]
    bridge._records = {
        "sdk-old": types.SimpleNamespace(plugin_id="sdk-old"),
        "sdk-a": types.SimpleNamespace(plugin_id="sdk-a"),
    }

    await bridge.reload_all(reset_restart_budget=True)

    bridge._teardown_plugin.assert_awaited_once_with("sdk-old")
    assert "sdk-old" not in bridge._records
    assert planned == [[plugin_a, plugin_b]]
    assert pruned == [{"sdk-a", "sdk-b"}]
    assert bridge._discovery_issues == {
        "broken": [
            {"plugin_id": "broken", "phase": "discovery", "message": "broken plugin"}
        ]
    }
    bridge._load_or_reload_plugin.assert_has_awaits(
        [
            call(plugin_a, load_order=0, reset_restart_budget=True),
            call(plugin_b, load_order=1, reset_restart_budget=True),
        ]
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_reload_plugin_updates_discovery_issues_and_loads_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    plugin_a = types.SimpleNamespace(name="sdk-a")
    plugin_b = types.SimpleNamespace(name="sdk-b")
    issue = types.SimpleNamespace(
        plugin_id="broken",
        to_payload=lambda: {"plugin_id": "broken", "message": "broken plugin"},
    )
    discovered = types.SimpleNamespace(plugins=[plugin_a, plugin_b], issues=[issue])
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.discover_plugins",
        lambda _plugins_dir: discovered,
    )
    planned: list[list[object]] = []
    bridge.env_manager.plan = lambda plugins: planned.append(list(plugins))  # type: ignore[method-assign]
    bridge._load_or_reload_plugin = AsyncMock()  # type: ignore[method-assign]

    await bridge.reload_plugin("sdk-b")

    assert planned == [[plugin_a, plugin_b]]
    assert bridge._discovery_issues == {
        "broken": [{"plugin_id": "broken", "message": "broken plugin"}]
    }
    bridge._load_or_reload_plugin.assert_awaited_once_with(
        plugin_b,
        load_order=1,
        reset_restart_budget=True,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_reload_plugin_raises_for_unknown_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    discovered = types.SimpleNamespace(plugins=[], issues=[])
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.plugin_bridge.discover_plugins",
        lambda _plugins_dir: discovered,
    )
    bridge.env_manager.plan = lambda plugins: None  # type: ignore[method-assign]
    bridge._load_or_reload_plugin = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="SDK plugin not found: missing"):
        await bridge.reload_plugin("missing")

    bridge._load_or_reload_plugin.assert_not_awaited()


@pytest.mark.unit
def test_sdk_bridge_match_waiter_plugins_returns_load_order_sorted_records() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    bridge._records = {
        "sdk-b": types.SimpleNamespace(plugin_id="sdk-b", load_order=2),
        "sdk-a": types.SimpleNamespace(plugin_id="sdk-a", load_order=1),
        "sdk-c": types.SimpleNamespace(plugin_id="sdk-c", load_order=3),
    }
    bridge._session_waiters = {
        "sdk-b": {"session-1"},
        "sdk-a": {"session-1"},
        "sdk-c": {"other-session"},
    }

    matches = bridge._match_waiter_plugins("session-1")

    assert [record.plugin_id for record in matches] == ["sdk-a", "sdk-b"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_dispatch_system_event_isolates_failures_and_preserves_order() -> (
    None
):
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    call_order: list[str] = []
    session_a = _OrderedSystemEventSession(call_order)
    session_b = _OrderedSystemEventSession(
        call_order,
        fail_on={"sdk-b:main.first"},
    )
    bridge._records = {
        "sdk-b": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-b",
            plugin=types.SimpleNamespace(manifest_data={}),
            load_order=1,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-b:main.first",
                        trigger=EventTrigger(event_type="platform_loaded"),
                        priority=10,
                    ),
                    declaration_order=0,
                )
            ],
            session=session_b,
        ),
        "sdk-a": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-a",
            plugin=types.SimpleNamespace(manifest_data={}),
            load_order=0,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-a:main.high",
                        trigger=EventTrigger(event_type="platform_loaded"),
                        priority=20,
                    ),
                    declaration_order=1,
                ),
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-a:main.low",
                        trigger=EventTrigger(event_type="platform_loaded"),
                        priority=10,
                    ),
                    declaration_order=0,
                ),
            ],
            session=session_a,
        ),
    }

    await bridge.dispatch_system_event(
        "platform_loaded",
        {"platform": "demo-platform", "platform_id": "demo-1"},
    )

    assert call_order == [
        "sdk-a:main.high",
        "sdk-a:main.low",
        "sdk-b:main.first",
    ]


@pytest.mark.unit
def test_sdk_bridge_list_plugins_skips_discovery_entry_for_loaded_plugin() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    bridge._discovery_issues = {
        "sdk-demo": [{"plugin_id": "sdk-demo", "message": "discovery failed"}],
        "broken": [{"plugin_id": "broken", "message": "still broken"}],
    }
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            plugin=types.SimpleNamespace(
                name="sdk-demo",
                manifest_data={"display_name": "SDK Demo"},
                plugin_dir=Path("."),
            ),
            plugin_id="sdk-demo",
            load_order=0,
            state="enabled",
            unsupported_features=[],
            handlers=[],
            failure_reason="",
            issues=[],
        )
    }

    items = bridge.list_plugins()

    assert [item["name"] for item in items] == ["sdk-demo", "broken"]


@pytest.mark.unit
def test_sdk_bridge_list_plugin_metadata_includes_legacy_sdk_and_discovery_entries() -> (
    None
):
    legacy = types.SimpleNamespace(
        name="legacy-demo",
        display_name="Legacy Demo",
        desc="legacy plugin",
        author="tester",
        version="1.0.0",
        activated=True,
        support_platforms=["qq"],
        astrbot_version="4.0.0",
    )
    bridge = SdkPluginBridge(
        types.SimpleNamespace(
            get_all_stars=lambda: [legacy],
            registered_web_apis=[],
            cron_manager=object(),
        )
    )
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            plugin=types.SimpleNamespace(
                name="sdk-demo",
                manifest_data={
                    "display_name": "SDK Demo",
                    "description": "sdk plugin",
                    "author": "tester",
                    "version": "0.1.0",
                    "support_platforms": ["telegram"],
                },
                plugin_dir=Path("."),
            ),
            plugin_id="sdk-demo",
            load_order=0,
            state="enabled",
            issues=[],
        )
    }
    bridge._discovery_issues = {
        "broken": [{"plugin_id": "broken", "message": "broken plugin"}]
    }

    metadata = bridge.list_plugin_metadata()

    assert [item["name"] for item in metadata] == [
        "legacy-demo",
        "sdk-demo",
        "broken",
    ]
    assert metadata[0]["runtime_kind"] == "legacy"
    assert metadata[1]["runtime_kind"] == "sdk"
    assert metadata[2]["enabled"] is False


@pytest.mark.unit
def test_sdk_bridge_state_override_load_and_persist_boundaries(tmp_path: Path) -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    bridge.state_path = tmp_path / "state.json"

    bridge.state_path.write_text("{invalid", encoding="utf-8")
    assert bridge._load_state_overrides() == {}

    bridge.state_path.write_text(
        json.dumps({"plugins": {"sdk-demo": {"disabled": True, "note": "keep"}}}),
        encoding="utf-8",
    )
    assert bridge._load_state_overrides() == {
        "sdk-demo": {"disabled": True, "note": "keep"}
    }

    bridge._state_overrides = {"sdk-demo": {"disabled": True, "note": "keep"}}
    bridge._set_disabled_override("sdk-demo", disabled=False)

    assert bridge._state_overrides == {"sdk-demo": {"note": "keep"}}
    persisted = json.loads(bridge.state_path.read_text(encoding="utf-8"))
    assert persisted == {"plugins": {"sdk-demo": {"note": "keep"}}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_dispatch_message_event_supports_agent_begin() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    session = _SystemEventSession()
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-demo",
            load_order=0,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.on_agent_begin",
                        trigger=EventTrigger(event_type="agent_begin"),
                    ),
                    declaration_order=0,
                )
            ],
            session=session,
        )
    }

    event = _TypedHookFakeEvent()
    bridge._request_overlays["dispatch-typed"] = bridge._ensure_request_overlay(
        "dispatch-typed",
        should_call_llm=True,
    )

    await bridge.dispatch_message_event("agent_begin", event)

    assert [call[0] for call in session.calls] == ["sdk-demo:main.on_agent_begin"]
    payload = session.calls[0][1]
    assert payload["event_type"] == "agent_begin"
    assert payload["raw"]["event_type"] == "agent_begin"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        (
            "llm_tool_start",
            {"tool_name": "search_docs", "tool_args": {"query": "sdk"}},
        ),
        (
            "llm_tool_end",
            {
                "tool_name": "search_docs",
                "tool_args": {"query": "sdk"},
                "tool_result": {"content": [{"type": "text", "text": "matched"}]},
            },
        ),
    ],
)
async def test_sdk_bridge_dispatch_message_event_supports_llm_tool_events(
    event_type: str,
    payload: dict[str, object],
) -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    session = _SystemEventSession()
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-demo",
            load_order=0,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id=f"sdk-demo:main.{event_type}",
                        trigger=EventTrigger(event_type=event_type),
                    ),
                    declaration_order=0,
                )
            ],
            session=session,
        )
    }

    event = _TypedHookFakeEvent()
    bridge._request_overlays["dispatch-typed"] = bridge._ensure_request_overlay(
        "dispatch-typed",
        should_call_llm=True,
    )

    await bridge.dispatch_message_event(event_type, event, payload)

    assert [call[0] for call in session.calls] == [f"sdk-demo:main.{event_type}"]
    sent_payload = session.calls[0][1]
    assert sent_payload["event_type"] == event_type
    assert sent_payload["raw"]["event_type"] == event_type
    for key, value in payload.items():
        assert sent_payload[key] == value
        assert sent_payload["raw"][key] == value


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_dispatch_system_event_exposes_sent_payload_fields() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    session = _SystemEventSession()
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-demo",
            load_order=0,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.after_send",
                        trigger=EventTrigger(event_type="after_message_sent"),
                    ),
                    declaration_order=0,
                )
            ],
            session=session,
        )
    }

    await bridge.dispatch_system_event(
        "after_message_sent",
        {
            "session_id": "demo:private:user-1",
            "platform": "Demo Platform",
            "platform_id": "demo",
            "message_type": "private",
            "message_outline": "reply text",
            "sent_message_outline": "reply text",
            "sent_messages": [
                {"type": "text", "data": {"text": "reply text"}},
            ],
        },
    )

    sent_payload = session.calls[0][1]
    assert sent_payload["text"] == "reply text"
    assert sent_payload["message_outline"] == "reply text"
    assert sent_payload["sent_message_outline"] == "reply text"
    assert sent_payload["sent_messages"] == [
        {"type": "text", "data": {"text": "reply text"}}
    ]


@pytest.mark.unit
def test_sdk_bridge_match_handlers_skips_plugins_without_platform_support() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    bridge._records = {
        "sdk-supported": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-supported",
            plugin=types.SimpleNamespace(
                manifest_data={"support_platforms": ["demo-platform"]}
            ),
            load_order=0,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-supported:main.on_message",
                        trigger=MessageTrigger(keywords=["hello"]),
                    ),
                    declaration_order=0,
                )
            ],
            dynamic_command_routes=[],
        ),
        "sdk-blocked": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-blocked",
            plugin=types.SimpleNamespace(
                manifest_data={"support_platforms": ["other-platform"]}
            ),
            load_order=1,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-blocked:main.on_message",
                        trigger=MessageTrigger(keywords=["hello"]),
                    ),
                    declaration_order=0,
                )
            ],
            dynamic_command_routes=[],
        ),
    }

    matches = bridge._match_handlers(_TypedHookFakeEvent())  # noqa: SLF001

    assert [match.plugin_id for match in matches] == ["sdk-supported"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_dispatch_system_event_filters_by_supported_platform() -> None:
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    supported_session = _SystemEventSession()
    blocked_session = _SystemEventSession()
    bridge._records = {
        "sdk-supported": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-supported",
            plugin=types.SimpleNamespace(
                manifest_data={"support_platforms": ["demo-platform"]}
            ),
            load_order=0,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-supported:main.platform_loaded",
                        trigger=EventTrigger(event_type="platform_loaded"),
                    ),
                    declaration_order=0,
                )
            ],
            session=supported_session,
        ),
        "sdk-blocked": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-blocked",
            plugin=types.SimpleNamespace(
                manifest_data={"support_platforms": ["other-platform"]}
            ),
            load_order=1,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-blocked:main.platform_loaded",
                        trigger=EventTrigger(event_type="platform_loaded"),
                    ),
                    declaration_order=0,
                )
            ],
            session=blocked_session,
        ),
    }

    await bridge.dispatch_system_event(
        "platform_loaded",
        {"platform": "demo-platform", "platform_id": "demo-1"},
    )

    assert [call[0] for call in supported_session.calls] == [
        "sdk-supported:main.platform_loaded"
    ]
    assert blocked_session.calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sdk_bridge_dispatch_message_event_respects_event_platform_filters() -> (
    None
):
    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    session = _SystemEventSession()
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-demo",
            plugin=types.SimpleNamespace(manifest_data={}),
            load_order=0,
            handlers=[
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.allowed",
                        trigger=EventTrigger(event_type="after_message_sent"),
                        filters=[PlatformFilterSpec(platforms=["demo-platform"])],
                    ),
                    declaration_order=0,
                ),
                types.SimpleNamespace(
                    descriptor=HandlerDescriptor(
                        id="sdk-demo:main.blocked",
                        trigger=EventTrigger(event_type="after_message_sent"),
                        filters=[PlatformFilterSpec(platforms=["other-platform"])],
                    ),
                    declaration_order=1,
                ),
            ],
            session=session,
        )
    }

    event = _TypedHookFakeEvent()
    bridge._request_overlays["dispatch-typed"] = bridge._ensure_request_overlay(
        "dispatch-typed",
        should_call_llm=False,
    )

    await bridge.dispatch_message_event(
        "after_message_sent",
        event,
        {"message_outline": "reply text"},
    )

    assert [call[0] for call in session.calls] == ["sdk-demo:main.allowed"]


@pytest.mark.unit
def test_sdk_bridge_dynamic_command_routes_register_and_match() -> None:
    class _RouteFakeEvent:
        def __init__(self, text: str) -> None:
            self._text = text

        def get_message_type(self):
            return types.SimpleNamespace(value="private")

        def get_group_id(self) -> str:
            return ""

        def get_sender_id(self) -> str:
            return "user-1"

        def get_platform_name(self) -> str:
            return "test-platform"

        def get_message_str(self) -> str:
            return self._text

        def is_admin(self) -> bool:
            return False

    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    descriptor = HandlerDescriptor(
        id="sdk-demo:demo.echo",
        trigger=CommandTrigger(command="noop"),
        param_specs=[ParamSpec(name="phrase", type="greedy_str")],
    )
    handler_ref = types.SimpleNamespace(descriptor=descriptor, declaration_order=0)
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            state="enabled",
            plugin_id="sdk-demo",
            load_order=0,
            handlers=[handler_ref],
            dynamic_command_routes=[],
            session=object(),
        )
    }

    bridge.register_dynamic_command_route(
        plugin_id="sdk-demo",
        command_name="hello",
        handler_full_name="sdk-demo:demo.echo",
        desc="dynamic hello",
        priority=6,
    )
    matches = bridge._match_handlers(_RouteFakeEvent("hello world"))

    assert len(matches) == 1
    assert matches[0].handler_id == "sdk-demo:demo.echo"
    assert matches[0].args == {"phrase": "world"}


@pytest.mark.unit
def test_sdk_bridge_register_skill_requires_plugin_local_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "sdk_demo"
    skill_dir = plugin_root / "skills" / "browser-helper"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text(
        "---\ndescription: demo skill\n---\n# skill\n",
        encoding="utf-8",
    )

    bridge = SdkPluginBridge(_OverlayFakeStarContext())
    published: list[str] = []
    monkeypatch.setattr(
        bridge,
        "_publish_plugin_skills",
        lambda plugin_id: published.append(plugin_id),
    )
    bridge._records = {
        "sdk-demo": types.SimpleNamespace(
            plugin=types.SimpleNamespace(plugin_dir=plugin_root),
            skills={},
        )
    }

    registered = bridge.register_skill(
        plugin_id="sdk-demo",
        name="sdk-demo.browser-helper",
        path="skills/browser-helper",
        description="",
    )

    assert registered["name"] == "sdk-demo.browser-helper"
    assert registered["description"] == "demo skill"
    assert published == ["sdk-demo"]

    outside_path = tmp_path / "outside" / "SKILL.md"
    outside_path.parent.mkdir(parents=True, exist_ok=True)
    outside_path.write_text("# nope", encoding="utf-8")
    with pytest.raises(Exception, match="must stay inside the plugin directory"):
        bridge.register_skill(
            plugin_id="sdk-demo",
            name="sdk-demo.outside",
            path=str(outside_path),
            description="",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_context_send_message_populates_proactive_sent_fields() -> None:
    platform = _FakePlatform()
    ctx = StarContext(
        event_queue=Queue(),
        config={},
        db=object(),
        provider_manager=object(),
        platform_manager=types.SimpleNamespace(platform_insts=[platform]),
        conversation_manager=object(),
        message_history_manager=object(),
        persona_manager=object(),
        astrbot_config_mgr=object(),
        knowledge_base_manager=object(),
        cron_manager=object(),
    )
    bridge = _CaptureSystemBridge()
    ctx.sdk_plugin_bridge = bridge

    sent = await ctx.send_message(
        "demo:FriendMessage:user-1",
        MessageChain([Plain("hello proactive", convert=False)]),
    )

    assert sent is True
    assert len(platform.sent) == 1
    assert bridge.calls == [
        (
            "after_message_sent",
            {
                "session_id": "demo:FriendMessage:user-1",
                "platform": "Demo Platform",
                "platform_id": "demo",
                "message_type": "private",
                "message_outline": "hello proactive",
                "sent_message_outline": "hello proactive",
                "sent_messages": [
                    {"type": "text", "data": {"text": "hello proactive"}}
                ],
            },
        )
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_third_party_runner_dispatches_live_provider_request_to_sdk_hooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = sys.modules[
        "astrbot.core.pipeline.process_stage.method.agent_sub_stages.third_party"
    ]
    monkeypatch.setattr(module, "astrbot_config", {"provider": [{"id": "provider-1"}]})

    async def fake_call_event_hook(*_args, **_kwargs) -> bool:
        return False

    async def fake_resolve_persona_message(_event) -> None:
        return None

    monkeypatch.setattr(module, "call_event_hook", fake_call_event_hook)
    monkeypatch.setattr(
        module,
        "set_persona_custom_error_message_on_event",
        lambda *_args, **_kwargs: None,
    )

    bridge = _ThirdPartyDispatchBridge()
    stage = ThirdPartyAgentSubStage()
    stage.ctx = types.SimpleNamespace(
        plugin_manager=types.SimpleNamespace(
            context=types.SimpleNamespace(
                sdk_plugin_bridge=bridge,
                conversation_manager=object(),
                persona_manager=object(),
            )
        )
    )
    stage.conf = {
        "provider_settings": {
            "agent_runner_type": "unsupported",
            "unsupported_streaming_strategy": "turn_off",
            "streaming_response": False,
        }
    }
    stage.runner_type = "unsupported"
    stage.prov_id = "provider-1"
    stage.streaming_response = False
    stage.unsupported_streaming_strategy = "turn_off"
    stage.stream_consumption_close_timeout_sec = 30
    stage._resolve_persona_custom_error_message = fake_resolve_persona_message
    event = _ThirdPartyFakeEvent()

    with pytest.raises(ValueError, match="Unsupported third party agent runner type"):
        async for _ in stage.process(event, ""):
            pass

    assert len(bridge.calls) == 1
    event_type, payload, provider_request = bridge.calls[0]
    assert event_type == "llm_request"
    assert payload == {"prompt": "hello runner", "provider_id": "provider-1"}
    assert provider_request is not None
    assert provider_request.prompt == "hello runner"
    assert provider_request.session_id == "demo:private:user-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mock_context_registry_client_round_trip() -> None:
    ctx = MockContext(plugin_id="sdk-demo")
    ctx.router.set_plugin_handlers(
        "sdk-demo",
        [
            {
                "plugin_name": "sdk-demo",
                "handler_full_name": "sdk-demo:demo.on_waiting",
                "trigger_type": "event",
                "description": "Observe waiting requests",
                "event_types": ["waiting_llm_request"],
                "enabled": True,
                "group_path": [],
                "priority": 7,
                "kind": "hook",
                "require_admin": True,
            }
        ],
    )

    handlers = await ctx.registry.get_handlers_by_event_type("waiting_llm_request")
    assert len(handlers) == 1
    assert handlers[0].handler_full_name == "sdk-demo:demo.on_waiting"
    assert handlers[0].description == "Observe waiting requests"
    assert handlers[0].priority == 7
    assert handlers[0].kind == "hook"
    assert handlers[0].require_admin is True

    handler = await ctx.registry.get_handler_by_full_name("sdk-demo:demo.on_waiting")
    assert handler is not None
    assert handler.plugin_name == "sdk-demo"
    assert handler.description == "Observe waiting requests"
    assert handler.priority == 7
    assert handler.kind == "hook"
    assert handler.require_admin is True

    request_id = "req-registry-whitelist"
    set_result = await ctx.router.execute(
        "system.event.handler_whitelist.set",
        {"plugin_names": ["sdk-demo"]},
        stream=False,
        cancel_token=None,
        request_id=request_id,
    )
    assert set_result == {"plugin_names": ["sdk-demo"]}
    get_result = await ctx.router.execute(
        "system.event.handler_whitelist.get",
        {},
        stream=False,
        cancel_token=None,
        request_id=request_id,
    )
    assert get_result == {"plugin_names": ["sdk-demo"]}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mock_context_skill_client_round_trip() -> None:
    ctx = MockContext(plugin_id="sdk-demo")

    registered = await ctx.skills.register(
        name="sdk-demo.browser-helper",
        path="/tmp/sdk-demo/browser-helper/SKILL.md",
        description="demo skill",
    )
    assert registered.name == "sdk-demo.browser-helper"
    assert registered.description == "demo skill"
    assert registered.skill_dir.replace("\\", "/") == "/tmp/sdk-demo/browser-helper"

    listed = await ctx.skills.list()
    assert len(listed) == 1
    assert listed[0].name == "sdk-demo.browser-helper"
    assert listed[0].path.replace("\\", "/") == "/tmp/sdk-demo/browser-helper/SKILL.md"

    removed = await ctx.skills.unregister("sdk-demo.browser-helper")
    assert removed is True
    assert await ctx.skills.list() == []
