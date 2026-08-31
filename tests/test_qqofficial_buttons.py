from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import botpy
import botpy.message
import pytest
from botpy.interaction import Interaction

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
from astrbot.core.platform.button_interaction import encode_button_callback
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    botClient as QQOfficialBotClient,
)
from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_adapter import (
    botClient as QQOfficialWebhookBotClient,
)


def _make_interaction(
    *,
    scene: str = "group",
    button_id: str = "approve",
    button_data: str | None = None,
) -> Interaction:
    resolved = {
        "button_id": button_id,
        "button_data": button_data
        or encode_button_callback("approve", {"request_id": "req-1"}),
        "message_id": "source-message-1",
        "user_id": "guild-user-1",
    }
    return Interaction(
        api=None,
        event_id="gateway-event-1",
        data={
            "id": "interaction-1",
            "application_id": "app-1",
            "type": 11,
            "scene": scene,
            "chat_type": 1,
            "data": {"type": 11, "resolved": resolved},
            "group_openid": "group-1",
            "group_member_openid": "member-1",
            "user_openid": "user-1",
            "guild_id": "guild-1",
            "channel_id": "channel-1",
            "timestamp": "2026-08-25T10:00:00+08:00",
            "version": 1,
        },
    )


def _make_group_event() -> QQOfficialMessageEvent:
    raw = botpy.message.GroupMessage(
        api=None,
        event_id="event-1",
        data={
            "id": "msg-1",
            "author": {"member_openid": "member-1"},
            "group_openid": "group-1",
            "content": "ping",
            "timestamp": "0",
        },
    )
    abm = AstrBotMessage()
    abm.message_id = "msg-1"
    abm.session_id = "group-1"
    abm.group_id = "group-1"
    abm.self_id = "bot-1"
    abm.sender = MessageMember(user_id="member-1")
    abm.type = MessageType.GROUP_MESSAGE
    abm.message_str = "ping"
    abm.message = []
    abm.raw_message = raw
    meta = PlatformMetadata(name="qq_official", description="test", id="test")
    bot = SimpleNamespace(api=SimpleNamespace(post_group_message=AsyncMock()))
    return QQOfficialMessageEvent(
        message_str="ping",
        message_obj=abm,
        platform_meta=meta,
        session_id="group-1",
        bot=bot,
    )


def test_qq_keyboard_renders_callback_and_url_buttons() -> None:
    chain = MessageChain(
        chain=[
            ActionRow(
                buttons=[
                    Button(
                        id="approve",
                        label="Approve request",
                        action=CallbackAction(data={"request_id": "req-1"}),
                        style=ButtonStyle.PRIMARY,
                    ),
                    Button(
                        id="docs",
                        label="Docs",
                        action=UrlAction(url="https://example.com/docs"),
                    ),
                ]
            )
        ]
    )

    keyboard = QQOfficialMessageEvent._parse_keyboard(chain)

    assert keyboard is not None
    buttons = keyboard["content"]["rows"][0]["buttons"]
    assert buttons[0] == {
        "id": "approve",
        "render_data": {
            "label": "Approve re",
            "visited_label": "Approve re",
            "style": 3,
        },
        "action": {
            "type": 1,
            "permission": {"type": 2},
            "data": encode_button_callback("approve", {"request_id": "req-1"}),
        },
    }
    assert buttons[1]["action"] == {
        "type": 0,
        "permission": {"type": 2},
        "data": "https://example.com/docs",
    }


def test_qq_keyboard_validates_platform_limits() -> None:
    chain = MessageChain(
        chain=[
            ActionRow(
                buttons=[
                    Button(
                        id=f"button-{index}",
                        label=str(index),
                        action=CallbackAction(),
                    )
                    for index in range(6)
                ]
            )
        ]
    )

    with pytest.raises(ValueError, match="at most 5 buttons"):
        QQOfficialMessageEvent._parse_keyboard(chain)


@pytest.mark.asyncio
async def test_qq_group_send_includes_rendered_keyboard() -> None:
    event = _make_group_event()
    chain = MessageChain(
        chain=[
            Plain("Choose"),
            ActionRow(
                buttons=[
                    Button(
                        id="approve",
                        label="Approve",
                        action=CallbackAction(data={"request_id": "req-1"}),
                    )
                ]
            ),
        ],
        use_markdown_=False,
    )
    event.send_buffer = chain

    await event._post_send_one(chain)

    kwargs = event.bot.api.post_group_message.await_args.kwargs
    assert kwargs["keyboard"]["content"]["rows"][0]["buttons"][0]["id"] == "approve"
    assert kwargs["content"] == "Choose"


@pytest.mark.asyncio
async def test_qq_interaction_reply_uses_gateway_event_id() -> None:
    interaction = _make_interaction(scene="c2c")
    abm = QQOfficialPlatformAdapter._parse_interaction_from_qqofficial(interaction)
    meta = PlatformMetadata(name="qq_official", description="test", id="test")
    event = QQOfficialMessageEvent(
        message_str="",
        message_obj=abm,
        platform_meta=meta,
        session_id=abm.session_id,
        bot=SimpleNamespace(api=SimpleNamespace()),
    )
    event.post_c2c_message = AsyncMock(return_value=SimpleNamespace())
    chain = MessageChain(chain=[Plain("Callback received")], use_markdown_=False)
    event.send_buffer = chain

    await event._post_send_one(chain)

    kwargs = event.post_c2c_message.await_args.kwargs
    assert kwargs["event_id"] == "gateway-event-1"
    assert kwargs["event_id"] != "interaction-1"


@pytest.mark.asyncio
async def test_qq_send_fallback_removes_reply_references() -> None:
    event = _make_group_event()
    sent_payloads = []

    async def send(payload):
        sent_payloads.append(payload)
        if len(sent_payloads) == 1:
            raise botpy.errors.ServerError("invalid event_id")
        return {"ok": True}

    result = await event._send_with_markdown_fallback(
        send_func=send,
        payload={
            "content": "Callback received",
            "msg_id": "source-message-1",
            "event_id": "gateway-event-1",
        },
        plain_text="Callback received",
    )

    assert result == {"ok": True}
    assert sent_payloads[0]["event_id"] == "gateway-event-1"
    assert "event_id" not in sent_payloads[1]
    assert "msg_id" not in sent_payloads[1]


def test_qq_interaction_is_normalized_to_portable_component() -> None:
    abm = QQOfficialPlatformAdapter._parse_interaction_from_qqofficial(
        _make_interaction()
    )

    assert abm.type == MessageType.GROUP_MESSAGE
    assert abm.session_id == "group-1"
    assert abm.sender.user_id == "member-1"
    assert len(abm.message) == 1
    component = abm.message[0]
    assert isinstance(component, ButtonInteraction)
    assert component.action_id == "approve"
    assert component.data == {"request_id": "req-1"}
    assert component.interaction_id == "interaction-1"
    assert component.source_message_id == "source-message-1"


def test_qq_interaction_falls_back_to_native_button_fields() -> None:
    abm = QQOfficialPlatformAdapter._parse_interaction_from_qqofficial(
        _make_interaction(button_id="template-button", button_data="native-data")
    )

    component = abm.message[0]
    assert isinstance(component, ButtonInteraction)
    assert component.action_id == "template-button"
    assert component.data == "native-data"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_class",
    [QQOfficialBotClient, QQOfficialWebhookBotClient],
)
async def test_qq_clients_acknowledge_and_dispatch_button_clicks(client_class) -> None:
    client = client_class(
        intents=botpy.Intents(interaction=True),
        bot_log=False,
    )
    try:
        client.api.on_interaction_result = AsyncMock()
        platform = SimpleNamespace(
            remember_session_scene=Mock(),
            create_event=Mock(side_effect=lambda message: message),
            commit_event=Mock(),
        )
        client.set_platform(platform)

        await client.on_interaction_create(_make_interaction())

        client.api.on_interaction_result.assert_awaited_once_with("interaction-1", 0)
        platform.remember_session_scene.assert_called_once_with("group-1", "group")
        event = platform.commit_event.call_args.args[0]
        assert isinstance(event.message[0], ButtonInteraction)
    finally:
        await client.close()
