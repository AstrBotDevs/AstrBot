from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.platform import MessageType
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.platform import Platform
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)


@pytest.mark.asyncio
async def test_qqofficial_send_by_session_channel_uses_markdown_payload():
    adapter = object.__new__(QQOfficialPlatformAdapter)
    adapter.config = {"id": ""}  # type: ignore[attr-defined]
    adapter._session_last_message_id = {"sess": "msgid"}  # type: ignore[attr-defined]
    adapter._session_scene = {"sess": "channel"}  # type: ignore[attr-defined]
    adapter.client = MagicMock()  # type: ignore[attr-defined]
    adapter.client.api = MagicMock()
    adapter.client.api.post_message = AsyncMock(return_value={"id": "newid"})
    adapter.client.api.post_group_message = AsyncMock()

    session = MessageSesion("qq_official", MessageType.GROUP_MESSAGE, "sess")
    message_chain = MessageChain()

    with (
        patch.object(Platform, "send_by_session", new=AsyncMock()),
        patch.object(
            QQOfficialMessageEvent,
            "_parse_to_qqofficial",
            new=AsyncMock(
                return_value=("**hello**", None, None, None, None, None, None),
            ),
        ),
    ):
        await adapter._send_by_session_common(session, message_chain)

    assert adapter.client.api.post_message.await_count == 1
    _args, kwargs = adapter.client.api.post_message.await_args
    assert kwargs["channel_id"] == "sess"
    assert kwargs["msg_id"] == "msgid"
    assert kwargs["msg_type"] == 2
    assert "content" not in kwargs
    assert kwargs["markdown"] is not None


@pytest.mark.asyncio
async def test_qqofficial_send_by_session_group_media_downgrades_to_content():
    adapter = object.__new__(QQOfficialPlatformAdapter)
    adapter.config = {"id": ""}  # type: ignore[attr-defined]
    adapter._session_last_message_id = {"group_sess": "msgid"}  # type: ignore[attr-defined]
    adapter._session_scene = {"group_sess": "group"}  # type: ignore[attr-defined]
    adapter.client = MagicMock()  # type: ignore[attr-defined]
    adapter.client.api = MagicMock()
    adapter.client.api.post_group_message = AsyncMock(return_value={"id": "newid"})
    adapter.client.api.post_message = AsyncMock()

    session = MessageSesion("qq_official", MessageType.GROUP_MESSAGE, "group_sess")
    message_chain = MessageChain()

    with (
        patch.object(Platform, "send_by_session", new=AsyncMock()),
        patch.object(
            QQOfficialMessageEvent,
            "_parse_to_qqofficial",
            new=AsyncMock(
                return_value=("hello", "deadbeef", None, None, None, None, None),
            ),
        ),
        patch.object(
            QQOfficialMessageEvent,
            "upload_group_and_c2c_image",
            new=AsyncMock(return_value={"media_id": "m"}),
        ),
    ):
        await adapter._send_by_session_common(session, message_chain)

    assert adapter.client.api.post_group_message.await_count == 1
    _args, kwargs = adapter.client.api.post_group_message.await_args
    assert kwargs["group_openid"] == "group_sess"
    assert kwargs["msg_type"] == 7
    assert kwargs["content"] == "hello"
    assert "markdown" not in kwargs
