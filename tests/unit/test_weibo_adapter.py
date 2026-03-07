import asyncio
import base64
from pathlib import Path

import pytest

import astrbot.api.message_components as Comp
from astrbot.api.event import MessageChain
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.weibo.weibo_adapter import (
    WeiboPlatformAdapter,
    _normalize_allow_from,
)


@pytest.fixture
def weibo_adapter(tmp_path: Path) -> WeiboPlatformAdapter:
    adapter = WeiboPlatformAdapter(
        {
            "id": "weibo_test",
            "type": "weibo",
            "enable": True,
            "app_id": "app-id",
            "app_secret": "app-secret",
            "dm_policy": "pairing",
            "allow_from": "12345,67890",
            "text_chunk_limit": 4,
            "chunk_mode": "length",
        },
        {},
        asyncio.Queue(),
    )
    adapter._inbound_dir = tmp_path
    return adapter


def test_normalize_allow_from() -> None:
    assert _normalize_allow_from("123, 456\n789") == {"123", "456", "789"}


@pytest.mark.asyncio
async def test_build_astrbot_message_from_text_and_file(
    weibo_adapter: WeiboPlatformAdapter,
) -> None:
    payload = {
        "messageId": "msg-1",
        "fromUserId": "12345",
        "timestamp": 1_710_000_000,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "你好"},
                    {
                        "type": "input_file",
                        "filename": "note.txt",
                        "source": {
                            "type": "base64",
                            "media_type": "text/plain",
                            "data": base64.b64encode(b"hello").decode(),
                        },
                    },
                ],
            }
        ],
    }

    message = await weibo_adapter._build_astrbot_message(
        {"type": "message", "payload": payload},
        payload,
        "msg-1",
    )

    assert message is not None
    assert message.type == MessageType.FRIEND_MESSAGE
    assert message.session_id == "12345"
    assert message.message_id == "msg-1"
    assert message.message_str == "你好\n[文件: note.txt]"
    assert isinstance(message.message[0], Comp.Plain)
    assert isinstance(message.message[1], Comp.File)


@pytest.mark.asyncio
async def test_send_text_message_chunks_payload(
    weibo_adapter: WeiboPlatformAdapter,
) -> None:
    sent_payloads: list[dict] = []

    async def fake_send(payload: dict) -> None:
        sent_payloads.append(payload)

    weibo_adapter._send_ws_json = fake_send  # type: ignore[method-assign]

    await weibo_adapter._send_text_message("12345", "abcdefgh")

    assert len(sent_payloads) == 2
    assert sent_payloads[0]["type"] == "send_message"
    assert sent_payloads[0]["payload"]["toUserId"] == "12345"
    assert sent_payloads[0]["payload"]["text"] == "abcd"
    assert sent_payloads[0]["payload"]["done"] is False
    assert sent_payloads[1]["payload"]["text"] == "efgh"
    assert sent_payloads[1]["payload"]["done"] is True


@pytest.mark.asyncio
async def test_render_message_chain_degrades_unsupported_media(
    weibo_adapter: WeiboPlatformAdapter,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "demo.png"
    file_path = tmp_path / "demo.txt"
    image_path.write_bytes(b"png")
    file_path.write_text("demo", encoding="utf-8")

    chain = MessageChain(
        [
            Comp.Plain("hello"),
            Comp.Image.fromFileSystem(str(image_path)),
            Comp.File(name="demo.txt", file=str(file_path)),
        ],
    )

    rendered = await weibo_adapter._render_message_chain(chain)

    assert "hello" in rendered
    assert "[图片: demo.png]" in rendered
    assert "[文件: demo.txt]" in rendered
