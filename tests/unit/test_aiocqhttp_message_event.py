import sys
import types
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.astrbot_message import AstrBotMessage, Group, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata


@pytest.mark.asyncio
async def test_get_group_normalizes_cached_member_roles():
    sys.modules.setdefault(
        "astrbot.core.star.star_tools",
        types.SimpleNamespace(StarTools=object),
    )
    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
        AiocqhttpMessageEvent,
    )

    bot = AsyncMock()
    bot.call_action.side_effect = [
        {"group_name": "Test Group"},
        [
            {"user_id": "1001", "nickname": "Owner", "role": "owner"},
            {"user_id": "1002", "nickname": "Admin", "role": "admin"},
            {"user_id": "1003", "nickname": "Guest", "role": "super-admin"},
        ],
    ]

    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.group = Group(group_id="123456")
    message.sender = MessageMember(user_id="1001", nickname="Owner", role="owner")
    message.message = []
    message.message_str = ""
    message.raw_message = None

    event = AiocqhttpMessageEvent(
        message_str="",
        message_obj=message,
        platform_meta=PlatformMetadata(
            name="aiocqhttp",
            description="test",
            id="aiocqhttp-test",
        ),
        session_id="123456",
        bot=bot,
    )

    group = await event.get_group()

    assert group is not None
    assert group.group_owner == "1001"
    assert group.group_admins == ["1002"]
    assert [member.role for member in group.members] == ["owner", "admin", None]
