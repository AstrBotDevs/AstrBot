"""Verify scheduler request scopes and transport completion using real events."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.config.runtime import MessageConfig, current_message_config
from astrbot.core.pipeline import scheduler as scheduler_module
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.platform.astr_message_event import (
    AstrMessageEvent,
    current_message_event,
)
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.webchat.webchat_event import WebChatMessageEvent
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_event import (
    WecomAIBotMessageEvent,
)


@pytest.fixture
def scheduler(monkeypatch):
    monkeypatch.setattr(scheduler_module, "registered_stages", [])
    monkeypatch.setattr(scheduler_module, "ensure_builtin_stages_registered", Mock())
    snapshot = {"provider_settings": {"enable": True}}
    config_manager = SimpleNamespace(
        _create_message_config=Mock(
            return_value=(snapshot, frozenset({"provider_settings.enable"}))
        )
    )
    plugin_context = SimpleNamespace(astrbot_config_mgr=config_manager)
    return PipelineScheduler(
        SimpleNamespace(plugin_manager=SimpleNamespace(context=plugin_context))
    )


@pytest.fixture
def make_event():
    def create(kind="ordinary"):
        message = AstrBotMessage()
        message.type = MessageType.FRIEND_MESSAGE
        message.self_id = "bot"
        message.message_id = "message-1"
        message.session_id = "session-1"
        message.sender = MessageMember(user_id="user", nickname="Test user")
        message.message = []
        message.message_str = "hello"
        message.raw_message = {}
        metadata = PlatformMetadata(name=kind, description="Test platform", id="test")
        args = ("hello", message, metadata, "session-1")
        if kind == "webchat":
            event = WebChatMessageEvent(*args)
        elif kind == "wecom":
            event = WecomAIBotMessageEvent(
                *args, api_client=None, queue_mgr=SimpleNamespace()
            )
        else:
            event = AstrMessageEvent(*args)
        event.send = AsyncMock()
        return event

    return create


@pytest.mark.asyncio
async def test_execute_installs_and_expires_message_scope(scheduler, make_event):
    event = make_event()
    captured = []
    previous = MessageConfig("previous", {}, scheduler.ctx, frozenset())
    token = current_message_config.set(previous)

    async def process(received):
        assert received is event
        assert current_message_event.get() is event
        scope = current_message_config.get()
        assert scope.active is True
        assert scope.umo == event.unified_msg_origin
        assert scope.context is scheduler.ctx
        assert scope.config == {"provider_settings": {"enable": True}}
        assert scope.override_paths == frozenset({"provider_settings.enable"})
        captured.append(scope)

    scheduler.stages = [SimpleNamespace(process=process)]
    try:
        await scheduler.execute(event)
        assert current_message_config.get() is previous
    finally:
        current_message_config.reset(token)

    scheduler.ctx.plugin_manager.context.astrbot_config_mgr._create_message_config.assert_called_once_with(
        event.unified_msg_origin
    )
    assert len(captured) == 1
    assert captured[0].active is False
    assert current_message_event.get() is None
    assert event._execution_active is False
    event.send.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [None, RuntimeError("stage failed"), asyncio.CancelledError()]
)
async def test_execute_cleans_event_files_overlay_and_scope(
    scheduler, make_event, tmp_path, failure
):
    event = make_event()
    temporary_file = tmp_path / "event-owned.txt"
    temporary_file.write_text("temporary")
    event._temporary_local_files.append(str(temporary_file))
    close_overlay = Mock()
    scheduler.ctx.plugin_manager.context.sdk_plugin_bridge = SimpleNamespace(
        close_request_overlay_for_event=close_overlay
    )
    captured = []

    async def process(_event):
        captured.append(current_message_config.get())
        if failure is not None:
            raise failure

    scheduler.stages = [SimpleNamespace(process=process)]
    if failure is None:
        await scheduler.execute(event)
    else:
        with pytest.raises(type(failure)):
            await scheduler.execute(event)

    assert not temporary_file.exists()
    close_overlay.assert_called_once_with(event)
    assert len(captured) == 1
    assert captured[0].active is False
    assert current_message_config.get() is None
    assert current_message_event.get() is None
    assert event._execution_active is False


@pytest.mark.asyncio
async def test_overlay_cleanup_failure_still_resets_message_scope(
    scheduler, make_event
):
    event = make_event()
    captured = []

    async def process(_event):
        captured.append(current_message_config.get())

    scheduler.stages = [SimpleNamespace(process=process)]
    scheduler.ctx.plugin_manager.context.sdk_plugin_bridge = SimpleNamespace(
        close_request_overlay_for_event=Mock(
            side_effect=RuntimeError("overlay cleanup failed")
        )
    )
    with pytest.raises(RuntimeError, match="overlay cleanup failed"):
        await scheduler.execute(event)

    assert captured[0].active is False
    assert current_message_config.get() is None
    assert current_message_event.get() is None
    assert event._execution_active is False


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["webchat", "wecom"])
async def test_streaming_transport_closes_after_stages_before_scope_cleanup(
    scheduler, make_event, kind
):
    event = make_event(kind)
    order = []

    async def process(_event):
        order.append("stage")

    async def send_closing_frame(message):
        assert message is None
        assert current_message_event.get() is event
        assert current_message_config.get().active is True
        assert event._execution_active is True
        order.append("closing frame")

    event.send = AsyncMock(side_effect=send_closing_frame)
    scheduler.stages = [SimpleNamespace(process=process)]
    await scheduler.execute(event)

    event.send.assert_awaited_once_with(None)
    assert order == ["stage", "closing frame"]
    assert current_message_config.get() is None
    assert current_message_event.get() is None
    assert event._execution_active is False
