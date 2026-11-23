"""Behavioral contracts shared by adapters after common-policy extraction."""

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from Crypto.Cipher import AES

from astrbot.api.message_components import Image, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, Group, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.queue_listener import listen_to_queue
from astrbot.core.platform.sources.satori.satori_event import SatoriPlatformEvent
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_utils import decrypt_wecom_image
from astrbot.core.platform.sources.wecom_ai_bot.WXBizJsonMsgCrypt import (
    WXBizJsonMsgCrypt,
)
from astrbot.core.platform.sources.weixin_shared import (
    normalize_weixin_api_base,
    split_weixin_text,
)


class RecordingEvent(AstrMessageEvent):
    def __init__(self) -> None:
        message = AstrBotMessage()
        message.type = MessageType.FRIEND_MESSAGE
        message.sender = MessageMember("user")
        message.self_id = "bot"
        message.message_id = "incoming"
        message.message_str = "incoming"
        message.message = [Plain("incoming")]
        message.raw_message = {}
        super().__init__(
            "incoming", message, PlatformMetadata("test", "Test", "test"), "user"
        )
        self.sent: list[MessageChain] = []

    async def send(self, message: MessageChain) -> None:
        self.sent.append(message)


async def stream(*chains: MessageChain) -> AsyncGenerator[MessageChain, None]:
    for chain in chains:
        yield chain


@pytest.mark.asyncio
@pytest.mark.parametrize("squash", [True, False])
async def test_buffering_retains_order_chain_identity_and_completion(
    squash: bool,
) -> None:
    event = RecordingEvent()
    first = MessageChain([Plain("one")])
    second = MessageChain([Plain("two")])
    generator = stream(first, second)
    completed = AsyncMock()

    await event._send_buffered_stream(generator, False, completed, squash_plain=squash)

    assert event.sent == [first]
    assert event.sent[0] is first
    assert [component.text for component in first.chain] == (
        ["onetwo"] if squash else ["one", "two"]
    )
    completed.assert_awaited_once_with(generator, False)


@pytest.mark.asyncio
async def test_empty_buffered_stream_has_no_send_or_completion() -> None:
    event = RecordingEvent()
    completed = AsyncMock()

    await event._send_buffered_stream(stream(), False, completed)

    assert event.sent == []
    completed.assert_not_awaited()


@pytest.mark.asyncio
async def test_buffered_send_failure_propagates_before_completion() -> None:
    event = RecordingEvent()
    event.send = AsyncMock(side_effect=RuntimeError("send failed"))
    completed = AsyncMock()

    with pytest.raises(RuntimeError, match="send failed"):
        await event._send_buffered_stream(
            stream(MessageChain([Plain("message")])), False, completed
        )

    completed.assert_not_awaited()


@pytest.mark.asyncio
async def test_punctuation_stream_preserves_media_order_and_tail(monkeypatch) -> None:
    event = RecordingEvent()
    image = Image.fromURL("https://example.test/image.png")
    completed = AsyncMock()
    sleep = AsyncMock()
    monkeypatch.setattr("astrbot.core.platform.astr_message_event.asyncio.sleep", sleep)
    generator = stream(
        MessageChain([Plain("first!")]),
        MessageChain([Plain("tail"), image]),
    )

    await event._send_punctuated_stream(generator, True, completed)

    assert event.sent[0].chain[0].text == "first!"
    assert event.sent[1].chain == [image]
    assert event.sent[2].chain[0].text == "tail"
    assert sleep.await_count == 2
    completed.assert_awaited_once_with(generator, True)


def test_group_snapshot_never_mutates_or_reuses_inbound_group() -> None:
    event = RecordingEvent()
    inbound = Group("room", group_name="Existing", group_admins=["admin"])
    event.message_obj.group = inbound

    same = event._group_lookup_snapshot("room")
    other = event._group_lookup_snapshot("another")
    same.group_name = "Fetched"

    assert same is not inbound
    assert inbound.group_name == "Existing"
    assert same.group_admins is None
    assert other.group_name is None
    assert other.group_id == "another"


@pytest.mark.asyncio
async def test_satori_instance_and_class_resolvers_remain_independent(
    monkeypatch,
) -> None:
    event = SatoriPlatformEvent.__new__(SatoriPlatformEvent)
    image = Image.fromURL("https://example.test/image.png")
    class_resolver = AsyncMock(return_value="data:image/png;base64,class")
    instance_resolver = AsyncMock(return_value="data:image/png;base64,instance")
    monkeypatch.setattr(SatoriPlatformEvent, "_image_to_data_url", class_resolver)
    event._image_to_data_url = instance_resolver

    assert "base64,instance" in await event._convert_component_to_satori(image)
    assert (
        "base64,class"
        in await SatoriPlatformEvent._convert_component_to_satori_static(image)
    )
    instance_resolver.assert_awaited_once_with(image)
    class_resolver.assert_awaited_once_with(image)


@pytest.mark.asyncio
async def test_queue_close_wins_when_data_and_close_are_ready() -> None:
    queue = asyncio.Queue()
    await queue.put("discarded")
    close = asyncio.Event()
    close.set()
    callback = AsyncMock()
    prior_tasks = asyncio.all_tasks()

    await listen_to_queue(queue, close, lambda: callback, lambda error: None)

    callback.assert_not_awaited()
    assert asyncio.all_tasks() == prior_tasks


@pytest.mark.asyncio
async def test_queue_cancellation_drains_both_child_waiters() -> None:
    started = asyncio.Event()

    class StartedQueue(asyncio.Queue):
        async def get(self):
            started.set()
            return await super().get()

    prior_tasks = asyncio.all_tasks()
    listener = asyncio.create_task(
        listen_to_queue(
            StartedQueue(), asyncio.Event(), lambda: None, lambda error: None
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    listener.cancel()
    await asyncio.wait_for(listener, timeout=1)

    assert asyncio.all_tasks() == prior_tasks


@pytest.mark.asyncio
async def test_queue_refreshes_callback_and_continues_after_handler_failure() -> None:
    queue = asyncio.Queue()
    close = asyncio.Event()
    calls = []
    errors = []

    async def second(value):
        calls.append(("second", value))
        close.set()

    async def first(value):
        calls.append(("first", value))
        callbacks[0] = second
        raise RuntimeError("callback failed")

    callbacks = [first]
    await queue.put(1)
    await queue.put(2)

    await asyncio.wait_for(
        listen_to_queue(queue, close, lambda: callbacks[0], errors.append), timeout=1
    )

    assert calls == [("first", 1), ("second", 2)]
    assert len(errors) == 1
    assert str(errors[0]) == "callback failed"


@pytest.mark.parametrize(
    ("text", "limit", "expected"),
    [
        ("", 5, [""]),
        ("ab!cdefg", 5, ["ab!", "cdefg"]),
        ("abcdef", 3, ["abc", "def"]),
        ("ab\ncd;ef", 5, ["ab\n", "cd;ef"]),
        ("a" * 2050, 2048, ["a" * 2048, "aa"]),
    ],
)
def test_weixin_text_limits_preserve_every_character(text, limit, expected) -> None:
    chunks = split_weixin_text(text, limit)
    assert chunks == expected
    assert "".join(chunks) == text
    assert all(len(chunk) <= limit for chunk in chunks)


def test_invalid_weixin_text_limit_fails_instead_of_looping() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        split_weixin_text("message", 0)


@pytest.mark.parametrize(
    "url",
    [
        "https://proxy.test",
        "https://proxy.test/",
        "https://proxy.test/cgi-bin",
        "https://proxy.test/cgi-bin/",
    ],
)
def test_weixin_url_suffix_is_consistent(url: str) -> None:
    assert normalize_weixin_api_base(url) == "https://proxy.test/cgi-bin/"


@pytest.mark.parametrize("content", [b"", b"binary\x00content", b"x" * 32])
def test_wecom_image_decryption_accepts_valid_protocol_padding(content: bytes) -> None:
    key = bytes(range(32))
    padding = 32 - len(content) % 32
    encrypted = AES.new(key, AES.MODE_CBC, key[:16]).encrypt(
        content + bytes([padding]) * padding
    )
    assert decrypt_wecom_image(encrypted, key) == content


@pytest.mark.parametrize(
    "invalid", [b"", b"x" * 15 + b"\x00", b"x" * 15 + b"\x21", b"x" * 15 + b"\x02"]
)
def test_wecom_image_decryption_rejects_malformed_padding(invalid: bytes) -> None:
    key = bytes(range(32))
    encrypted = AES.new(key, AES.MODE_CBC, key[:16]).encrypt(invalid)
    with pytest.raises(ValueError):
        decrypt_wecom_image(encrypted, key)


def test_wecom_authenticated_decryption_uses_identical_signature_policy() -> None:
    import base64
    import json

    key = base64.b64encode(bytes(range(32))).decode().rstrip("=")
    crypt = WXBizJsonMsgCrypt("token", key, "receiver")
    status, encrypted = crypt.EncryptMsg("payload", "nonce", "1700000000")
    assert status == 0
    envelope = json.loads(encrypted)

    assert crypt.DecryptMsg(
        encrypted, envelope["msgsignature"], "1700000000", "nonce"
    ) == (0, "payload")
    assert crypt.VerifyURL(
        envelope["msgsignature"], "1700000000", "nonce", envelope["encrypt"]
    ) == (0, "payload")
    assert crypt.VerifyURL("wrong", "1700000000", "nonce", envelope["encrypt"])[0] != 0


@pytest.mark.asyncio
async def test_telegram_formatter_failure_preserves_plaintext_and_last_keyboard(
    monkeypatch,
) -> None:
    from astrbot.core.platform.sources.telegram import tg_event

    client = AsyncMock()
    text = "x" * (tg_event.TelegramPlatformEvent.MAX_MESSAGE_LENGTH + 5)
    keyboard = object()
    monkeypatch.setattr(
        tg_event.telegramify_markdown,
        "markdownify",
        lambda chunk: (_ for _ in ()).throw(RuntimeError("formatter failed")),
    )

    await tg_event.TelegramPlatformEvent._send_text_chunks(
        client, text, {"chat_id": "1", "reply_markup": keyboard}
    )

    sent = [call.kwargs for call in client.send_message.await_args_list]
    assert "".join(call["text"] for call in sent) == text
    assert all("parse_mode" not in call for call in sent)
    assert "reply_markup" not in sent[0]
    assert sent[-1]["reply_markup"] is keyboard


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [RuntimeError("unknown delivery"), TimeoutError("unknown delivery")]
)
async def test_telegram_transport_uncertainty_does_not_replay_as_plaintext(
    monkeypatch, error
) -> None:
    from astrbot.core.platform.sources.telegram import tg_event

    client = AsyncMock()
    client.send_message.side_effect = error
    monkeypatch.setattr(
        tg_event.telegramify_markdown, "markdownify", lambda chunk: chunk
    )

    with pytest.raises(type(error), match="unknown delivery"):
        await tg_event.TelegramPlatformEvent._send_text_chunks(
            client, "message", {"chat_id": "1"}
        )

    client.send_message.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("silent", [True, False])
async def test_webhook_json_wrapper_preserves_silent_error_contract(
    silent: bool,
) -> None:
    from starlette.requests import Request

    from astrbot.core.platform.webhook_server import WebhookRequest

    async def receive():
        return {"type": "http.request", "body": b"{invalid"}

    request = Request(
        {
            "type": "http",
            "headers": [],
            "method": "POST",
            "path": "/",
            "query_string": b"",
        },
        receive,
    )
    wrapper = WebhookRequest(request)
    if silent:
        assert await wrapper.get_json(force=True, silent=True) is None
    else:
        with pytest.raises(ValueError):
            await wrapper.get_json()
