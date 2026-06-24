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


def test_reply_to_dict_contains_only_id_in_data():
    """Reply.toDict() 应当只输出 id 字段，不含 chain、sender_id 等多余字段。

    当前实际行为：继承了 BaseMessageComponent.toDict()，会将所有
    非 None 的默认值（chain: [], sender_id: 0, qq: 0, seq: 0 等）
    一起序列化，违反了 OneBot V11 的 reply 段格式约定。
    """
    reply = Comp.Reply(id="123456")

    result = reply.toDict()

    assert result["type"] == "reply"
    assert "id" in result["data"]

    # 这些字段不应出现在 OneBot 协议的 reply segment 中
    unexpectedFields = ["chain", "sender_id", "qq", "seq", "text"]
    for field in unexpectedFields:
        if field in result["data"]:
            pytest.fail(
                f"Reply.toDict() 的 data 中不应包含 '{field}' 字段，"
                f"但实际输出了 {field}={result['data'][field]!r}。"
                f"完整输出: {result}"
            )


def test_reply_to_dict_outputs_only_id():
    """Reply.toDict() 应当只输出 id 字段，不含任何多余字段。"""
    reply = Comp.Reply(id="123456")
    result = reply.toDict()

    assert result["type"] == "reply"
    assert set(result["data"].keys()) == {"id"}, (
        f"Reply.toDict() data 中包含多余字段: {set(result['data'].keys()) - {'id'}}"
    )
    assert result["data"]["id"] == "123456"


# ============================================================
# _parse_onebot_json 输出测试
# ============================================================


@pytest.mark.asyncio
async def test_parse_onebot_json_reply_produces_extra_fields():
    """_parse_onebot_json 处理 Reply 时会输出多余字段。

    这验证了 bug 的链路：从 Reply 组件 → _parse_onebot_json →
    OneBot 协议 payload，多余字段一直传递到 send_private_msg。
    """
    chain = MessageChain([Comp.Reply(id="123456"), Comp.Plain("你好")])

    data = await AiocqhttpMessageEvent._parse_onebot_json(chain)

    assert len(data) == 2
    replySegment = data[0]
    assert replySegment["type"] == "reply"

    # 检查 reply 段的 data 中是否有多余字段
    extraFields = [k for k in replySegment["data"] if k != "id"]
    if extraFields:
        pytest.fail(
            f"_parse_onebot_json 输出的 reply 段包含了多余的 data 字段: "
            f"{extraFields}。这些字段可能被 OneBot 协议端误解析，"
            f"导致 message not found 错误。\n"
            f"完整 reply 段: {replySegment}"
        )


# ============================================================
# 私聊发送路径测试
# ============================================================


@pytest.mark.asyncio
async def test_send_private_msg_with_reply_includes_extra_fields():
    """验证私聊发送带 Reply 的消息时，实际传给 bot.send_private_msg 的
    payload 包含多余字段。

    这是导致私聊下 'message not found' 的直接原因：
    OneBot 协议端收到的 reply 段数据不符合标准格式。
    """
    bot = AsyncMock()
    chain = MessageChain([Comp.Reply(id="123456"), Comp.Plain("你好")])

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=chain,
        event=None,
        is_group=False,  # 私聊
        session_id="987654",
    )

    # 验证调用了 send_private_msg（而非 send_group_msg）
    bot.send_private_msg.assert_awaited_once()

    callArgs = bot.send_private_msg.call_args
    assert callArgs.kwargs["user_id"] == 987654

    messages = callArgs.kwargs["message"]
    assert len(messages) >= 1
    replySegment = messages[0]
    assert replySegment["type"] == "reply"

    # 检查 payload 中的多余字段
    extraFields = [k for k in replySegment["data"] if k != "id"]
    if extraFields:
        pytest.fail(
            f"send_private_msg 的 message[0] reply 段包含了多余的 data 字段: "
            f"{extraFields}。\n"
            f"这是导致私聊引用回复报 'message not found' 的根因。\n"
            f"完整 payload: {messages}"
        )


@pytest.mark.asyncio
async def test_send_group_msg_with_reply_also_includes_extra_fields():
    """对比：群聊发送带 Reply 的消息同样包含多余字段。

    如果群聊引用回复正常而私聊失败，可能的原因是不同协议端
    对多余字段的容忍度不同（例如 napcat 在 send_group_msg 中
    忽略了多余字段，但在 send_private_msg 中严格校验）。
    """
    bot = AsyncMock()
    chain = MessageChain([Comp.Reply(id="123456"), Comp.Plain("你好")])

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=chain,
        event=None,
        is_group=True,
        session_id="123456",
    )

    bot.send_group_msg.assert_awaited_once()

    callArgs = bot.send_group_msg.call_args
    messages = callArgs.kwargs["message"]
    replySegment = messages[0]
    assert replySegment["type"] == "reply"

    extraFields = [k for k in replySegment["data"] if k != "id"]
    if extraFields:
        pytest.fail(
            f"send_group_msg 的 reply 段也包含多余字段: {extraFields}。\n"
            f"完整 payload: {messages}"
        )


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
