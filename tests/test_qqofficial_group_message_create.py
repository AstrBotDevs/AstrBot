import asyncio
import re
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import botpy
import botpy.message
import pytest
from botpy import ConnectionSession

from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Image, Plain, Reply
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
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


@pytest.mark.parametrize(
    "mention_markup",
    ["<@bot-123>", "<@!bot-123>", '<qqbot-at-user id="bot-123" />'],
)
@pytest.mark.asyncio
async def test_parse_group_message_create_bot_mention_cleans_plain_text(
    mention_markup: str,
):
    _, message = _dispatch_group_message(
        _make_group_payload(
            content=f"{mention_markup} hello there",
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
async def test_parse_to_qqofficial_preserves_at_component_order():
    parsed = await QQOfficialMessageEvent._parse_to_qqofficial(
        MessageChain(chain=[At(qq="member-1"), Plain(" hello"), At(qq="all")])
    )

    assert parsed[0] == "<@member-1> hello"


@pytest.mark.parametrize("qq", [None, ""])
@pytest.mark.asyncio
async def test_parse_to_qqofficial_ignores_empty_at_component(qq: str | None):
    mention = At(qq="placeholder")
    mention.qq = cast(Any, qq)
    chain = MessageChain(chain=[mention, Plain("hello")])

    parsed = await QQOfficialMessageEvent._parse_to_qqofficial(chain)

    assert parsed[0] == "hello"
    assert QQOfficialMessageEvent._has_mention(chain) is False


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
async def test_ws_group_send_by_session_with_at_uses_markdown():
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
        post_group_message=AsyncMock(return_value={"id": "sent-at"}),
        post_message=AsyncMock(),
    )
    adapter._session_scene["group-1"] = "group"
    chain = MessageChain(chain=[At(qq="member-1"), Plain(" hello")])
    chain.use_markdown(False)

    await adapter.send_by_session(
        MessageSession("qq_official", MessageType.GROUP_MESSAGE, "group-1"),
        chain,
    )

    kwargs = adapter.client.api.post_group_message.await_args.kwargs
    assert kwargs["msg_type"] == 2
    assert kwargs["markdown"]["content"] == "<@member-1> hello"
    assert "content" not in kwargs


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
            plugin_manager=SimpleNamespace(
                context=SimpleNamespace(get_using_tts_provider=lambda _umo: None)
            ),
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
