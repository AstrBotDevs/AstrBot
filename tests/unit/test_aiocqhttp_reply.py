"""测试 aiocqhttp 平台中私聊环境下引用回复（Reply）的消息发送行为。

Bug 背景：在私聊中引用上文消息时，OneBot 协议端返回
ActionFailed status='failed', retcode=100, wording='message not found'。

根因：Reply.toDict() 继承了 BaseMessageComponent.toDict()，
会将所有非 None 的默认字段（chain, sender_id, qq, seq 等）序列化到
OneBot 协议的 message 数组中。OneBot V11 标准只期望
{"type": "reply", "data": {"id": "..."}}，多余的字段可能导致
协议端（napcat/Lagrange）查找消息时失败。
"""

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

# ============================================================
# Reply.toDict() 输出格式测试
# ============================================================


@pytest.mark.asyncio
async def test_parse_onebot_json_reply_uses_standard_segment():
    """Serialize replies with only the OneBot message ID field."""
    chain = MessageChain([Comp.Reply(id="123456"), Comp.Plain("你好")])

    data = await AiocqhttpMessageEvent._parse_onebot_json(chain)

    assert data == [
        {"type": "reply", "data": {"id": "123456"}},
        {"type": "text", "data": {"text": "你好"}},
    ]


# ============================================================
# 私聊发送路径测试
# ============================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_group", "method_name", "target_key", "session_id"),
    [
        (False, "send_private_msg", "user_id", "987654"),
        (True, "send_group_msg", None, "123456"),
    ],
)
async def test_send_msg_with_reply_uses_standard_segment(
    is_group, method_name, target_key, session_id
):
    bot = AsyncMock()
    chain = MessageChain([Comp.Reply(id="123456"), Comp.Plain("你好")])

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=chain,
        event=None,
        is_group=is_group,
        session_id=session_id,
    )

    method = getattr(bot, method_name)
    method.assert_awaited_once()

    call_args = method.call_args
    if target_key:
        assert call_args.kwargs[target_key] == int(session_id)
    messages = call_args.kwargs["message"]
    reply_segment = messages[0]
    assert reply_segment["type"] == "reply"
    assert reply_segment["data"] == {"id": "123456"}


# ============================================================
# Reply 组件只传 id 时的正确 OneBot 格式测试
# ============================================================


def test_reply_to_dict_matches_onebot_v11_format():
    """OneBot V11 标准 reply 段格式：
    {"type": "reply", "data": {"id": "..."}}
    """
    expected = {
        "type": "reply",
        "data": {"id": "123456"},
    }

    reply = Comp.Reply(id="123456")
    actual = reply.toDict()

    assert actual == expected, (
        f"Reply.toDict() 输出不符合 OneBot V11 标准。\n期望: {expected}\n实际: {actual}"
    )
