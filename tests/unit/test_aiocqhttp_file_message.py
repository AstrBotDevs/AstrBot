"""测试 aiocqhttp 平台发送文件消息时的行为。

验证 File 段通过 upload_group_file / upload_private_file API 上传，
以及各种回退场景。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

# 先导入 astrbot.api 完成模块初始化，避免 star_tools → aiocqhttp_message_event 的循环导入
import astrbot.api  # noqa: F401

from astrbot.core.message import components as Comp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


@pytest.mark.asyncio
async def test_file_group_uses_upload_group_file_api(tmp_path):
    """群聊发送本地文件：应调用 upload_group_file API，不走 send_group_msg。"""
    testFile = tmp_path / "test.txt"
    testFile.write_text("hello world", encoding="utf-8")

    fileComp = Comp.File(name="test.txt", file=str(testFile))
    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    bot.send_private_msg = AsyncMock()
    bot.call_action = AsyncMock()

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=MessageChain([fileComp]),
        is_group=True,
        session_id="123456",
    )

    bot.call_action.assert_called_once_with(
        "upload_group_file",
        group_id=123456,
        file=str(testFile.resolve()),
        name="test.txt",
    )
    bot.send_group_msg.assert_not_called()
    bot.send_private_msg.assert_not_called()


@pytest.mark.asyncio
async def test_file_private_uses_upload_private_file_api(tmp_path):
    """私聊发送本地文件：应调用 upload_private_file API，不走 send_private_msg。"""
    testFile = tmp_path / "doc.pdf"
    testFile.write_text("pdf content", encoding="utf-8")

    fileComp = Comp.File(name="doc.pdf", file=str(testFile))
    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    bot.send_private_msg = AsyncMock()
    bot.call_action = AsyncMock()

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=MessageChain([fileComp]),
        is_group=False,
        session_id="789012",
    )

    bot.call_action.assert_called_once_with(
        "upload_private_file",
        user_id=789012,
        file=str(testFile.resolve()),
        name="doc.pdf",
    )
    bot.send_private_msg.assert_not_called()


@pytest.mark.asyncio
async def test_file_and_plain_mixed_file_uses_upload_api(tmp_path):
    """File 与 Plain 混合时：Plain 走 send_group_msg，File 走 upload API。"""
    testFile = tmp_path / "data.txt"
    testFile.write_text("sample", encoding="utf-8")

    fileComp = Comp.File(name="data.txt", file=str(testFile))
    plainComp = Comp.Plain(text="请查收文件")

    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    bot.send_private_msg = AsyncMock()
    bot.call_action = AsyncMock()

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=MessageChain([plainComp, fileComp]),
        is_group=True,
        session_id="123456",
    )

    # Plain 走 send_group_msg
    assert bot.send_group_msg.call_count == 1
    plainMessage = bot.send_group_msg.call_args.kwargs["message"]
    assert plainMessage[0]["type"] == "text"
    assert plainMessage[0]["data"]["text"] == "请查收文件"

    # File 走 upload API
    bot.call_action.assert_called_once_with(
        "upload_group_file",
        group_id=123456,
        file=str(testFile.resolve()),
        name="data.txt",
    )


@pytest.mark.asyncio
async def test_upload_failure_falls_back_to_dispatch_send(tmp_path):
    """upload API 失败时回退到 _from_segment_to_dict + _dispatch_send。"""
    testFile = tmp_path / "test.txt"
    testFile.write_text("fallback", encoding="utf-8")

    fileComp = Comp.File(name="test.txt", file=str(testFile))
    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    bot.send_private_msg = AsyncMock()
    bot.call_action = AsyncMock(side_effect=RuntimeError("upload failed"))

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=MessageChain([fileComp]),
        is_group=True,
        session_id="123456",
    )

    # upload 尝试了但失败了
    bot.call_action.assert_called_once()
    # 回退到 send_group_msg
    bot.send_group_msg.assert_called_once()
    fallbackMessage = bot.send_group_msg.call_args.kwargs["message"]
    assert fallbackMessage[0]["type"] == "file"
    assert "file:///" in str(fallbackMessage[0]["data"]["file"])


@pytest.mark.asyncio
async def test_no_local_file_falls_back_to_dispatch_send():
    """无本地文件（纯 URL）时回退到 _from_segment_to_dict + _dispatch_send。"""
    fileComp = Comp.File(name="remote.txt", url="https://example.com/remote.txt")
    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    bot.send_private_msg = AsyncMock()
    bot.call_action = AsyncMock()

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=MessageChain([fileComp]),
        is_group=True,
        session_id="123456",
    )

    # 无本地文件路径，不应调用 upload API
    bot.call_action.assert_not_called()
    # 回退到 send_group_msg
    bot.send_group_msg.assert_called_once()


@pytest.mark.asyncio
async def test_no_session_id_falls_back_to_dispatch_send(tmp_path):
    """session_id 为 None 时回退到 _dispatch_send（会抛 ValueError）。"""
    testFile = tmp_path / "test.txt"
    testFile.write_text("hello", encoding="utf-8")

    fileComp = Comp.File(name="test.txt", file=str(testFile))
    bot = MagicMock()
    bot.send = AsyncMock()
    bot.send_group_msg = AsyncMock()
    bot.send_private_msg = AsyncMock()

    with pytest.raises(ValueError, match="无法发送消息"):
        await AiocqhttpMessageEvent.send_message(
            bot=bot,
            message_chain=MessageChain([fileComp]),
            is_group=True,
            session_id=None,
        )


@pytest.mark.asyncio
async def test_multiple_files_each_uses_upload_api(tmp_path):
    """多个 File 段：每个都独立调用 upload API。"""
    file1 = tmp_path / "a.txt"
    file2 = tmp_path / "b.txt"
    file1.write_text("aaa", encoding="utf-8")
    file2.write_text("bbb", encoding="utf-8")

    comp1 = Comp.File(name="a.txt", file=str(file1))
    comp2 = Comp.File(name="b.txt", file=str(file2))

    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    bot.call_action = AsyncMock()

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=MessageChain([comp1, comp2]),
        is_group=True,
        session_id="123456",
    )

    assert bot.call_action.call_count == 2
    bot.call_action.assert_any_call(
        "upload_group_file",
        group_id=123456,
        file=str(file1.resolve()),
        name="a.txt",
    )
    bot.call_action.assert_any_call(
        "upload_group_file",
        group_id=123456,
        file=str(file2.resolve()),
        name="b.txt",
    )
    bot.send_group_msg.assert_not_called()


@pytest.mark.asyncio
async def test_multiple_files_each_uses_upload_private_api(tmp_path):
    """多个 File 段私聊：每个都独立调用 upload_private_file API。"""
    file1 = tmp_path / "a.txt"
    file2 = tmp_path / "b.txt"
    file1.write_text("aaa", encoding="utf-8")
    file2.write_text("bbb", encoding="utf-8")

    comp1 = Comp.File(name="a.txt", file=str(file1))
    comp2 = Comp.File(name="b.txt", file=str(file2))

    bot = MagicMock()
    bot.send_private_msg = AsyncMock()
    bot.call_action = AsyncMock()

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=MessageChain([comp1, comp2]),
        is_group=False,
        session_id="123456",
    )

    assert bot.call_action.call_count == 2
    bot.call_action.assert_any_call(
        "upload_private_file",
        user_id=123456,
        file=str(file1.resolve()),
        name="a.txt",
    )
    bot.call_action.assert_any_call(
        "upload_private_file",
        user_id=123456,
        file=str(file2.resolve()),
        name="b.txt",
    )
    bot.send_private_msg.assert_not_called()


@pytest.mark.asyncio
async def test_non_digit_session_id_group_falls_back_to_dispatch_send(tmp_path):
    """群聊：session_id 为非数字字符串时跳过 upload API，回退到 _dispatch_send。"""
    testFile = tmp_path / "test.txt"
    testFile.write_text("hello", encoding="utf-8")

    fileComp = Comp.File(name="test.txt", file=str(testFile))
    bot = MagicMock()
    bot.send = AsyncMock()
    bot.send_group_msg = AsyncMock()
    bot.send_private_msg = AsyncMock()
    bot.call_action = AsyncMock()

    with pytest.raises(ValueError, match="无法发送消息"):
        await AiocqhttpMessageEvent.send_message(
            bot=bot,
            message_chain=MessageChain([fileComp]),
            is_group=True,
            session_id="abc123",
        )

    # upload API 未被调用
    bot.call_action.assert_not_called()


@pytest.mark.asyncio
async def test_non_digit_session_id_private_falls_back_to_dispatch_send(tmp_path):
    """私聊：session_id 为非数字字符串时跳过 upload API，回退到 _dispatch_send。"""
    testFile = tmp_path / "test.txt"
    testFile.write_text("hello", encoding="utf-8")

    fileComp = Comp.File(name="test.txt", file=str(testFile))
    bot = MagicMock()
    bot.send = AsyncMock()
    bot.send_group_msg = AsyncMock()
    bot.send_private_msg = AsyncMock()
    bot.call_action = AsyncMock()

    with pytest.raises(ValueError, match="无法发送消息"):
        await AiocqhttpMessageEvent.send_message(
            bot=bot,
            message_chain=MessageChain([fileComp]),
            is_group=False,
            session_id="abc123",
        )

    bot.call_action.assert_not_called()


@pytest.mark.asyncio
async def test_file_group_without_name_defaults_to_file(tmp_path):
    """群聊发送文件未提供 name：应使用默认 name='file'。"""
    testFile = tmp_path / "test.txt"
    testFile.write_text("hello", encoding="utf-8")

    fileComp = Comp.File(name="", file=str(testFile))
    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    bot.send_private_msg = AsyncMock()
    bot.call_action = AsyncMock()

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=MessageChain([fileComp]),
        is_group=True,
        session_id="123456",
    )

    bot.call_action.assert_called_once_with(
        "upload_group_file",
        group_id=123456,
        file=str(testFile.resolve()),
        name="file",
    )
    bot.send_group_msg.assert_not_called()


@pytest.mark.asyncio
async def test_file_private_without_name_defaults_to_file(tmp_path):
    """私聊发送文件未提供 name：应使用默认 name='file'。"""
    testFile = tmp_path / "doc.pdf"
    testFile.write_text("pdf content", encoding="utf-8")

    fileComp = Comp.File(name="", file=str(testFile))
    bot = MagicMock()
    bot.send_group_msg = AsyncMock()
    bot.send_private_msg = AsyncMock()
    bot.call_action = AsyncMock()

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=MessageChain([fileComp]),
        is_group=False,
        session_id="789012",
    )

    bot.call_action.assert_called_once_with(
        "upload_private_file",
        user_id=789012,
        file=str(testFile.resolve()),
        name="file",
    )
    bot.send_private_msg.assert_not_called()
