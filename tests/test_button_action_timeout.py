import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import ActionRow, Button, CallbackAction
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform import button_interaction
from astrbot.core.platform.sources.dingtalk import dingtalk_adapter
from astrbot.core.platform.sources.discord.components import action_rows_to_discord_view
from astrbot.core.platform.sources.kook.kook_event import KookEvent
from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
from astrbot.core.platform.sources.line.line_event import LineMessageEvent
from astrbot.core.platform.sources.mattermost.client import MattermostClient
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.satori.satori_event import SatoriPlatformEvent
from astrbot.core.platform.sources.slack.slack_event import SlackMessageEvent
from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
from astrbot.core.platform.sources.webchat import webchat_event
from astrbot.core.platform.sources.webchat.message_parts_helper import (
    message_chain_to_storage_message_parts,
)
from astrbot.core.platform.sources.wecom.wecom_event import WecomPlatformEvent
from astrbot.core.platform.sources.wecom.wecom_kf_message import WeChatKFMessage
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_buttons import (
    build_wecom_button_card,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("action_timeout", [None, 60])
@pytest.mark.parametrize(
    "platform",
    [
        "telegram",
        "discord",
        "qq",
        "lark",
        "line",
        "slack",
        "mattermost",
        "kook",
        "satori",
        "satori_static",
        "wecom",
        "wecom_kf",
        "wecom_ai",
        "dingtalk",
        "webchat",
        "webchat_storage",
    ],
)
async def test_platform_callback_honors_row_deadline(
    platform, action_timeout, monkeypatch, tmp_path
):
    """Exercise native rendering and expiry without making network requests.

    Args:
        platform: Native renderer under test.
        action_timeout: Optional row lifetime in seconds.
        monkeypatch: Fixture isolating the clock, callback registry, and clients.
        tmp_path: Temporary directory for WebChat storage.
    """
    clock = [100.0]
    monkeypatch.setattr(button_interaction.time, "time", lambda: clock[0])
    monkeypatch.setattr(
        button_interaction,
        "_button_callback_registry",
        button_interaction._ButtonCallbackRegistry(),
    )
    row = ActionRow(
        buttons=[
            Button(
                id="approve", label="Approve", action=CallbackAction(data={"item": 42})
            )
        ],
        action_timeout=action_timeout,
    )
    chain = MessageChain([row])

    if platform == "telegram":
        token = (
            TelegramPlatformEvent._build_inline_keyboard([row])
            .inline_keyboard[0][0]
            .callback_data
        )
    elif platform == "discord":
        token = action_rows_to_discord_view([row]).children[0].custom_id
    elif platform == "qq":
        token = QQOfficialMessageEvent._parse_keyboard(chain)["content"]["rows"][0][
            "buttons"
        ][0]["action"]["data"]
    elif platform == "lark":
        card = LarkMessageEvent._build_button_card([row])
        token = card["body"]["elements"][0]["columns"][0]["elements"][0]["behaviors"][
            0
        ]["value"]["astrbot_callback"]
    elif platform == "line":
        message = await LineMessageEvent._component_to_message_object(row)
        token = message["template"]["actions"][0]["data"]
    elif platform == "slack":
        block = await SlackMessageEvent._from_segment_to_slack_block(row, AsyncMock())
        token = block["elements"][0]["value"]
    elif platform == "mattermost":
        client = MattermostClient(
            "https://chat.example.com",
            "token",
            action_callback_url="https://bot.example.com/callback",
        )
        attachment = client._build_action_row_attachment(row, 0)
        token = attachment["actions"][0]["integration"]["context"]["astrbot_callback"]
    elif platform == "kook":
        event = object.__new__(KookEvent)
        result = await event._wrap_message(0, row)
        token = json.loads(result.text)[0]["modules"][0]["elements"][0]["value"]
    elif platform in {"satori", "satori_static"}:
        if platform == "satori":
            event = object.__new__(SatoriPlatformEvent)
            markup = await event._convert_component_to_satori(row)
        else:
            markup = await SatoriPlatformEvent._convert_component_to_satori_static(row)
        token = markup.split('id="', 1)[1].split('"', 1)[0]
    elif platform in {"wecom", "wecom_kf"}:
        message = AstrBotMessage()
        message.type = MessageType.FRIEND_MESSAGE
        message.self_id = "100001"
        message.session_id = "alice"
        message.message_id = "message-1"
        message.sender = MessageMember("alice", "Alice")
        message.message = []
        message.raw_message = {}
        if platform == "wecom":
            client = SimpleNamespace(message=MagicMock())
        else:
            client = SimpleNamespace(kf_message=MagicMock(spec=WeChatKFMessage))
        event = WecomPlatformEvent(
            "", message, PlatformMetadata("wecom", "WeCom", "test"), "alice", client
        )
        await event.send(chain)
        if platform == "wecom":
            token = client.message.send.call_args.kwargs["msg"]["template_card"][
                "button_list"
            ][0]["key"]
        else:
            token = client.kf_message.send_msgmenu.call_args.args[3][0]["click"]["id"]
    elif platform == "wecom_ai":
        token = build_wecom_button_card([row])["button_list"][0]["key"]
    elif platform == "dingtalk":
        session = MagicMock()
        session.__aenter__.return_value = session
        session.post.return_value.__aenter__.return_value = SimpleNamespace(status=200)
        monkeypatch.setattr(dingtalk_adapter.aiohttp, "ClientSession", lambda: session)
        adapter = object.__new__(dingtalk_adapter.DingtalkPlatformAdapter)
        adapter.get_access_token = AsyncMock(return_value="token")
        assert await adapter._send_button_card(
            "group", "conversation", "robot", "Choose", [row]
        )
        card = session.post.call_args.kwargs["json"]["cardData"]["cardParamMap"]
        token = json.loads(card["sys_full_json_obj"])["msgButtons"][0]["id"]
    elif platform == "webchat":
        queue = AsyncMock(return_value=True)
        monkeypatch.setattr(webchat_event.webchat_queue_mgr, "put_back_queue", queue)
        await webchat_event.WebChatMessageEvent._send("message-1", chain, "session-1")
        token = queue.await_args_list[0].args[1]["data"]["buttons"][0]["action"][
            "callback_data"
        ]
    else:
        parts = await message_chain_to_storage_message_parts(
            chain, insert_attachment=AsyncMock(), attachments_dir=tmp_path
        )
        token = parts[0]["buttons"][0]["action"]["callback_data"]

    assert button_interaction.decode_button_callback(token) == ("approve", {"item": 42})
    clock[0] = 160.0
    if action_timeout is None:
        assert button_interaction.decode_button_callback(token) == (
            "approve",
            {"item": 42},
        )
    else:
        with pytest.raises(ValueError, match="expired"):
            button_interaction.decode_button_callback(token)
