# ruff: noqa: E402
"""SdkDispatchEngine 的单元测试。

覆盖四条分发路径：
- dispatch_message：用户消息 → 匹配的插件 handler
- dispatch_system_event：系统事件 → 订阅的插件 handler
- dispatch_message_event：消息生命周期事件 → 插件 handler
- dispatch_waiter_event：会话等待器 → 插件 handler

使用 mock bridge 避免依赖 AstrBot 核心运行时。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.sdk_bridge.runtime_store import (
    SdkDispatchResult,
    SdkPluginRecord,
    _DispatchState,
    _InFlightRequest,
    _RequestContext,
    _RequestOverlayState,
)
from astrbot_sdk.protocol.descriptors import HandlerDescriptor
from astrbot_sdk.runtime.loader import PluginSpec
from astrbot_sdk.runtime.supervisor import WorkerSession


# ---------------------------------------------------------------------------
# Fakes / Helpers
# ---------------------------------------------------------------------------


def _make_plugin_spec(plugin_id: str = "test_plugin") -> PluginSpec:
    """创建一个最小可用的 PluginSpec 实例。"""
    spec = MagicMock(spec=PluginSpec)
    spec.name = plugin_id
    return spec


def _make_record(
    plugin_id: str = "test_plugin",
    state: str = "enabled",
    has_session: bool = True,
) -> SdkPluginRecord:
    """创建一个带 mock session 的 SdkPluginRecord。"""
    session = AsyncMock(spec=WorkerSession) if has_session else None
    return SdkPluginRecord(
        plugin=_make_plugin_spec(plugin_id),
        load_order=0,
        state=state,
        unsupported_features=[],
        config_schema={},
        config={},
        handlers=[],
        session=session,
    )


def _make_event(
    *,
    stopped: bool = False,
    platform: str = "test_platform",
    unified_msg_origin: str = "session-1",
) -> MagicMock:
    """创建一个最小 fake AstrMessageEvent。"""
    event = MagicMock()
    event.is_stopped.return_value = stopped
    event.unified_msg_origin = unified_msg_origin
    event.get_platform_name.return_value = platform
    event.get_platform_id.return_value = "platform-id-1"
    event.get_self_id.return_value = "self-1"
    event.get_message_str.return_value = "hello"
    event.get_sender_id.return_value = "user-1"
    event.get_sender_name.return_value = "Tester"
    event.get_group_id.return_value = ""
    event.get_message_type.return_value = SimpleNamespace(value="private")
    event.get_message_outline.return_value = "hello"
    event.is_admin.return_value = False
    event.is_wake = False
    event.is_at_or_wake_command = False
    event.get_messages.return_value = []
    # result 相关
    _result = MagicMock()
    event._result = _result
    event.set_result = MagicMock()
    event.stop_event = MagicMock()
    return event


def _make_overlay(
    dispatch_token: str = "tok-1",
    should_call_llm: bool = False,
    handler_whitelist: set[str] | None = None,
) -> _RequestOverlayState:
    return _RequestOverlayState(
        dispatch_token=dispatch_token,
        should_call_llm=should_call_llm,
        handler_whitelist=handler_whitelist,
    )


def _make_bridge(
    *,
    records: dict[str, SdkPluginRecord] | None = None,
    overlays: dict[str, _RequestOverlayState] | None = None,
    request_contexts: dict[str, _RequestContext] | None = None,
) -> MagicMock:
    """构造一个 mock bridge，预填充 dispatch_engine 需要的所有属性和方法。"""
    bridge = MagicMock()

    # 常量
    bridge.SKIP_LEGACY_STOPPED = "legacy_stopped"
    bridge.SKIP_LEGACY_REPLIED = "legacy_replied"
    bridge.SKIP_SDK_RELOADING = "sdk_reloading"
    bridge.SKIP_NO_MATCH = "no_match"
    bridge.SKIP_WORKER_FAILED = "worker_failed"
    bridge.SDK_STATE_ENABLED = "enabled"
    bridge.SDK_STATE_DISABLED = "disabled"
    bridge.SDK_STATE_RELOADING = "reloading"
    bridge.SDK_STATE_FAILED = "failed"

    # 共享存储
    bridge._records = records if records is not None else {}
    bridge._request_contexts = request_contexts if request_contexts is not None else {}
    bridge._request_overlays = overlays if overlays is not None else {}
    bridge._plugin_requests = {}

    # mock 方法
    bridge._legacy_has_replied = MagicMock(return_value=False)
    bridge._match_waiter_plugins = MagicMock(return_value=[])
    bridge.get_or_bind_dispatch_token = MagicMock(return_value="tok-1")
    bridge.get_effective_should_call_llm = MagicMock(return_value=False)
    bridge._ensure_request_overlay = MagicMock(
        side_effect=lambda token, should_call_llm=False: _make_overlay(
            dispatch_token=token,
            should_call_llm=should_call_llm,
        )
    )
    bridge._match_handlers = MagicMock(return_value=[])
    bridge._resolve_command_permission_denied = MagicMock(return_value=None)
    bridge._resolve_group_root_fallback = MagicMock(return_value=None)
    bridge._has_command_trigger_match = MagicMock(return_value=False)
    bridge._set_sdk_origin_plugin_id = MagicMock()
    bridge._track_request_scope = MagicMock()
    bridge._persist_sdk_local_extras_from_handler = MagicMock()
    bridge._normalize_platform_name = MagicMock(side_effect=lambda v: str(v or ""))
    bridge.build_sdk_event_payload = MagicMock(return_value={})
    bridge._match_event_handlers = MagicMock(return_value=[])
    bridge._core_provider_request_to_sdk_payload = MagicMock(return_value={})
    bridge._core_llm_response_to_sdk_payload = MagicMock(return_value={})
    bridge._legacy_result_to_sdk_payload = MagicMock(return_value=None)
    bridge.set_result_for_request = MagicMock(return_value=False)
    bridge._apply_sdk_provider_request_payload = MagicMock()
    bridge._apply_sdk_result_payload = MagicMock()
    bridge._get_dispatch_token = MagicMock(return_value=None)
    bridge.get_request_overlay_by_token = MagicMock(return_value=None)

    # request_runtime mock
    request_runtime = MagicMock()
    request_runtime._mark_event_send_operation = MagicMock()
    request_runtime._set_event_default_llm_blocked = MagicMock()
    bridge.request_runtime = request_runtime

    return bridge


# ---------------------------------------------------------------------------
# dispatch_message 测试
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDispatchMessage:
    """dispatch_message: 用户消息 → 匹配的插件 handler。"""

    @pytest.mark.asyncio
    async def test_event_already_stopped(self) -> None:
        """已停止的事件应立即跳过，返回 legacy_stopped 原因。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        bridge = _make_bridge()
        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event(stopped=True)

        result = await engine.dispatch_message(event)

        assert result.skipped_reason == "legacy_stopped"
        assert not result.stopped
        assert not result.sent_message

    @pytest.mark.asyncio
    async def test_legacy_already_replied(self) -> None:
        """旧插件已回复时，应跳过。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        bridge = _make_bridge()
        bridge._legacy_has_replied.return_value = True
        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_message(event)

        assert result.skipped_reason == "legacy_replied"

    @pytest.mark.asyncio
    async def test_no_matching_handlers(self) -> None:
        """没有匹配的 handler 时应返回 no_match。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        bridge = _make_bridge()
        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_message(event)

        assert result.skipped_reason == "no_match"

    @pytest.mark.asyncio
    async def test_permission_denied_without_command_match(self) -> None:
        """权限被拒绝且无命令匹配时，应设置拒绝消息并停止事件。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        bridge = _make_bridge()
        bridge._resolve_command_permission_denied.return_value = {
            "plugin_id": "admin_plugin",
            "message": "权限不足，无法执行此命令",
        }
        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_message(event)

        assert result.stopped is True
        event.set_result.assert_called_once()
        event.stop_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_group_fallback_without_command_match(self) -> None:
        """群组回退（无命令匹配时）应设置帮助文本并停止事件。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        bridge = _make_bridge()
        bridge._resolve_group_root_fallback.return_value = {
            "plugin_id": "fallback_plugin",
            "help_text": "可用命令: /hello, /ping",
        }
        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_message(event)

        assert result.stopped is True
        event.set_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_handler_whitelist_filters_plugin(self) -> None:
        """白名单过滤：handler_whitelist 中不存在的 plugin 应被跳过。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="plugin_a", state="enabled")
        bridge = _make_bridge(records={"plugin_a": record})
        bridge._ensure_request_overlay = MagicMock(
            side_effect=lambda token, should_call_llm=False: _make_overlay(
                dispatch_token=token,
                handler_whitelist={"plugin_b"},
            )
        )

        match = MagicMock()
        match.plugin_id = "plugin_a"
        match.handler_id = "handler.echo"
        match.args = {}
        bridge._match_handlers = MagicMock(return_value=[match])

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_message(event)

        assert result.skipped_reason == "no_match"
        assert result.executed_handlers == []

    @pytest.mark.asyncio
    async def test_reloading_plugin_skipped(self) -> None:
        """正在 reload 的插件应被跳过。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="plugin_a", state="reloading")
        bridge = _make_bridge(records={"plugin_a": record})

        match = MagicMock()
        match.plugin_id = "plugin_a"
        match.handler_id = "handler.echo"
        match.args = {}
        bridge._match_handlers = MagicMock(return_value=[match])

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_message(event)

        assert result.skipped_reason == "sdk_reloading"
        assert result.executed_handlers == []

    @pytest.mark.asyncio
    async def test_failed_plugin_skipped(self) -> None:
        """失败状态的插件应被跳过。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="plugin_a", state="failed")
        bridge = _make_bridge(records={"plugin_a": record})

        match = MagicMock()
        match.plugin_id = "plugin_a"
        match.handler_id = "handler.echo"
        match.args = {}
        bridge._match_handlers = MagicMock(return_value=[match])

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_message(event)

        assert result.skipped_reason == "worker_failed"
        assert result.executed_handlers == []

    @pytest.mark.asyncio
    async def test_successful_handler_execution(self) -> None:
        """正常执行 handler 并返回结果。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="plugin_a", state="enabled")
        record.session.invoke_handler = AsyncMock(return_value={})
        bridge = _make_bridge(records={"plugin_a": record})

        match = MagicMock()
        match.plugin_id = "plugin_a"
        match.handler_id = "handler.echo"
        match.args = {"text": "hi"}
        bridge._match_handlers = MagicMock(return_value=[match])

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_message(event)

        assert len(result.executed_handlers) == 1
        assert result.executed_handlers[0]["plugin_id"] == "plugin_a"
        assert result.executed_handlers[0]["handler_id"] == "handler.echo"
        assert not result.sent_message
        assert not result.stopped

    @pytest.mark.asyncio
    async def test_handler_sent_message_marks_event(self) -> None:
        """handler 返回 sent_message=True 时，应标记事件并停止 LLM 调用。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="plugin_a", state="enabled")
        record.session.invoke_handler = AsyncMock(
            return_value={"sent_message": True, "stop": False, "call_llm": False}
        )
        bridge = _make_bridge(records={"plugin_a": record})

        match = MagicMock()
        match.plugin_id = "plugin_a"
        match.handler_id = "handler.reply"
        match.args = {}
        bridge._match_handlers = MagicMock(return_value=[match])

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_message(event)

        assert result.sent_message is True
        bridge.request_runtime._mark_event_send_operation.assert_called_once_with(event)
        bridge.request_runtime._set_event_default_llm_blocked.assert_called()

    @pytest.mark.asyncio
    async def test_handler_stop_stops_event(self) -> None:
        """handler 返回 stop=True 时应停止事件传播。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="plugin_a", state="enabled")
        record.session.invoke_handler = AsyncMock(
            return_value={"stop": True}
        )
        bridge = _make_bridge(records={"plugin_a": record})

        match = MagicMock()
        match.plugin_id = "plugin_a"
        match.handler_id = "handler.stop"
        match.args = {}
        bridge._match_handlers = MagicMock(return_value=[match])

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_message(event)

        assert result.stopped is True
        event.stop_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_handler_exception_skips_gracefully(self) -> None:
        """handler 抛异常时不应崩溃，应优雅跳过。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="plugin_a", state="enabled")
        record.session.invoke_handler = AsyncMock(side_effect=RuntimeError("boom"))
        bridge = _make_bridge(records={"plugin_a": record})

        match = MagicMock()
        match.plugin_id = "plugin_a"
        match.handler_id = "handler.broken"
        match.args = {}
        bridge._match_handlers = MagicMock(return_value=[match])

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_message(event)

        # 异常被捕获后 output={}，handler 仍算已执行（只是返回空结果）
        assert len(result.executed_handlers) == 1
        assert not result.sent_message
        assert not result.stopped

    @pytest.mark.asyncio
    async def test_multiple_handlers_executed_in_order(self) -> None:
        """多个匹配的 handler 应按顺序执行。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record_a = _make_record(plugin_id="plugin_a", state="enabled")
        record_a.session.invoke_handler = AsyncMock(return_value={})
        record_b = _make_record(plugin_id="plugin_b", state="enabled")
        record_b.session.invoke_handler = AsyncMock(return_value={})
        bridge = _make_bridge(records={"plugin_a": record_a, "plugin_b": record_b})

        match_a = MagicMock()
        match_a.plugin_id = "plugin_a"
        match_a.handler_id = "handler.a"
        match_a.args = {}
        match_b = MagicMock()
        match_b.plugin_id = "plugin_b"
        match_b.handler_id = "handler.b"
        match_b.args = {}
        bridge._match_handlers = MagicMock(return_value=[match_a, match_b])

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_message(event)

        assert len(result.executed_handlers) == 2
        assert result.executed_handlers[0]["plugin_id"] == "plugin_a"
        assert result.executed_handlers[1]["plugin_id"] == "plugin_b"

    @pytest.mark.asyncio
    async def test_stop_breaks_handler_loop(self) -> None:
        """第一个 handler 返回 stop=True 时，后续 handler 不应执行。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record_a = _make_record(plugin_id="plugin_a", state="enabled")
        record_a.session.invoke_handler = AsyncMock(return_value={"stop": True})
        record_b = _make_record(plugin_id="plugin_b", state="enabled")
        record_b.session.invoke_handler = AsyncMock(return_value={})
        bridge = _make_bridge(records={"plugin_a": record_a, "plugin_b": record_b})

        match_a = MagicMock()
        match_a.plugin_id = "plugin_a"
        match_a.handler_id = "handler.a"
        match_a.args = {}
        match_b = MagicMock()
        match_b.plugin_id = "plugin_b"
        match_b.handler_id = "handler.b"
        match_b.args = {}
        bridge._match_handlers = MagicMock(return_value=[match_a, match_b])

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_message(event)

        assert len(result.executed_handlers) == 1
        assert result.executed_handlers[0]["plugin_id"] == "plugin_a"
        record_b.session.invoke_handler.assert_not_called()


# ---------------------------------------------------------------------------
# dispatch_system_event 测试
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDispatchSystemEvent:
    """dispatch_system_event: 系统事件 → 订阅的插件。"""

    @pytest.mark.asyncio
    async def test_no_matching_handlers(self) -> None:
        """没有订阅该事件类型的 handler 时，不应出错。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        bridge = _make_bridge()
        bridge._match_event_handlers = MagicMock(return_value=[])
        engine = SdkDispatchEngine(bridge=bridge)

        await engine.dispatch_system_event("platform_loaded", {"platform": "qq"})

    @pytest.mark.asyncio
    async def test_dispatches_to_matching_handlers(self) -> None:
        """匹配到的 handler 应被调用。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="plugin_a", state="enabled")
        record.session.invoke_handler = AsyncMock(return_value={})
        bridge = _make_bridge(records={"plugin_a": record})

        descriptor = MagicMock()
        descriptor.id = "handler.on_platform_loaded"
        bridge._match_event_handlers = MagicMock(return_value=[(record, descriptor)])

        engine = SdkDispatchEngine(bridge=bridge)
        await engine.dispatch_system_event(
            "platform_loaded", {"platform": "qq", "message_outline": "QQ 已加载"}
        )

        record.session.invoke_handler.assert_called_once()
        call_args = record.session.invoke_handler.call_args
        payload = call_args[0][1]
        assert payload["type"] == "platform_loaded"
        assert payload["text"] == "QQ 已加载"

    @pytest.mark.asyncio
    async def test_handler_exception_logged_not_crash(self) -> None:
        """handler 异常应被记录而非崩溃。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="plugin_a", state="enabled")
        record.session.invoke_handler = AsyncMock(side_effect=RuntimeError("event boom"))
        bridge = _make_bridge(records={"plugin_a": record})

        descriptor = MagicMock()
        descriptor.id = "handler.on_loaded"
        bridge._match_event_handlers = MagicMock(return_value=[(record, descriptor)])

        engine = SdkDispatchEngine(bridge=bridge)
        await engine.dispatch_system_event("astrbot_loaded")

    @pytest.mark.asyncio
    async def test_null_session_skipped(self) -> None:
        """session 为 None 的记录应被跳过。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="plugin_a", state="enabled", has_session=False)
        bridge = _make_bridge(records={"plugin_a": record})

        descriptor = MagicMock()
        descriptor.id = "handler.on_loaded"
        bridge._match_event_handlers = MagicMock(return_value=[(record, descriptor)])

        engine = SdkDispatchEngine(bridge=bridge)
        await engine.dispatch_system_event("astrbot_loaded")

    @pytest.mark.asyncio
    async def test_payload_fields_populated(self) -> None:
        """事件 payload 应包含完整的字段。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="plugin_a", state="enabled")
        record.session.invoke_handler = AsyncMock(return_value={})
        bridge = _make_bridge(records={"plugin_a": record})

        descriptor = MagicMock()
        descriptor.id = "handler.on_sent"
        bridge._match_event_handlers = MagicMock(return_value=[(record, descriptor)])

        engine = SdkDispatchEngine(bridge=bridge)
        await engine.dispatch_system_event(
            "after_message_sent",
            {
                "platform": "telegram",
                "session_id": "sess-123",
                "platform_id": "tg-1",
                "message_type": "group",
                "sender_name": "Alice",
                "self_id": "bot-1",
                "message_outline": "hello world",
            },
        )

        payload = record.session.invoke_handler.call_args[0][1]
        assert payload["event_type"] == "after_message_sent"
        assert payload["session_id"] == "sess-123"
        assert payload["platform"] == "telegram"
        assert payload["sender_name"] == "Alice"
        assert payload["self_id"] == "bot-1"


# ---------------------------------------------------------------------------
# dispatch_message_event 测试
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDispatchMessageEvent:
    """dispatch_message_event: 消息生命周期事件 → 插件 handler。"""

    @pytest.mark.asyncio
    async def test_no_dispatch_token_returns_early(self) -> None:
        """没有 dispatch_token 时直接返回。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        bridge = _make_bridge()
        bridge._get_dispatch_token = MagicMock(return_value=None)
        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        await engine.dispatch_message_event("llm_response", event)

    @pytest.mark.asyncio
    async def test_no_overlay_returns_early(self) -> None:
        """有 token 但无 overlay 时直接返回。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        bridge = _make_bridge()
        bridge._get_dispatch_token = MagicMock(return_value="tok-1")
        bridge.get_request_overlay_by_token = MagicMock(return_value=None)
        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        await engine.dispatch_message_event("llm_response", event)

    @pytest.mark.asyncio
    async def test_dispatches_with_llm_response(self) -> None:
        """携带 llm_response 的事件应正确传递给 handler。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="plugin_a", state="enabled")
        record.session.invoke_handler = AsyncMock(return_value={})
        bridge = _make_bridge(records={"plugin_a": record})

        overlay = _make_overlay(dispatch_token="tok-1")
        bridge._get_dispatch_token = MagicMock(return_value="tok-1")
        bridge.get_request_overlay_by_token = MagicMock(return_value=overlay)

        descriptor = MagicMock()
        descriptor.id = "handler.on_llm_response"
        bridge._match_event_handlers = MagicMock(return_value=[(record, descriptor)])

        # 让 build_sdk_event_payload 返回一个可更新的 dict
        bridge.build_sdk_event_payload = MagicMock(return_value={"raw": {}})
        bridge._core_llm_response_to_sdk_payload = MagicMock(
            return_value={"completion": "Hello!"}
        )

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        llm_response = MagicMock()
        await engine.dispatch_message_event(
            "llm_response", event, llm_response=llm_response
        )

        record.session.invoke_handler.assert_called_once()
        # _core_llm_response_to_sdk_payload 应被调用
        bridge._core_llm_response_to_sdk_payload.assert_called_once_with(llm_response)

    @pytest.mark.asyncio
    async def test_handler_stop_stops_event(self) -> None:
        """handler 返回 stop=True 时应停止事件。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="plugin_a", state="enabled")
        record.session.invoke_handler = AsyncMock(return_value={"stop": True})
        bridge = _make_bridge(records={"plugin_a": record})

        overlay = _make_overlay(dispatch_token="tok-1")
        bridge._get_dispatch_token = MagicMock(return_value="tok-1")
        bridge.get_request_overlay_by_token = MagicMock(return_value=overlay)

        descriptor = MagicMock()
        descriptor.id = "handler.on_response"
        bridge._match_event_handlers = MagicMock(return_value=[(record, descriptor)])
        bridge.build_sdk_event_payload = MagicMock(return_value={"raw": {}})

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        await engine.dispatch_message_event("llm_response", event)
        event.stop_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_crash(self) -> None:
        """handler 异常应被吞掉而非崩溃。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="plugin_a", state="enabled")
        record.session.invoke_handler = AsyncMock(side_effect=RuntimeError("msg event boom"))
        bridge = _make_bridge(records={"plugin_a": record})

        overlay = _make_overlay(dispatch_token="tok-1")
        bridge._get_dispatch_token = MagicMock(return_value="tok-1")
        bridge.get_request_overlay_by_token = MagicMock(return_value=overlay)

        descriptor = MagicMock()
        descriptor.id = "handler.on_response"
        bridge._match_event_handlers = MagicMock(return_value=[(record, descriptor)])
        bridge.build_sdk_event_payload = MagicMock(return_value={"raw": {}})

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        # 不应抛异常
        await engine.dispatch_message_event("llm_response", event)


# ---------------------------------------------------------------------------
# dispatch_waiter_event 测试
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDispatchWaiterEvent:
    """dispatch_waiter_event: 会话等待器 → 插件。"""

    @pytest.mark.asyncio
    async def test_no_active_records_skips(self) -> None:
        """所有 waiter 插件都不可用时返回 no_match。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        bridge = _make_bridge()
        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        record = _make_record(plugin_id="waiter_1", state="disabled")
        result = await engine.dispatch_waiter_event(event, [record])

        assert result.skipped_reason == "no_match"
        assert result.executed_handlers == []

    @pytest.mark.asyncio
    async def test_successful_waiter_dispatch(self) -> None:
        """正常的 waiter 插件应被调用。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="waiter_1", state="enabled")
        record.session.invoke_handler = AsyncMock(return_value={})
        bridge = _make_bridge()

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_waiter_event(event, [record])

        assert len(result.executed_handlers) == 1
        assert result.executed_handlers[0]["plugin_id"] == "waiter_1"
        assert result.executed_handlers[0]["handler_id"] == "__sdk_session_waiter__"
        record.session.invoke_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_waiter_sent_message_marks_event(self) -> None:
        """waiter 发送消息后应标记事件。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="waiter_1", state="enabled")
        record.session.invoke_handler = AsyncMock(
            return_value={"sent_message": True}
        )
        bridge = _make_bridge()

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_waiter_event(event, [record])

        assert result.sent_message is True
        bridge.request_runtime._mark_event_send_operation.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_waiter_stop_stops_event(self) -> None:
        """waiter 返回 stop=True 时应停止事件。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="waiter_1", state="enabled")
        record.session.invoke_handler = AsyncMock(return_value={"stop": True})
        bridge = _make_bridge()

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_waiter_event(event, [record])

        assert result.stopped is True
        event.stop_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_waiter_exception_handled_gracefully(self) -> None:
        """waiter 异常应被捕获，不影响后续 waiter。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record_a = _make_record(plugin_id="waiter_a", state="enabled")
        record_a.session.invoke_handler = AsyncMock(side_effect=RuntimeError("waiter boom"))
        record_b = _make_record(plugin_id="waiter_b", state="enabled")
        record_b.session.invoke_handler = AsyncMock(return_value={})
        bridge = _make_bridge()

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_waiter_event(event, [record_a, record_b])

        # waiter_a 异常后走 {} 分支，executed_handlers 仍包含它
        assert len(result.executed_handlers) == 2

    @pytest.mark.asyncio
    async def test_waiter_whitelist_filtering(self) -> None:
        """白名单过滤：不在白名单中的 waiter 应被跳过。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record = _make_record(plugin_id="waiter_1", state="enabled")
        bridge = _make_bridge()
        bridge._ensure_request_overlay = MagicMock(
            side_effect=lambda token, should_call_llm=False: _make_overlay(
                dispatch_token=token,
                handler_whitelist={"waiter_2"},
            )
        )

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_waiter_event(event, [record])

        assert result.skipped_reason == "no_match"
        assert result.executed_handlers == []

    @pytest.mark.asyncio
    async def test_multiple_waiters_stop_breaks_loop(self) -> None:
        """第一个 waiter 返回 stop=True 时，后续 waiter 不执行。"""
        from astrbot.core.sdk_bridge.dispatch_engine import SdkDispatchEngine

        record_a = _make_record(plugin_id="waiter_a", state="enabled")
        record_a.session.invoke_handler = AsyncMock(return_value={"stop": True})
        record_b = _make_record(plugin_id="waiter_b", state="enabled")
        record_b.session.invoke_handler = AsyncMock(return_value={})
        bridge = _make_bridge()

        engine = SdkDispatchEngine(bridge=bridge)
        event = _make_event()

        result = await engine.dispatch_waiter_event(event, [record_a, record_b])

        assert len(result.executed_handlers) == 1
        record_b.session.invoke_handler.assert_not_called()
