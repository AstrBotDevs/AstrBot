from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.core.pipeline.waking_check.stage import (
    WakingCheckStage,
    star_handlers_registry,
)
from astrbot.core.star.session_plugin_manager import SessionPluginManager


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("api_key_allow_admin_role", "expected_role"),
    [
        (False, "member"),
        (True, "admin"),
        (None, "admin"),
    ],
)
async def test_waking_check_enforces_api_key_admin_authorization(
    api_key_allow_admin_role,
    expected_role,
    monkeypatch,
):
    """Only explicitly authorized API requests may assume a configured admin ID."""
    stage = WakingCheckStage()
    stage.ctx = SimpleNamespace(
        astrbot_config={
            "admins_id": ["admin-user"],
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

    event = MagicMock()
    event.message_str = "hello"
    event.role = "member"
    event.get_sender_id.return_value = "admin-user"
    event.get_messages.return_value = []
    event.is_private_chat.return_value = True
    event.get_platform_name.return_value = "webchat"
    event.get_extra.side_effect = lambda key=None, default=None: (
        api_key_allow_admin_role
        if key == "_api_key_allow_admin_role"
        else default
    )
    monkeypatch.setattr(
        star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *_args, **_kwargs: [],
    )

    async def return_handlers(_event, handlers):
        return handlers

    monkeypatch.setattr(
        SessionPluginManager,
        "filter_handlers_by_session",
        return_handlers,
    )

    await stage.process(event)

    assert event.role == expected_role
