from unittest.mock import AsyncMock, MagicMock

import pytest
from wechatpy.enterprise import parse_message

from astrbot.api.event import MessageChain
from astrbot.api.message_components import (
    ActionRow,
    Button,
    ButtonInteraction,
    ButtonStyle,
    CallbackAction,
    Plain,
    UrlAction,
)
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform.button_interaction import (
    decode_button_callback,
    encode_button_callback,
)
from astrbot.core.platform.sources.wecom.wecom_adapter import WecomPlatformAdapter
from astrbot.core.platform.sources.wecom.wecom_event import WecomPlatformEvent
from astrbot.core.platform.sources.wecom.wecom_kf_message import WeChatKFMessage


def _message() -> AstrBotMessage:
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "100001"
    message.session_id = "alice"
    message.message_id = "message-1"
    message.sender = MessageMember("alice", "Alice")
    message.message = []
    message.message_str = ""
    message.raw_message = {}
    return message


def _event(client) -> WecomPlatformEvent:
    message = _message()
    return WecomPlatformEvent(
        message_str="",
        message_obj=message,
        platform_meta=PlatformMetadata("wecom", "WeCom", "test-wecom"),
        session_id=message.session_id,
        client=client,
    )


def _row() -> ActionRow:
    return ActionRow(
        fallback_text="Choose an action",
        buttons=[
            Button(
                id="approve",
                label="Approve",
                style=ButtonStyle.SUCCESS,
                action=CallbackAction(data={"request_id": 42}),
            ),
            Button(
                id="docs",
                label="Documentation",
                action=UrlAction(url="https://example.com/docs"),
            ),
        ],
    )


@pytest.mark.asyncio
async def test_wecom_application_sends_action_row_as_template_card():
    class AppClient:
        def __init__(self) -> None:
            self.message = MagicMock()

    client = AppClient()

    await _event(client).send(MessageChain([_row()]))

    client.message.send.assert_called_once()
    args, kwargs = client.message.send.call_args
    assert args == ("100001", "alice")
    payload = kwargs["msg"]
    assert payload["msgtype"] == "template_card"
    card = payload["template_card"]
    assert card["card_type"] == "button_interaction"
    assert card["main_title"] == {"title": "Choose an action"}
    assert card["task_id"].startswith("astrbot_")
    callback_button, url_button = card["button_list"]
    assert callback_button["type"] == 0
    assert callback_button["style"] == 4
    action_id, data = decode_button_callback(callback_button["key"])
    assert action_id == "approve"
    assert data == {"request_id": 42}
    assert url_button == {
        "text": "Documentation",
        "style": 1,
        "type": 1,
        "url": "https://example.com/docs",
    }


@pytest.mark.asyncio
async def test_wecom_customer_service_sends_action_row_as_menu():
    kf_message = MagicMock(spec=WeChatKFMessage)

    class CustomerServiceClient:
        def __init__(self) -> None:
            self.kf_message = kf_message

    await _event(CustomerServiceClient()).send(MessageChain([_row()]))

    kf_message.send_msgmenu.assert_called_once()
    user_id, open_kfid, head, menu, tail = kf_message.send_msgmenu.call_args.args
    assert (user_id, open_kfid, head, tail) == (
        "alice",
        "100001",
        "Choose an action",
        "",
    )
    action_id, data = decode_button_callback(menu[0]["click"]["id"])
    assert action_id == "approve"
    assert data == {"request_id": 42}
    assert menu[1] == {
        "type": "view",
        "view": {
            "url": "https://example.com/docs",
            "content": "Documentation",
        },
    }


@pytest.mark.asyncio
async def test_wecom_template_card_callback_becomes_button_interaction():
    callback = encode_button_callback("approve", {"request_id": 42})
    raw_message = parse_message(
        "<xml>"
        "<ToUserName><![CDATA[corp]]></ToUserName>"
        "<FromUserName><![CDATA[alice]]></FromUserName>"
        "<CreateTime>1700000000</CreateTime>"
        "<MsgType><![CDATA[event]]></MsgType>"
        "<Event><![CDATA[template_card_event]]></Event>"
        f"<EventKey><![CDATA[{callback}]]></EventKey>"
        "<TaskId><![CDATA[task-1]]></TaskId>"
        "<CardType><![CDATA[button_interaction]]></CardType>"
        "<ResponseCode><![CDATA[response-1]]></ResponseCode>"
        "<AgentID>100001</AgentID>"
        "</xml>"
    )
    adapter = object.__new__(WecomPlatformAdapter)
    adapter.agent_id = None
    adapter.handle_msg = AsyncMock()

    message = await adapter.convert_message(raw_message)

    assert message is not None
    assert message.message_str == "approve"
    assert message.message_id == "response-1"
    assert message.session_id == "alice"
    interaction = message.message[0]
    assert isinstance(interaction, ButtonInteraction)
    assert interaction.action_id == "approve"
    assert interaction.data == {"request_id": 42}
    assert interaction.interaction_id == "response-1"
    assert interaction.source_message_id == "task-1"
    adapter.handle_msg.assert_awaited_once_with(message)


@pytest.mark.asyncio
async def test_wecom_foreign_customer_service_menu_stays_plain_text():
    adapter = object.__new__(WecomPlatformAdapter)
    adapter._wechat_kf_seen_text_messages = {}
    adapter.handle_msg = AsyncMock()

    message = await adapter.convert_wechat_kf_message(
        {
            "msgtype": "text",
            "external_userid": "customer-1",
            "open_kfid": "kf-1",
            "msgid": "click-2",
            "text": {"content": "Another menu", "menu_id": "foreign-menu"},
        }
    )

    assert message is not None
    assert message.message_str == "Another menu"
    assert len(message.message) == 1
    assert isinstance(message.message[0], Plain)
    assert message.message[0].text == "Another menu"
    adapter.handle_msg.assert_awaited_once_with(message)


@pytest.mark.asyncio
async def test_wecom_customer_service_menu_click_becomes_button_interaction():
    adapter = object.__new__(WecomPlatformAdapter)
    adapter._wechat_kf_seen_text_messages = {}
    adapter.handle_msg = AsyncMock()
    callback = encode_button_callback("approve", {"request_id": 42})

    message = await adapter.convert_wechat_kf_message(
        {
            "msgtype": "text",
            "external_userid": "customer-1",
            "open_kfid": "kf-1",
            "msgid": "click-1",
            "text": {"content": "Approve", "menu_id": callback},
        }
    )

    assert message is not None
    assert message.message_str == "approve"
    interaction = message.message[0]
    assert isinstance(interaction, ButtonInteraction)
    assert interaction.action_id == "approve"
    assert interaction.data == {"request_id": 42}
    assert interaction.interaction_id == "click-1"
    assert interaction.source_message_id is None
    adapter.handle_msg.assert_awaited_once_with(message)
