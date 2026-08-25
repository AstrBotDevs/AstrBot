import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.core.platform.button_interaction import decode_button_callback
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_adapter import (
    WecomAIBotAdapter,
)
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_buttons import (
    build_wecom_button_card,
)
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_event import (
    WecomAIBotMessageEvent,
)
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_queue_mgr import (
    WecomAIQueueMgr,
)
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_webhook import (
    WecomAIBotWebhookClient,
)


def _button_row() -> ActionRow:
    return ActionRow(
        fallback_text="Choose an action",
        buttons=[
            Button(
                id="approve",
                label="Approve",
                action=CallbackAction(data={"request_id": 42}),
                style=ButtonStyle.SUCCESS,
            ),
            Button(
                id="docs",
                label="Docs",
                action=UrlAction(url="https://example.com/docs"),
                style=ButtonStyle.DANGER,
            ),
        ],
    )


def _interaction_message(stream_id: str) -> AstrBotMessage:
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "bot"
    message.session_id = "session"
    message.message_id = "event-1"
    message.message_str = ""
    message.sender = MessageMember(user_id="user-1", nickname="user-1")
    message.message = []
    message.raw_message = {"stream_id": stream_id}
    return message


def test_wecom_button_card_maps_callback_and_url_actions():
    card = build_wecom_button_card([_button_row()], task_id="task-1")

    assert card is not None
    assert card["card_type"] == "button_interaction"
    assert card["main_title"] == {"title": "Choose an action"}
    assert card["task_id"] == "task-1"
    callback_button, url_button = card["button_list"]
    assert callback_button["type"] == 0
    assert callback_button["style"] == 3
    assert decode_button_callback(callback_button["key"]) == (
        "approve",
        {"request_id": 42},
    )
    assert url_button == {
        "text": "Docs",
        "style": 2,
        "type": 1,
        "url": "https://example.com/docs",
    }


@pytest.mark.asyncio
async def test_wecom_webhook_sends_action_row_as_template_card():
    client = WecomAIBotWebhookClient(
        "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key"
    )
    client.send_payload = AsyncMock()

    await client.send_message_chain(MessageChain([_button_row()]))

    payload = client.send_payload.await_args.args[0]
    assert payload["msgtype"] == "template_card"
    assert payload["template_card"]["card_type"] == "button_interaction"


@pytest.mark.asyncio
async def test_wecom_template_card_callback_becomes_button_interaction():
    adapter = object.__new__(WecomAIBotAdapter)
    adapter.bot_name = "AstrBot"
    adapter.encoding_aes_key = ""
    callback_key = build_wecom_button_card([_button_row()])["button_list"][0]["key"]

    message = await adapter.convert_message(
        {
            "message_data": {
                "msgtype": "event",
                "msgid": "event-1",
                "create_time": 1720000000,
                "chattype": "group",
                "chatid": "group-1",
                "from": {"userid": "user-1"},
                "event": {
                    "eventtype": "template_card_event",
                    "template_card_event": {
                        "event_key": callback_key,
                        "task_id": "task-1",
                    },
                },
            },
            "session_id": "session-1",
            "stream_id": "interaction-1",
        }
    )

    assert message.message_str == ""
    assert message.message_id == "event-1"
    assert message.timestamp == 1720000000
    assert message.type == MessageType.GROUP_MESSAGE
    assert len(message.message) == 1
    interaction = message.message[0]
    assert isinstance(interaction, ButtonInteraction)
    assert interaction.action_id == "approve"
    assert interaction.data == {"request_id": 42}
    assert interaction.interaction_id == "event-1"
    assert interaction.source_message_id == "task-1"


def test_wecom_button_card_rejects_more_than_six_buttons():
    buttons = [
        Button(
            id=f"action-{index}",
            label=f"Action {index}",
            action=CallbackAction(),
        )
        for index in range(7)
    ]

    with pytest.raises(ValueError, match="at most 6"):
        build_wecom_button_card([ActionRow(buttons=buttons)])


@pytest.mark.asyncio
async def test_wecom_long_connection_click_reply_updates_source_card():
    queue_mgr = WecomAIQueueMgr()
    stream_id = "interaction-stream"
    queue_mgr.set_pending_response(
        stream_id,
        {
            "req_id": "request-1",
            "connection_mode": "long_connection",
            "button_interaction": "true",
            "task_id": "task-1",
        },
    )
    update_sender = AsyncMock(return_value=True)
    event = WecomAIBotMessageEvent(
        message_str="",
        message_obj=_interaction_message(stream_id),
        platform_meta=PlatformMetadata(
            name="wecom_ai_bot",
            description="WeCom AI Bot",
            id="wecom-ai-test",
        ),
        session_id="session",
        api_client=None,
        queue_mgr=queue_mgr,
        long_connection_update_sender=update_sender,
    )

    await event.send(MessageChain([Plain("Approved")]))

    update_sender.assert_awaited_once()
    req_id, body = update_sender.await_args.args
    assert req_id == "request-1"
    assert body["response_type"] == "update_template_card"
    assert body["template_card"]["main_title"] == {"title": "Approved"}
    assert body["template_card"]["task_id"] == "task-1"


@pytest.mark.asyncio
async def test_wecom_webhook_click_can_return_immediate_card_update():
    adapter = object.__new__(WecomAIBotAdapter)
    adapter.api_client = SimpleNamespace(
        encrypt_message=AsyncMock(side_effect=lambda payload, _nonce, _time: payload)
    )
    adapter.queue_mgr = WecomAIQueueMgr()
    adapter.only_use_webhook_url_to_send = False
    adapter.webhook_client = None
    adapter.initial_respond_text = ""
    adapter.friend_message_welcome_text = ""
    adapter.bot_name = "AstrBot"
    adapter.encoding_aes_key = ""
    adapter.metadata = PlatformMetadata(
        name="wecom_ai_bot",
        description="WeCom AI Bot",
        id="wecom-ai-test",
    )
    callback_key = build_wecom_button_card([_button_row()])["button_list"][0]["key"]

    async def reply_to_click(payload: dict) -> None:
        message = await adapter.convert_message(payload)
        event = adapter.create_event(message)
        await event.send(MessageChain([Plain("Approved")]))

    adapter.queue_mgr.set_listener(reply_to_click)
    response = await adapter._process_message(
        {
            "msgtype": "event",
            "msgid": "event-1",
            "chattype": "single",
            "from": {"userid": "user-1"},
            "event": {
                "eventtype": "template_card_event",
                "template_card_event": {
                    "event_key": callback_key,
                    "task_id": "task-1",
                },
            },
        },
        {"nonce": "nonce", "timestamp": "timestamp"},
    )

    assert response is not None
    update = json.loads(response)
    assert update["response_type"] == "update_template_card"
    assert update["template_card"]["main_title"] == {"title": "Approved"}
    assert update["template_card"]["task_id"] == "task-1"
