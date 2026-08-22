"""测试 aiocqhttp 平台发送本地文件消息段(File)时的 base64 行为。

Bug 背景(#9626)：Docker 分容器部署时，AstrBot 将本地文件以
file:///path 形式传给 OneBot 协议端(如 NapCat)。协议端与 AstrBot
不在同一文件系统，读取该路径时抛出 ENOENT: no such file or directory。

修复：与 Image/Record 段保持一致，将本地存在的文件内容转为
base64:// 传输；http(s) 链接保持原样由协议端自行下载。
"""

import base64
from unittest.mock import AsyncMock

import pytest

import astrbot.core.message.components as Comp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.pipeline.respond.stage import (
    RespondStage,  # noqa: F401 — 预加载避免循环导入
)
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


@pytest.mark.asyncio
async def test_local_file_converted_to_base64(tmp_path):
    """本地存在的文件应转为 base64:// 传输，内容可正确解码。"""
    f = tmp_path / "cash.py"
    f.write_bytes(b"print('hello')")

    segment = Comp.File(name="cash.py", file=str(f))
    d = await AiocqhttpMessageEvent._from_segment_to_dict(segment)

    assert d["type"] == "file"
    payload = d["data"]["file"]
    assert payload.startswith("base64://")
    decoded = base64.b64decode(payload.removeprefix("base64://"))
    assert decoded == b"print('hello')"
    assert d["data"]["name"] == "cash.py"


@pytest.mark.asyncio
async def test_url_file_kept_as_is():
    """http(s) 链接文件不应被改动，由协议端自行下载。"""
    url = "https://example.com/report.pdf"

    segment = Comp.File(name="report.pdf", url=url)
    d = await AiocqhttpMessageEvent._from_segment_to_dict(segment)

    assert d["data"]["file"] == url


@pytest.mark.asyncio
async def test_missing_local_file_keeps_empty_value(tmp_path):
    """本地不存在的文件保持空值，不应抛异常也不应产生 base64。"""
    missing = tmp_path / "ghost.bin"

    segment = Comp.File(name="ghost.bin", file=str(missing))
    d = await AiocqhttpMessageEvent._from_segment_to_dict(segment)

    assert d["data"]["file"] == ""


@pytest.mark.asyncio
async def test_send_message_delivers_file_as_base64(tmp_path):
    """端到端：send_message 私聊发文件时 payload 应携带 base64 内容。"""
    f = tmp_path / "report.txt"
    f.write_bytes(b"data")
    bot = AsyncMock()
    chain = MessageChain([Comp.File(name="report.txt", file=str(f))])

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=chain,
        event=None,
        is_group=False,
        session_id="987654",
    )

    bot.send_private_msg.assert_awaited_once()
    call_args = bot.send_private_msg.call_args
    assert call_args.kwargs["user_id"] == 987654
    seg = call_args.kwargs["message"][0]
    assert seg["type"] == "file"
    payload = seg["data"]["file"]
    assert payload.startswith("base64://")
    assert base64.b64decode(payload.removeprefix("base64://")) == b"data"
