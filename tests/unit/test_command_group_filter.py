from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.pipeline.waking_check import stage as waking_stage
from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionType, PermissionTypeFilter
from astrbot.core.star.session_plugin_manager import SessionPluginManager
from astrbot.core.star.star import StarMetadata
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("math add 1 2", True),
        ("math   add\n1 2", True),
        ("数学 add 1 2", True),
        ("mathematics", False),
        ("math123", False),
        ("数学题", False),
    ],
)
def test_group_matches_whole_words_only(message, expected):
    group = CommandGroupFilter("math", alias={"数学"})
    assert group.startswith(message) is expected


def test_nested_group_matches_whole_words_only():
    parent = CommandGroupFilter("tool")
    child = CommandGroupFilter("config", parent_group=parent)
    assert child.startswith("tool config set a 1")
    assert not child.startswith("tool configure")


@pytest.mark.parametrize(
    "message",
    ["tool config", "tool   config", "tool\tconfig", "tool\nconfig"],
)
def test_nested_group_without_subcommand_shows_help(message):
    parent = CommandGroupFilter("tool")
    group = CommandGroupFilter("config", parent_group=parent)
    event = SimpleNamespace(is_at_or_wake_command=True, message_str=message)

    with pytest.raises(ValueError, match="参数不足"):
        group.filter(event, {})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "blocked"),
    [
        ("天气真好啊", False),
        ("天气 设置 北京", True),
    ],
)
async def test_admin_group_only_blocks_its_own_commands(message, blocked, monkeypatch):
    """A non-admin chat message that merely starts with the group name must pass."""

    async def group_handler(self, event):
        pass

    module = "data.plugins.weather_probe.main"
    handler = StarHandlerMetadata(
        event_type=EventType.AdapterMessageEvent,
        handler_full_name=f"{module}_weather",
        handler_name="weather",
        handler_module_path=module,
        handler=group_handler,
        event_filters=[
            PermissionTypeFilter(PermissionType.ADMIN),
            CommandGroupFilter("天气"),
        ],
    )
    monkeypatch.setattr(
        waking_stage.star_handlers_registry,
        "get_handlers_by_event_type",
        lambda *_args, **_kwargs: [handler],
    )
    monkeypatch.setattr(
        waking_stage,
        "star_map",
        {module: StarMetadata(name="weather_probe", module_path=module)},
    )

    async def return_handlers(_event, handlers):
        return handlers

    monkeypatch.setattr(
        SessionPluginManager,
        "filter_handlers_by_session",
        return_handlers,
    )

    stage = WakingCheckStage()
    stage.ctx = SimpleNamespace(
        astrbot_config={
            "admins_id": ["admin-user"],
            "wake_prefix": ["/"],
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

    event = MagicMock()
    event.message_str = message
    event.role = "member"
    event.send = AsyncMock()
    event.is_admin.return_value = False
    event.get_sender_id.return_value = "member-user"
    event.get_messages.return_value = []
    event.is_private_chat.return_value = True
    event.get_platform_name.return_value = "aiocqhttp"
    event.get_extra.side_effect = lambda key=None, default=None: default

    await stage.process(event)

    assert event.send.await_count == int(blocked)
    assert event.stop_event.called is blocked
