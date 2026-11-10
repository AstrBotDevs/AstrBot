from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.event import filter
from astrbot.core.message.components import ButtonInteraction
from astrbot.core.pipeline.waking_check.stage import (
    WakingCheckStage,
    star_handlers_registry,
)
from astrbot.core.platform import button_interaction
from astrbot.core.star.filter.button_action import ButtonActionFilter
from astrbot.core.star.session_plugin_manager import SessionPluginManager


def test_button_action_filter_matches_action():
    interaction = ButtonInteraction(
        action_id="approve",
        interaction_id="interaction-1",
    )

    class Event:
        def get_button_interaction(self):
            return interaction

    event = Event()
    assert ButtonActionFilter().filter(event, {})
    assert ButtonActionFilter("approve").filter(event, {})
    assert not ButtonActionFilter("reject").filter(event, {})


def test_public_button_action_decorator_registers_filter():
    assert callable(filter.button_action("approve"))


@pytest.mark.asyncio
async def test_expired_button_notifies_before_any_plugin_filter(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(button_interaction.time, "time", lambda: clock[0])
    registry = button_interaction._ButtonCallbackRegistry()
    monkeypatch.setattr(button_interaction, "_button_callback_registry", registry)
    token = button_interaction.encode_button_callback("approve", expires_at=160)
    interaction = ButtonInteraction(
        action_id="approve", interaction_id="click-1", callback_data=token
    )
    event = MagicMock()
    event.get_button_interaction.return_value = interaction
    event.send = AsyncMock()
    stage = WakingCheckStage()
    stage.ignore_bot_self_message = False
    handlers = MagicMock()
    monkeypatch.setattr(star_handlers_registry, "get_handlers_by_event_type", handlers)
    clock[0] = 160.0

    for _ in range(2):
        await stage.process(event)

    assert event.send.await_count == 2
    assert event.stop_event.call_count == 2
    assert event.send.await_args.args[0].chain[0].text == (
        "按钮已过期，请重新发起操作。 / This button has expired. Please start again."
    )
    handlers.assert_not_called()


@pytest.mark.asyncio
async def test_button_click_only_activates_button_handlers(monkeypatch):
    stage = WakingCheckStage()
    stage.ctx = SimpleNamespace(
        astrbot_config={
            "admins_id": [],
            "wake_prefix": [],
            "plugin_set": ["*"],
        }
    )
    stage.unique_session = False
    stage.ignore_bot_self_message = False
    stage.friend_message_needs_wake_prefix = False
    stage.ignore_at_all = False
    stage.disable_builtin_commands = False
    stage.no_permission_reply = True
    stage._umo_auto_name_recorder = MagicMock()

    ordinary_filter = MagicMock()
    ordinary_filter.filter.return_value = True
    ordinary_handler = SimpleNamespace(
        event_filters=[ordinary_filter],
        handler_module_path="test.ordinary",
        handler_full_name="test.ordinary.handler",
    )
    button_handler = SimpleNamespace(
        event_filters=[ButtonActionFilter("approve")],
        handler_module_path="test.button",
        handler_full_name="test.button.handler",
    )
    monkeypatch.setattr(
        star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *_args, **_kwargs: [ordinary_handler, button_handler],
    )

    async def return_handlers(_event, handlers):
        return handlers

    monkeypatch.setattr(
        SessionPluginManager,
        "filter_handlers_by_session",
        return_handlers,
    )

    interaction = ButtonInteraction(
        action_id="approve",
        interaction_id="interaction-1",
    )
    event = MagicMock()
    event.message_str = "approve"
    event.role = "member"
    event.plugins_name = None
    event.get_sender_id.return_value = "user-1"
    event.get_messages.return_value = [interaction]
    event.get_extra.side_effect = lambda _key=None, default=None: default
    event.get_button_interaction.return_value = interaction
    event.is_button_interaction.return_value = True
    event.is_private_chat.return_value = True

    await stage.process(event)

    ordinary_filter.filter.assert_not_called()
    activated_call = next(
        call
        for call in event.set_extra.call_args_list
        if call.args[0] == "activated_handlers"
    )
    assert activated_call.args[1] == [button_handler]
