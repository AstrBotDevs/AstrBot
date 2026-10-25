from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter


@pytest.fixture(autouse=True)
def mock_private_chat_storage(monkeypatch):
    """Keep sender-name tests independent of persistent routing storage.

    Args:
        monkeypatch: Fixture used to replace the route storage writer.
    """
    monkeypatch.setattr(
        "astrbot.core.platform.sources.lark.lark_adapter.sp.put_async", AsyncMock()
    )


def _message_event(
    message_id: str = "message-1", *, chat_type: str = "p2p", sender_type: str = "user"
) -> SimpleNamespace:
    """Build a Lark group or private-message event.

    Args:
        message_id: Unique message identifier.
        chat_type: Group or private chat type reported by Lark.
        sender_type: User or application sender reported by Lark.

    Returns:
        Lark-compatible event object.
    """
    return SimpleNamespace(
        event=SimpleNamespace(
            sender=SimpleNamespace(
                sender_id=SimpleNamespace(open_id="ou_sender"),
                sender_type=sender_type,
            ),
            message=SimpleNamespace(
                create_time="1700000000000",
                chat_type=chat_type,
                chat_id="oc_private",
                parent_id=None,
                mentions=None,
                content='{"text":"hello"}',
                message_id=message_id,
                message_type="text",
            ),
        ),
    )


def _adapter(user_response: SimpleNamespace) -> LarkPlatformAdapter:
    """Builds an adapter with a mocked Contact API.

    Args:
        user_response: Response returned by the Contact API.

    Returns:
        Lark adapter test double.
    """
    adapter = LarkPlatformAdapter.__new__(LarkPlatformAdapter)
    adapter.config = {"id": "lark-test"}
    adapter.appid = "cli_test"
    adapter.bot_open_id = "ou_bot"
    adapter.bot_name = "AstrBot"
    adapter._user_name_cache = {}
    adapter.handle_msg = AsyncMock()
    adapter.lark_api = SimpleNamespace(
        contact=SimpleNamespace(
            v3=SimpleNamespace(
                user=SimpleNamespace(aget=AsyncMock(return_value=user_response)),
            ),
        ),
    )
    return adapter


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_type", ["p2p", "group"])
async def test_lark_sender_uses_contact_display_name_and_cache(chat_type):
    adapter = _adapter(
        SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(user=SimpleNamespace(name="Alice Zhang")),
        ),
    )

    await adapter.convert_msg(_message_event("message-1", chat_type=chat_type))
    await adapter.convert_msg(_message_event("message-2", chat_type=chat_type))

    first_message = adapter.handle_msg.await_args_list[0].args[0]
    second_message = adapter.handle_msg.await_args_list[1].args[0]
    assert first_message.sender.user_id == "ou_sender"
    assert first_message.sender.nickname == "Alice Zhang"
    assert second_message.sender.nickname == "Alice Zhang"
    adapter.lark_api.contact.v3.user.aget.assert_awaited_once()
    request = adapter.lark_api.contact.v3.user.aget.await_args.args[0]
    assert request.user_id == "ou_sender"
    assert request.user_id_type == "open_id"


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_type", ["p2p", "group"])
async def test_lark_sender_falls_back_when_contact_lookup_fails(chat_type):
    adapter = _adapter(
        SimpleNamespace(
            success=lambda: False,
            data=None,
            code=999,
            msg="permission denied",
        ),
    )

    await adapter.convert_msg(_message_event(chat_type=chat_type))
    await adapter.convert_msg(_message_event("message-2", chat_type=chat_type))

    message = adapter.handle_msg.await_args.args[0]
    assert message.sender.user_id == "ou_sender"
    assert message.sender.nickname == "ou_sende"
    adapter.lark_api.contact.v3.user.aget.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_type", ["p2p", "group"])
async def test_lark_sender_retries_after_failure_cache_expires(chat_type):
    adapter = _adapter(
        SimpleNamespace(
            success=lambda: False,
            data=None,
            code=999,
            msg="permission denied",
        ),
    )

    await adapter.convert_msg(_message_event("message-1", chat_type=chat_type))
    adapter._user_name_cache["ou_sender"] = ("ou_sende", 0)
    adapter.lark_api.contact.v3.user.aget.return_value = SimpleNamespace(
        success=lambda: True,
        data=SimpleNamespace(user=SimpleNamespace(name="Alice Zhang")),
    )
    await adapter.convert_msg(_message_event("message-2", chat_type=chat_type))

    message = adapter.handle_msg.await_args_list[1].args[0]
    assert message.sender.nickname == "Alice Zhang"
    assert adapter.lark_api.contact.v3.user.aget.await_count == 2


@pytest.mark.asyncio
async def test_lark_group_and_private_messages_share_sender_name_cache():
    """Reuse one user lookup across private messages and different group chats."""
    adapter = _adapter(
        SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(user=SimpleNamespace(name="Alice Zhang")),
        )
    )
    for index, chat_type in enumerate(["group", "p2p", "group"]):
        event = _message_event(f"message-{index}", chat_type=chat_type)
        event.event.message.chat_id = f"oc_chat_{index}"
        await adapter.convert_msg(event)
    adapter.lark_api.contact.v3.user.aget.assert_awaited_once()
    assert all(
        call.args[0].sender.nickname == "Alice Zhang"
        for call in adapter.handle_msg.await_args_list
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_type", ["p2p", "group"])
async def test_lark_app_senders_skip_contact_lookup(chat_type):
    """Avoid querying the user directory for application senders."""
    adapter = _adapter(SimpleNamespace())
    await adapter.convert_msg(_message_event(chat_type=chat_type, sender_type="app"))
    adapter.lark_api.contact.v3.user.aget.assert_not_awaited()
