import base64
from pathlib import Path
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
    File,
    Image,
    Plain,
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


def test_qq_expired_callback_does_not_fall_back_to_button_id(monkeypatch):
    from astrbot.core.platform import button_interaction

    clock = [100.0]
    monkeypatch.setattr(button_interaction.time, "time", lambda: clock[0])
    interaction = _make_interaction(
        button_data=encode_button_callback("approve", expires_at=160)
    )
    clock[0] = 160.0
    message = QQOfficialPlatformAdapter._parse_interaction_from_qqofficial(interaction)
    assert message.message[0].action_id == "approve"
    assert message.message[0].callback_data == interaction.data.resolved.button_data
    with pytest.raises(button_interaction.ButtonActionExpiredError):
        button_interaction.decode_button_callback(message.message[0].callback_data)


def test_qq_keyboard_renders_callback_and_url_buttons() -> None:
    chain = MessageChain(
        chain=[
            ActionRow(
                buttons=[
                    Button(
                        id="approve",
                        label="Approve request",
                        action=Button.CallbackAction(data={"request_id": "req-1"}),
                        style=Button.Style.PRIMARY,
                    ),
                    Button(
                        id="docs",
                        label="Docs",
                        action=Button.UrlAction(url="https://example.com/docs"),
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
                        action=Button.CallbackAction(),
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
                        action=Button.CallbackAction(data={"request_id": "req-1"}),
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
@pytest.mark.parametrize("scene", ["group", "c2c"])
@pytest.mark.parametrize("media_type", ["image", "file"])
@pytest.mark.parametrize("source_type", ["message", "button"])
@pytest.mark.parametrize("use_markdown", [False, True])
@pytest.mark.parametrize("with_text", [False, True])
async def test_qq_reply_uploads_media(
    scene: str,
    media_type: str,
    source_type: str,
    use_markdown: bool,
    with_text: bool,
    tmp_path: Path,
) -> None:
    """Compare ordinary and button replies through the real media parser.

    Args:
        scene: QQ group or C2C conversation.
        media_type: Image or file attachment to include with the text.
        source_type: Ordinary message or button interaction event.
        use_markdown: Whether the reply starts with a Markdown payload.
        with_text: Whether the attachment is accompanied by text.
        tmp_path: Temporary directory for local attachment fixtures.
    """
    interaction = _make_interaction(scene=scene)
    abm = QQOfficialPlatformAdapter._parse_interaction_from_qqofficial(interaction)
    if source_type == "message":
        raw_data = {
            "id": "msg-1",
            "author": {"member_openid": "member-1", "user_openid": "user-1"},
            "group_openid": "group-1",
            "content": "ping",
            "timestamp": "0",
        }
        message_class = (
            botpy.message.GroupMessage if scene == "group" else botpy.message.C2CMessage
        )
        abm.raw_message = message_class(
            api=None, event_id="gateway-event-1", data=raw_data
        )
        abm.message_id = "msg-1"

    event = QQOfficialMessageEvent(
        message_str="",
        message_obj=abm,
        platform_meta=PlatformMetadata(name="qq_official", description="test", id="test"),
        session_id=abm.session_id,
        bot=SimpleNamespace(api=SimpleNamespace(post_group_message=AsyncMock())),
    )
    event.post_c2c_message = AsyncMock()
    media = {"file_info": "uploaded-media"}
    event.upload_group_and_c2c_image = AsyncMock(return_value=media)
    event.upload_group_and_c2c_media = AsyncMock(return_value=media)
    if media_type == "image":
        path = tmp_path / "pixel.png"
        path.write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aHosAAAAASUVORK5CYII="
            )
        )
        attachment = Image.fromFileSystem(str(path))
        upload = event.upload_group_and_c2c_image
    else:
        path = tmp_path / "attachment.txt"
        path.write_text("QQ media reproduction", encoding="utf-8")
        attachment = File(name=path.name, file=str(path))
        upload = event.upload_group_and_c2c_media

    await event.send(
        MessageChain(
            chain=([Plain("Media reply")] if with_text else []) + [attachment],
            use_markdown_=use_markdown,
        )
    )

    send = (
        event.bot.api.post_group_message if scene == "group" else event.post_c2c_message
    )
    send.assert_awaited_once()
    payload = send.await_args.kwargs
    assert payload["content"] == ("Media reply" if with_text else None)
    assert payload["group_openid" if scene == "group" else "openid"] == (
        "group-1" if scene == "group" else "user-1"
    )
    if source_type == "button":
        assert payload["event_id"] == "gateway-event-1"
        assert "msg_id" not in payload
    upload.assert_awaited_once()
    assert upload.await_args.kwargs[
        "group_openid" if scene == "group" else "openid"
    ] == ("group-1" if scene == "group" else "user-1")
    assert payload["media"] == media
    assert payload["msg_type"] == 7
    assert "markdown" not in payload


@pytest.mark.asyncio
async def test_qq_guild_button_reply_attaches_local_image(tmp_path: Path) -> None:
    """Keep guild button images on the ordinary channel upload path.

    Args:
        tmp_path: Temporary directory for the local image fixture.
    """
    abm = QQOfficialPlatformAdapter._parse_interaction_from_qqofficial(
        _make_interaction(scene="guild")
    )
    event = QQOfficialMessageEvent(
        message_str="",
        message_obj=abm,
        platform_meta=PlatformMetadata(name="qq_official", description="test", id="test"),
        session_id=abm.session_id,
        bot=SimpleNamespace(api=SimpleNamespace(post_message=AsyncMock())),
    )
    path = tmp_path / "pixel.png"
    path.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aHosAAAAASUVORK5CYII="
        )
    )

    await event.send(
        MessageChain(
            chain=[Plain("Image reply"), Image.fromFileSystem(str(path))],
            use_markdown_=False,
        )
    )

    event.bot.api.post_message.assert_awaited_once()
    payload = event.bot.api.post_message.await_args.kwargs
    assert payload["channel_id"] == "channel-1"
    assert payload["event_id"] == "gateway-event-1"
    assert payload["file_image"] == str(path.resolve())
    assert payload["content"] == "Image reply"
    assert "msg_type" not in payload


@pytest.mark.asyncio
@pytest.mark.parametrize("with_keyboard", [False, True])
async def test_qq_c2c_request_omits_unset_optional_fields(with_keyboard: bool) -> None:
    """Validate the wire payload rather than replacing the C2C send method.

    Args:
        with_keyboard: Whether an explicitly supplied keyboard must be retained.
    """
    event = _make_group_event()
    event.bot.api._http = SimpleNamespace(
        request=AsyncMock(return_value={"id": "reply-1"})
    )
    keyboard = {"id": "keyboard-template"} if with_keyboard else None

    await event.post_c2c_message(
        openid="user-1",
        msg_type=2 if with_keyboard else 7,
        markdown={"content": "Choose"} if with_keyboard else None,
        media=None if with_keyboard else {"file_info": "uploaded-media"},
        keyboard=keyboard,
        event_id="gateway-event-1",
    )

    payload = event.bot.api._http.request.await_args.kwargs["json"]
    assert all(value is not None for value in payload.values())
    assert payload["event_id"] == "gateway-event-1"
    assert "msg_id" not in payload
    if with_keyboard:
        assert payload["keyboard"] == keyboard
        assert "media" not in payload
    else:
        assert payload["media"] == {"file_info": "uploaded-media"}
        assert "keyboard" not in payload


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
