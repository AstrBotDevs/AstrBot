from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.core.pipeline.whitelist_check.stage import WhitelistCheckStage
from astrbot.core.platform.message_type import MessageType


def _config(whitelist: list[str]) -> dict:
    """Build a minimal AstrBot config for the whitelist stage.

    Args:
        whitelist: Entries configured in the ID whitelist.

    Returns:
        Config object accepted by ``WhitelistCheckStage.initialize``.
    """
    return {
        "platform_settings": {
            "enable_id_white_list": True,
            "id_whitelist": whitelist,
            "id_whitelist_log": False,
            "wl_ignore_admin_on_group": True,
            "wl_ignore_admin_on_friend": True,
        }
    }


def _event(
    *,
    umo: str,
    group_id: str = "",
    sender_id: str = "ou_sender",
    aliases: list[str] | None = None,
    message_type: MessageType = MessageType.FRIEND_MESSAGE,
) -> MagicMock:
    """Build a message event for whitelist matching tests.

    Args:
        umo: Unified message origin of the event.
        group_id: Group ID, empty for private chats.
        sender_id: Primary sender ID.
        aliases: Alternate sender IDs exposed by the adapter.
        message_type: Private or group message type.

    Returns:
        Mock event accepted by ``WhitelistCheckStage.process``.
    """
    event = MagicMock()
    event.unified_msg_origin = umo
    event.role = "member"
    event.get_group_id.return_value = group_id
    event.get_sender_id.return_value = sender_id
    event.get_sender_aliases.return_value = aliases or []
    event.get_message_type.return_value = message_type
    event.get_platform_name.return_value = "lark"
    return event


async def _stage(whitelist: list[str]) -> WhitelistCheckStage:
    """Build an initialized whitelist stage.

    Args:
        whitelist: Entries configured in the ID whitelist.

    Returns:
        Initialized stage under test.
    """
    stage = WhitelistCheckStage()
    await stage.initialize(SimpleNamespace(astrbot_config=_config(whitelist)))
    return stage


@pytest.mark.asyncio
async def test_whitelist_allows_private_chat_by_sender_alias():
    stage = await _stage(["u_123"])
    event = _event(umo="lark:FriendMessage:ou_sender", aliases=["u_123"])

    await stage.process(event)

    event.stop_event.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["u_123", "on_456"])
async def test_whitelist_allows_group_member_by_sender_alias(alias):
    stage = await _stage([alias])
    event = _event(
        umo="lark:GroupMessage:oc_group",
        group_id="oc_group",
        aliases=[alias],
        message_type=MessageType.GROUP_MESSAGE,
    )

    await stage.process(event)

    event.stop_event.assert_not_called()


@pytest.mark.asyncio
async def test_whitelist_blocks_unlisted_sender_alias():
    stage = await _stage(["u_123"])
    event = _event(umo="lark:FriendMessage:ou_sender", aliases=["u_999"])

    await stage.process(event)

    event.stop_event.assert_called_once()


@pytest.mark.asyncio
async def test_whitelist_blocks_sender_without_aliases():
    stage = await _stage(["u_123"])
    event = _event(umo="lark:FriendMessage:ou_sender")

    await stage.process(event)

    event.stop_event.assert_called_once()


@pytest.mark.asyncio
async def test_whitelist_does_not_match_primary_sender_id_for_group():
    stage = await _stage(["ou_sender"])
    event = _event(
        umo="lark:GroupMessage:oc_group",
        group_id="oc_group",
        sender_id="ou_sender",
        message_type=MessageType.GROUP_MESSAGE,
    )

    await stage.process(event)

    event.stop_event.assert_called_once()


@pytest.mark.asyncio
async def test_whitelist_still_allows_umo_and_group_entries():
    private_stage = await _stage(["lark:FriendMessage:ou_sender"])
    private_event = _event(umo="lark:FriendMessage:ou_sender")

    await private_stage.process(private_event)

    private_event.stop_event.assert_not_called()

    group_stage = await _stage(["oc_group"])
    group_event = _event(
        umo="lark:GroupMessage:oc_group",
        group_id="oc_group",
        message_type=MessageType.GROUP_MESSAGE,
    )

    await group_stage.process(group_event)

    group_event.stop_event.assert_not_called()
