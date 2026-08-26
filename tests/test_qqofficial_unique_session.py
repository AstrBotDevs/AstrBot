import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain
from astrbot.core.pipeline.waking_check.stage import build_unique_session_id
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)


@pytest.mark.parametrize("platform_name", ["qq_official", "qq_official_webhook"])
def test_qqofficial_unique_session_keeps_group_id(platform_name):
    """Ensure QQ Official unique sessions retain their delivery target."""
    event = SimpleNamespace(
        get_platform_name=lambda: platform_name,
        get_sender_id=lambda: "member-1",
        get_group_id=lambda: "group-1",
    )

    assert build_unique_session_id(event) == "member-1_group-1"


@pytest.mark.asyncio
async def test_qqofficial_unique_session_sends_to_group_id():
    """Ensure a QQ Official unique session routes to its encoded group."""
    adapter = QQOfficialPlatformAdapter(
        {
            "id": "qq-official-test",
            "appid": "123",
            "secret": "secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        {},
        asyncio.Queue(),
    )
    adapter.client.api = SimpleNamespace(
        post_group_message=AsyncMock(return_value={"id": "sent-1"}),
        post_message=AsyncMock(),
    )
    adapter._session_scene["group-1"] = "group"

    await adapter.send_by_session(
        MessageSession(
            "qq_official",
            MessageType.GROUP_MESSAGE,
            "member-1_group-1",
        ),
        MessageChain(chain=[Plain("proactive hello")]),
    )

    adapter.client.api.post_group_message.assert_awaited_once()
    kwargs = adapter.client.api.post_group_message.await_args.kwargs
    assert kwargs["group_openid"] == "group-1"
    assert adapter._session_last_message_id["group-1"] == "sent-1"
