"""Tests for QQ Official msg_id handling in FRIEND_MESSAGE proactive sends.

Verifies the fix for:
  - https://github.com/AstrBotDevs/AstrBot/issues/6599
  - https://github.com/AstrBotDevs/AstrBot/issues/6670
  - https://github.com/AstrBotDevs/AstrBot/pull/6604

Bug: When a cron/scheduled task calls send_message_to_user on the qq_official
adapter, the cached msg_id is stale or missing. The QQ API rejects payloads
with an invalid msg_id, raising `botpy.errors.ServerError: 请求参数msg_id无效或越权`.

Fix: For FRIEND_MESSAGE payloads, always remove msg_id so the QQ API treats
the message as a proactive push (which is allowed for private/C2C messages).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image, Plain
from astrbot.api.platform import MessageType
from astrbot.core.platform.message_session import MessageSession


def _build_adapter():
    """Build a QQOfficialPlatformAdapter with minimal mocked dependencies."""
    from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
        QQOfficialPlatformAdapter,
    )

    platform_config = {
        "id": "test-qq-official",
        "appid": "test_appid",
        "secret": "test_secret",
        "enable_group_c2c": True,
        "enable_guild_direct_message": False,
    }
    event_queue = asyncio.Queue()
    adapter = QQOfficialPlatformAdapter(platform_config, {}, event_queue)
    return adapter


def _build_session(session_id: str, message_type: MessageType) -> MessageSession:
    """Build a MessageSession for testing."""
    return MessageSession(
        platform_name="test-qq-official",
        message_type=message_type,
        session_id=session_id,
    )


def _plain_chain(text: str) -> MessageChain:
    """Build a plain text MessageChain."""
    return MessageChain(chain=[Plain(text=text)])


# ============================================================
# Tests
# ============================================================


class TestFriendMessageMsgIdRemoval:
    """Verify msg_id is removed from FRIEND_MESSAGE payloads."""

    @pytest.mark.asyncio
    async def test_plain_text_friend_message_should_not_contain_msg_id(self):
        """Plain text c2c message payload must NOT contain msg_id.

        On master (before the fix), the payload still has msg_id for plain
        text friend messages. This causes the QQ API to reject the message
        with a '请求参数msg_id无效或越权' error when the msg_id is stale.
        """
        adapter = _build_adapter()
        session_id = "test-user-openid"
        stale_msg_id = "STALE_MSG_ID_FROM_HOURS_AGO"

        # Simulate a cached (stale) msg_id — this is what the cron task sees
        adapter.remember_session_message_id(session_id, stale_msg_id)
        adapter.remember_session_scene(session_id, "friend")

        session = _build_session(session_id, MessageType.FRIEND_MESSAGE)
        chain = _plain_chain("Hello from cron task!")

        captured_payloads: list[dict] = []

        async def mock_post_c2c_message(send_helper, openid, **kwargs):
            captured_payloads.append(kwargs)
            return {"id": "new_msg_id_123"}

        with patch(
            "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
            ".QQOfficialMessageEvent.post_c2c_message",
            side_effect=mock_post_c2c_message,
        ):
            with patch(
                "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
                ".QQOfficialMessageEvent._parse_to_qqofficial",
                return_value=(
                    "Hello from cron task!",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            ):
                with patch(
                    "astrbot.core.platform.platform.Platform.send_by_session",
                    new_callable=AsyncMock,
                ):
                    await adapter._send_by_session_common(session, chain)

        assert len(captured_payloads) == 1, "Expected exactly one post_c2c_message call"
        payload = captured_payloads[0]
        assert "msg_id" not in payload, (
            f"msg_id should have been removed from FRIEND_MESSAGE payload, "
            f"but found msg_id={payload.get('msg_id')!r}. "
            f"This is the bug described in #6599 and #6670."
        )

    @pytest.mark.asyncio
    async def test_image_friend_message_should_not_contain_msg_id(self):
        """Image c2c message payload must NOT contain msg_id."""
        adapter = _build_adapter()
        session_id = "test-user-openid"
        stale_msg_id = "STALE_MSG_ID_FROM_HOURS_AGO"

        adapter.remember_session_message_id(session_id, stale_msg_id)
        adapter.remember_session_scene(session_id, "friend")

        session = _build_session(session_id, MessageType.FRIEND_MESSAGE)
        chain = MessageChain(
            chain=[
                Plain(text="Check this image"),
                Image(file="http://example.com/img.png"),
            ]
        )

        captured_payloads: list[dict] = []

        async def mock_post_c2c_message(send_helper, openid, **kwargs):
            captured_payloads.append(kwargs)
            return {"id": "new_msg_id_456"}

        mock_media = MagicMock()

        with patch(
            "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
            ".QQOfficialMessageEvent.post_c2c_message",
            side_effect=mock_post_c2c_message,
        ):
            with patch(
                "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
                ".QQOfficialMessageEvent._parse_to_qqofficial",
                return_value=(
                    "Check this image",
                    "base64_image_data",
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            ):
                with patch(
                    "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
                    ".QQOfficialMessageEvent.upload_group_and_c2c_image",
                    new_callable=AsyncMock,
                    return_value=mock_media,
                ):
                    with patch(
                        "astrbot.core.platform.platform.Platform.send_by_session",
                        new_callable=AsyncMock,
                    ):
                        await adapter._send_by_session_common(session, chain)

        assert len(captured_payloads) == 1
        payload = captured_payloads[0]
        assert "msg_id" not in payload, (
            f"msg_id should have been removed from image FRIEND_MESSAGE payload, "
            f"but found msg_id={payload.get('msg_id')!r}"
        )

    @pytest.mark.asyncio
    async def test_video_friend_message_should_not_contain_msg_id(self):
        """Video c2c message payload must NOT contain msg_id.

        Before the fix, the video path already removed msg_id (line 271-273),
        but only inside the `if media:` block. The fix moves the removal to
        the top of the FRIEND_MESSAGE branch so it covers all cases.
        """
        adapter = _build_adapter()
        session_id = "test-user-openid"
        stale_msg_id = "STALE_MSG_ID"

        adapter.remember_session_message_id(session_id, stale_msg_id)
        adapter.remember_session_scene(session_id, "friend")

        session = _build_session(session_id, MessageType.FRIEND_MESSAGE)
        chain = _plain_chain("video message")

        captured_payloads: list[dict] = []

        async def mock_post_c2c_message(send_helper, openid, **kwargs):
            captured_payloads.append(kwargs)
            return {"id": "new_msg_id_789"}

        mock_media = MagicMock()

        with patch(
            "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
            ".QQOfficialMessageEvent.post_c2c_message",
            side_effect=mock_post_c2c_message,
        ):
            with patch(
                "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
                ".QQOfficialMessageEvent._parse_to_qqofficial",
                return_value=(
                    "video message",
                    None,
                    None,
                    None,
                    "http://example.com/video.mp4",
                    None,
                    None,
                ),
            ):
                with patch(
                    "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
                    ".QQOfficialMessageEvent.upload_group_and_c2c_media",
                    new_callable=AsyncMock,
                    return_value=mock_media,
                ):
                    with patch(
                        "astrbot.core.platform.platform.Platform.send_by_session",
                        new_callable=AsyncMock,
                    ):
                        await adapter._send_by_session_common(session, chain)

        assert len(captured_payloads) == 1
        payload = captured_payloads[0]
        assert "msg_id" not in payload, (
            f"msg_id should have been removed from video FRIEND_MESSAGE payload, "
            f"but found msg_id={payload.get('msg_id')!r}"
        )

    @pytest.mark.asyncio
    async def test_file_friend_message_should_not_contain_msg_id(self):
        """File c2c message payload must NOT contain msg_id."""
        adapter = _build_adapter()
        session_id = "test-user-openid"
        stale_msg_id = "STALE_MSG_ID"

        adapter.remember_session_message_id(session_id, stale_msg_id)
        adapter.remember_session_scene(session_id, "friend")

        session = _build_session(session_id, MessageType.FRIEND_MESSAGE)
        chain = _plain_chain("file message")

        captured_payloads: list[dict] = []

        async def mock_post_c2c_message(send_helper, openid, **kwargs):
            captured_payloads.append(kwargs)
            return {"id": "new_msg_id_abc"}

        mock_media = MagicMock()

        with patch(
            "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
            ".QQOfficialMessageEvent.post_c2c_message",
            side_effect=mock_post_c2c_message,
        ):
            with patch(
                "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
                ".QQOfficialMessageEvent._parse_to_qqofficial",
                return_value=(
                    "file message",
                    None,
                    None,
                    None,
                    None,
                    "/path/to/file.pdf",
                    "file.pdf",
                ),
            ):
                with patch(
                    "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
                    ".QQOfficialMessageEvent.upload_group_and_c2c_media",
                    new_callable=AsyncMock,
                    return_value=mock_media,
                ):
                    with patch(
                        "astrbot.core.platform.platform.Platform.send_by_session",
                        new_callable=AsyncMock,
                    ):
                        await adapter._send_by_session_common(session, chain)

        assert len(captured_payloads) == 1
        payload = captured_payloads[0]
        assert "msg_id" not in payload, (
            f"msg_id should have been removed from file FRIEND_MESSAGE payload, "
            f"but found msg_id={payload.get('msg_id')!r}"
        )


class TestGroupMessageMsgIdPreserved:
    """Verify msg_id is preserved for GROUP_MESSAGE (the fix is FRIEND_MESSAGE only)."""

    @pytest.mark.asyncio
    async def test_group_message_still_has_msg_id(self):
        """Group message payload should still contain msg_id (unaffected by fix)."""
        adapter = _build_adapter()
        session_id = "test-group-openid"
        msg_id = "VALID_GROUP_MSG_ID"

        adapter.remember_session_message_id(session_id, msg_id)
        adapter.remember_session_scene(session_id, "group")

        session = _build_session(session_id, MessageType.GROUP_MESSAGE)
        chain = _plain_chain("Hello group!")

        mock_api = AsyncMock(return_value={"id": "group_reply_id"})
        adapter.client.api = MagicMock()
        adapter.client.api.post_group_message = mock_api

        with patch(
            "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
            ".QQOfficialMessageEvent._parse_to_qqofficial",
            return_value=(
                "Hello group!",
                None,
                None,
                None,
                None,
                None,
                None,
            ),
        ):
            with patch(
                "astrbot.core.platform.platform.Platform.send_by_session",
                new_callable=AsyncMock,
            ):
                await adapter._send_by_session_common(session, chain)

        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args
        # msg_id should be in the call for group messages
        all_kwargs = {**call_kwargs.kwargs}
        assert all_kwargs.get("msg_id") == msg_id, (
            f"Group message should preserve msg_id, "
            f"but msg_id={all_kwargs.get('msg_id')!r}"
        )


class TestFriendMessageMsgSeqPresent:
    """Verify msg_seq is still set for FRIEND_MESSAGE after the fix."""

    @pytest.mark.asyncio
    async def test_friend_message_has_msg_seq(self):
        """msg_seq should always be present in FRIEND_MESSAGE payloads."""
        adapter = _build_adapter()
        session_id = "test-user-openid"
        adapter.remember_session_message_id(session_id, "some_msg_id")
        adapter.remember_session_scene(session_id, "friend")

        session = _build_session(session_id, MessageType.FRIEND_MESSAGE)
        chain = _plain_chain("Test msg_seq")

        captured_payloads: list[dict] = []

        async def mock_post_c2c_message(send_helper, openid, **kwargs):
            captured_payloads.append(kwargs)
            return {"id": "new_msg_id"}

        with patch(
            "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
            ".QQOfficialMessageEvent.post_c2c_message",
            side_effect=mock_post_c2c_message,
        ):
            with patch(
                "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
                ".QQOfficialMessageEvent._parse_to_qqofficial",
                return_value=(
                    "Test msg_seq",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            ):
                with patch(
                    "astrbot.core.platform.platform.Platform.send_by_session",
                    new_callable=AsyncMock,
                ):
                    await adapter._send_by_session_common(session, chain)

        assert len(captured_payloads) == 1
        payload = captured_payloads[0]
        assert "msg_seq" in payload, (
            "msg_seq should be present in FRIEND_MESSAGE payload"
        )
        assert isinstance(payload["msg_seq"], int), "msg_seq should be an integer"


class TestNoMsgIdReturnEarly:
    """Verify that when there is NO cached msg_id, the adapter returns early."""

    @pytest.mark.asyncio
    async def test_no_cached_msg_id_returns_early(self):
        """If no msg_id is cached for the session, _send_by_session_common returns early.

        This means proactive messages to users who have never messaged the bot
        will silently fail. This is the existing behavior (not changed by the PR).
        """
        adapter = _build_adapter()
        session_id = "never-messaged-user"
        # Do NOT call remember_session_message_id

        session = _build_session(session_id, MessageType.FRIEND_MESSAGE)
        chain = _plain_chain("This should not be sent")

        mock_post = AsyncMock()

        with patch(
            "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
            ".QQOfficialMessageEvent.post_c2c_message",
            mock_post,
        ):
            with patch(
                "astrbot.core.platform.sources.qqofficial.qqofficial_message_event"
                ".QQOfficialMessageEvent._parse_to_qqofficial",
                return_value=(
                    "This should not be sent",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            ):
                await adapter._send_by_session_common(session, chain)

        mock_post.assert_not_called()
