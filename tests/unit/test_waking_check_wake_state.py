from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.pipeline.waking_check import stage as waking_stage
from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
from astrbot.core.star.session_plugin_manager import SessionPluginManager
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata


@pytest.mark.asyncio
async def test_handler_match_does_not_mark_ordinary_group_message_as_wake(monkeypatch):
    module = "data.plugins.listener.main"

    async def handler_callback(_event):
        pass

    handler = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name=f"{module}_listener",
        handler_name="listener",
        handler_module_path=module,
        handler=handler_callback,
        event_filters=[],
    )
    handler.event_filters = [MagicMock(filter=MagicMock(return_value=True))]
    monkeypatch.setattr(
        waking_stage.star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *_args, **_kwargs: [handler],
    )
    monkeypatch.setattr(
        waking_stage,
        "star_map",
        {module: StarMetadata(name="listener", module_path=module)},
    )
    monkeypatch.setattr(
        SessionPluginManager,
        "filter_handlers_by_session",
        AsyncMock(side_effect=lambda _event, handlers: handlers),
    )

    stage = WakingCheckStage()
    stage.ctx = SimpleNamespace(
        astrbot_config={
            "admins_id": [],
            "wake_prefix": ["/"],
            "plugin_set": ["*"],
        }
    )
    stage.ignore_bot_self_message = False
    stage.friend_message_needs_wake_prefix = True
    stage.ignore_at_all = False
    stage.disable_builtin_commands = False
    stage.no_permission_reply = True
    stage._umo_auto_name_recorder = MagicMock()

    event = MagicMock()
    event.message_str = "ordinary message"
    event.role = "member"
    event.is_wake = False
    event.is_at_or_wake_command = False
    event.send = AsyncMock()
    event.get_messages.return_value = []
    event.is_private_chat.return_value = False
    event.get_platform_name.return_value = "aiocqhttp"
    event.get_sender_id.return_value = "member-user"
    event.get_self_id.return_value = "bot"
    event.get_sender_name.return_value = "Member"
    event.get_extra.side_effect = lambda key=None, default=None: default
    event.set_extra.side_effect = lambda key, value: setattr(event, key, value)

    await stage.process(event)

    assert event.is_wake is False
    assert event.matched_handlers == [handler]
    event.set_extra.assert_any_call("activated_handlers", [handler])
    event.stop_event.assert_not_called()


@pytest.mark.asyncio
async def test_handler_match_does_not_skip_process_stage(monkeypatch):
    """A matched listener keeps ordinary events in the process pipeline."""
    from astrbot.core.pipeline.process_stage.stage import ProcessStage

    event = MagicMock()
    event.get_extra.side_effect = lambda key=None, default=None: (
        [object()] if key == "activated_handlers" else default
    )
    event.is_at_or_wake_command = False
    event._has_send_oper = False
    event.call_llm = False
    event.get_result.return_value = None
    event.is_stopped.return_value = False

    ctx = SimpleNamespace(
        astrbot_config={"provider_settings": {"enable": True}},
    )
    process = ProcessStage()
    process.ctx = ctx

    async def no_plugin_response(_event):
        if False:
            yield

    process.star_request_sub_stage = SimpleNamespace(process=no_plugin_response)
    process.agent_sub_stage = SimpleNamespace(process=no_plugin_response)

    responses = [response async for response in process.process(event)]

    assert responses == []


@pytest.mark.asyncio
async def test_at_message_still_wakes_and_matches_handler(monkeypatch):
    monkeypatch.setattr(
        waking_stage.star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        SessionPluginManager,
        "filter_handlers_by_session",
        AsyncMock(return_value=[]),
    )

    stage = WakingCheckStage()
    stage.ctx = SimpleNamespace(
        astrbot_config={"admins_id": [], "wake_prefix": ["/"], "plugin_set": ["*"]}
    )
    stage.ignore_bot_self_message = False
    stage.friend_message_needs_wake_prefix = True
    stage.ignore_at_all = False
    stage.disable_builtin_commands = False
    stage.no_permission_reply = True
    stage._umo_auto_name_recorder = MagicMock()

    event = MagicMock()
    event.message_str = "hello"
    event.role = "member"
    event.is_wake = False
    event.is_at_or_wake_command = False
    event.send = AsyncMock()
    event.set_extra.side_effect = lambda key, value: setattr(event, key, value)
    at = SimpleNamespace(qq="bot")
    event.get_messages.return_value = [at]
    event.get_self_id.return_value = "bot"
    event.get_sender_id.return_value = "member-user"
    event.get_sender_name.return_value = "Member"
    event.is_private_chat.return_value = False
    event.get_platform_name.return_value = "aiocqhttp"
    event.get_extra.side_effect = lambda key=None, default=None: default
    event.set_extra.side_effect = lambda key, value: setattr(event, key, value)

    monkeypatch.setattr(waking_stage, "At", type(at))
    await stage.process(event)

    assert event.is_wake is True
    assert event.is_at_or_wake_command is True
