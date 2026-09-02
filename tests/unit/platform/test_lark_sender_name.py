from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter

pytestmark = pytest.mark.platform


def _private_message_event(message_id: str = "message-1") -> SimpleNamespace:
    """Builds a Lark private-message event.

    Args:
        message_id: Unique message identifier.

    Returns:
        Lark-compatible event object.
    """
    return SimpleNamespace(
        event=SimpleNamespace(
            sender=SimpleNamespace(
                sender_id=SimpleNamespace(open_id="ou_sender"),
                sender_type="user",
            ),
            message=SimpleNamespace(
                create_time="1700000000000",
                chat_type="p2p",
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
async def test_lark_private_sender_uses_contact_display_name_and_cache():
    adapter = _adapter(
        SimpleNamespace(
            success=lambda: True,
            data=SimpleNamespace(user=SimpleNamespace(name="Alice Zhang")),
        ),
    )

    await adapter.convert_msg(_private_message_event("message-1"))
    await adapter.convert_msg(_private_message_event("message-2"))

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
async def test_lark_private_sender_falls_back_when_contact_lookup_fails():
    adapter = _adapter(
        SimpleNamespace(
            success=lambda: False,
            data=None,
            code=999,
            msg="permission denied",
        ),
    )

    await adapter.convert_msg(_private_message_event())

    message = adapter.handle_msg.await_args.args[0]
    assert message.sender.user_id == "ou_sender"
    assert message.sender.nickname == "ou_sende"


@pytest.mark.asyncio
async def test_lark_private_sender_redacts_contact_lookup_exceptions(caplog):
    adapter = _adapter(SimpleNamespace(success=lambda: True, data=None))
    adapter.lark_api.contact.v3.user.aget.side_effect = RuntimeError(
        "lookup failed https://open.feishu.cn/open-apis/contact/v3/users?token=secret"
    )

    with caplog.at_level("DEBUG"):
        await adapter.convert_msg(_private_message_event())

    message = adapter.handle_msg.await_args.args[0]
    assert message.sender.nickname == "ou_sende"
    debug_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "https://open.feishu.cn" not in debug_text
    assert "token=secret" not in debug_text
    assert "Sender name lookup failed" in debug_text


@pytest.mark.asyncio
async def test_lark_private_sender_retries_after_failure_cache_expires():
    adapter = _adapter(
        SimpleNamespace(
            success=lambda: False,
            data=None,
            code=999,
            msg="permission denied",
        ),
    )

    await adapter.convert_msg(_private_message_event("message-1"))
    adapter._user_name_cache["ou_sender"] = ("ou_sende", 0)
    adapter.lark_api.contact.v3.user.aget.return_value = SimpleNamespace(
        success=lambda: True,
        data=SimpleNamespace(user=SimpleNamespace(name="Alice Zhang")),
    )
    await adapter.convert_msg(_private_message_event("message-2"))

    message = adapter.handle_msg.await_args_list[1].args[0]
    assert message.sender.nickname == "Alice Zhang"
    assert adapter.lark_api.contact.v3.user.aget.await_count == 2
