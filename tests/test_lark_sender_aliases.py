from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.message_components import ActionRow, Button
from astrbot.api.platform import MessageType
from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter
from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent


@pytest.fixture(autouse=True)
def mock_private_chat_storage(monkeypatch):
    """Keep sender-alias tests independent of persistent routing storage.

    Args:
        monkeypatch: Fixture used to replace the route storage writer.
    """
    monkeypatch.setattr(
        "astrbot.core.platform.sources.lark.lark_adapter.sp.put_async", AsyncMock()
    )


def _message_event(
    *,
    open_id: str = "ou_sender",
    user_id: str | None = None,
    union_id: str | None = None,
    chat_type: str = "p2p",
) -> SimpleNamespace:
    """Build a Lark message event with the optional sender aliases.

    Args:
        open_id: Primary Lark open_id for the sender.
        user_id: Tenant-level Lark user_id, when available.
        union_id: Lark union_id, when available.
        chat_type: Group or private chat type reported by Lark.

    Returns:
        Lark-compatible event object.
    """
    return SimpleNamespace(
        event=SimpleNamespace(
            sender=SimpleNamespace(
                sender_id=SimpleNamespace(
                    open_id=open_id,
                    user_id=user_id,
                    union_id=union_id,
                ),
                sender_type="user",
            ),
            message=SimpleNamespace(
                create_time="1700000000000",
                chat_type=chat_type,
                chat_id="oc_private" if chat_type == "p2p" else "oc_group",
                parent_id=None,
                mentions=None,
                content='{"text":"hello"}',
                message_id="message-1",
                message_type="text",
            ),
        ),
    )


def _adapter() -> LarkPlatformAdapter:
    """Build an adapter with a mocked Contact API.

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
                user=SimpleNamespace(
                    aget=AsyncMock(
                        return_value=SimpleNamespace(
                            success=lambda: False,
                            data=None,
                            code=999,
                            msg="permission denied",
                        )
                    )
                )
            ),
        ),
    )
    return adapter


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_type", ["p2p", "group"])
async def test_lark_message_collects_user_and_union_aliases(chat_type):
    adapter = _adapter()

    await adapter.convert_msg(
        _message_event(chat_type=chat_type, user_id="u_123", union_id="on_456")
    )

    message = adapter.handle_msg.await_args.args[0]
    assert message.sender.user_id == "ou_sender"
    assert message.sender.aliases == ["u_123", "on_456"]
    assert message.session_id == ("ou_sender" if chat_type == "p2p" else "oc_group")


@pytest.mark.asyncio
async def test_lark_message_omits_missing_and_duplicate_aliases():
    adapter = _adapter()

    await adapter.convert_msg(_message_event(user_id="ou_sender", union_id=None))

    message = adapter.handle_msg.await_args.args[0]
    assert message.sender.aliases == []


@pytest.mark.asyncio
async def test_lark_message_omits_empty_alias_ids():
    adapter = _adapter()

    await adapter.convert_msg(_message_event(user_id="", union_id=""))

    message = adapter.handle_msg.await_args.args[0]
    assert message.sender.aliases == []


@pytest.mark.asyncio
async def test_lark_message_tolerates_missing_alias_attributes():
    adapter = _adapter()
    event = _message_event()
    event.event.sender.sender_id = SimpleNamespace(open_id="ou_sender")

    await adapter.convert_msg(event)

    message = adapter.handle_msg.await_args.args[0]
    assert message.sender.user_id == "ou_sender"
    assert message.sender.aliases == []


@pytest.mark.asyncio
async def test_lark_message_collects_available_alias_only():
    adapter = _adapter()

    await adapter.convert_msg(_message_event(user_id=None, union_id="on_456"))

    message = adapter.handle_msg.await_args.args[0]
    assert message.sender.aliases == ["on_456"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operator", "expected_aliases"),
    [
        (
            {"open_id": "ou_user", "user_id": "u_123", "union_id": "on_456"},
            ["u_123", "on_456"],
        ),
        ({"open_id": "ou_user"}, []),
        ({"open_id": "ou_user", "user_id": "ou_user"}, []),
    ],
)
async def test_lark_card_callback_collects_operator_aliases(
    operator, expected_aliases
):
    adapter = object.__new__(LarkPlatformAdapter)
    adapter.event_id_timestamps = {}
    adapter.bot_open_id = "ou_bot"
    adapter.bot_name = "AstrBot"
    adapter.handle_msg = AsyncMock()
    card = LarkMessageEvent._build_button_card(
        [
            ActionRow(
                buttons=[
                    Button(
                        id="approve",
                        label="Approve",
                        action=Button.CallbackAction(data={"request_id": 42}),
                    )
                ]
            )
        ],
        MessageType.GROUP_MESSAGE.value,
    )
    callback_value = card["body"]["elements"][0]["columns"][0]["elements"][0][
        "behaviors"
    ][0]["value"]

    await adapter.convert_card_action(
        {
            "header": {
                "event_id": "event-1",
                "create_time": "1720000000000000",
            },
            "event": {
                "operator": operator,
                "action": {"tag": "button", "value": callback_value},
                "context": {
                    "open_message_id": "om_source",
                    "open_chat_id": "oc_group",
                },
            },
        }
    )

    message = adapter.handle_msg.await_args.args[0]
    assert message.sender.user_id == "ou_user"
    assert message.sender.aliases == expected_aliases
