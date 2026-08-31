from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.api.event import filter
from astrbot.core.message.components import ButtonInteraction
from astrbot.core.pipeline.waking_check.stage import (
    WakingCheckStage,
    star_handlers_registry,
)
from astrbot.core.star.filter.button_interaction import ButtonInteractionFilter
from astrbot.core.star.session_plugin_manager import SessionPluginManager


def test_button_interaction_filter_matches_action():
    interaction = ButtonInteraction(
        action_id="approve",
        interaction_id="interaction-1",
    )

    class Event:
        def get_button_interaction(self):
            return interaction

    event = Event()
    assert ButtonInteractionFilter().filter(event, {})
    assert ButtonInteractionFilter("approve").filter(event, {})
    assert not ButtonInteractionFilter("reject").filter(event, {})


def test_public_button_interaction_decorator_registers_filter():
    assert callable(filter.button_interaction("approve"))


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

    ordinary_filter = MagicMock()
    ordinary_filter.filter.return_value = True
    ordinary_handler = SimpleNamespace(
        event_filters=[ordinary_filter],
        handler_module_path="test.ordinary",
        handler_full_name="test.ordinary.handler",
    )
    button_handler = SimpleNamespace(
        event_filters=[ButtonInteractionFilter("approve")],
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
