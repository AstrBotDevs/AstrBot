import asyncio
import re
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import botpy
import botpy.message
import pytest
from botpy import ConnectionSession

from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, File, Image, Plain, Record, Reply, Video
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.platform.sources.qqofficial import qqofficial_message_event
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    PatchedMessage,
    QQOfficialPlatformAdapter,
    _ensure_group_message_create_parser,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    botClient as QQOfficialBotClient,
)
from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_adapter import (
    QQOfficialWebhookPlatformAdapter,
)


def _make_group_payload(
    *,
    message_id: str = "msg-1",
    content: str = "hello world",
    mentions: list[dict] | None = None,
    member_openid: str = "member-1",
    group_openid: str = "group-1",
    group_name: str | None = None,
    message_type: int | None = None,
    msg_elements: list[dict] | None = None,
    message_reference: dict | None = None,
) -> dict:
    data = {
        "id": f"event-{message_id}",
        "d": {
            "id": message_id,
            "content": content,
            "author": {"member_openid": member_openid},
            "group_openid": group_openid,
            "mentions": mentions or [],
            "attachments": [],
        },
    }
    if group_name is not None:
        data["d"]["group_name"] = group_name
    if message_type is not None:
        data["d"]["message_type"] = message_type
    if msg_elements is not None:
        data["d"]["msg_elements"] = msg_elements
    if message_reference is not None:
        data["d"]["message_reference"] = message_reference
    return data


def _dispatch_group_message(payload: dict) -> tuple[str, botpy.message.GroupMessage]:
    dispatched: list[tuple[str, botpy.message.GroupMessage]] = []
    _ensure_group_message_create_parser()
    connection = ConnectionSession(
        max_async=1,
        connect=lambda: None,
        dispatch=lambda event, message: dispatched.append((event, message)),
        loop=asyncio.get_event_loop(),
        api=None,
    )
    connection.parser["group_message_create"](payload)
    return dispatched[0]


@pytest.mark.asyncio
async def test_group_message_create_parser_is_registered_and_dispatches_group_message():
    QQOfficialPlatformAdapter(
        {
            "id": "qq-official-test",
            "appid": "123",
            "secret": "secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        {},
        asyncio.Queue(),
    )

    event_name, message = _dispatch_group_message(_make_group_payload())

    assert event_name == "group_message_create"
    assert isinstance(message, botpy.message.GroupMessage)
    assert message.group_openid == "group-1"


@pytest.mark.asyncio
async def test_parse_group_message_create_plain_message_has_no_at_component():
    _, message = _dispatch_group_message(
        _make_group_payload(content="plain group message")
    )

    abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        message,
        MessageType.GROUP_MESSAGE,
    )

    assert abm.type == MessageType.GROUP_MESSAGE
    assert abm.sender.user_id == "member-1"
    assert abm.group_id == "group-1"
    assert abm.message_str == "plain group message"
    assert not any(isinstance(component, At) for component in abm.message)
    assert [
        component.text for component in abm.message if isinstance(component, Plain)
    ] == ["plain group message"]


@pytest.mark.asyncio
async def test_parse_group_message_create_quoted_context():
    _, message = _dispatch_group_message(
        _make_group_payload(
            content="answer",
            message_type=103,
            message_reference={"message_id": "quoted-1"},
            msg_elements=[
                {
                    "content": "quoted text",
                    "attachments": [
                        {
                            "content_type": "image/png",
                            "filename": "quoted.png",
                            "url": "img.example.com/quoted.png",
                        }
                    ],
                }
            ],
        )
    )

    abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        message,
        MessageType.GROUP_MESSAGE,
    )

    assert getattr(message, "message_type") == 103
    assert getattr(message, "msg_elements")[0]["content"] == "quoted text"
    reply = abm.message[0]
    assert isinstance(reply, Reply)
    assert reply.id == "quoted-1"
    assert reply.message_str == "quoted text"
    assert isinstance(reply.chain[0], Plain)
    assert reply.chain[0].text == "quoted text"
    assert isinstance(reply.chain[1], Image)
    assert reply.chain[1].file == "https://img.example.com/quoted.png"
    assert abm.message_str == "answer"
    assert [
        component.text for component in abm.message if isinstance(component, Plain)
    ][-1] == "answer"


@pytest.mark.asyncio
async def test_parse_group_message_create_bot_mention_cleans_plain_text():
    _, message = _dispatch_group_message(
        _make_group_payload(
            content="<@!bot-123> hello there",
            mentions=[{"id": "bot-123", "is_you": True}],
        )
    )

    abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        message,
        MessageType.GROUP_MESSAGE,
    )

    assert isinstance(abm.message[0], At)
    assert abm.message[0].qq == "bot-123"
    assert abm.self_id == "bot-123"
    assert isinstance(abm.message[1], Plain)
    assert abm.message[1].text == "hello there"
    assert abm.message_str == "hello there"
    assert abm.sender.user_id == "member-1"
    assert abm.group_id == "group-1"


@pytest.mark.asyncio
async def test_legacy_group_at_path_forces_bot_mention_when_mentions_missing():
    message = botpy.message.GroupMessage(
        None,
        "event-legacy",
        _make_group_payload(content="legacy text", mentions=[])["d"],
    )

    abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        message,
        MessageType.GROUP_MESSAGE,
        force_group_mention=True,
    )

    assert isinstance(abm.message[0], At)
    assert abm.message[0].qq == "qq_official"
    assert abm.self_id == "qq_official"
    assert isinstance(abm.message[1], Plain)
    assert abm.message[1].text == "legacy text"


@pytest.mark.asyncio
async def test_group_message_create_handler_maps_group_session_and_scene():
    _, message = _dispatch_group_message(_make_group_payload())
    committed: list = []
    remembered_scenes: list[tuple[str, str]] = []
    remembered_ids: list[tuple[str, str]] = []

    class PlatformStub:
        def remember_session_scene(self, session_id: str, scene: str) -> None:
            remembered_scenes.append((session_id, scene))

        def remember_session_message_id(self, session_id: str, message_id: str) -> None:
            remembered_ids.append((session_id, message_id))

        def create_event(self, message_obj):
            return message_obj

        def commit_event(self, event) -> None:
            committed.append(event)

    client = QQOfficialBotClient(
        intents=botpy.Intents(public_messages=True),
        bot_log=False,
    )
    client.set_platform(cast(Any, PlatformStub()))

    await client.on_group_message_create(message)

    assert remembered_scenes == [("group-1", "group")]
    assert remembered_ids == [("group-1", "msg-1")]
    assert committed[0].type == MessageType.GROUP_MESSAGE
    assert committed[0].group_id == "group-1"
    assert committed[0].session_id == "group-1"


@pytest.mark.asyncio
async def test_ws_group_send_by_session_without_cached_msg_id_omits_msg_id():
    adapter = QQOfficialPlatformAdapter(
        {
            "id": "qq-official-test",
            "appid": "123",
            "secret": "secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        {},
        asyncio.Queue(),
    )
    adapter.client.api = SimpleNamespace(
        post_group_message=AsyncMock(return_value={"id": "sent-1"}),
        post_message=AsyncMock(),
    )
    adapter._session_scene["group-1"] = "group"

    await adapter.send_by_session(
        MessageSession("qq_official", MessageType.GROUP_MESSAGE, "group-1"),
        MessageChain(chain=[Plain("proactive hello")]),
    )

    adapter.client.api.post_group_message.assert_awaited_once()
    kwargs = adapter.client.api.post_group_message.await_args.kwargs
    assert kwargs["group_openid"] == "group-1"
    assert kwargs["content"] == "proactive hello"
    assert "msg_id" not in kwargs
    assert "msg_seq" in kwargs
    assert adapter._session_last_message_id["group-1"] == "sent-1"


@pytest.mark.asyncio
async def test_ws_group_send_by_session_strips_unique_session_suffix():
    adapter = QQOfficialPlatformAdapter(
        {
            "id": "qq-official-test",
            "appid": "123",
            "secret": "secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        {},
        asyncio.Queue(),
    )
    adapter.client.api = SimpleNamespace(
        post_group_message=AsyncMock(return_value={"id": "sent-unique"}),
        post_message=AsyncMock(),
    )
    adapter._session_scene["group-1"] = "group"

    await adapter.send_by_session(
        MessageSession(
            "qq_official",
            MessageType.GROUP_MESSAGE,
            "user-1_group-1",
        ),
        MessageChain(chain=[Plain("unique session hello")]),
    )

    adapter.client.api.post_group_message.assert_awaited_once()
    kwargs = adapter.client.api.post_group_message.await_args.kwargs
    assert kwargs["group_openid"] == "group-1"
    assert kwargs["content"] == "unique session hello"


@pytest.mark.asyncio
async def test_ws_group_send_by_session_with_cached_msg_id_still_omits_msg_id():
    adapter = QQOfficialPlatformAdapter(
        {
            "id": "qq-official-test",
            "appid": "123",
            "secret": "secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        {},
        asyncio.Queue(),
    )
    adapter.client.api = SimpleNamespace(
        post_group_message=AsyncMock(return_value={"id": "sent-2"}),
        post_message=AsyncMock(),
    )
    adapter._session_scene["group-1"] = "group"
    adapter._session_last_message_id["group-1"] = "stale-msg-id"

    await adapter.send_by_session(
        MessageSession("qq_official", MessageType.GROUP_MESSAGE, "group-1"),
        MessageChain(chain=[Plain("proactive with cache")]),
    )

    adapter.client.api.post_group_message.assert_awaited_once()
    kwargs = adapter.client.api.post_group_message.await_args.kwargs
    assert kwargs["group_openid"] == "group-1"
    assert kwargs["content"] == "proactive with cache"
    assert "msg_id" not in kwargs
    assert "msg_seq" in kwargs


@pytest.mark.asyncio
async def test_media_upload_propagates_qq_api_error(monkeypatch):
    """QQ upload errors propagate so callers cannot report a false success."""
    request = AsyncMock(
        side_effect=botpy.errors.ServerError("413 Request Entity Too Large")
    )
    send_helper = SimpleNamespace(
        _bot=SimpleNamespace(
            api=SimpleNamespace(_http=SimpleNamespace(request=request))
        )
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.qqofficial.qqofficial_message_event._qqofficial_retry",
        lambda *args, **kwargs: lambda func: func,
    )

    with pytest.raises(botpy.errors.ServerError, match="413 Request Entity Too Large"):
        await QQOfficialMessageEvent.upload_group_and_c2c_media(
            send_helper,
            "https://example.com/large.bin",
            QQOfficialMessageEvent.FILE_FILE_TYPE,
            group_openid="group-1",
        )


@pytest.mark.asyncio
async def test_webhook_group_send_by_session_without_cached_msg_id_omits_msg_id():
    adapter = QQOfficialWebhookPlatformAdapter(
        {
            "id": "qq-official-webhook-test",
            "appid": "123",
            "secret": "secret",
        },
        {},
        asyncio.Queue(),
    )
    adapter.client.api = SimpleNamespace(
        post_group_message=AsyncMock(return_value={"id": "sent-1"}),
        post_message=AsyncMock(),
    )
    adapter._session_scene["group-1"] = "group"

    await adapter.send_by_session(
        MessageSession("qq_official_webhook", MessageType.GROUP_MESSAGE, "group-1"),
        MessageChain(chain=[Plain("webhook proactive hello")]),
    )

    adapter.client.api.post_group_message.assert_awaited_once()
    kwargs = adapter.client.api.post_group_message.await_args.kwargs
    assert kwargs["group_openid"] == "group-1"
    assert kwargs["content"] == "webhook proactive hello"
    assert "msg_id" not in kwargs
    assert "msg_seq" in kwargs
    assert adapter._session_last_message_id["group-1"] == "sent-1"


@pytest.mark.asyncio
async def test_append_attachments_normalizes_schema_less_urls_and_skips_empty_attachments():
    msg = []

    await QQOfficialPlatformAdapter._append_attachments(
        msg,
        [
            SimpleNamespace(
                content_type="image/png",
                url="cdn.example/image.png",
                filename="image.png",
            ),
            SimpleNamespace(
                content_type="",
                url="cdn.example/archive.bin",
                filename="archive.bin",
            ),
            SimpleNamespace(content_type="image/png", url="", filename="ignored.png"),
        ],
    )

    assert len(msg) == 2
    assert isinstance(msg[0], Image)
    assert msg[0].file == "https://cdn.example/image.png"
    assert isinstance(msg[1], File)
    assert msg[1].name == "archive.bin"
    assert msg[1].file_ == "https://cdn.example/archive.bin"


@pytest.mark.asyncio
async def test_append_attachments_keeps_audio_attachment_lazy():
    msg = []
    await QQOfficialPlatformAdapter._append_attachments(
        msg,
        [
            SimpleNamespace(
                content_type="audio/ogg",
                url="cdn.example/voice.ogg",
                filename="voice.ogg",
            )
        ],
    )

    assert len(msg) == 1
    assert isinstance(msg[0], Record)
    assert msg[0].file == ""
    assert msg[0].url == ""


def test_parse_face_message_decodes_ext_text_and_falls_back_on_invalid_payload():
    encoded = "eyJ0ZXh0IjoiW+a7oeWktOmXruWPt10ifQ=="

    assert (
        QQOfficialPlatformAdapter._parse_face_message(
            f'before <faceType=4,faceId="",ext="{encoded}"> after'
        )
        == "before [表情:[满头问号]] after"
    )
    assert (
        QQOfficialPlatformAdapter._parse_face_message(
            '<faceType=4,faceId="",ext="not-base64">'
        )
        == "[表情]"
    )


@pytest.mark.asyncio
async def test_ws_channel_send_by_session_without_cached_msg_id_skips_send():
    adapter = QQOfficialPlatformAdapter(
        {
            "id": "qq-official-test",
            "appid": "123",
            "secret": "secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        {},
        asyncio.Queue(),
    )
    adapter.client.api = SimpleNamespace(
        post_group_message=AsyncMock(),
        post_message=AsyncMock(),
    )
    adapter._session_scene["channel-1"] = "channel"

    await adapter.send_by_session(
        MessageSession("qq_official", MessageType.GROUP_MESSAGE, "channel-1"),
        MessageChain(chain=[Plain("channel proactive hello")]),
    )

    adapter.client.api.post_group_message.assert_not_called()
    adapter.client.api.post_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_with_markdown_fallback_retries_streaming_newline_fix(monkeypatch):
    event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
    payloads: list[dict] = []

    async def flaky_send(payload: dict):
        payloads.append(dict(payload))
        if len(payloads) == 1:
            raise RuntimeError(QQOfficialMessageEvent.STREAM_MARKDOWN_NEWLINE_ERROR)
        return payload

    monkeypatch.setattr(
        qqofficial_message_event, "_QQOFFICIAL_SEND_API_ERRORS", (RuntimeError,)
    )
    monkeypatch.setattr(
        qqofficial_message_event.botpy.errors, "ServerError", RuntimeError
    )

    result = await event._send_with_markdown_fallback(
        send_func=flaky_send,
        payload={"markdown": {"content": "hello"}, "content": "hello"},
        plain_text="hello",
        stream={"state": 10},
    )

    assert result["content"] == "hello\n"
    assert payloads[1]["content"] == "hello\n"
    assert payloads[1]["markdown"]["content"] == "hello\n"


@pytest.mark.asyncio
async def test_send_with_markdown_fallback_downgrades_to_plain_content(monkeypatch):
    event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
    payloads: list[dict] = []

    async def flaky_send(payload: dict):
        payloads.append(dict(payload))
        if len(payloads) == 1:
            raise RuntimeError(QQOfficialMessageEvent.MARKDOWN_NOT_ALLOWED_ERROR)
        return payload

    monkeypatch.setattr(
        qqofficial_message_event, "_QQOFFICIAL_SEND_API_ERRORS", (RuntimeError,)
    )
    monkeypatch.setattr(
        qqofficial_message_event.botpy.errors, "ServerError", RuntimeError
    )

    result = await event._send_with_markdown_fallback(
        send_func=flaky_send,
        payload={"markdown": {"content": "hello"}, "msg_type": 2},
        plain_text="hello",
    )

    assert result["content"] == "hello"
    assert "markdown" not in payloads[1]
    assert payloads[1]["msg_type"] == 0


@pytest.mark.asyncio
async def test_post_c2c_message_drops_none_msg_id_and_stream_id():
    request = AsyncMock(return_value=None)
    event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
    event._bot = SimpleNamespace(
        api=SimpleNamespace(_http=SimpleNamespace(request=request))
    )

    result = await event.post_c2c_message(
        openid="friend-1",
        content="hello",
        msg_id=None,
        stream={"state": 1, "id": None, "index": 0},
    )

    assert result is None
    sent_json = request.await_args.kwargs["json"]
    assert "msg_id" not in sent_json
    assert sent_json["stream"] == {"state": 1, "index": 0}


@pytest.mark.asyncio
async def test_split_message_chain_by_media_separates_each_additional_media_component():
    chunks = QQOfficialMessageEvent._split_message_chain_by_media(
        MessageChain(
            chain=[
                Plain("before "),
                Image.fromURL("https://example.com/1.png"),
                Plain("middle "),
                File(name="doc.txt", url="https://example.com/doc.txt"),
                Plain("after"),
            ]
        )
    )

    assert len(chunks) == 2
    assert [
        component.text for component in chunks[0].chain if isinstance(component, Plain)
    ] == [
        "before ",
        "middle ",
    ]
    assert isinstance(chunks[0].chain[1], Image)
    assert [
        component.text for component in chunks[1].chain if isinstance(component, Plain)
    ] == ["after"]
    assert isinstance(chunks[1].chain[0], File)


@pytest.mark.asyncio
async def test_post_send_splits_send_buffer_and_clears_it_after_last_chunk():
    event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
    event.send_buffer = MessageChain(
        chain=[
            Plain("before "),
            Image.fromURL("https://example.com/1.png"),
            Plain("middle "),
            File(name="doc.txt", url="https://example.com/doc.txt"),
            Plain("after"),
        ]
    )
    sent_calls = []

    async def fake_post_send_one(message_chain, stream):
        sent_calls.append((message_chain, stream))
        return f"ret-{len(sent_calls)}"

    event._post_send_one = fake_post_send_one

    result = await event._post_send(stream={"state": 1})

    assert result == "ret-2"
    assert len(sent_calls) == 2
    assert sent_calls[0][1] is None
    assert sent_calls[1][1] is None
    assert event.send_buffer is None


@pytest.mark.asyncio
async def test_post_send_one_c2c_stream_downgrades_rich_media_to_non_stream(
    monkeypatch,
):
    source = botpy.message.C2CMessage(
        None,
        "evt-1",
        {"id": "msg-1", "author": {"user_openid": "user-1"}, "content": "hello"},
    )
    message_obj = SimpleNamespace(
        raw_message=source,
        message_id="msg-1",
        self_id="bot-1",
        session_id="user-1",
    )
    event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
    event.message_obj = message_obj
    event.send_buffer = MessageChain(
        [Plain("hello"), Image.fromURL("https://img/1.png")]
    )
    event.track_temporary_local_file = MagicMock()
    event.upload_group_and_c2c_image = AsyncMock(return_value={"file_uuid": "file-1"})
    event.upload_group_and_c2c_media = AsyncMock()
    event.post_c2c_message = AsyncMock(return_value={"id": "sent-1"})

    async def fake_parse(_message):
        return ("hello", "base64://img", None, None, None, None, None)

    monkeypatch.setattr(QQOfficialMessageEvent, "_parse_to_qqofficial", fake_parse)
    with patch.object(
        AstrMessageEvent,
        "send",
        AsyncMock(return_value=None),
    ) as parent_send:
        await event._post_send_one(event.send_buffer, stream={"state": 1, "id": None})

    event.post_c2c_message.assert_awaited_once()
    assert "stream" not in event.post_c2c_message.await_args.kwargs
    assert event.post_c2c_message.await_args.kwargs["media"] == {"file_uuid": "file-1"}
    parent_send.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "api_method", "target_key", "target_value"),
    [
        (
            botpy.message.GroupMessage(
                None,
                "evt-group",
                {
                    "id": "msg-group",
                    "group_openid": "group-1",
                    "author": {"member_openid": "member-1"},
                },
            ),
            "post_group_message",
            "group_openid",
            "group-1",
        ),
        (
            botpy.message.C2CMessage(
                None,
                "evt-c2c",
                {"id": "msg-c2c", "author": {"user_openid": "user-1"}},
            ),
            "post_c2c_message",
            "openid",
            "user-1",
        ),
        (
            botpy.message.Message(
                None,
                "evt-channel",
                {"id": "msg-channel", "channel_id": "channel-1"},
            ),
            "post_message",
            "channel_id",
            "channel-1",
        ),
        (
            botpy.message.DirectMessage(
                None,
                "evt-dm",
                {"id": "msg-dm", "guild_id": "guild-1"},
            ),
            "post_dms",
            "guild_id",
            "guild-1",
        ),
    ],
)
async def test_post_send_one_routes_text_for_every_qq_message_source(
    source,
    api_method,
    target_key,
    target_value,
):
    api = SimpleNamespace(
        post_group_message=AsyncMock(return_value={"id": "group-sent"}),
        post_message=AsyncMock(return_value={"id": "channel-sent"}),
        post_dms=AsyncMock(return_value={"id": "dm-sent"}),
    )
    event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
    event._bot = SimpleNamespace(api=api)
    event.message_obj = SimpleNamespace(raw_message=source, message_id="msg-1")
    event.send_buffer = MessageChain([Plain("hello")], use_markdown_=False)
    event.track_temporary_local_file = MagicMock()
    event.post_c2c_message = AsyncMock(return_value={"id": "c2c-sent"})

    with patch.object(AstrMessageEvent, "send", AsyncMock(return_value=None)):
        await event._post_send_one(
            event.send_buffer,
            stream={"state": 10, "id": None},
        )

    sender = (
        event.post_c2c_message
        if api_method == "post_c2c_message"
        else getattr(api, api_method)
    )
    if api_method == "post_c2c_message":
        sent_kwargs = sender.await_args.kwargs
        assert sent_kwargs["stream"] == {"state": 10, "id": None}
        assert sent_kwargs["content"] == "hello\n"
    else:
        sent_kwargs = sender.await_args.kwargs
        assert sent_kwargs[target_key] == target_value
        if api_method == "post_group_message":
            assert sent_kwargs["msg_type"] == 0
            assert "msg_seq" in sent_kwargs
        else:
            assert "msg_type" not in sent_kwargs


@pytest.mark.asyncio
async def test_post_send_one_group_media_uses_group_target_and_last_media_wins(
    monkeypatch,
):
    source = botpy.message.GroupMessage(
        None,
        "evt-group",
        {
            "id": "msg-group",
            "group_openid": "group-1",
            "author": {"member_openid": "member-1"},
        },
    )
    event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
    event._bot = SimpleNamespace(
        api=SimpleNamespace(post_group_message=AsyncMock(return_value={"id": "sent"}))
    )
    event.message_obj = SimpleNamespace(raw_message=source, message_id="msg-1")
    event.send_buffer = MessageChain([Plain("caption")])
    event.track_temporary_local_file = MagicMock()
    event.upload_group_and_c2c_image = AsyncMock(return_value="image-media")
    event.upload_group_and_c2c_media = AsyncMock(
        side_effect=["record-media", "video-media", "file-media"]
    )

    async def fake_parse(_message):
        return (
            "caption",
            "base64://image",
            None,
            "voice.silk",
            "video.mp4",
            "file.txt",
            "file.txt",
        )

    monkeypatch.setattr(QQOfficialMessageEvent, "_parse_to_qqofficial", fake_parse)
    with patch.object(AstrMessageEvent, "send", AsyncMock(return_value=None)):
        await event._post_send_one(event.send_buffer, stream={"state": 1})

    event.upload_group_and_c2c_image.assert_awaited_once_with(
        "base64://image",
        event.IMAGE_FILE_TYPE,
        group_openid="group-1",
    )
    assert event.upload_group_and_c2c_media.await_count == 3
    for call in event.upload_group_and_c2c_media.await_args_list:
        assert call.kwargs["group_openid"] == "group-1"
    sent_kwargs = event._bot.api.post_group_message.await_args.kwargs
    assert sent_kwargs["media"] == "file-media"
    assert sent_kwargs["msg_type"] == 7
    assert sent_kwargs["content"] == "caption"


@pytest.mark.asyncio
async def test_send_streaming_c2c_break_ends_previous_segment_and_resets_state():
    source = botpy.message.C2CMessage(
        None,
        "evt-1",
        {"id": "msg-1", "author": {"user_openid": "user-1"}, "content": "hello"},
    )
    event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
    event.message_obj = SimpleNamespace(raw_message=source)
    event.send_buffer = None
    sent_streams: list[dict | None] = []
    times = iter([0.0, 0.2])

    async def fake_post_send(stream=None):
        sent_streams.append(dict(stream) if stream else None)
        return {"id": f"resp-{len(sent_streams)}"}

    event._post_send = AsyncMock(side_effect=fake_post_send)
    loop = asyncio.get_running_loop()
    original_time = loop.time
    loop.time = lambda: next(times, 2.0)

    async def generator():
        yield MessageChain([Plain("first")])
        yield MessageChain(type="break")
        yield MessageChain([Plain("second")])

    with patch.object(
        AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value=None),
    ):
        await event.send_streaming(generator())
    loop.time = original_time

    assert sent_streams == [
        {"state": 10, "id": None, "index": 0, "reset": False},
        {"state": 10, "id": None, "index": 0, "reset": False},
    ]


@pytest.mark.asyncio
async def test_send_streaming_c2c_throttled_updates_reuse_returned_message_id(
    monkeypatch,
):
    source = botpy.message.C2CMessage(
        None,
        "evt-1",
        {"id": "msg-1", "author": {"user_openid": "user-1"}, "content": "hello"},
    )
    event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
    event.message_obj = SimpleNamespace(raw_message=source)
    event.send_buffer = None
    stream_calls: list[dict | None] = []

    async def fake_post_send(stream=None):
        stream_calls.append(dict(stream) if stream else None)
        return {"id": "stream-msg"}

    times = iter([0.0, 2.0, 2.0])
    event._post_send = AsyncMock(side_effect=fake_post_send)
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "time", lambda: next(times, 9.0))

    async def generator():
        yield MessageChain([Plain("hello ")])
        yield MessageChain([Plain("world")])

    with patch.object(
        AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value=None),
    ):
        await event.send_streaming(generator())

    assert stream_calls == [
        {"state": 1, "id": None, "index": 0, "reset": False},
        {"state": 10, "id": "stream-msg", "index": 1, "reset": False},
    ]


@pytest.mark.asyncio
async def test_send_streaming_non_c2c_batches_and_posts_once_at_end():
    source = botpy.message.GroupMessage(
        None,
        "evt-2",
        {
            "id": "msg-2",
            "group_openid": "group-1",
            "author": {"member_openid": "member-1"},
            "content": "hello",
        },
    )
    event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
    event.message_obj = SimpleNamespace(raw_message=source)
    event.send_buffer = None

    async def fake_post_send():
        buffered = event.send_buffer
        event.send_buffer = None
        return buffered

    event._post_send = AsyncMock(side_effect=fake_post_send)

    async def generator():
        yield MessageChain([Plain("hello ")])
        yield MessageChain([Plain("world")])

    with patch.object(
        AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value=None),
    ):
        await event.send_streaming(generator())

    event._post_send.assert_awaited_once_with()
    buffered_chain = event._post_send.await_args_list[0]
    assert buffered_chain.args == ()
    assert event.send_buffer is None


def test_append_stream_delta_owns_reused_plain_components():
    event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
    event.send_buffer = None
    shared = MessageChain([Plain("不")])

    event._append_stream_delta(shared)
    shared.chain[0].text = "稀"
    event._append_stream_delta(shared)
    shared.chain[0].text = "罕"
    event._append_stream_delta(shared)

    assert (
        "".join(
            component.text
            for component in event.send_buffer.chain
            if isinstance(component, Plain)
        )
        == "不稀罕"
    )


@pytest.mark.asyncio
async def test_send_streaming_non_c2c_keeps_reused_delta_text():
    source = botpy.message.GroupMessage(
        None,
        "evt-2",
        {
            "id": "msg-2",
            "group_openid": "group-1",
            "author": {"member_openid": "member-1"},
            "content": "hello",
        },
    )
    event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
    event.message_obj = SimpleNamespace(raw_message=source)
    event.send_buffer = None
    sent_text: list[str] = []

    async def fake_post_send():
        sent_text.append(
            "".join(
                component.text
                for component in event.send_buffer.chain
                if isinstance(component, Plain)
            )
        )
        event.send_buffer = None

    event._post_send = AsyncMock(side_effect=fake_post_send)
    shared = MessageChain([Plain("不")])

    async def generator():
        shared.chain[0].text = "不"
        yield shared
        shared.chain[0].text = "稀"
        yield shared
        shared.chain[0].text = "罕"
        yield shared

    with patch.object(
        AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value=None),
    ):
        await event.send_streaming(generator())

    assert sent_text == ["不稀罕"]


@pytest.mark.asyncio
async def test_send_streaming_c2c_keeps_reused_delta_before_final_flush(monkeypatch):
    source = botpy.message.C2CMessage(
        None,
        "evt-1",
        {"id": "msg-1", "author": {"user_openid": "user-1"}, "content": "hello"},
    )
    event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
    event.message_obj = SimpleNamespace(raw_message=source)
    event.send_buffer = None
    sent_text: list[str] = []

    async def fake_post_send(stream=None):
        assert stream == {"state": 10, "id": None, "index": 0, "reset": False}
        sent_text.append(
            "".join(
                component.text
                for component in event.send_buffer.chain
                if isinstance(component, Plain)
            )
        )
        event.send_buffer = None
        return {"id": "out-1"}

    event._post_send = AsyncMock(side_effect=fake_post_send)
    shared = MessageChain([Plain("不")])
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "time", lambda: 0.5)

    async def generator():
        shared.chain[0].text = "不"
        yield shared
        shared.chain[0].text = "稀"
        yield shared
        shared.chain[0].text = "罕"
        yield shared

    with patch.object(
        AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value=None),
    ):
        await event.send_streaming(generator())

    assert sent_text == ["不稀罕"]


@pytest.mark.asyncio
async def test_send_streaming_clears_buffer_when_post_send_raises():
    source = botpy.message.C2CMessage(
        None,
        "evt-1",
        {"id": "msg-1", "author": {"user_openid": "user-1"}, "content": "hello"},
    )
    event = QQOfficialMessageEvent.__new__(QQOfficialMessageEvent)
    event.message_obj = SimpleNamespace(raw_message=source)
    event.send_buffer = None
    event._post_send = AsyncMock(side_effect=RuntimeError("network down"))

    async def generator():
        yield MessageChain([Plain("hello")])

    with patch.object(
        AstrMessageEvent,
        "send_streaming",
        AsyncMock(return_value=None),
    ):
        result = await event.send_streaming(generator())

    assert isinstance(result, PlatformSendResult)
    assert result.status == "unknown"
    assert event.send_buffer is None


@pytest.mark.asyncio
async def test_parse_to_qqofficial_extracts_at_video_and_first_file_source():
    parsed = await QQOfficialMessageEvent._parse_to_qqofficial(
        MessageChain(
            chain=[
                At(qq="user-1"),
                Plain(" hello"),
                Video(file="https://example.com/video.mp4"),
                File(name="doc.txt", url="https://example.com/doc.txt"),
                File(name="ignored.txt", url="https://example.com/ignored.txt"),
            ]
        )
    )

    assert parsed[0] == "<@user-1> hello"
    assert parsed[4] == "https://example.com/video.mp4"
    assert parsed[5] == "https://example.com/doc.txt"
    assert parsed[6] == "doc.txt"


def test_qqofficial_ws_is_not_excluded_from_segmented_reply():
    stage = RespondStage()
    stage.enable_seg = True
    stage.only_llm_result = False
    result = MessageEventResult(chain=[Plain("hello")])

    event = SimpleNamespace(
        get_result=lambda: result,
        get_platform_name=lambda: "qq_official",
    )

    assert stage.is_seg_reply_required(cast(Any, event)) is True


def test_qqofficial_webhook_remains_excluded_from_segmented_reply():
    stage = RespondStage()
    stage.enable_seg = True
    stage.only_llm_result = False
    result = MessageEventResult(chain=[Plain("hello")])

    event = SimpleNamespace(
        get_result=lambda: result,
        get_platform_name=lambda: "qq_official_webhook",
    )

    assert stage.is_seg_reply_required(cast(Any, event)) is False


@pytest.mark.asyncio
async def test_result_decorate_segments_qqofficial_ws_plain_result():
    stage = ResultDecorateStage()
    stage.reply_prefix = ""
    stage.content_safe_check_reply = False
    stage.enable_segmented_reply = True
    stage.only_llm_result = False
    stage.words_count_threshold = 100
    stage.split_mode = "words"
    stage.split_words = ["。"]
    stage.split_words_pattern = re.compile(r"(.*?(。)|.+$)", re.DOTALL)
    stage.content_cleanup_rule = ""
    stage.show_reasoning = False
    stage.tts_trigger_probability = 0
    stage.reply_with_mention = False
    stage.reply_with_quote = False
    stage.forward_threshold = 1000
    setattr(
        stage,
        "ctx",
        SimpleNamespace(
            execution_context=SimpleNamespace(get_using_tts_provider=lambda _umo: None),
            handlers=SimpleNamespace(
                get_handlers_by_event_type=lambda *_args, **_kwargs: []
            ),
            plugins=SimpleNamespace(get_by_module=lambda _module_path: None),
            astrbot_config={
                "provider_tts_settings": {
                    "enable": False,
                    "use_file_service": False,
                    "dual_output": False,
                },
                "callback_api_base": "",
                "t2i": False,
            },
        ),
    )
    result = MessageEventResult(
        chain=[Plain("第一段。第二段。")],
        result_content_type=ResultContentType.LLM_RESULT,
    )

    event = SimpleNamespace(
        plugins_name=None,
        unified_msg_origin="qq_official:GroupMessage:group-1",
        get_result=lambda: result,
        get_platform_name=lambda: "qq_official",
        is_stopped=lambda: False,
        get_extra=lambda *_args, **_kwargs: None,
    )

    processed = stage.process(cast(Any, event))
    if hasattr(processed, "__aiter__"):
        async for _ in cast(Any, processed):
            pass
    else:
        yielded = await cast(Any, processed)
        if yielded is not None:
            async for _ in cast(Any, yielded):
                pass

    assert [comp.text for comp in result.chain if isinstance(comp, Plain)] == [
        "第一段",
        "第二段",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("use_webhook", [False, True])
async def test_get_group_uses_authenticated_client_for_ws_and_webhook(use_webhook):
    _, message = _dispatch_group_message(
        _make_group_payload(group_name="Incoming Group")
    )
    abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        message,
        MessageType.GROUP_MESSAGE,
    )
    abm.session_id = abm.group_id
    inbound = abm.group

    request = AsyncMock(
        return_value={
            "group_openid": "group-1",
            "group_name": "API Group",
            "group_member_num": 42,
        }
    )
    bot = SimpleNamespace(api=SimpleNamespace(_http=SimpleNamespace(request=request)))
    if use_webhook:
        from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_event import (
            QQOfficialWebhookMessageEvent,
        )

        event = QQOfficialWebhookMessageEvent(
            abm.message_str,
            abm,
            SimpleNamespace(name="qq_official_webhook", id="qq-official-webhook-test"),
            abm.session_id,
            cast(Any, bot),
        )
    else:
        event = QQOfficialMessageEvent(
            abm.message_str,
            abm,
            SimpleNamespace(name="qq_official", id="qq-official-test"),
            abm.session_id,
            cast(Any, bot),
        )

    group = await event.get_group()

    assert group is not inbound
    assert group.group_id == "group-1"
    assert group.group_name == "API Group"
    assert group.member_count == 42
    assert inbound.group_name == "Incoming Group"
    route = request.await_args.args[0]
    assert route.method == "GET"
    assert route.path == "/v2/groups/{group_openid}/info"
    assert route.parameters == {"group_openid": "group-1"}


@pytest.mark.asyncio
async def test_get_group_keeps_incoming_metadata_when_group_info_api_fails():
    _, message = _dispatch_group_message(
        _make_group_payload(group_name="Incoming Group")
    )
    abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        message,
        MessageType.GROUP_MESSAGE,
    )
    abm.session_id = abm.group_id
    inbound = abm.group
    bot = SimpleNamespace(
        api=SimpleNamespace(
            _http=SimpleNamespace(request=AsyncMock(side_effect=PermissionError))
        )
    )
    event = QQOfficialMessageEvent(
        abm.message_str,
        abm,
        SimpleNamespace(name="qq_official", id="qq-official-test"),
        abm.session_id,
        cast(Any, bot),
    )

    group = await event.get_group()

    assert group is not inbound
    assert group.group_id == "group-1"
    assert group.group_name == "Incoming Group"
    assert group.member_count is None


@pytest.mark.asyncio
async def test_get_group_loads_channel_and_parent_guild_metadata():
    message = PatchedMessage(
        None,
        "event-channel-1",
        {
            "id": "channel-message-1",
            "content": "<@!bot-1> hello channel",
            "author": {"id": "user-1", "username": "Alice"},
            "channel_id": "channel-1",
            "channel_name": "Incoming Channel",
            "guild_id": "guild-1",
            "mentions": [{"id": "bot-1", "is_you": True}],
            "attachments": [],
        },
    )
    abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        message,
        MessageType.GROUP_MESSAGE,
    )
    abm.session_id = abm.group_id
    api = SimpleNamespace(
        get_channel=AsyncMock(
            return_value={
                "id": "channel-1",
                "guild_id": "guild-1",
                "name": "API Channel",
            }
        ),
        get_guild=AsyncMock(
            return_value={
                "id": "guild-1",
                "icon": "https://example.com/guild.png",
                "owner_id": "owner-1",
                "member_count": "128",
            }
        ),
    )
    event = QQOfficialMessageEvent(
        abm.message_str,
        abm,
        SimpleNamespace(name="qq_official", id="qq-official-test"),
        abm.session_id,
        cast(Any, SimpleNamespace(api=api)),
    )

    assert abm.group is not None
    assert abm.group.group_name == "Incoming Channel"

    group = await event.get_group()

    assert group is not abm.group
    assert group.group_id == "channel-1"
    assert group.group_name == "API Channel"
    assert group.group_avatar == "https://example.com/guild.png"
    assert group.group_owner == "owner-1"
    assert group.member_count == 128
    api.get_channel.assert_awaited_once_with("channel-1")
    api.get_guild.assert_awaited_once_with("guild-1")
